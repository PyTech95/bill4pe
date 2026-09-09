"""Razorpay payment endpoints.

Thin HTTP layer over `services.payment_service` — the reconciliation brain.
Legacy routes (`/razorpay/order`, `/razorpay/verify`) keep their old contracts
so existing Wallet/PayNow code keeps working; new spec routes add the
transaction-before-checkout + recovery flow.
"""
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.config import compute_fee_breakdown
from core.db import db
from core.security import get_current_user
from services import payment_service, payout_service, razorpay_service, razorpayx_service

router = APIRouter(tags=["payments"])


class LegacyOrderReq(BaseModel):
    amount: float
    purpose: Literal["wallet_recharge", "bill", "bill_fee", "merchant_payment"] = "wallet_recharge"


class CreateOrderReq(BaseModel):
    purpose: Literal["wallet_recharge", "bill", "bill_fee", "merchant_payment"] = "merchant_payment"
    amount: Optional[float] = None
    expense_draft: Optional[dict[str, Any]] = None
    billing_session_id: Optional[str] = None


class LegacyVerifyReq(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    purpose: str = "wallet_recharge"


class VerifyReq(BaseModel):
    transaction_id: Optional[str] = None
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class CreateMerchantOrderReq(BaseModel):
    payee_name: Optional[str] = None
    payee_upi: str
    merchant_amount: Optional[float] = None
    expense_draft: Optional[dict[str, Any]] = None
    billing_session_id: Optional[str] = None


@router.get("/payments/config")
async def payments_config():
    return {
        "provider": "razorpay",
        "key_id": razorpay_service.key_id() or None,
        "enabled": razorpay_service.enabled(),
        "mode": razorpay_service.mode(),
        "payout_enabled": razorpayx_service.enabled(),
        "platform_fee_percent": await payment_service.get_fee_percent(),
    }


@router.get("/payments/fee-preview")
async def fee_preview(merchant_amount: float, user=Depends(get_current_user)):
    """Backend-authoritative preview of the 10% fee breakdown for a merchant amount."""
    if merchant_amount <= 0:
        raise HTTPException(400, "merchant_amount must be positive")
    fee_percent = await payment_service.get_fee_percent()
    b = compute_fee_breakdown(int(round(merchant_amount * 100)), fee_percent)
    return {
        **b,
        "merchant_amount": round(b["merchant_amount_paise"] / 100, 2),
        "platform_fee": round(b["platform_fee_paise"] / 100, 2),
        "customer_total": round(b["customer_total_paise"] / 100, 2),
    }


@router.post("/payments/merchant/create-order")
async def create_merchant_order(body: CreateMerchantOrderReq, user=Depends(get_current_user)):
    """v2: lock the scanned payee, compute 10% fee server-side, create a Razorpay
    order for merchant_amount + fee. The payee UPI is immutable after this."""
    try:
        return await payment_service.create_merchant_payment_order(
            user, payee_name=body.payee_name, payee_upi=body.payee_upi,
            merchant_amount=body.merchant_amount, expense_draft=body.expense_draft,
            billing_session_id=body.billing_session_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if any(k in msg for k in ("authentication", "unauthorized", "401")):
            raise HTTPException(502, "Razorpay authentication failed — verify the API keys in backend/.env")
        raise HTTPException(502, f"Could not create Razorpay order: {str(e)[:150]}")


@router.post("/payments/create-order")
async def create_order(body: CreateOrderReq, user=Depends(get_current_user)):
    """Preferred: creates the internal transaction (with expense draft) BEFORE
    checkout so a captured payment can always be recovered server-side."""
    if body.purpose == "wallet_recharge" and user.get("role") == "employee":
        raise HTTPException(403, "Employees don't recharge personal wallets — ask your admin.")
    try:
        return await payment_service.create_payment_order(
            user, body.purpose, amount=body.amount,
            expense_draft=body.expense_draft, billing_session_id=body.billing_session_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if any(k in msg for k in ("authentication", "unauthorized", "401")):
            raise HTTPException(502, "Razorpay authentication failed — verify the API keys in backend/.env")
        raise HTTPException(502, f"Could not create Razorpay order: {str(e)[:150]}")


@router.post("/payments/razorpay/order")
async def legacy_create_order(body: LegacyOrderReq, user=Depends(get_current_user)):
    """Legacy contract (used by Wallet recharge). Returns both old + new keys."""
    if body.purpose == "wallet_recharge" and user.get("role") == "employee":
        raise HTTPException(403, "Employees don't recharge personal wallets — ask your admin.")
    try:
        res = await payment_service.create_payment_order(user, body.purpose, amount=body.amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if any(k in msg for k in ("authentication", "unauthorized", "401")):
            raise HTTPException(502, "Razorpay authentication failed — verify the API keys in backend/.env")
        raise HTTPException(502, f"Could not create Razorpay order: {str(e)[:150]}")
    return {
        "order_id": res["razorpay_order_id"],
        "razorpay_order_id": res["razorpay_order_id"],
        "amount": res["amount"],
        "currency": res["currency"],
        "key_id": res["razorpay_key_id"],
        "razorpay_key_id": res["razorpay_key_id"],
        "transaction_id": res["transaction_id"],
    }


@router.post("/payments/verify")
async def verify_payment(body: VerifyReq, user=Depends(get_current_user)):
    res = await payment_service.reconcile_payment(
        transaction_id=body.transaction_id,
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
        source="checkout",
    )
    if not res.get("found"):
        raise HTTPException(404, "Transaction not found")
    if res.get("verified") is False:
        return {"success": False, "payment_status": "verification_failed"}
    return {"success": True, **res}


@router.post("/payments/razorpay/verify")
async def legacy_verify(body: LegacyVerifyReq, user=Depends(get_current_user)):
    res = await payment_service.reconcile_payment(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
        source="checkout",
    )
    if not res.get("found"):
        raise HTTPException(404, "Order not found")
    if res.get("verified") is False:
        raise HTTPException(400, "Payment signature verification failed")
    out = {"verified": True, "payment_id": body.razorpay_payment_id}
    if "wallet_balance" in res and res["wallet_balance"] is not None:
        out["balance"] = res["wallet_balance"]
    if res.get("bill_id"):
        out["bill_id"] = res["bill_id"]
    return out


@router.get("/payments/{transaction_id}/status")
async def payment_status(transaction_id: str, user=Depends(get_current_user)):
    res = await payment_service.get_status(transaction_id, user_id=user["id"])
    if not res:
        raise HTTPException(404, "Transaction not found")
    return res


@router.get("/payments/history")
async def payment_history(user=Depends(get_current_user)):
    rows = await db.payment_orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"payments": rows}
