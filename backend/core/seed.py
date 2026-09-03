"""Seed default platform data — Super Admin account."""
import os
import uuid

from core.db import db
from core.security import hash_pw, now_iso


SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "ujjwal@bill4pe.com").lower()
SUPER_ADMIN_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "Bill4Pe@2026")
SUPER_ADMIN_NAME = os.environ.get("SUPER_ADMIN_NAME", "Ujjwal (Founder)")


async def seed_super_admin():
    """Idempotent: create or upgrade the configured super-admin account."""
    existing = await db.users.find_one({"email": SUPER_ADMIN_EMAIL})
    if existing:
        # Always ensure the flag is set and the password matches the configured one.
        await db.users.update_one(
            {"email": SUPER_ADMIN_EMAIL},
            {"$set": {
                "is_super_admin": True,
                "role": "superadmin",
                "password": hash_pw(SUPER_ADMIN_PASSWORD),
                "is_active": True,
            }}
        )
        return existing["id"]
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid,
        "email": SUPER_ADMIN_EMAIL,
        "name": SUPER_ADMIN_NAME,
        "password": hash_pw(SUPER_ADMIN_PASSWORD),
        "is_super_admin": True,
        "role": "superadmin",
        "user_type": "platform",
        "wallet_balance": 0.0,
        "is_active": True,
        "created_at": now_iso(),
    })
    return uid
