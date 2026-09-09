"""Admin payment & settlement operations (super-admin only).

Monitoring + manual recovery levers: list transactions with filters + payout +
margin data, flag captured-but-billless / failed payouts, force a reconcile,
retry a settlement or a payout, manage the platform fee %, and report the
backend outbound IP for RazorpayX allowlisting.
"""
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.enums import BillStatus, PaymentStatus, PayoutStatus, SettlementStatus
from core.security import get_current_user
from services import payment_service, payout_service, settlement_service

router = APIRouter(prefix="/admin", tags=["admin-payments"])


async def require_super_admin(user=Depends(get_current_user)):
    if not user.get("is_super_admin"):
        raise HTTPException(403, "Super admin access required")
    return user


def _margin(row: dict) -> dict:
    """Provider-adjusted margin = platform fee − gateway fee/tax − payout fee/tax.
    Only computed from authoritative provider fee values; None when unknown."""
    fee = row.get("platform_fee_paise")
    if fee is None:
        return {"provider_adjusted_margin_paise": None}
    costs = 0
    known_any = False
    for k in ("gateway_fee_paise", "gateway_tax_paise", "payout_fee_paise", "payout_tax_paise"):
        v = row.get(k)
        if v is not None:
            costs += int(v)
            known_any = True
    return {
        "provider_adjusted_margin_paise": (int(fee) - costs) if known_any else None,
        "provider_costs_known": known_any,
    }


@router.get("/payments")
async def list_payments(
    status: Optional[str] = None,
    flag: Optional[str] = None,        # bill_missing | settlement_pending | settlement_failed | payout_failed | payout_pending
    limit: int = 200,
    _=Depends(require_super_admin),
):
    limit = max(1, min(int(limit), 500))
    q: dict = {}
    if status:
        q["payment_status"] = status
    if flag == "bill_missing":
        q["payment_status"] = PaymentStatus.CAPTURED
        q["bill_status"] = {"$ne": BillStatus.GENERATED}
    elif flag == "settlement_pending":
        q["settlement_status"] = SettlementStatus.PENDING
    elif flag == "settlement_failed":
        q["settlement_status"] = SettlementStatus.FAILED
    elif flag == "payout_failed":
        q["payout_status"] = {"$in": [PayoutStatus.FAILED, PayoutStatus.REJECTED, PayoutStatus.MANUAL_REVIEW]}
    elif flag == "payout_pending":
        q["payout_status"] = {"$in": [PayoutStatus.QUEUED, PayoutStatus.PENDING, PayoutStatus.PROCESSING, PayoutStatus.REQUESTED]}

    rows = await db.payment_orders.find(q, {"_id": 0}).sort("created_at", -1).limit(int(limit)).to_list(int(limit))
    for r in rows:
        r["margin"] = _margin(r)

    missing_bill = await db.payment_orders.count_documents({
        "payment_status": PaymentStatus.CAPTURED,
        "purpose": {"$in": ["bill", "merchant_payment"]},
        "bill_status": {"$ne": BillStatus.GENERATED},
    })
    payout_failed = await db.payment_orders.count_documents({
        "purpose": "merchant_payment",
        "payout_status": {"$in": [PayoutStatus.FAILED, PayoutStatus.REJECTED, PayoutStatus.MANUAL_REVIEW]},
    })
    payout_pending = await db.payment_orders.count_documents({
        "purpose": "merchant_payment",
        "payout_status": {"$in": [PayoutStatus.QUEUED, PayoutStatus.PENDING, PayoutStatus.PROCESSING, PayoutStatus.REQUESTED]},
    })
    return {
        "payments": rows,
        "alerts": {
            "bill_missing": missing_bill,
            "payout_failed": payout_failed,
            "payout_pending": payout_pending,
            "settlement_pending": await db.payment_orders.count_documents({"settlement_status": SettlementStatus.PENDING}),
            "settlement_failed": await db.payment_orders.count_documents({"settlement_status": SettlementStatus.FAILED}),
        },
    }


@router.post("/payments/{transaction_id}/reconcile")
async def admin_reconcile(transaction_id: str, _=Depends(require_super_admin)):
    return await payment_service.reconcile_payment(transaction_id=transaction_id, source="admin")


@router.post("/payouts/{transaction_id}/retry")
async def admin_retry_payout(transaction_id: str, _=Depends(require_super_admin)):
    """Retry a failed/queued merchant payout (idempotent — reuses the same key)."""
    return await payout_service.retry_payout(transaction_id)


@router.post("/settlements/{transaction_id}/retry")
async def admin_retry_settlement(transaction_id: str, _=Depends(require_super_admin)):
    return await settlement_service.retry_settlement(transaction_id)


@router.post("/payments/scan")
async def admin_scan(older_than_minutes: int = 3, _=Depends(require_super_admin)):
    return await payment_service.scan_and_reconcile_pending(older_than_minutes=older_than_minutes)


# ---------------- Platform fee setting (future txns only) ----------------
class FeeReq(BaseModel):
    percent: float


@router.get("/settings/platform-fee")
async def get_platform_fee(_=Depends(require_super_admin)):
    return {"percent": await payment_service.get_fee_percent()}


@router.post("/settings/platform-fee")
async def set_platform_fee(body: FeeReq, _=Depends(require_super_admin)):
    """Change the fee for FUTURE transactions only. Historical bills keep their snapshot."""
    try:
        percent = await payment_service.set_fee_percent(body.percent)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"percent": percent, "note": "Applies to future transactions only."}


# ---------------- Outbound IP (for RazorpayX static-IP allowlisting §32) ----------------
@router.get("/system/outbound-ip")
async def outbound_ip(_=Depends(require_super_admin)):
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get("https://api.ipify.org?format=json")
        return {"outbound_ip": r.json().get("ip"), "note": "Allowlist this IP in RazorpayX Developer Controls."}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Could not determine outbound IP: {str(e)[:120]}")
