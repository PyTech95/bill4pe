"""Runtime application settings managed by the Super Admin.

Secrets are never returned by the public settings endpoint. Environment values
remain the fallback so existing deployments keep working after this upgrade.
"""
import os

from core.db import db
from core.security import now_iso

_env_otp_mode = os.environ.get("OTP_MODE", "demo").strip().lower()
if _env_otp_mode in ("live", "prod"):
    _env_otp_mode = "production"
elif _env_otp_mode in ("demo", "dev", "test"):
    _env_otp_mode = "development"

DEFAULTS = {
    "otp_mode": _env_otp_mode,
    "otp_provider": os.environ.get("OTP_PROVIDER", "msg91").strip().lower(),
    "otp_api_key": os.environ.get("MSG91_AUTH_KEY", "").strip(),
    "otp_expiry_minutes": int(os.environ.get("OTP_EXPIRY_MINUTES", "5") or 5),
    "otp_resend_seconds": int(os.environ.get("OTP_RESEND_SECONDS", "60") or 60),
    "otp_max_requests": int(os.environ.get("OTP_MAX_REQUESTS", "5") or 5),
    "otp_lock_minutes": int(os.environ.get("OTP_LOCK_MINUTES", "15") or 15),
    "welcome_bonus": float(os.environ.get("WELCOME_BONUS", "50") or 50),
}


async def get_runtime_settings() -> dict:
    doc = await db.app_settings.find_one({"_id": "runtime"}, {"_id": 0}) or {}
    settings = {**DEFAULTS, **doc}
    # Backwards compatibility for deployments that previously stored/used
    # OTP_MODE=live|demo before Super Admin runtime settings were introduced.
    mode = str(settings.get("otp_mode", "development")).lower()
    settings["otp_mode"] = "production" if mode in ("live", "prod", "production") else "development"
    return settings


async def update_runtime_settings(patch: dict) -> dict:
    clean = {k: v for k, v in patch.items() if v is not None and k in DEFAULTS}
    clean["updated_at"] = now_iso()
    await db.app_settings.update_one({"_id": "runtime"}, {"$set": clean}, upsert=True)
    return await get_runtime_settings()


def public_settings(settings: dict) -> dict:
    return {
        "otp_mode": settings["otp_mode"],
        "otp_provider": settings["otp_provider"],
        "otp_expiry_minutes": settings["otp_expiry_minutes"],
        "otp_resend_seconds": settings["otp_resend_seconds"],
        "otp_max_requests": settings["otp_max_requests"],
        "otp_lock_minutes": settings["otp_lock_minutes"],
        "welcome_bonus": settings["welcome_bonus"],
        "otp_api_key_configured": bool(settings.get("otp_api_key")),
    }
