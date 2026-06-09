"""Wallet — balance, recharge (mocked), transactions list."""
import uuid
from fastapi import APIRouter, Depends, HTTPException

from core.db import db
from core.models import WalletRecharge
from core.security import get_current_user, now_iso

router = APIRouter(tags=["wallet"])


@router.get("/wallet")
async def wallet(user=Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "wallet_balance": 1})
    txns = await db.wallet_txns.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"balance": round(u.get("wallet_balance", 0.0), 2), "transactions": txns}


@router.post("/wallet/recharge")
async def recharge(body: WalletRecharge, user=Depends(get_current_user)):
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if body.amount > 10000:
        raise HTTPException(400, "Max recharge per txn is ₹10,000")
    new_bal = round(user.get("wallet_balance", 0.0) + body.amount, 2)
    await db.users.update_one({"id": user["id"]}, {"$set": {"wallet_balance": new_bal}})
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "type": "credit",
        "amount": body.amount, "reason": "Wallet recharge (mock)", "created_at": now_iso()
    })
    return {"balance": new_bal}
