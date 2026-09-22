"""Phone OTP provider abstraction.

Development mode generates a short-lived random 4-digit OTP. Production mode
uses the Super Admin-managed API key for real delivery.
"""
from __future__ import annotations

import os
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import httpx

from core.config import logger
from core.db import db
from services.app_settings import get_runtime_settings

OTP_MODE = os.environ.get("OTP_MODE", "demo").strip().lower()
MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY", "").strip()
OTP_EXPIRY_MINUTES = int(os.environ.get("OTP_EXPIRY_MINUTES", "5") or 5)


async def is_demo() -> bool:
    return (await get_runtime_settings()).get("otp_mode") != "production"


def _mobile(phone10: str) -> str:
    return "91" + "".join(c for c in (phone10 or "") if c.isdigit())[-10:]


def _ensure_live_config(api_key: str) -> None:
    if not api_key:
        raise RuntimeError("Production OTP is not configured. Add the API key in Super Admin settings.")


def _otp_hash(phone10: str, otp: str) -> str:
    return hashlib.sha256(f"{phone10}:{otp}".encode()).hexdigest()


async def send_otp(phone10: str) -> dict:
    cfg = await get_runtime_settings()
    resend_seconds = max(10, min(3600, int(cfg.get("otp_resend_seconds", 60))))
    max_requests = max(1, min(20, int(cfg.get("otp_max_requests", 5))))
    lock_minutes = max(1, min(1440, int(cfg.get("otp_lock_minutes", 15))))
    now = datetime.now(timezone.utc)
    state = await db.otp_rate_limits.find_one({"phone": phone10}) or {}
    locked_until = state.get("locked_until")
    if locked_until:
        try:
            remaining = int((datetime.fromisoformat(locked_until) - now).total_seconds())
            if remaining > 0:
                raise RuntimeError(f"Too many OTP requests. Please try again in {max(1, remaining // 60 + 1)} minute(s).")
        except ValueError:
            pass
    last_sent = state.get("last_sent_at")
    if last_sent:
        try:
            remaining = resend_seconds - int((now - datetime.fromisoformat(last_sent)).total_seconds())
            if remaining > 0:
                raise RuntimeError(f"Please wait {remaining} seconds before requesting another OTP.")
        except ValueError:
            pass
    window_start = state.get("window_start")
    count = int(state.get("request_count", 0))
    if not window_start or (now - datetime.fromisoformat(window_start)).total_seconds() >= lock_minutes * 60:
        count = 0
        window_start = now.isoformat()
    count += 1
    update = {"phone": phone10, "request_count": count, "window_start": window_start, "last_sent_at": now.isoformat()}
    if count > max_requests:
        update["locked_until"] = (now + timedelta(minutes=lock_minutes)).isoformat()
        await db.otp_rate_limits.update_one({"phone": phone10}, {"$set": update}, upsert=True)
        raise RuntimeError(f"Too many OTP requests. Please try again after {lock_minutes} minute(s).")
    await db.otp_rate_limits.update_one({"phone": phone10}, {"$set": update, "$unset": {"locked_until": ""}}, upsert=True)

    if cfg.get("otp_mode") != "production":
        otp = f"{secrets.randbelow(10000):04d}"
        expires_at = (now + timedelta(minutes=int(cfg.get("otp_expiry_minutes", 5)))).isoformat()
        await db.development_otps.update_one(
            {"phone": phone10},
            {"$set": {"otp_hash": _otp_hash(phone10, otp), "expires_at": expires_at, "created_at": now.isoformat()}},
            upsert=True,
        )
        logger.info("Development OTP generated for +91%s", phone10)
        return {"ok": True, "mode": "development", "development_otp": otp,
                "otp_length": 4, "resend_seconds": resend_seconds}

    api_key = str(cfg.get("otp_api_key") or MSG91_AUTH_KEY).strip()
    _ensure_live_config(api_key)
    url = "https://control.msg91.com/api/v5/otp"
    params = {
        "mobile": _mobile(phone10),
        "authkey": api_key,
        "otp_length": 4,
        "otp_expiry": int(cfg.get("otp_expiry_minutes", OTP_EXPIRY_MINUTES)),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, params=params)
    try:
        data = resp.json()
    except Exception:
        data = {}
    if resp.status_code >= 400 or str(data.get("type", "")).lower() not in ("success", ""):
        logger.error("MSG91 send OTP failed status=%s response=%s", resp.status_code, str(data)[:300])
        raise RuntimeError("OTP could not be sent. Please try again.")
    return {"ok": True, "mode": "production", "otp_length": 4, "resend_seconds": resend_seconds}


async def verify_otp(phone10: str, otp: str) -> bool:
    cfg = await get_runtime_settings()
    if cfg.get("otp_mode") != "production":
        row = await db.development_otps.find_one({"phone": phone10}) or {}
        if not row.get("otp_hash") or not row.get("expires_at"):
            return False
        try:
            if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
                await db.development_otps.delete_one({"phone": phone10})
                return False
        except ValueError:
            return False
        valid = hmac.compare_digest(row["otp_hash"], _otp_hash(phone10, (otp or "").strip()))
        if valid:
            await db.development_otps.delete_one({"phone": phone10})
        return valid

    api_key = str(cfg.get("otp_api_key") or MSG91_AUTH_KEY).strip()
    _ensure_live_config(api_key)
    url = "https://control.msg91.com/api/v5/otp/verify"
    params = {"otp": (otp or "").strip(), "mobile": _mobile(phone10)}
    headers = {"authkey": api_key}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params, headers=headers)
    try:
        data = resp.json()
    except Exception:
        data = {}
    text = (str(data.get("message", "")) + " " + str(data.get("type", ""))).lower()
    return resp.status_code < 400 and ("verified" in text or "success" in text) and "invalid" not in text and "expired" not in text
