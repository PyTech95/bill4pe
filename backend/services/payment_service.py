"""Payment service — the ONE reusable reconciliation brain.

`reconcile_payment` is the single idempotent function called by:
  * the frontend verify endpoint (source="checkout", carries a signature),
  * the Razorpay webhook (source="webhook", signature already verified upstream),
  * admin manual reconcile (source="admin"),
  * the background safety job (source="background").

Invariant: a captured payment ALWAYS ends with exactly one bill, regardless of
how many times / from how many sources reconcile runs.
"""
import hashlib
import uuid

from core.config import DEFAULT_PLATFORM_FEE_PERCENT, compute_fee_breakdown, logger
from core.db import db
from core.enums import AuditEvent, BillStatus, PaymentStatus, PayoutStatus, SettlementStatus
from core.security import now_iso
from services import billing_service, payout_service, razorpay_service, settlement_service

try:
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError
    _AFTER = ReturnDocument.AFTER
except Exception:  # pragma: no cover
    _AFTER = True

    class DuplicateKeyError(Exception):
        pass


async def ensure_indexes() -> None:
    """Idempotent index creation for concurrency-safety + idempotency."""
    await db.payment_orders.create_index("order_id", unique=True, sparse=True)
    await db.payment_orders.create_index("id", unique=True)
    await db.webhook_events.create_index("dedupe_key", unique=True)
    await db.settlements.create_index([("transaction_id", 1), ("merchant_id", 1)], unique=True)
    await db.expenses.create_index(
        "bill_id", unique=True,
        partialFilterExpression={"bill_id": {"$type": "string"}},
    )
    logger.info("[payments] indexes ensured")


async def audit(transaction_id, event, source, metadata=None) -> None:
    try:
        await db.payment_audit.insert_one({
            "id": str(uuid.uuid4()),
            "transaction_id": transaction_id,
            "event": event,
            "source": source,
            "metadata": metadata or {},
            "timestamp": now_iso(),
        })
    except Exception:  # audit must never break a financial op
        pass
    logger.info("[audit] %s txn=%s source=%s", event, transaction_id, source)


async def _find_txn(transaction_id=None, order_id=None, payment_id=None):
    if transaction_id:
        t = await db.payment_orders.find_one({"id": transaction_id})
        if t:
            return t
    if order_id:
        t = await db.payment_orders.find_one({"order_id": order_id})
        if t:
            return t
    if payment_id:
        return await db.payment_orders.find_one({"razorpay_payment_id": payment_id})
    return None


# ---------------- Order creation (transaction BEFORE checkout) ----------------
async def create_payment_order(user, purpose, amount=None, expense_draft=None, billing_session_id=None):
    """Create the internal transaction + Razorpay order. Amount is authoritative
    server-side. Idempotent per billing_session_id to stop duplicate orders."""
    if not razorpay_service.enabled():
        raise ValueError("Razorpay not configured")

    # Authoritative amount: for a draft, compute from items server-side.
    if expense_draft:
        items = expense_draft.get("items", []) or []
        amount = round(sum(float(i.get("quantity", 1) or 0) * float(i.get("unit_price", 0) or 0) for i in items), 2)
    if not amount or float(amount) <= 0:
        raise ValueError("Amount must be positive")
    amount = round(float(amount), 2)
    if purpose == "wallet_recharge" and amount > 10000:
        raise ValueError("Max recharge per txn is ₹10,000")

    # Dedupe: reuse an existing un-paid order for the same billing session.
    if billing_session_id:
        existing = await db.payment_orders.find_one({
            "user_id": user["id"],
            "billing_session_id": billing_session_id,
            "payment_status": {"$in": [PaymentStatus.CREATED, PaymentStatus.PENDING]},
        })
        if existing and existing.get("order_id"):
            await audit(existing["id"], AuditEvent.ORDER_REUSED, "create_order")
            return {
                "transaction_id": existing["id"],
                "razorpay_order_id": existing["order_id"],
                "amount": existing["amount_paise"],
                "currency": "INR",
                "razorpay_key_id": razorpay_service.key_id(),
                "reused": True,
            }

    tid = str(uuid.uuid4())
    amount_paise = int(round(amount * 100))
    order = razorpay_service.create_order(
        amount_paise, receipt=f"b4p_{tid[:20]}",
        notes={"transaction_id": tid, "purpose": purpose, "user_id": user["id"]},
    )
    doc = {
        "id": tid,
        "order_id": order["id"],
        "user_id": user["id"],
        "purpose": purpose,
        "amount": amount,
        "amount_paise": amount_paise,
        "payment_status": PaymentStatus.CREATED,
        "status": "created",  # legacy field kept for /payments/history UI
        "bill_status": BillStatus.PENDING,
        "settlement_status": SettlementStatus.NOT_REQUIRED,
        "credited": False,
        "expense_id": None,
        "expense_draft": expense_draft,
        "billing_session_id": billing_session_id,
        "razorpay_payment_id": None,
        "created_at": now_iso(),
    }
    await db.payment_orders.insert_one(doc)
    await audit(tid, AuditEvent.TRANSACTION_CREATED, "create_order", {"purpose": purpose, "amount": amount})
    await audit(tid, AuditEvent.ORDER_CREATED, "create_order", {"order_id": order["id"]})
    return {
        "transaction_id": tid,
        "razorpay_order_id": order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "razorpay_key_id": razorpay_service.key_id(),
    }


# ---------------- Platform fee (configurable; DB overrides env) ----------------
async def get_fee_percent() -> str:
    """Authoritative CURRENT fee %: admin DB setting → env default → 10.
    Historical transactions keep their own platform_fee_percent_snapshot."""
    doc = await db.app_settings.find_one({"_id": "platform_fee"})
    if doc and doc.get("percent") is not None:
        return str(doc["percent"])
    return str(DEFAULT_PLATFORM_FEE_PERCENT)


async def set_fee_percent(percent) -> str:
    pct = float(percent)
    if pct < 0 or pct > 100:
        raise ValueError("Fee percent must be between 0 and 100")
    await db.app_settings.update_one(
        {"_id": "platform_fee"},
        {"$set": {"percent": f"{pct:.2f}", "updated_at": now_iso()}}, upsert=True,
    )
    return f"{pct:.2f}"


# ---------------- Bill-generation fee % (per user-type; Super Admin editable) ----------------
# Distinct from the v2 platform fee above. This is the convenience fee charged
# when a user generates an official bill. Super Admin can set DIFFERENT rates for
# corporate vs individual users, changeable at any time.
DEFAULT_BILL_FEE_PERCENT = {"individual": 1.0, "corporate": 1.0}
BILL_FEE_MIN_RUPEES = 1.0  # minimum convenience fee for any non-zero rate


async def get_bill_fee_percents() -> dict:
    """Current bill-generation fee % per user type. DB setting → default 1%/1%."""
    doc = await db.app_settings.find_one({"_id": "bill_fee"})
    if not doc:
        return dict(DEFAULT_BILL_FEE_PERCENT)
    return {
        "individual": float(doc.get("individual", DEFAULT_BILL_FEE_PERCENT["individual"])),
        "corporate": float(doc.get("corporate", DEFAULT_BILL_FEE_PERCENT["corporate"])),
    }


async def set_bill_fee_percents(individual=None, corporate=None) -> dict:
    cur = await get_bill_fee_percents()
    if individual is not None:
        cur["individual"] = float(individual)
    if corporate is not None:
        cur["corporate"] = float(corporate)
    for k, v in cur.items():
        if v < 0 or v > 100:
            raise ValueError("Bill fee percent must be between 0 and 100")
    await db.app_settings.update_one(
        {"_id": "bill_fee"},
        {"$set": {"individual": round(cur["individual"], 2),
                  "corporate": round(cur["corporate"], 2),
                  "updated_at": now_iso()}},
        upsert=True,
    )
    return cur


def bill_fee_kind_for_user(user) -> str:
    """Corporate admins AND employees are billed at the corporate rate."""
    return "corporate" if (user or {}).get("user_type") == "corporate" else "individual"


async def bill_fee_for_user(user, total) -> tuple:
    """Returns (fee_amount_rupees, percent_applied) for this user + expense total.

    Corporate accounts are on a monthly SUBSCRIPTION -> unlimited bills with NO
    per-bill convenience fee. Only individual ("simple") users are charged."""
    kind = bill_fee_kind_for_user(user)
    if kind == "corporate":
        return 0.0, 0.0
    percents = await get_bill_fee_percents()
    pct = percents["individual"]
    try:
        amt = round(float(total or 0) * pct / 100.0, 2)
    except (TypeError, ValueError):
        amt = 0.0
    if pct > 0:
        amt = max(BILL_FEE_MIN_RUPEES, amt)
    return amt, pct


# ---------------- v2 collect-and-payout order (payee locked server-side) ----------------
async def create_merchant_payment_order(user, payee_name, payee_upi, merchant_amount=None,
                                        expense_draft=None, billing_session_id=None):
    """Lock the scanned payee + compute the 10% fee server-side, then create a
    Razorpay order for merchant_amount + fee (customer_total). The payee UPI is
    IMMUTABLE after this point (spec §14)."""
    if not razorpay_service.enabled():
        raise ValueError("Razorpay not configured")
    payee_upi = (payee_upi or "").strip()
    if not payee_upi or "@" not in payee_upi or len(payee_upi) < 3:
        raise ValueError("A valid payee UPI/VPA is required")

    # Merchant amount is authoritative from draft items when present.
    if expense_draft and (expense_draft.get("items") or []):
        items = expense_draft.get("items", []) or []
        merchant_amount = round(sum(float(i.get("quantity", 1) or 0) * float(i.get("unit_price", 0) or 0) for i in items), 2)
    if not merchant_amount or float(merchant_amount) <= 0:
        raise ValueError("Merchant amount must be positive")

    merchant_amount_paise = int(round(float(merchant_amount) * 100))
    fee_percent = await get_fee_percent()
    b = compute_fee_breakdown(merchant_amount_paise, fee_percent)

    # Dedupe: reuse an un-paid order for the same billing session (duplicate Pay tap).
    if billing_session_id:
        existing = await db.payment_orders.find_one({
            "user_id": user["id"], "billing_session_id": billing_session_id,
            "payment_status": {"$in": [PaymentStatus.CREATED, PaymentStatus.PENDING]},
        })
        if existing and existing.get("order_id"):
            await audit(existing["id"], AuditEvent.ORDER_REUSED, "create_merchant_order")
            return _merchant_order_response(existing, reused=True)

    tid = str(uuid.uuid4())
    order = razorpay_service.create_order(
        b["customer_total_paise"], receipt=f"b4p_{tid[:20]}",
        notes={"transaction_id": tid, "purpose": "merchant_payment", "payee_upi": payee_upi, "user_id": user["id"]},
    )
    # Ensure the draft carries the locked payee so the bill snapshot is correct.
    draft = dict(expense_draft or {})
    pay = dict(draft.get("payment") or {})
    pay.update({"merchant_name": payee_name, "merchant_upi": payee_upi, "payment_method": "Razorpay"})
    draft["payment"] = pay
    doc = {
        "id": tid, "order_id": order["id"], "user_id": user["id"],
        "purpose": "merchant_payment",
        "payee_name_snapshot": (payee_name or "").strip() or None,
        "payee_upi_snapshot": payee_upi,
        "merchant_amount_paise": b["merchant_amount_paise"],
        "platform_fee_percent_snapshot": b["platform_fee_percent_snapshot"],
        "platform_fee_paise": b["platform_fee_paise"],
        "customer_total_paise": b["customer_total_paise"],
        "merchant_payout_amount_paise": b["merchant_payout_amount_paise"],
        # `amount`/`amount_paise` are the AUTHORITATIVE order amount = customer_total.
        "amount": round(b["customer_total_paise"] / 100, 2),
        "amount_paise": b["customer_total_paise"],
        "payment_status": PaymentStatus.CREATED, "status": "created",
        "bill_status": BillStatus.PENDING,
        "settlement_status": SettlementStatus.NOT_REQUIRED,
        "payout_status": PayoutStatus.NOT_STARTED,
        "credited": False, "expense_id": None, "expense_draft": draft,
        "billing_session_id": billing_session_id, "razorpay_payment_id": None,
        "gateway_fee_paise": None, "gateway_tax_paise": None,
        "payout_fee_paise": None, "payout_tax_paise": None,
        "razorpayx_payout_id": None, "razorpay_contact_id": None,
        "razorpay_fund_account_id": None, "created_at": now_iso(),
    }
    await db.payment_orders.insert_one(doc)
    await audit(tid, AuditEvent.TRANSACTION_CREATED, "create_merchant_order", {"merchant_amount_paise": b["merchant_amount_paise"]})
    await audit(tid, AuditEvent.QR_SCANNED, "create_merchant_order", {"upi": payee_upi})
    await audit(tid, AuditEvent.PAYEE_LOCKED, "create_merchant_order", {"upi": payee_upi, "name": payee_name})
    await audit(tid, AuditEvent.ORDER_CREATED, "create_merchant_order", {"order_id": order["id"]})
    return _merchant_order_response(doc)


def _merchant_order_response(doc, reused=False):
    return {
        "transaction_id": doc["id"],
        "razorpay_order_id": doc["order_id"],
        "amount": doc["customer_total_paise"],   # paise, authoritative order amount
        "currency": "INR",
        "razorpay_key_id": razorpay_service.key_id(),
        "payee_name": doc.get("payee_name_snapshot"),
        "payee_upi": doc.get("payee_upi_snapshot"),
        "merchant_amount_paise": doc["merchant_amount_paise"],
        "platform_fee_percent": doc["platform_fee_percent_snapshot"],
        "platform_fee_paise": doc["platform_fee_paise"],
        "customer_total_paise": doc["customer_total_paise"],
        "merchant_payout_amount_paise": doc["merchant_payout_amount_paise"],
        "reused": reused,
    }


# ---------------- Wallet crediting (idempotent) ----------------
async def _credit_wallet_once(txn: dict, payment_id: str):
    doc = await db.payment_orders.find_one_and_update(
        {"id": txn["id"], "purpose": "wallet_recharge", "credited": {"$ne": True}},
        {"$set": {"credited": True}},
        return_document=_AFTER,
    )
    if not doc:
        return None
    amt = float(doc.get("amount") or 0)
    u = await db.users.find_one_and_update(
        {"id": doc["user_id"]}, {"$inc": {"wallet_balance": amt}}, return_document=_AFTER
    )
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": doc["user_id"], "type": "credit",
        "amount": amt, "reason": f"Wallet recharge (Razorpay {payment_id})", "created_at": now_iso(),
    })
    return round(float((u or {}).get("wallet_balance", 0.0)), 2)


# ---------------- THE reconciler ----------------
async def reconcile_payment(*, transaction_id=None, order_id=None, payment_id=None,
                            signature=None, source="unknown", amount_paise=None,
                            verified_captured=False, gateway_fee_paise=None,
                            gateway_tax_paise=None):
    txn = await _find_txn(transaction_id, order_id)
    if not txn:
        await audit(transaction_id or order_id, AuditEvent.RECONCILED, source, {"found": False})
        return {"found": False}
    tid = txn["id"]
    order_id = txn.get("order_id")

    # 1) Establish that the payment is genuinely captured.
    captured = False
    if signature:
        if not razorpay_service.verify_checkout_signature(order_id, payment_id, signature):
            await db.payment_orders.update_one({"id": tid}, {"$set": {"processing_error": "signature_verification_failed", "last_reconciled_at": now_iso()}})
            await audit(tid, AuditEvent.SIGNATURE_FAILED, source)
            return {"found": True, "verified": False, "payment_status": txn.get("payment_status", PaymentStatus.PENDING)}
        await audit(tid, AuditEvent.PAYMENT_VERIFIED, source)
        captured = True
    elif verified_captured:
        captured = True
    else:
        # admin / background: if already captured, don't waste a live API call.
        if txn.get("payment_status") == PaymentStatus.CAPTURED:
            captured = True
            payment_id = payment_id or txn.get("razorpay_payment_id")
        else:
            try:
                if not payment_id:
                    pays = razorpay_service.fetch_order_payments(order_id)
                    cap = next((p for p in pays if p.get("status") in ("captured", "authorized")), None)
                    if not cap:
                        return {"found": True, "captured": False, "payment_status": txn.get("payment_status", PaymentStatus.PENDING)}
                    payment_id = cap["id"]
                    amount_paise = amount_paise or cap.get("amount")
                else:
                    pay = razorpay_service.fetch_payment(payment_id)
                    amount_paise = amount_paise or pay.get("amount")
                    if pay.get("status") not in ("captured", "authorized"):
                        return {"found": True, "captured": False, "payment_status": txn.get("payment_status", PaymentStatus.PENDING)}
                captured = True
                await audit(tid, AuditEvent.RECOVERED, source, {"payment_id": payment_id})
            except Exception as e:  # noqa: BLE001
                logger.error("[reconcile] provider fetch failed txn=%s: %s", tid, str(e)[:150])
                return {"found": True, "captured": False, "error": "provider_fetch_failed"}

    if not captured:
        return {"found": True, "captured": False}

    # 2) Amount integrity — never bill a mismatched amount silently.
    expected = txn.get("amount_paise") or int(round(float(txn.get("amount", 0) or 0) * 100))
    if amount_paise is not None and expected and int(amount_paise) != int(expected):
        await db.payment_orders.update_one({"id": tid}, {"$set": {
            "payment_status": PaymentStatus.MANUAL_REVIEW,
            "razorpay_payment_id": payment_id,
            "processing_error": f"amount_mismatch expected={expected} got={amount_paise}",
            "last_reconciled_at": now_iso(),
        }})
        await audit(tid, AuditEvent.AMOUNT_MISMATCH, source, {"expected": expected, "got": amount_paise})
        return {"found": True, "payment_status": PaymentStatus.MANUAL_REVIEW, "amount_mismatch": True}

    # 3) Atomically flip to captured exactly once (the concurrency gate).
    _cap_set = {
        "payment_status": PaymentStatus.CAPTURED, "status": "paid",
        "razorpay_payment_id": payment_id, "razorpay_signature": signature,
        "paid_at": now_iso(), "last_reconciled_at": now_iso(),
    }
    if gateway_fee_paise is not None:
        _cap_set["gateway_fee_paise"] = int(gateway_fee_paise)
    if gateway_tax_paise is not None:
        _cap_set["gateway_tax_paise"] = int(gateway_tax_paise)
    claimed = await db.payment_orders.find_one_and_update(
        {"id": tid, "payment_status": {"$ne": PaymentStatus.CAPTURED}},
        {"$set": _cap_set},
        return_document=_AFTER,
    )
    if claimed is not None:
        await audit(tid, AuditEvent.PAYMENT_CAPTURED, source, {"payment_id": payment_id})

    # 4) Fulfil by purpose — every step below is independently idempotent, so
    #    concurrent callers converge to exactly one bill / one credit.
    purpose = txn.get("purpose")
    result = {"found": True, "captured": True, "transaction_id": tid, "payment_status": PaymentStatus.CAPTURED}

    if purpose == "wallet_recharge":
        bal = await _credit_wallet_once(txn, payment_id)
        result["wallet_balance"] = bal
    elif purpose in ("bill", "merchant_payment"):
        eid = await billing_service.ensure_expense_for_transaction(
            await db.payment_orders.find_one({"id": tid}), payment_id
        )
        if eid:
            bill = await billing_service.ensure_bill_generated(eid, txn)
            await db.payment_orders.update_one({"id": tid}, {"$set": {
                "bill_status": BillStatus.GENERATED, "bill_id": bill.get("bill_id"),
                "expense_id": eid, "bill_generated_at": now_iso(),
            }})
            await audit(tid, AuditEvent.BILL_GENERATED if not bill.get("existing") else AuditEvent.BILL_REUSED, source, {"bill_id": bill.get("bill_id")})
            exp = await db.expenses.find_one({"id": eid})
            await settlement_service.ensure_settlement_record(await db.payment_orders.find_one({"id": tid}), exp)
            result["bill_id"] = bill.get("bill_id")
            result["expense_id"] = eid
            # v2 collect-and-payout: after the bill exists, pay the merchant —
            # BUT never in manual_upi_double_scan mode (merchant is paid directly
            # by the customer, so RazorpayX must not send a second payout, spec §31).
            import os as _os
            if purpose == "merchant_payment" and _os.environ.get("PAYMENT_FLOW_MODE") != "manual_upi_double_scan":
                payout_res = await payout_service.ensure_payout(await db.payment_orders.find_one({"id": tid}))
                result["payout_status"] = payout_res.get("payout_status")
    elif purpose == "bill_fee":
        target = (txn.get("expense_draft") or {}).get("target_expense_id") or txn.get("expense_id")
        if target:
            bill = await billing_service.ensure_bill_generated(target, txn)
            await db.payment_orders.update_one({"id": tid}, {"$set": {"bill_status": BillStatus.GENERATED, "bill_id": bill.get("bill_id"), "expense_id": target}})
            result["bill_id"] = bill.get("bill_id")

    await audit(tid, AuditEvent.RECONCILED, source)
    fresh = await db.payment_orders.find_one({"id": tid}, {"_id": 0})
    result["bill_status"] = fresh.get("bill_status")
    result["settlement_status"] = fresh.get("settlement_status")
    result["bill_id"] = fresh.get("bill_id")
    return result


async def mark_failed(order_id=None, payment_id=None, transaction_id=None):
    txn = await _find_txn(transaction_id, order_id, payment_id)
    if not txn:
        return
    # Never downgrade an already-captured payment.
    await db.payment_orders.update_one(
        {"id": txn["id"], "payment_status": {"$nin": [PaymentStatus.CAPTURED, PaymentStatus.REFUNDED]}},
        {"$set": {"payment_status": PaymentStatus.FAILED, "status": "failed", "razorpay_payment_id": payment_id, "last_reconciled_at": now_iso()}},
    )
    await audit(txn["id"], AuditEvent.PAYMENT_FAILED, "webhook", {"payment_id": payment_id})


async def mark_refunded(order_id=None, payment_id=None, transaction_id=None):
    txn = await _find_txn(transaction_id, order_id, payment_id)
    if not txn:
        return
    # Only a captured payment can be refunded — a stray refund event must not
    # corrupt a created/failed transaction.
    res = await db.payment_orders.update_one(
        {"id": txn["id"], "payment_status": PaymentStatus.CAPTURED},
        {"$set": {"payment_status": PaymentStatus.REFUNDED, "refunded_at": now_iso()}},
    )
    if res.modified_count and txn.get("expense_id"):
        await db.expenses.update_one({"id": txn["expense_id"]}, {"$set": {"bill_status": BillStatus.REFUNDED}})
    await audit(txn["id"], AuditEvent.REFUND_PROCESSED, "webhook", {"payment_id": payment_id})


# ---------------- Authoritative status (self-healing) ----------------
async def get_status(transaction_id: str, user_id: str | None = None):
    txn = await db.payment_orders.find_one({"id": transaction_id}, {"_id": 0})
    if not txn:
        return None
    if user_id and txn.get("user_id") != user_id:
        return None
    # Self-heal: captured but bill missing → ensure it now.
    if txn.get("payment_status") == PaymentStatus.CAPTURED and txn.get("bill_status") != BillStatus.GENERATED \
            and txn.get("purpose") in ("bill", "merchant_payment"):
        await reconcile_payment(transaction_id=transaction_id, payment_id=txn.get("razorpay_payment_id"),
                                source="status_read", verified_captured=True,
                                amount_paise=txn.get("amount_paise"))
        txn = await db.payment_orders.find_one({"id": transaction_id}, {"_id": 0})
    return {
        "transaction_id": txn["id"],
        "payment_status": txn.get("payment_status", PaymentStatus.PENDING),
        "bill_status": txn.get("bill_status", BillStatus.PENDING),
        "bill_id": txn.get("bill_id"),
        "expense_id": txn.get("expense_id"),
        "settlement_status": txn.get("settlement_status", SettlementStatus.NOT_REQUIRED),
        "payout_status": txn.get("payout_status", PayoutStatus.NOT_STARTED),
        "payout_utr": txn.get("payout_utr"),
        "razorpayx_payout_id": txn.get("razorpayx_payout_id"),
        "payee_name": txn.get("payee_name_snapshot"),
        "payee_upi": txn.get("payee_upi_snapshot"),
        "merchant_amount": round((txn.get("merchant_amount_paise") or 0) / 100, 2) if txn.get("merchant_amount_paise") is not None else None,
        "platform_fee_percent": txn.get("platform_fee_percent_snapshot"),
        "platform_fee": round((txn.get("platform_fee_paise") or 0) / 100, 2) if txn.get("platform_fee_paise") is not None else None,
        "customer_total": round((txn.get("customer_total_paise") or 0) / 100, 2) if txn.get("customer_total_paise") is not None else txn.get("amount"),
        "amount": txn.get("amount"),
        "purpose": txn.get("purpose"),
        "processing_error": txn.get("processing_error"),
    }


# ---------------- Background safety job ----------------
async def scan_and_reconcile_pending(older_than_minutes: int = 3, limit: int = 50):
    """Find stale un-captured orders and ask Razorpay if they actually paid."""
    if not razorpay_service.enabled():
        return {"scanned": 0, "recovered": 0}
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)).isoformat()
    cursor = db.payment_orders.find({
        "payment_status": {"$in": [PaymentStatus.CREATED, PaymentStatus.PENDING]},
        "order_id": {"$ne": None},
        "created_at": {"$lt": cutoff},
    }).limit(limit)
    scanned = recovered = 0
    async for txn in cursor:
        scanned += 1
        try:
            res = await reconcile_payment(transaction_id=txn["id"], source="background")
            if res.get("captured"):
                recovered += 1
        except Exception as e:  # noqa: BLE001
            logger.error("[background] reconcile failed txn=%s: %s", txn["id"], str(e)[:120])
    if scanned:
        logger.info("[background] scan complete scanned=%s recovered=%s", scanned, recovered)
    return {"scanned": scanned, "recovered": recovered}
