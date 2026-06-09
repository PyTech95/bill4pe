"""Referral program helpers — code generation, validation, dual-credit logic."""
from fastapi import HTTPException
from typing import Optional
import secrets
import uuid

from core.config import REFERRAL_BONUS
from core.db import db
from core.security import now_iso


_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/1/I/O


def gen_referral_code() -> str:
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))


async def ensure_referral_code(uid: str) -> str:
    user = await db.users.find_one({"id": uid}, {"_id": 0, "referral_code": 1})
    code = (user or {}).get("referral_code")
    if code:
        return code
    # Generate a unique code
    for _ in range(20):
        candidate = gen_referral_code()
        exists = await db.users.find_one({"referral_code": candidate}, {"_id": 1})
        if not exists:
            await db.users.update_one({"id": uid}, {"$set": {"referral_code": candidate}})
            return candidate
    raise HTTPException(500, "Could not generate referral code")


async def apply_referral(new_user_id: str, referrer_code: Optional[str]) -> Optional[str]:
    """If referrer_code is valid and isn't self, credit ₹50 to both users.
    Returns referrer name or None."""
    if not referrer_code:
        return None
    code = referrer_code.strip().upper()
    if not code:
        return None
    referrer = await db.users.find_one({"referral_code": code})
    if not referrer or referrer["id"] == new_user_id:
        return None
    # Check this user hasn't already been credited
    existing = await db.referrals.find_one({"referee_id": new_user_id})
    if existing:
        return None
    # Credit both
    now = now_iso()
    rid = str(uuid.uuid4())
    await db.referrals.insert_one({
        "id": rid,
        "referrer_id": referrer["id"],
        "referee_id": new_user_id,
        "bonus_each": REFERRAL_BONUS,
        "created_at": now,
    })
    # Referrer
    await db.users.update_one(
        {"id": referrer["id"]},
        {"$inc": {"wallet_balance": REFERRAL_BONUS}},
    )
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": referrer["id"], "type": "credit",
        "amount": REFERRAL_BONUS, "reason": "Referral bonus (friend joined)",
        "created_at": now,
    })
    # Referee
    await db.users.update_one(
        {"id": new_user_id},
        {"$inc": {"wallet_balance": REFERRAL_BONUS}},
    )
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": new_user_id, "type": "credit",
        "amount": REFERRAL_BONUS, "reason": f"Welcome referral bonus (invited by {referrer.get('name','a friend')})",
        "created_at": now,
    })
    return referrer.get("name")
