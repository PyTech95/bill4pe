"""Wallet — balance, recharge (mock, env-gated), transactions list."""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException

from core.db import db
from core.models import WalletRecharge, WalletPinSetup, WalletPinVerify
from core.security import get_current_user, now_iso, hash_pw, check_pw

router = APIRouter(tags=["wallet"])

# Mock recharge mints wallet balance with NO payment proof. It must never be
# reachable on a hardened/production build — enable only when explicitly opted in.
ALLOW_MOCK_RECHARGE = os.environ.get("ALLOW_MOCK_RECHARGE", "false").strip().lower() == "true"


def _validate_wallet_pin(pin: str) -> str:
    pin = (pin or "").strip()
    if len(pin) != 4 or not pin.isdigit():
        raise HTTPException(400, "Wallet PIN must be exactly 4 digits")
    return pin


@router.get("/wallet/pin/status")
async def wallet_pin_status(user=Depends(get_current_user)):
    """Return only whether a wallet PIN exists; never return the hash."""
    return {"is_set": bool(user.get("wallet_pin_set"))}


@router.post("/wallet/pin/setup")
async def wallet_pin_setup(body: WalletPinSetup, user=Depends(get_current_user)):
    """First-time 4-digit wallet PIN setup for authenticated app users."""
    pin = _validate_wallet_pin(body.pin)
    confirm = _validate_wallet_pin(body.confirm_pin)
    if pin != confirm:
        raise HTTPException(400, "Wallet PIN and confirmation do not match")

    full = await db.users.find_one({"id": user["id"]})
    if not full:
        raise HTTPException(404, "User not found")
    if full.get("wallet_pin_set") and full.get("wallet_pin_hash"):
        raise HTTPException(409, "Wallet PIN is already set")

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "wallet_pin_hash": hash_pw(pin),
            "wallet_pin_set": True,
            "wallet_pin_created_at": now_iso(),
        }},
    )
    return {"ok": True, "wallet_pin_set": True}


@router.post("/wallet/pin/verify")
async def wallet_pin_verify(body: WalletPinVerify, user=Depends(get_current_user)):
    """Verification endpoint for future wallet-sensitive actions."""
    pin = _validate_wallet_pin(body.pin)
    full = await db.users.find_one({"id": user["id"]})
    if not full or not full.get("wallet_pin_hash"):
        raise HTTPException(400, "Wallet PIN is not set")
    if not check_pw(pin, full["wallet_pin_hash"]):
        raise HTTPException(401, "Incorrect Wallet PIN")
    return {"ok": True}


@router.get("/wallet")
async def wallet(user=Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "wallet_balance": 1})
    txns = await db.wallet_txns.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"balance": round(u.get("wallet_balance", 0.0), 2), "transactions": txns}


@router.post("/wallet/recharge")
async def recharge(body: WalletRecharge, user=Depends(get_current_user)):
    if not ALLOW_MOCK_RECHARGE:
        raise HTTPException(
            403,
            "Mock wallet recharge is disabled. Recharge must go through a verified payment (set ALLOW_MOCK_RECHARGE=true only in dev/test).",
        )
    if user.get("role") == "employee":
        raise HTTPException(
            403,
            "Employees don't recharge personal wallets — your bills are billed to the company wallet. Ask your admin to recharge.",
        )
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if body.amount > 10000:
        raise HTTPException(400, "Max recharge per txn is ₹10,000")
    # Atomic increment avoids lost updates under concurrent recharges.
    res = await db.users.find_one_and_update(
        {"id": user["id"]},
        {"$inc": {"wallet_balance": body.amount}},
        return_document=True,
    )
    new_bal = round((res or {}).get("wallet_balance", 0.0), 2)
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "type": "credit",
        "amount": body.amount, "reason": "Wallet recharge (mock)", "created_at": now_iso()
    })
    return {"balance": new_bal}
