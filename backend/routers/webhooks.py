"""Razorpay webhook — the server-side source of truth / safety net.

Verifies the signature against the RAW body, dedupes events so retries never
double-process, then routes every event through the shared reconciler.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.db import db
from core.enums import AuditEvent
from core.security import now_iso
from services import payment_service, payout_service, razorpay_service, razorpayx_service

try:
    from pymongo.errors import DuplicateKeyError
except Exception:  # pragma: no cover
    class DuplicateKeyError(Exception):
        pass

router = APIRouter(tags=["webhooks"])

_CAPTURE_EVENTS = ("payment.captured", "order.paid")
_FAIL_EVENTS = ("payment.failed",)
_REFUND_EVENTS = ("refund.processed", "refund.created", "payment.refunded")


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    raw = await request.body()  # RAW bytes — required for signature verification
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not razorpay_service.webhook_configured():
        return JSONResponse({"detail": "Webhook not configured"}, status_code=503)

    if not razorpay_service.verify_webhook_signature(raw, signature):
        await payment_service.audit(None, AuditEvent.WEBHOOK_INVALID_SIGNATURE, "webhook")
        return JSONResponse({"detail": "Invalid webhook signature"}, status_code=400)

    try:
        event = json.loads(raw or b"{}")
    except Exception:
        return JSONResponse({"detail": "Bad payload"}, status_code=400)

    etype = event.get("event", "")
    payload = event.get("payload", {}) or {}
    payment_entity = (payload.get("payment", {}) or {}).get("entity", {}) or {}
    order_entity = (payload.get("order", {}) or {}).get("entity", {}) or {}
    refund_entity = (payload.get("refund", {}) or {}).get("entity", {}) or {}

    payment_id = payment_entity.get("id") or refund_entity.get("payment_id") or ""
    order_id = payment_entity.get("order_id") or order_entity.get("id")
    amount_paise = payment_entity.get("amount") or order_entity.get("amount_paid")

    # Idempotency key: prefer Razorpay's event id header, else payment_id+event.
    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    dedupe_key = event_id or f"{payment_id}:{etype}"

    await payment_service.audit(None, AuditEvent.WEBHOOK_RECEIVED, "webhook", {"event": etype, "dedupe": dedupe_key})

    try:
        await db.webhook_events.insert_one({
            "provider": "razorpay",
            "dedupe_key": dedupe_key,
            "event_type": etype,
            "payment_id": payment_id,
            "order_id": order_id,
            "processed": False,
            "received_at": now_iso(),
        })
    except DuplicateKeyError:
        await payment_service.audit(None, AuditEvent.WEBHOOK_DUPLICATE_IGNORED, "webhook", {"dedupe": dedupe_key})
        return {"status": "ignored_duplicate"}

    try:
        if etype in _CAPTURE_EVENTS:
            await payment_service.reconcile_payment(
                order_id=order_id, payment_id=payment_id, source="webhook",
                amount_paise=amount_paise, verified_captured=True,
            )
        elif etype in _FAIL_EVENTS:
            await payment_service.mark_failed(order_id=order_id, payment_id=payment_id)
        elif etype in _REFUND_EVENTS:
            await payment_service.mark_refunded(order_id=order_id, payment_id=payment_id)
    finally:
        await db.webhook_events.update_one(
            {"dedupe_key": dedupe_key}, {"$set": {"processed": True, "processed_at": now_iso()}}
        )

    return {"status": "ok"}


# ============================================================================
# v2 endpoints (collect-and-payout). Payment + payout webhooks are separate so
# each can carry its own secret and its own idempotency namespace.
# ============================================================================
@router.post("/webhooks/razorpay/payments")
async def razorpay_payments_webhook(request: Request):
    """Server-side source of truth for CUSTOMER payments (v2). Uses
    RAZORPAY_PAYMENT_WEBHOOK_SECRET, dedupes, then runs the shared reconciler."""
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not razorpay_service.payment_webhook_configured():
        return JSONResponse({"detail": "Payment webhook not configured"}, status_code=503)
    if not razorpay_service.verify_payment_webhook_signature(raw, signature):
        await payment_service.audit(None, AuditEvent.WEBHOOK_INVALID_SIGNATURE, "payment_webhook")
        return JSONResponse({"detail": "Invalid webhook signature"}, status_code=400)

    try:
        event = json.loads(raw or b"{}")
    except Exception:
        return JSONResponse({"detail": "Bad payload"}, status_code=400)

    etype = event.get("event", "")
    payload = event.get("payload", {}) or {}
    payment_entity = (payload.get("payment", {}) or {}).get("entity", {}) or {}
    order_entity = (payload.get("order", {}) or {}).get("entity", {}) or {}
    refund_entity = (payload.get("refund", {}) or {}).get("entity", {}) or {}

    payment_id = payment_entity.get("id") or refund_entity.get("payment_id") or ""
    order_id = payment_entity.get("order_id") or order_entity.get("id")
    amount_paise = payment_entity.get("amount") or order_entity.get("amount_paid")
    gateway_fee = payment_entity.get("fee")
    gateway_tax = payment_entity.get("tax")

    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    dedupe_key = f"pg:{event_id or f'{payment_id}:{etype}'}"

    await payment_service.audit(None, AuditEvent.WEBHOOK_RECEIVED, "payment_webhook", {"event": etype, "dedupe": dedupe_key})
    try:
        await db.webhook_events.insert_one({
            "provider": "razorpay_pg", "dedupe_key": dedupe_key, "event_type": etype,
            "payment_id": payment_id, "order_id": order_id, "processed": False, "received_at": now_iso(),
        })
    except DuplicateKeyError:
        await payment_service.audit(None, AuditEvent.WEBHOOK_DUPLICATE_IGNORED, "payment_webhook", {"dedupe": dedupe_key})
        return {"status": "ignored_duplicate"}

    try:
        if etype in _CAPTURE_EVENTS:
            await payment_service.reconcile_payment(
                order_id=order_id, payment_id=payment_id, source="payment_webhook",
                amount_paise=amount_paise, verified_captured=True,
                gateway_fee_paise=gateway_fee, gateway_tax_paise=gateway_tax,
            )
        elif etype in _FAIL_EVENTS:
            await payment_service.mark_failed(order_id=order_id, payment_id=payment_id)
        elif etype in _REFUND_EVENTS:
            await payment_service.mark_refunded(order_id=order_id, payment_id=payment_id)
    finally:
        await db.webhook_events.update_one({"dedupe_key": dedupe_key}, {"$set": {"processed": True, "processed_at": now_iso()}})
    return {"status": "ok"}


_PAYOUT_EVENTS = (
    "payout.processed", "payout.reversed", "payout.failed", "payout.updated",
    "payout.queued", "payout.pending", "payout.rejected", "payout.initiated",
)


@router.post("/webhooks/razorpayx/payouts")
async def razorpayx_payouts_webhook(request: Request):
    """Authoritative merchant PAYOUT status (v2). Uses RAZORPAYX_WEBHOOK_SECRET."""
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not razorpayx_service.webhook_configured():
        return JSONResponse({"detail": "Payout webhook not configured"}, status_code=503)
    if not razorpayx_service.verify_webhook_signature(raw, signature):
        await payment_service.audit(None, AuditEvent.WEBHOOK_INVALID_SIGNATURE, "payout_webhook")
        return JSONResponse({"detail": "Invalid webhook signature"}, status_code=400)

    try:
        event = json.loads(raw or b"{}")
    except Exception:
        return JSONResponse({"detail": "Bad payload"}, status_code=400)

    etype = event.get("event", "")
    payout_entity = ((event.get("payload", {}) or {}).get("payout", {}) or {}).get("entity", {}) or {}
    payout_id = payout_entity.get("id") or ""

    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    dedupe_key = f"px:{event_id or f'{payout_id}:{etype}'}"

    await payment_service.audit(None, AuditEvent.PAYOUT_WEBHOOK_RECEIVED, "payout_webhook", {"event": etype, "dedupe": dedupe_key})
    try:
        await db.webhook_events.insert_one({
            "provider": "razorpayx", "dedupe_key": dedupe_key, "event_type": etype,
            "payout_id": payout_id, "processed": False, "received_at": now_iso(),
        })
    except DuplicateKeyError:
        await payment_service.audit(None, AuditEvent.WEBHOOK_DUPLICATE_IGNORED, "payout_webhook", {"dedupe": dedupe_key})
        return {"status": "ignored_duplicate"}

    try:
        if payout_entity:
            await payout_service.reconcile_payout_from_provider(payout_entity)
    finally:
        await db.webhook_events.update_one({"dedupe_key": dedupe_key}, {"$set": {"processed": True, "processed_at": now_iso()}})
    return {"status": "ok"}
