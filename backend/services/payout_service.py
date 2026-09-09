"""Payout service — the ONE idempotent RazorpayX payout brain (v2).

One captured BILL4PE transaction → AT MOST ONE merchant payout of exactly the
merchant amount, driven by ANY of: the reconciler (after bill), the payout
webhook, admin retry. Guarantees:
  * DB atomic claim flips payout_status not_started → requested exactly once.
  * A stable idempotency key (payout_<tid>) is reused on every retry, so even a
    provider-side retry can never create a second payout.
  * Beneficiary (Contact + VPA Fund Account) is cached per normalized UPI.
  * Payout failure NEVER downgrades the customer payment or the bill.
"""
import uuid

from core.config import logger
from core.db import db
from core.enums import AuditEvent, PaymentStatus, PayoutStatus
from core.security import now_iso
from services import razorpayx_service

try:
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError
    _AFTER = ReturnDocument.AFTER
except Exception:  # pragma: no cover
    _AFTER = True

    class DuplicateKeyError(Exception):
        pass

# States from which a (re)start is NOT allowed — in-flight or terminal-success.
_LOCKED = {
    PayoutStatus.REQUESTED, PayoutStatus.QUEUED, PayoutStatus.PENDING,
    PayoutStatus.SCHEDULED, PayoutStatus.PROCESSING, PayoutStatus.PROCESSED,
    PayoutStatus.REVERSED,
}
_STARTABLE = [
    PayoutStatus.NOT_STARTED, PayoutStatus.NOT_CONFIGURED,
    PayoutStatus.FAILED, PayoutStatus.REJECTED, PayoutStatus.CANCELLED, None,
]

_STATUS_MAP = {
    "queued": PayoutStatus.QUEUED, "pending": PayoutStatus.PENDING,
    "scheduled": PayoutStatus.SCHEDULED, "processing": PayoutStatus.PROCESSING,
    "processed": PayoutStatus.PROCESSED, "cancelled": PayoutStatus.CANCELLED,
    "rejected": PayoutStatus.REJECTED, "reversed": PayoutStatus.REVERSED,
    "failed": PayoutStatus.FAILED,
}


def normalize_upi(upi: str) -> str:
    return (upi or "").strip().lower()


def map_status(provider_status: str) -> str:
    return _STATUS_MAP.get((provider_status or "").lower(), PayoutStatus.REQUESTED)


def idempotency_key(tid: str) -> str:
    return f"payout_{tid}"


async def ensure_indexes() -> None:
    await db.beneficiaries.create_index("normalized_upi", unique=True)
    await db.payouts.create_index("transaction_id", unique=True)
    await db.payouts.create_index("razorpayx_payout_id", unique=True, sparse=True)
    logger.info("[payouts] indexes ensured")


async def _audit(tid, event, metadata=None):
    try:
        await db.payment_audit.insert_one({
            "id": str(uuid.uuid4()), "transaction_id": tid, "event": event,
            "source": "payout", "metadata": metadata or {}, "timestamp": now_iso(),
        })
    except Exception:
        pass
    logger.info("[payout-audit] %s txn=%s", event, tid)


async def _resolve_beneficiary(name: str, upi: str, tid: str):
    """Reuse a cached Contact + VPA Fund Account, or create + cache them once."""
    norm = normalize_upi(upi)
    b = await db.beneficiaries.find_one({"normalized_upi": norm})
    if b and b.get("razorpay_contact_id") and b.get("razorpay_fund_account_id"):
        await _audit(tid, AuditEvent.BENEFICIARY_REUSED, {"upi": norm})
        return b["razorpay_contact_id"], b["razorpay_fund_account_id"]

    contact = await razorpayx_service.create_contact(name, tid, upi)
    fa = await razorpayx_service.create_vpa_fund_account(contact["id"], upi)
    doc = {
        "normalized_upi": norm, "payee_name": name,
        "razorpay_contact_id": contact["id"],
        "razorpay_fund_account_id": fa["id"], "created_at": now_iso(),
    }
    try:
        await db.beneficiaries.insert_one(doc)
    except DuplicateKeyError:
        existing = await db.beneficiaries.find_one({"normalized_upi": norm})
        if existing and existing.get("razorpay_fund_account_id"):
            return existing["razorpay_contact_id"], existing["razorpay_fund_account_id"]
    await _audit(tid, AuditEvent.BENEFICIARY_CREATED, {"upi": norm, "contact_id": contact["id"], "fund_account_id": fa["id"]})
    return contact["id"], fa["id"]


async def _apply_payout(tid: str, resp: dict, contact_id: str, fa_id: str):
    payout_id = resp.get("id")
    status = map_status(resp.get("status"))
    sets = {
        "payout_status": status,
        "razorpayx_payout_id": payout_id,
        "razorpay_contact_id": contact_id,
        "razorpay_fund_account_id": fa_id,
        "payout_utr": resp.get("utr"),
        "payout_fee_paise": resp.get("fees"),
        "payout_tax_paise": resp.get("tax"),
        "payout_provider_status": resp.get("status"),
        "payout_updated_at": now_iso(),
    }
    if status == PayoutStatus.PROCESSED:
        sets["payout_processed_at"] = now_iso()
    await db.payment_orders.update_one({"id": tid}, {"$set": sets})
    try:
        await db.payouts.update_one(
            {"transaction_id": tid},
            {"$set": {
                "transaction_id": tid, "razorpayx_payout_id": payout_id,
                "status": status, "amount_paise": resp.get("amount"),
                "utr": resp.get("utr"), "updated_at": now_iso(),
            }, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now_iso()}},
            upsert=True,
        )
    except DuplicateKeyError:
        pass
    evt = {
        PayoutStatus.PROCESSED: AuditEvent.PAYOUT_PROCESSED,
        PayoutStatus.QUEUED: AuditEvent.PAYOUT_QUEUED,
        PayoutStatus.PROCESSING: AuditEvent.PAYOUT_PROCESSING,
        PayoutStatus.REVERSED: AuditEvent.PAYOUT_REVERSED,
    }.get(status, AuditEvent.PAYOUT_REQUESTED)
    await _audit(tid, evt, {"payout_id": payout_id, "status": status})


async def ensure_payout(txn: dict) -> dict:
    """Idempotently create the merchant payout for a captured merchant_payment."""
    tid = txn["id"]
    if txn.get("purpose") != "merchant_payment":
        return {"payout_status": txn.get("payout_status")}
    if txn.get("payment_status") != PaymentStatus.CAPTURED:
        return {"payout_status": txn.get("payout_status")}

    amount = int(txn.get("merchant_payout_amount_paise") or 0)
    upi = txn.get("payee_upi_snapshot")
    if not upi or amount <= 0:
        return {"payout_status": txn.get("payout_status"), "skipped": "no_payee_or_amount"}

    if (txn.get("payout_status") in _LOCKED):
        return {"payout_status": txn.get("payout_status")}

    if not razorpayx_service.enabled():
        await db.payment_orders.update_one({"id": tid}, {"$set": {"payout_status": PayoutStatus.NOT_CONFIGURED}})
        await _audit(tid, AuditEvent.PAYOUT_REQUESTED, {"result": "not_configured"})
        return {"payout_status": PayoutStatus.NOT_CONFIGURED}

    key = idempotency_key(tid)
    claim = await db.payment_orders.find_one_and_update(
        {"id": tid, "payout_status": {"$in": _STARTABLE}},
        {"$set": {"payout_status": PayoutStatus.REQUESTED, "payout_idempotency_key": key}},
        return_document=_AFTER,
    )
    if not claim:
        fresh = await db.payment_orders.find_one({"id": tid})
        return {"payout_status": (fresh or {}).get("payout_status")}

    await _audit(tid, AuditEvent.PAYOUT_REQUESTED, {"amount_paise": amount, "upi": normalize_upi(upi)})
    try:
        contact_id, fa_id = await _resolve_beneficiary(txn.get("payee_name_snapshot"), upi, tid)
        resp = await razorpayx_service.create_payout(
            fund_account_id=fa_id, amount_paise=amount, reference_id=tid,
            idempotency_key=key, narration="BILL4PE payout",
        )
        await _apply_payout(tid, resp, contact_id, fa_id)
    except Exception as e:  # noqa: BLE001 — payout failure must never touch payment/bill
        msg = str(e)[:250]
        # Compliance / beneficiary rejection → manual review, not a blind retry loop.
        status = PayoutStatus.MANUAL_REVIEW if any(k in msg.lower() for k in ("compliance", "not allowed", "rejected beneficiary")) else PayoutStatus.FAILED
        await db.payment_orders.update_one({"id": tid}, {"$set": {"payout_status": status, "payout_error": msg}})
        await _audit(tid, AuditEvent.PAYOUT_FAILED, {"error": msg})
        logger.error("[payout] FAILED txn=%s: %s", tid, msg)
    fresh = await db.payment_orders.find_one({"id": tid}, {"_id": 0})
    return {"payout_status": fresh.get("payout_status"), "razorpayx_payout_id": fresh.get("razorpayx_payout_id"), "payout_utr": fresh.get("payout_utr")}


async def reconcile_payout_from_provider(payout_entity: dict) -> dict:
    """Update our records from an authoritative RazorpayX payout entity (webhook/fetch)."""
    payout_id = payout_entity.get("id")
    reference_id = payout_entity.get("reference_id")
    txn = None
    if payout_id:
        txn = await db.payment_orders.find_one({"razorpayx_payout_id": payout_id})
    if not txn and reference_id:
        txn = await db.payment_orders.find_one({"id": reference_id})
    if not txn:
        return {"found": False}
    tid = txn["id"]
    status = map_status(payout_entity.get("status"))
    sets = {
        "payout_status": status,
        "razorpayx_payout_id": payout_id or txn.get("razorpayx_payout_id"),
        "payout_utr": payout_entity.get("utr") or txn.get("payout_utr"),
        "payout_fee_paise": payout_entity.get("fees") if payout_entity.get("fees") is not None else txn.get("payout_fee_paise"),
        "payout_tax_paise": payout_entity.get("tax") if payout_entity.get("tax") is not None else txn.get("payout_tax_paise"),
        "payout_provider_status": payout_entity.get("status"),
        "payout_updated_at": now_iso(),
    }
    if status == PayoutStatus.PROCESSED:
        sets["payout_processed_at"] = now_iso()
    await db.payment_orders.update_one({"id": tid}, {"$set": sets})
    await db.payouts.update_one({"transaction_id": tid}, {"$set": {"status": status, "utr": sets["payout_utr"], "updated_at": now_iso()}}, upsert=False)
    evt = {
        PayoutStatus.PROCESSED: AuditEvent.PAYOUT_PROCESSED,
        PayoutStatus.QUEUED: AuditEvent.PAYOUT_QUEUED,
        PayoutStatus.PROCESSING: AuditEvent.PAYOUT_PROCESSING,
        PayoutStatus.REVERSED: AuditEvent.PAYOUT_REVERSED,
        PayoutStatus.FAILED: AuditEvent.PAYOUT_FAILED,
    }.get(status, AuditEvent.PAYOUT_WEBHOOK_RECEIVED)
    await _audit(tid, evt, {"payout_id": payout_id, "status": status})
    return {"found": True, "transaction_id": tid, "payout_status": status}


async def retry_payout(transaction_id: str) -> dict:
    txn = await db.payment_orders.find_one({"id": transaction_id})
    if not txn:
        return {"ok": False, "reason": "not_found"}
    if txn.get("payout_status") == PayoutStatus.PROCESSED:
        return {"ok": True, "payout_status": PayoutStatus.PROCESSED, "already": True}
    res = await ensure_payout(txn)
    return {"ok": True, **res}
