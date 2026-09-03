"""BILL4PE manual double-scan UPI flow (PAYMENT_FLOW_MODE=manual_upi_double_scan).

Merchant is paid DIRECTLY by the customer in their own UPI app — Bill4Pe never
collects the merchant amount and RazorpayX never pays it out. The only money in
Bill4Pe's path is the configurable service fee (default 1%), taken from the
wallet or via a Bill4Pe-owned Razorpay fee payment.

Backend is authoritative for: frozen merchant UPI, merchant amount, fee amount,
wallet balance, fee status and bill status. Every transition is an atomic,
idempotent claim so refresh / retries / duplicate webhooks can never double-charge
or produce a second receipt.
"""
import uuid

from core.config import compute_fee_breakdown, logger
from core.db import db
from core.security import now_iso
from services import billing_service

try:
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError
    _AFTER = ReturnDocument.AFTER
except Exception:  # pragma: no cover
    _AFTER = True

    class DuplicateKeyError(Exception):
        pass


# States (spec §36)
S_SECOND_QR_REQUIRED = "second_qr_required"
S_AWAITING_MERCHANT_PAYMENT = "awaiting_merchant_payment"
S_MERCHANT_PAYMENT_CLAIMED = "merchant_payment_claimed"
S_PROOF_SUBMITTED = "proof_submitted"
S_FEE_DUE = "fee_due"
S_FEE_PENDING = "fee_pending"
S_FEE_PAID = "fee_paid"
S_COMPLETED = "completed"


def normalize_upi(v: str) -> str:
    return (v or "").strip().lower()


async def ensure_indexes() -> None:
    await db.manual_transactions.create_index("id", unique=True)
    await db.manual_transactions.create_index([("user_id", 1), ("created_at", -1)])
    await db.wallet_ledger.create_index(
        [("transaction_id", 1), ("type", 1)], unique=True
    )
    await db.receipt_verifications.create_index("id", unique=True)
    # Uniqueness is enforced only for VERIFIED receipts — a rejected/misread
    # OCR attempt must never permanently lock out a legitimate payment.
    for legacy in ("extracted_utr_1", "extracted_transaction_id_1"):
        try:
            await db.receipt_verifications.drop_index(legacy)
        except Exception:
            pass
    await db.receipt_verifications.create_index(
        [("extracted_utr", 1)], unique=True, name="uniq_verified_utr",
        partialFilterExpression={"verification_status": "verified", "extracted_utr": {"$type": "string"}},
    )
    await db.receipt_verifications.create_index(
        [("extracted_transaction_id", 1)], unique=True, name="uniq_verified_txnid",
        partialFilterExpression={"verification_status": "verified", "extracted_transaction_id": {"$type": "string"}},
    )
    logger.info("[manual_flow] indexes ensured")


async def _fee_percent() -> str:
    from services import payment_service
    return await payment_service.get_fee_percent()


async def _fee_percent_for_user(user) -> str:
    """The Super-Admin-configured bill fee % for THIS user's type. Corporate
    accounts are on a subscription -> 0% per-bill fee. Only individuals are charged."""
    from services import payment_service
    if payment_service.bill_fee_kind_for_user(user) == "corporate":
        return "0"
    percents = await payment_service.get_bill_fee_percents()
    return str(percents["individual"])


def _public(txn: dict) -> dict:
    return {
        "transaction_id": txn["id"],
        "state": txn.get("state"),
        "payee_name": txn.get("payee_name_snapshot"),
        "payee_upi": txn.get("payee_upi_snapshot"),
        "merchant_amount": round((txn.get("merchant_amount_paise") or 0) / 100, 2),
        "merchant_amount_paise": txn.get("merchant_amount_paise"),
        "first_qr_verified": txn.get("first_qr_verified", False),
        "second_qr_verified": txn.get("second_qr_verified", False),
        "payment_session_locked": txn.get("payment_session_locked", False),
        "merchant_payment_status": txn.get("merchant_payment_status"),
        "merchant_verification_status": txn.get("merchant_verification_status"),
        "utr_full": _mask_utr(txn.get("utr_full")),
        "utr_last4": txn.get("utr_last4"),
        "proof_status": txn.get("proof_status"),
        "has_screenshot": bool(txn.get("proof_file")),
        "platform_fee_percent": txn.get("platform_fee_percent_snapshot"),
        "platform_fee": round((txn.get("platform_fee_paise") or 0) / 100, 2),
        "platform_fee_paise": txn.get("platform_fee_paise"),
        "fee_status": txn.get("fee_status"),
        "fee_payment_method": txn.get("fee_payment_method"),
        "fee_payment_session_id": txn.get("fee_payment_session_id"),
        "bill_id": txn.get("bill_id"),
        "expense_id": txn.get("expense_id"),
        "bill_status": txn.get("bill_status"),
        "verification": _public_verification(txn.get("verification")),
        "created_at": txn.get("created_at"),
    }


def _mask_utr(utr):
    if not utr:
        return None
    utr = str(utr)
    return ("X" * max(0, len(utr) - 4)) + utr[-4:] if len(utr) > 4 else utr


_VERIFICATION_PUBLIC_KEYS = (
    "payment_status", "extracted_amount", "currency", "extracted_utr",
    "extracted_transaction_id", "transaction_date", "transaction_time",
    "payee_name", "payee_upi", "payer_name", "payer_upi", "bank_name",
    "payment_provider", "amount_matched", "receiver_matched", "duplicate_check",
    "verification_status", "failure_reasons", "verified_at", "created_at",
)


def _public_verification(v):
    if not v:
        return None
    return {k: v.get(k) for k in _VERIFICATION_PUBLIC_KEYS}


# ---------------- 1) FIRST QR SCAN → freeze merchant + amount ----------------
async def first_scan(user, payee_upi, payee_name=None, merchant_amount=None, expense_draft=None):
    upi = normalize_upi(payee_upi)
    if not upi or "@" not in upi or len(upi) < 3:
        raise ValueError("A valid merchant UPI/VPA is required (name@bank)")

    # Authoritative amount: prefer draft items, else supplied merchant_amount.
    if expense_draft and (expense_draft.get("items") or []):
        items = expense_draft["items"]
        merchant_amount = round(
            sum(float(i.get("quantity", 1) or 0) * float(i.get("unit_price", 0) or 0) for i in items), 2
        )
    if not merchant_amount or float(merchant_amount) <= 0:
        raise ValueError("Merchant/bill amount must be positive")

    merchant_amount_paise = int(round(float(merchant_amount) * 100))
    fee_percent = await _fee_percent_for_user(user)
    b = compute_fee_breakdown(merchant_amount_paise, fee_percent)

    tid = f"B4P-{now_iso()[:4]}-{uuid.uuid4().hex[:8].upper()}"
    doc = {
        "id": tid,
        "user_id": user["id"],
        "company_id": (expense_draft or {}).get("company_id") or user.get("company_id"),
        "flow_mode": "manual_upi_double_scan",
        # SINGLE-SCAN flow: one scan locks the merchant and moves straight to
        # "awaiting merchant payment" (no confirm re-scan). The second-scan fields
        # are marked verified so downstream transitions remain valid.
        "state": S_AWAITING_MERCHANT_PAYMENT,
        # frozen merchant snapshot (immutable after this)
        "payee_name_snapshot": (payee_name or "").strip() or None,
        "payee_upi_snapshot": upi,
        "merchant_amount_paise": merchant_amount_paise,
        "first_qr_verified": True,
        "first_qr_payload_hash": None,
        "second_qr_verified": True,
        "second_qr_verified_at": now_iso(),
        "payment_session_locked": True,
        "merchant_payment_status": "awaiting_payment",
        "merchant_payment_claimed_at": None,
        "merchant_verification_status": "unverified",
        "utr_full": None,
        "utr_last4": None,
        "proof_file": None,
        "proof_status": "none",
        "proof_uploaded_at": None,
        # fee snapshot (integer paise)
        "platform_fee_percent_snapshot": b["platform_fee_percent_snapshot"],
        "platform_fee_paise": b["platform_fee_paise"],
        "fee_status": "not_started",
        "fee_payment_method": None,
        "wallet_ledger_id": None,
        "fee_payment_session_id": None,
        "razorpay_fee_order_id": None,
        "razorpay_fee_payment_id": None,
        "expense_draft": expense_draft,
        "expense_id": None,
        "bill_id": None,
        "bill_status": "pending",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.manual_transactions.insert_one(doc)
    logger.info("[manual_flow] first_scan txn=%s upi=%s amt_paise=%s", tid, upi, merchant_amount_paise)
    return _public(doc)


# ---------------- 2) SECOND QR SCAN → must match frozen merchant ----------------
async def second_scan(user, tid, payee_upi):
    txn = await _owned(user, tid)
    scanned = normalize_upi(payee_upi)
    if not scanned or "@" not in scanned:
        raise ValueError("Not a valid UPI QR")
    frozen = normalize_upi(txn.get("payee_upi_snapshot"))
    if scanned != frozen:
        return {"match": False, "message": "QR does not match the merchant selected for this bill.",
                **_public(txn)}
    # idempotent lock
    updated = await db.manual_transactions.find_one_and_update(
        {"id": tid, "user_id": user["id"]},
        {"$set": {
            "second_qr_verified": True,
            "second_qr_verified_at": now_iso(),
            "payment_session_locked": True,
            "state": S_AWAITING_MERCHANT_PAYMENT,
            "updated_at": now_iso(),
        }},
        return_document=_AFTER,
    )
    return {"match": True, **_public(updated)}


# ---------------- Cancel payment session ----------------
async def cancel(user, tid):
    txn = await _owned(user, tid)
    if txn.get("bill_status") == "generated":
        raise ValueError("Receipt already generated; cannot cancel")
    await db.manual_transactions.update_one(
        {"id": tid, "user_id": user["id"]},
        {"$set": {"state": "cancelled", "merchant_payment_status": "cancelled",
                  "payment_session_locked": False, "updated_at": now_iso()}},
    )
    return {"cancelled": True}


# ---------------- 3) Confirm "Did you pay?" ----------------
async def confirm_payment(user, tid, completed: bool):
    txn = await _owned(user, tid)
    if not txn.get("second_qr_verified"):
        raise ValueError("Second QR not verified yet")
    if not completed:
        # keep awaiting; do NOT charge fee or generate receipt (spec §11)
        await db.manual_transactions.update_one(
            {"id": tid, "user_id": user["id"], "merchant_payment_status": {"$ne": "user_confirmed"}},
            {"$set": {"merchant_payment_status": "awaiting_payment", "updated_at": now_iso()}},
        )
        fresh = await db.manual_transactions.find_one({"id": tid})
        return _public(fresh)
    updated = await db.manual_transactions.find_one_and_update(
        {"id": tid, "user_id": user["id"]},
        {"$set": {"merchant_payment_status": "user_confirmed",
                  "merchant_payment_claimed_at": now_iso(),
                  "state": S_MERCHANT_PAYMENT_CLAIMED, "updated_at": now_iso()}},
        return_document=_AFTER,
    )
    return _public(updated)


# ---------------- 4) Submit proof (receipt screenshot, server-side OCR) ----------------
async def submit_proof(user, tid, proof_file=None, image_bytes=None, mime=None):
    txn = await _owned(user, tid)
    # Freeze the proof once the fee is paid / receipt is generated (spec §40).
    if txn.get("fee_status") == "paid" or txn.get("bill_status") == "generated":
        raise ValueError("Proof is locked — the receipt has already been generated")
    if txn.get("merchant_payment_status") not in ("user_confirmed", "proof_submitted", "partial_reference"):
        raise ValueError("Confirm the merchant payment before submitting proof")
    if not proof_file or not image_bytes:
        raise ValueError("Upload a payment receipt screenshot")

    from services import receipt_verify
    rec = await receipt_verify.verify_receipt(
        user=user, txn=txn, image_bytes=image_bytes, mime=mime, proof_file=proof_file,
    )
    verified = rec["verification_status"] == "verified"
    utr = rec.get("extracted_utr")
    patch = {
        # UTR/reference is ALWAYS the OCR-extracted value — never client input.
        "utr_full": utr,
        "utr_last4": (utr[-4:] if utr else None),
        "proof_file": proof_file,
        "proof_status": "proof_submitted",
        "proof_uploaded_at": now_iso(),
        "merchant_payment_status": "proof_submitted",
        "merchant_verification_status": rec["verification_status"],
        "state": S_PROOF_SUBMITTED,
        "verification": rec,
        "updated_at": now_iso(),
    }
    if verified:
        patch["fee_status"] = "due"
    updated = await db.manual_transactions.find_one_and_update(
        {"id": tid, "user_id": user["id"]}, {"$set": patch}, return_document=_AFTER,
    )
    return {**_public(updated), "verification": _public_verification(rec)}


# ---------------- 5) Atomic, idempotent wallet fee debit ----------------
async def _debit_wallet_fee(txn) -> str | None:
    """Debit the service fee from the wallet exactly once. Returns 'paid',
    'insufficient', or 'already'. Uses a unique wallet_ledger entry as the
    idempotency guard (transaction_id + type)."""
    tid = txn["id"]
    fee_paise = int(txn.get("platform_fee_paise") or 0)
    fee_rupees = round(fee_paise / 100, 2)

    existing = await db.wallet_ledger.find_one({"transaction_id": tid, "type": "bill4pe_service_fee"})
    if existing:
        return "already"

    uid = txn["user_id"]
    u = await db.users.find_one({"id": uid})
    bal_paise = int(round(float(u.get("wallet_balance", 0.0)) * 100))
    if bal_paise < fee_paise:
        return "insufficient"

    debited = await db.users.find_one_and_update(
        {"id": uid, "wallet_balance": {"$gte": fee_rupees}},
        {"$inc": {"wallet_balance": -fee_rupees}},
        return_document=_AFTER,
    )
    if not debited:
        return "insufficient"

    ledger_id = str(uuid.uuid4())
    try:
        await db.wallet_ledger.insert_one({
            "ledger_id": ledger_id,
            "transaction_id": tid,
            "type": "bill4pe_service_fee",
            "amount_paise": -fee_paise,
            "balance_before_paise": bal_paise,
            "balance_after_paise": bal_paise - fee_paise,
            "created_at": now_iso(),
        })
    except DuplicateKeyError:
        # A concurrent caller already recorded the fee — refund our debit.
        await db.users.update_one({"id": uid}, {"$inc": {"wallet_balance": fee_rupees}})
        return "already"

    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "type": "debit",
        "amount": fee_rupees, "reason": f"Bill4Pe service fee ({tid})", "created_at": now_iso(),
    })
    await db.manual_transactions.update_one({"id": tid}, {"$set": {"wallet_ledger_id": ledger_id}})
    return "paid"


# ---------------- 6) Generate receipt (wallet-first) ----------------
async def generate_receipt(user, tid):
    """Wallet-first: debit fee from wallet if sufficient, then generate exactly
    one receipt. If wallet is short, return needs_fee so the client shows the
    Bill4Pe Fee QR / Add-money options."""
    txn = await _owned(user, tid)
    if txn.get("bill_status") == "generated" and txn.get("bill_id"):
        return {"generated": True, **_public(txn)}
    if txn.get("proof_status") not in ("proof_submitted", "partial_reference"):
        raise ValueError("Submit payment proof before generating the receipt")
    if txn.get("merchant_verification_status") not in ("verified", "admin_reviewed"):
        raise ValueError("Payment is not verified yet — upload a clear receipt that matches the bill amount and payee")

    if txn.get("fee_status") != "paid":
        res = await _debit_wallet_fee(txn)
        if res in ("paid", "already"):
            await db.manual_transactions.update_one(
                {"id": tid}, {"$set": {"fee_status": "paid", "fee_payment_method": "wallet",
                                       "state": S_FEE_PAID, "updated_at": now_iso()}},
            )
        else:
            fee = round((txn.get("platform_fee_paise") or 0) / 100, 2)
            u = await db.users.find_one({"id": user["id"]})
            return {
                "generated": False, "needs_fee": True,
                "fee": fee, "fee_paise": txn.get("platform_fee_paise"),
                "wallet_balance": round(float(u.get("wallet_balance", 0.0)), 2),
                **_public(await db.manual_transactions.find_one({"id": tid})),
            }

    bill = await _make_receipt(await db.manual_transactions.find_one({"id": tid}), user)
    fresh = await db.manual_transactions.find_one({"id": tid})
    return {"generated": True, "bill_id": bill.get("bill_id"), **_public(fresh)}


async def _make_receipt(txn, user) -> dict:
    """Create ONE expense + one sequential bill for a fee-paid transaction."""
    tid = txn["id"]
    # Atomic claim: only one caller generates.
    claim = await db.manual_transactions.find_one_and_update(
        {"id": tid, "bill_status": "pending", "fee_status": "paid"},
        {"$set": {"bill_status": "generating"}},
        return_document=_AFTER,
    )
    if not claim:
        # Another caller is generating (or already did). Briefly poll so we never
        # return a null bill_id to the client while the winner finishes writing it.
        import asyncio
        for _ in range(20):
            fresh = await db.manual_transactions.find_one({"id": tid})
            if fresh.get("bill_id"):
                return {"bill_id": fresh["bill_id"], "existing": True}
            await asyncio.sleep(0.15)
        return {"bill_id": None, "existing": True}

    draft = txn.get("expense_draft") or {}
    items = draft.get("items") or [{
        "name": txn.get("payee_name_snapshot") or "Merchant payment",
        "quantity": 1,
        "unit_price": round((txn.get("merchant_amount_paise") or 0) / 100, 2),
    }]
    total = round((txn.get("merchant_amount_paise") or 0) / 100, 2)
    fee = round((txn.get("platform_fee_paise") or 0) / 100, 2)
    eid = str(uuid.uuid4())
    bill_id = await billing_service.next_bill_number()

    snapshot = {
        "document_title": "BILL4PE DIGITAL EXPENSE RECEIPT",
        "merchant_name": txn.get("payee_name_snapshot"),
        "merchant_upi": txn.get("payee_upi_snapshot"),
        "merchant_payment_status_label": "Payment Verified via Receipt" if txn.get("merchant_verification_status") in ("verified", "admin_reviewed") else "Payment Confirmed by User",
        "customer_name": user.get("name"),
        "customer_email": user.get("email"),
        "items": [{"name": i.get("name"), "quantity": float(i.get("quantity", 1) or 1),
                   "unit_price": float(i.get("unit_price", 0) or 0),
                   "amount": round(float(i.get("quantity", 1) or 1) * float(i.get("unit_price", 0) or 0), 2)}
                  for i in items],
        "subtotal": total,
        "total": total,
        "currency": "INR",
        "model": "manual_upi_double_scan",
        "utr": _mask_utr(txn.get("utr_full")) or txn.get("utr_last4"),
        "bill4pe_service_fee": fee,
        "fee_payment_method": txn.get("fee_payment_method"),
        "fee_status": "paid",
        "frozen_at": now_iso(),
    }
    expense = {
        "id": eid,
        "user_id": txn["user_id"],
        "company_id": txn.get("company_id"),
        "category": draft.get("category", "other"),
        "sub_category": draft.get("sub_category"),
        "items": snapshot["items"],
        "payment": {
            "merchant_name": txn.get("payee_name_snapshot"),
            "merchant_upi": txn.get("payee_upi_snapshot"),
            "transaction_id": tid,
            "amount": total,
            "payment_method": "UPI (direct to merchant)",
            "payment_status": "verified" if txn.get("merchant_verification_status") in ("verified", "admin_reviewed") else "user_confirmed",
        },
        "total": total,
        "notes": draft.get("notes"),
        "approval_status": "approved",
        "bill_generated": True,
        "bill_id": bill_id,
        "bill_number": bill_id,
        "bill_fee": fee,
        "bill_fee_settled": True,
        "bill_status": "generated",
        "bill_snapshot": snapshot,
        "bill_generated_at": now_iso(),
        "source": "manual_upi_double_scan",
        "transaction_id": tid,
        "created_at": now_iso(),
    }
    await db.expenses.insert_one(expense)
    await db.manual_transactions.update_one({"id": tid}, {"$set": {
        "expense_id": eid, "bill_id": bill_id, "bill_status": "generated",
        "state": S_COMPLETED, "updated_at": now_iso(),
    }})
    logger.info("[manual_flow] receipt %s (expense %s) for txn %s", bill_id, eid, tid)
    return {"bill_id": bill_id, "expense_id": eid, "existing": False}


# ---------------- Bill4Pe fee via Razorpay (server-verified) ----------------
async def create_fee_order(user, tid):
    from services import razorpay_service
    txn = await _owned(user, tid)
    if txn.get("fee_status") == "paid":
        return {"already_paid": True, **_public(txn)}
    if not razorpay_service.enabled():
        raise ValueError("Razorpay not configured — top up the wallet instead")
    fee_paise = int(txn.get("platform_fee_paise") or 0)
    if fee_paise <= 0:
        raise ValueError("No fee due")
    session_id = f"FEE-{tid}"
    order = razorpay_service.create_order(
        fee_paise, receipt=f"fee_{tid[:20]}",
        notes={"transaction_id": tid, "purpose": "bill_fee", "fee_session": session_id, "user_id": user["id"]},
    )
    # Record in payment_orders for reconciliation + on the manual txn.
    await db.payment_orders.update_one(
        {"order_id": order["id"]},
        {"$setOnInsert": {
            "id": str(uuid.uuid4()), "order_id": order["id"], "user_id": user["id"],
            "purpose": "bill_fee", "amount": round(fee_paise / 100, 2), "amount_paise": fee_paise,
            "payment_status": "created", "status": "created",
            "manual_transaction_id": tid, "created_at": now_iso(),
        }}, upsert=True,
    )
    await db.manual_transactions.update_one({"id": tid}, {"$set": {
        "razorpay_fee_order_id": order["id"], "fee_payment_session_id": session_id,
        "fee_status": "pending", "state": S_FEE_PENDING, "updated_at": now_iso(),
    }})
    return {
        "fee_payment_session_id": session_id,
        "razorpay_order_id": order["id"],
        "amount_paise": fee_paise,
        "amount": round(fee_paise / 100, 2),
        "razorpay_key_id": razorpay_service.key_id(),
        "currency": "INR",
    }


async def verify_fee_payment(user, tid, order_id, payment_id, signature):
    from services import razorpay_service
    txn = await _owned(user, tid)
    if txn.get("fee_status") == "paid":
        return {"generated": bool(txn.get("bill_id")), **_public(txn)}
    if txn.get("razorpay_fee_order_id") and txn["razorpay_fee_order_id"] != order_id:
        raise ValueError("Fee order does not match this transaction")
    if not razorpay_service.verify_checkout_signature(order_id, payment_id, signature):
        raise ValueError("Fee payment verification failed")
    await db.manual_transactions.update_one({"id": tid, "fee_status": {"$ne": "paid"}}, {"$set": {
        "fee_status": "paid", "fee_payment_method": "razorpay",
        "razorpay_fee_payment_id": payment_id, "state": S_FEE_PAID, "updated_at": now_iso(),
    }})
    await db.payment_orders.update_one(
        {"order_id": order_id},
        {"$set": {"payment_status": "captured", "status": "paid", "razorpay_payment_id": payment_id, "paid_at": now_iso()}},
    )
    bill = await _make_receipt(await db.manual_transactions.find_one({"id": tid}), user)
    fresh = await db.manual_transactions.find_one({"id": tid})
    return {"generated": True, "bill_id": bill.get("bill_id"), **_public(fresh)}


# ---------------- Recovery / status ----------------
async def get_status(user, tid):
    txn = await db.manual_transactions.find_one({"id": tid})
    if not txn or txn.get("user_id") != user["id"]:
        return None
    return _public(txn)


async def history(user):
    rows = await db.manual_transactions.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return [_public(r) for r in rows]


async def _owned(user, tid) -> dict:
    txn = await db.manual_transactions.find_one({"id": tid})
    if not txn or txn.get("user_id") != user["id"]:
        raise LookupError("Transaction not found")
    return txn
