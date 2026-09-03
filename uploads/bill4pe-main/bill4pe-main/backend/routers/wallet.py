"""Wallet — balance, recharge (mock, env-gated), transactions list."""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException

from core.db import db
from core.models import WalletRecharge
from core.security import get_current_user, now_iso

router = APIRouter(tags=["wallet"])

# Mock recharge mints wallet balance with NO payment proof. It must never be
# reachable on a hardened/production build — enable only when explicitly opted in.
ALLOW_MOCK_RECHARGE = os.environ.get("ALLOW_MOCK_RECHARGE", "false").strip().lower() == "true"


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
