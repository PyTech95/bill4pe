"""Merchant settlement service — modular, Route-ready, disabled by default.

Business model = REIMBURSEMENT: the customer pays the merchant directly, Bill4Pe
is never in the money path, so settlement is `not_required`. This module is a
clean, idempotent scaffold so the platform can flip to Razorpay Route (split to
merchant Linked Accounts) later WITHOUT touching bill-generation code.

Hard rule: settlement NEVER blocks or reverses a customer's paid bill.
"""
import os
import uuid

from core.config import logger
from core.db import db
from core.enums import SettlementStatus
from core.security import now_iso
from services import razorpay_service

ROUTE_ENABLED = os.environ.get("RAZORPAY_ROUTE_ENABLED", "false").strip().lower() == "true"
PLATFORM_FEE_PERCENT = float(os.environ.get("PLATFORM_FEE_PERCENT", "0"))  # marketplace only

try:
    from pymongo.errors import DuplicateKeyError
except Exception:  # pragma: no cover
    class DuplicateKeyError(Exception):
        pass


async def _resolve_merchant(txn: dict, expense: dict | None):
    """Look up a merchant settlement config. In reimbursement mode there is none."""
    pay = ((expense or {}).get("payment")) or (txn.get("expense_draft") or {}).get("payment") or {}
    upi = pay.get("merchant_upi")
    if not upi:
        return None
    return await db.merchants.find_one({"upi_id": upi})


async def ensure_settlement_record(txn: dict, expense: dict | None = None) -> dict | None:
    """Create at most ONE settlement instruction per transaction.

    Reimbursement mode (Route disabled, or merchant has no linked account) →
    settlement_status = not_required, no payout ever attempted.
    """
    tid = txn["id"]
    if not ROUTE_ENABLED:
        await db.payment_orders.update_one({"id": tid}, {"$set": {"settlement_status": SettlementStatus.NOT_REQUIRED}})
        return None

    merchant = await _resolve_merchant(txn, expense)
    if not merchant or not merchant.get("razorpay_linked_account_id"):
        await db.payment_orders.update_one({"id": tid}, {"$set": {"settlement_status": SettlementStatus.NOT_REQUIRED}})
        return None

    gross = float(txn.get("amount", 0) or 0)
    ctype = merchant.get("commission_type", "percentage" if PLATFORM_FEE_PERCENT else "none")
    cval = float(merchant.get("commission_value", PLATFORM_FEE_PERCENT))
    if ctype == "percentage":
        platform_fee = round(gross * cval / 100.0, 2)
    elif ctype == "fixed":
        platform_fee = round(cval, 2)
    else:
        platform_fee = 0.0
    merchant_amount = round(gross - platform_fee, 2)

    doc = {
        "id": str(uuid.uuid4()),
        "transaction_id": tid,
        "merchant_id": merchant["id"],
        "provider": "razorpay_route",
        "razorpay_linked_account_id": merchant["razorpay_linked_account_id"],
        "gross_amount": gross,
        "platform_fee": platform_fee,
        "merchant_amount": merchant_amount,
        "status": SettlementStatus.PENDING,
        "provider_transfer_id": None,
        "attempts": 0,
        "created_at": now_iso(),
    }
    try:
        await db.settlements.insert_one(doc)
        await db.payment_orders.update_one({"id": tid}, {"$set": {"settlement_status": SettlementStatus.PENDING}})
        logger.info("[settlement] record created txn=%s merchant=%s", tid, merchant["id"])
    except DuplicateKeyError:
        logger.info("[settlement] record already exists txn=%s", tid)
    return await db.settlements.find_one({"transaction_id": tid, "merchant_id": merchant["id"]}, {"_id": 0})


async def process_settlement(settlement: dict) -> dict:
    """Attempt the Route transfer. Idempotent on provider_transfer_id."""
    if settlement.get("provider_transfer_id") or settlement.get("status") == SettlementStatus.PROCESSED:
        return settlement
    tid = settlement["transaction_id"]
    txn = await db.payment_orders.find_one({"id": tid})
    if not txn or not txn.get("razorpay_payment_id"):
        return settlement  # never transfer before capture
    await db.settlements.update_one({"id": settlement["id"]}, {"$set": {"status": SettlementStatus.PROCESSING}, "$inc": {"attempts": 1}})
    try:
        transfers = [{
            "account": settlement["razorpay_linked_account_id"],
            "amount": int(round(settlement["merchant_amount"] * 100)),
            "currency": "INR",
        }]
        resp = razorpay_service.create_transfer(txn["razorpay_payment_id"], transfers)
        transfer_id = None
        if isinstance(resp, dict):
            items = resp.get("items") or []
            transfer_id = (items[0].get("id") if items else None) or resp.get("id")
        await db.settlements.update_one({"id": settlement["id"]}, {"$set": {
            "status": SettlementStatus.PROCESSED, "provider_transfer_id": transfer_id, "processed_at": now_iso(),
        }})
        await db.payment_orders.update_one({"id": tid}, {"$set": {"settlement_status": SettlementStatus.PROCESSED}})
        logger.info("[settlement] processed txn=%s transfer=%s", tid, transfer_id)
    except Exception as e:  # noqa: BLE001
        await db.settlements.update_one({"id": settlement["id"]}, {"$set": {
            "status": SettlementStatus.FAILED, "last_error": str(e)[:200], "failed_at": now_iso(),
        }})
        await db.payment_orders.update_one({"id": tid}, {"$set": {"settlement_status": SettlementStatus.FAILED}})
        logger.error("[settlement] FAILED txn=%s: %s", tid, str(e)[:200])
    return await db.settlements.find_one({"id": settlement["id"]}, {"_id": 0})


async def retry_settlement(transaction_id: str) -> dict:
    """Retry only failed/pending settlements — never a processed one."""
    s = await db.settlements.find_one({"transaction_id": transaction_id})
    if not s:
        return {"ok": False, "reason": "no_settlement_record"}
    if s.get("status") == SettlementStatus.PROCESSED:
        return {"ok": True, "status": SettlementStatus.PROCESSED, "already": True}
    updated = await process_settlement(s)
    return {"ok": True, "status": (updated or {}).get("status")}
