"""Production phone OTP provider abstraction.

Set OTP_MODE=live with MSG91_AUTH_KEY and MSG91_TEMPLATE_ID for real SMS OTP.
OTP_MODE=demo is intended only for local/staging testing.
"""
from __future__ import annotations

import os
import httpx

from core.config import DEMO_OTP, logger

OTP_MODE = os.environ.get("OTP_MODE", "demo").strip().lower()
MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY", "").strip()
MSG91_TEMPLATE_ID = os.environ.get("MSG91_TEMPLATE_ID", "").strip()
OTP_EXPIRY_MINUTES = int(os.environ.get("OTP_EXPIRY_MINUTES", "5") or 5)


def is_demo() -> bool:
    return OTP_MODE != "live"


def _mobile(phone10: str) -> str:
    return "91" + "".join(c for c in (phone10 or "") if c.isdigit())[-10:]


def _ensure_live_config() -> None:
    if not MSG91_AUTH_KEY or not MSG91_TEMPLATE_ID:
        raise RuntimeError("Live OTP is not configured. Set MSG91_AUTH_KEY and MSG91_TEMPLATE_ID.")


async def send_otp(phone10: str) -> dict:
    if is_demo():
        logger.warning("OTP_MODE=demo: using development OTP for +91%s", phone10)
        return {"ok": True, "mode": "demo", "demo_hint": f"Use OTP {DEMO_OTP} (development mode)"}

    _ensure_live_config()
    url = "https://control.msg91.com/api/v5/otp"
    params = {
        "template_id": MSG91_TEMPLATE_ID,
        "mobile": _mobile(phone10),
        "authkey": MSG91_AUTH_KEY,
        "otp_length": 6,
        "otp_expiry": OTP_EXPIRY_MINUTES,
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
    return {"ok": True, "mode": "live"}


async def verify_otp(phone10: str, otp: str) -> bool:
    if is_demo():
        return (otp or "").strip() == DEMO_OTP

    _ensure_live_config()
    url = "https://control.msg91.com/api/v5/otp/verify"
    params = {"otp": (otp or "").strip(), "mobile": _mobile(phone10)}
    headers = {"authkey": MSG91_AUTH_KEY}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params, headers=headers)
    try:
        data = resp.json()
    except Exception:
        data = {}
    text = (str(data.get("message", "")) + " " + str(data.get("type", ""))).lower()
    return resp.status_code < 400 and ("verified" in text or "success" in text) and "invalid" not in text and "expired" not in text
