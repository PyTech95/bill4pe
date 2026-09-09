"""RazorpayX Payouts adapter — Contacts, Fund Accounts (UPI/VPA), Payouts.

Isolates ALL RazorpayX REST details behind small, testable functions. RazorpayX
reuses the SAME Razorpay key id/secret via HTTP Basic auth. Payout creation is
IDEMPOTENT via the `X-Payout-Idempotency` header so a retry with the same key
can never create a second payout.

Nothing here is ever called from the browser — payouts originate only from the
BILL4PE backend (see spec §32 static-IP allowlisting).
"""
import hashlib
import hmac
import os

import httpx

from core.config import (
    RAZORPAYX_ACCOUNT_NUMBER,
    RAZORPAYX_WEBHOOK_SECRET,
    logger,
)

API_BASE = "https://api.razorpay.com/v1"
KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "").strip()
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def enabled() -> bool:
    """RazorpayX is usable only with keys AND a source account number."""
    return bool(KEY_ID and KEY_SECRET and RAZORPAYX_ACCOUNT_NUMBER)


def webhook_configured() -> bool:
    return bool(RAZORPAYX_WEBHOOK_SECRET)


def validate_config() -> None:
    if not (KEY_ID and KEY_SECRET):
        logger.warning("RazorpayX NOT configured (no Razorpay keys). Merchant payouts disabled; payments still bill and payouts queue as not_configured.")
        return
    if not RAZORPAYX_ACCOUNT_NUMBER:
        logger.warning("RAZORPAYX_ACCOUNT_NUMBER missing — payout source account unknown. Payouts disabled.")
        return
    if not webhook_configured():
        logger.warning("RAZORPAYX_WEBHOOK_SECRET not set — payout webhook safety-net disabled.")
    logger.info("RazorpayX configured (account=%s..., webhook=%s)", RAZORPAYX_ACCOUNT_NUMBER[:6], webhook_configured())


def _auth():
    return (KEY_ID, KEY_SECRET)


async def _post(path: str, payload: dict, idempotency_key: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if idempotency_key:
        headers["X-Payout-Idempotency"] = idempotency_key
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(f"{API_BASE}{path}", json=payload, auth=_auth(), headers=headers)
    if r.status_code >= 400:
        raise RuntimeError(f"razorpayx {path} {r.status_code}: {r.text[:300]}")
    return r.json()


async def _get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{API_BASE}{path}", auth=_auth())
    if r.status_code >= 400:
        raise RuntimeError(f"razorpayx GET {path} {r.status_code}: {r.text[:300]}")
    return r.json()


# ---------------- Contacts ----------------
async def create_contact(name: str, reference_id: str, upi: str) -> dict:
    """Create a vendor contact. Name falls back to a neutral safe value."""
    safe_name = (name or "").strip()[:50] or f"UPI {upi}"
    return await _post("/contacts", {
        "name": safe_name,
        "type": "vendor",
        "reference_id": reference_id[:40],
        "notes": {"upi": upi},
    })


# ---------------- Fund accounts (UPI / VPA) ----------------
async def create_vpa_fund_account(contact_id: str, upi: str) -> dict:
    return await _post("/fund_accounts", {
        "contact_id": contact_id,
        "account_type": "vpa",
        "vpa": {"address": upi},
    })


# ---------------- Payouts ----------------
async def create_payout(*, fund_account_id: str, amount_paise: int, reference_id: str,
                        idempotency_key: str, narration: str = "BILL4PE Payout") -> dict:
    """Create a UPI payout from the RazorpayX account. Idempotent by header.

    queue_if_low_balance=True → provider queues instead of failing when the
    payout balance is short (spec §33). Customer is NEVER asked to pay again.
    """
    if not enabled():
        raise RuntimeError("RazorpayX not configured")
    payload = {
        "account_number": RAZORPAYX_ACCOUNT_NUMBER,
        "fund_account_id": fund_account_id,
        "amount": int(amount_paise),
        "currency": "INR",
        "mode": "UPI",
        "purpose": "payout",
        "queue_if_low_balance": True,
        "reference_id": reference_id[:40],
        "narration": narration[:30],
    }
    return await _post("/payouts", payload, idempotency_key=idempotency_key)


async def fetch_payout(payout_id: str) -> dict:
    return await _get(f"/payouts/{payout_id}")


# ---------------- Webhook signature (raw-body HMAC-SHA256) ----------------
def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    if not (RAZORPAYX_WEBHOOK_SECRET and signature):
        return False
    body = raw_body if isinstance(raw_body, (bytes, bytearray)) else str(raw_body).encode()
    expected = hmac.new(RAZORPAYX_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
