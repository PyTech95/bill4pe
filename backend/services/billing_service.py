"""Billing service — concurrency-safe, idempotent bill generation.

A "bill" is stored on the expense document (the app's existing convention).
Two guarantees:
  * `ensure_expense_for_transaction` — builds exactly one expense from a paid
    transaction's stored draft, even under concurrent webhook + callback.
  * `ensure_bill_generated` — allocates exactly one sequential bill number and
    freezes a snapshot, exactly once per expense.
"""
import uuid
from datetime import datetime, timezone

from core.config import calc_bill_fee, logger
from core.db import db
from core.enums import BillStatus
from core.security import now_iso

try:
    from pymongo import ReturnDocument
    _AFTER = ReturnDocument.AFTER
except Exception:  # pragma: no cover
    _AFTER = True


async def next_bill_number() -> str:
    """Atomic, gap-tolerant, concurrency-safe: BILL-YYYY-000001.

    Uses an atomic $inc on a counters doc — never `count()+1`.
    """
    year = datetime.now(timezone.utc).year
    doc = await db.counters.find_one_and_update(
        {"_id": f"bill:{year}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=_AFTER,
    )
    return f"BILL-{year}-{int(doc['seq']):06d}"


def build_snapshot(expense: dict, user: dict | None, txn: dict | None = None) -> dict:
    """Freeze billing data so a later merchant/profile edit can't mutate an issued bill."""
    pay = expense.get("payment") or {}
    items = []
    subtotal = 0.0
    for it in expense.get("items", []):
        qty = float(it.get("quantity", 1) or 0)
        unit = float(it.get("unit_price", 0) or 0)
        amount = round(qty * unit, 2)
        subtotal += amount
        items.append({"name": it.get("name"), "quantity": qty, "unit_price": unit, "amount": amount})
    subtotal = round(subtotal, 2)
    snap = {
        "merchant_name": pay.get("merchant_name"),
        "merchant_upi": pay.get("merchant_upi"),
        "customer_name": (user or {}).get("name"),
        "customer_email": (user or {}).get("email"),
        "customer_gstin": (user or {}).get("gstin"),
        "items": items,
        "subtotal": subtotal,
        "total": round(float(expense.get("total", subtotal) or subtotal), 2),
        "currency": "INR",
        "payment_method": pay.get("payment_method"),
        "transaction_id": pay.get("transaction_id"),
        "razorpay_payment_id": pay.get("razorpay_payment_id"),
        "frozen_at": now_iso(),
    }
    # v2 collect-and-payout accounting (present only for merchant_payment).
    if txn and txn.get("platform_fee_paise") is not None:
        snap.update({
            "model": "collect_and_payout",
            "payee_name": txn.get("payee_name_snapshot"),
            "payee_upi": txn.get("payee_upi_snapshot"),
            "merchant_amount": round((txn.get("merchant_amount_paise") or 0) / 100, 2),
            "platform_fee_percent": txn.get("platform_fee_percent_snapshot"),
            "platform_fee": round((txn.get("platform_fee_paise") or 0) / 100, 2),
            "total_paid": round((txn.get("customer_total_paise") or 0) / 100, 2),
            "merchant_payout_amount": round((txn.get("merchant_payout_amount_paise") or 0) / 100, 2),
        })
    return snap


async def ensure_expense_for_transaction(txn: dict, payment_id: str | None) -> str | None:
    """Idempotently materialise the expense a paid transaction should produce.

    Returns the expense id (existing or newly created), or None if the
    transaction carries no draft to build from.
    """
    tid = txn["id"]
    if txn.get("expense_id"):
        exp = await db.expenses.find_one({"id": txn["expense_id"]})
        if exp:
            return txn["expense_id"]

    draft = txn.get("expense_draft")
    if not draft:
        return None

    new_eid = str(uuid.uuid4())
    # Atomic claim: only ONE caller wins the right to create the expense.
    claim = await db.payment_orders.find_one_and_update(
        {"id": tid, "$or": [{"expense_id": None}, {"expense_id": {"$exists": False}}]},
        {"$set": {"expense_id": new_eid}},
        return_document=_AFTER,
    )
    if not claim or claim.get("expense_id") != new_eid:
        fresh = await db.payment_orders.find_one({"id": tid})
        return (fresh or {}).get("expense_id")

    items = draft.get("items", []) or []
    total = round(sum(float(i.get("quantity", 1) or 0) * float(i.get("unit_price", 0) or 0) for i in items), 2)
    payment = dict(draft.get("payment") or {})
    payment.update({
        "payment_status": "paid",
        "payment_method": payment.get("payment_method") or "Razorpay",
        "razorpay_payment_id": payment_id,
        "transaction_id": payment.get("transaction_id") or payment_id,
        "amount": total,
    })
    doc = {
        "id": new_eid,
        "user_id": txn["user_id"],
        "company_id": draft.get("company_id"),
        "category": draft.get("category", "other"),
        "sub_category": draft.get("sub_category"),
        "items": items,
        "payment": payment,
        "total": total,
        "notes": draft.get("notes"),
        "approval_status": "approved",
        "bill_generated": False,
        "bill_id": None,
        "bill_status": BillStatus.PENDING,
        "source": "razorpay_recovery",
        "transaction_id": tid,
        "created_at": now_iso(),
    }
    await db.expenses.insert_one(doc)
    logger.info("[billing] created expense %s from txn %s", new_eid, tid)
    return new_eid


async def ensure_bill_generated(eid: str, txn: dict | None = None) -> dict:
    """Generate exactly one bill for an expense. Safe under concurrency."""
    exp = await db.expenses.find_one({"id": eid})
    if not exp:
        raise ValueError(f"Expense {eid} not found")
    if exp.get("bill_generated") and exp.get("bill_id"):
        return {"bill_id": exp["bill_id"], "fee": exp.get("bill_fee", 0.0), "existing": True}

    # Atomic claim of the right to generate — flips bill_generated exactly once.
    claimed = await db.expenses.find_one_and_update(
        {"id": eid, "bill_generated": {"$ne": True}},
        {"$set": {"bill_generated": True, "bill_claimed_at": now_iso()}},
        return_document=_AFTER,
    )
    if not claimed:
        fresh = await db.expenses.find_one({"id": eid})
        return {"bill_id": (fresh or {}).get("bill_id"), "existing": True}

    try:
        bill_id = await next_bill_number()
        user = await db.users.find_one({"id": exp["user_id"]})
        total = float(exp.get("total", 0) or 0)

        # v2 collect-and-payout: the 10% platform fee was already collected at
        # checkout — do NOT also debit the legacy 1% wallet convenience fee.
        is_v2 = bool(txn and txn.get("platform_fee_paise") is not None)
        fee = 0.0 if is_v2 else calc_bill_fee(total)

        fee_settled = is_v2  # v2 fee is collected upfront; nothing to settle from wallet
        if not is_v2:
            debited = await db.users.find_one_and_update(
                {"id": exp["user_id"], "wallet_balance": {"$gte": fee}},
                {"$inc": {"wallet_balance": -round(fee, 2)}},
                return_document=_AFTER,
            )
            if debited:
                fee_settled = True
                await db.wallet_txns.insert_one({
                    "id": str(uuid.uuid4()), "user_id": exp["user_id"], "type": "debit",
                    "amount": round(fee, 2), "reason": f"Bill generation: {bill_id}", "created_at": now_iso(),
                })

        snapshot = build_snapshot(exp, user, txn)
        await db.expenses.update_one({"id": eid}, {"$set": {
            "bill_id": bill_id,
            "bill_number": bill_id,
            "bill_fee": round(fee, 2),
            "bill_fee_settled": fee_settled,
            "bill_status": BillStatus.GENERATED,
            "bill_generated_at": now_iso(),
            "bill_snapshot": snapshot,
        }})
    except Exception:
        # Roll back the claim so a later reconcile/status-read can retry cleanly —
        # a captured payment must never be stranded with bill_generated=True but no bill.
        await db.expenses.update_one(
            {"id": eid}, {"$set": {"bill_generated": False}, "$unset": {"bill_claimed_at": ""}}
        )
        raise
    logger.info("[billing] generated bill %s for expense %s (fee_settled=%s)", bill_id, eid, fee_settled)
    return {"bill_id": bill_id, "fee": round(fee, 2), "fee_settled": fee_settled, "existing": False}
