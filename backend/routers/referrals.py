"""Referral program endpoints — list, validate."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from core.config import REFERRAL_BONUS
from core.db import db
from core.security import get_current_user
from services.referrals import ensure_referral_code

router = APIRouter(tags=["referrals"])


@router.get("/referrals/me")
async def referrals_me(user=Depends(get_current_user)):
    code = await ensure_referral_code(user["id"])
    refs = await db.referrals.find(
        {"referrer_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    items: List[dict] = []
    for r in refs:
        ref_user = await db.users.find_one(
            {"id": r["referee_id"]}, {"_id": 0, "name": 1, "created_at": 1}
        )
        items.append({
            "id": r["id"],
            "referee_name": (ref_user or {}).get("name", "Friend"),
            "bonus": float(r.get("bonus_each", REFERRAL_BONUS)),
            "joined_at": r.get("created_at"),
        })
    earnings = round(sum(i["bonus"] for i in items), 2)
    return {
        "code": code,
        "bonus_per_referral": REFERRAL_BONUS,
        "total_referrals": len(items),
        "total_earnings": earnings,
        "referrals": items,
    }


@router.get("/referrals/validate/{code}")
async def referrals_validate(code: str):
    code = (code or "").strip().upper()
    if not code:
        raise HTTPException(400, "Empty code")
    ref = await db.users.find_one({"referral_code": code}, {"_id": 0, "name": 1})
    if not ref:
        raise HTTPException(404, "Invalid code")
    return {"valid": True, "referrer_name": ref.get("name", "A friend"), "bonus": REFERRAL_BONUS}
