"""Razorpay provider adapter.

Isolates ALL Razorpay SDK / crypto details behind small, testable functions.
Signature verification is implemented with Razorpay's exact documented HMAC-SHA256
algorithm directly (no network, deterministic) so the recovery guarantees can be
validated without touching the live API or moving real money.
"""
import hashlib
import hmac
import os

import razorpay

from core.config import RAZORPAY_PAYMENT_WEBHOOK_SECRET, logger

KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "").strip()
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
RAZORPAY_ENV = os.environ.get("RAZORPAY_ENV", "test").strip().lower()
ROUTE_ENABLED = os.environ.get("RAZORPAY_ROUTE_ENABLED", "false").strip().lower() == "true"

_client = razorpay.Client(auth=(KEY_ID, KEY_SECRET)) if (KEY_ID and KEY_SECRET) else None


def enabled() -> bool:
    return _client is not None


def webhook_configured() -> bool:
    return bool(WEBHOOK_SECRET)


def mode() -> str | None:
    if not KEY_ID:
        return None
    return "test" if KEY_ID.startswith("rzp_test_") else "live"


def key_id() -> str:
    return KEY_ID


def validate_config() -> None:
    """Loud startup validation — never silently mix test/live credentials."""
    if not enabled():
        logger.warning("Razorpay NOT configured (RAZORPAY_KEY_ID / SECRET missing). Payment collection disabled; app degrades gracefully.")
        return
    detected = mode()
    if detected == "live" and RAZORPAY_ENV != "live":
        logger.warning(
            "SECURITY: a LIVE Razorpay key (rzp_live_) is configured but RAZORPAY_ENV=%s. "
            "Real payments will move REAL money. Set RAZORPAY_ENV=live only in production.",
            RAZORPAY_ENV,
        )
    if detected == "test" and RAZORPAY_ENV == "live":
        logger.warning("CONFIG: RAZORPAY_ENV=live but a TEST key is configured — live payments will fail.")
    if not webhook_configured():
        logger.warning("RAZORPAY_WEBHOOK_SECRET not set — the webhook safety-net is disabled until you configure it.")
    logger.info("Razorpay configured (mode=%s, env=%s, route=%s)", detected, RAZORPAY_ENV, ROUTE_ENABLED)


# ---------------- Orders ----------------
def create_order(amount_paise: int, receipt: str, notes: dict | None = None, transfers: list | None = None) -> dict:
    if not _client:
        raise RuntimeError("Razorpay not configured")
    payload = {
        "amount": int(amount_paise),
        "currency": "INR",
        "payment_capture": 1,
        "receipt": receipt[:40],  # Razorpay hard limit
    }
    if notes:
        payload["notes"] = notes
    if transfers:  # Route: split at order time
        payload["transfers"] = transfers
    return _client.order.create(payload)


def fetch_payment(payment_id: str) -> dict:
    if not _client:
        raise RuntimeError("Razorpay not configured")
    return _client.payment.fetch(payment_id)


def fetch_order_payments(order_id: str) -> list:
    if not _client:
        raise RuntimeError("Razorpay not configured")
    resp = _client.order.payments(order_id)
    return resp.get("items", []) if isinstance(resp, dict) else []


def create_transfer(payment_id: str, transfers: list) -> dict:
    """Razorpay Route: split a captured payment to linked accounts."""
    if not _client:
        raise RuntimeError("Razorpay not configured")
    return _client.payment.transfer(payment_id, {"transfers": transfers})


# ---------------- Signature verification (local HMAC, no network) ----------------
def verify_checkout_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """HMAC_SHA256(key_secret, "<order_id>|<payment_id>") == signature."""
    if not (KEY_SECRET and order_id and payment_id and signature):
        return False
    expected = hmac.new(
        KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """HMAC_SHA256(webhook_secret, RAW_BODY) == X-Razorpay-Signature.

    The RAW request bytes must be used — never a re-serialized JSON.
    """
    if not (WEBHOOK_SECRET and signature):
        return False
    body = raw_body if isinstance(raw_body, (bytes, bytearray)) else str(raw_body).encode()
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def compute_checkout_signature(order_id: str, payment_id: str) -> str:
    """Test/utility helper — produce the signature Razorpay would send."""
    return hmac.new(KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


# ---------------- Dedicated payment webhook (v2 endpoint) ----------------
def payment_webhook_configured() -> bool:
    return bool(RAZORPAY_PAYMENT_WEBHOOK_SECRET)


def verify_payment_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """HMAC_SHA256(RAZORPAY_PAYMENT_WEBHOOK_SECRET, RAW_BODY) == signature."""
    if not (RAZORPAY_PAYMENT_WEBHOOK_SECRET and signature):
        return False
    body = raw_body if isinstance(raw_body, (bytes, bytearray)) else str(raw_body).encode()
    expected = hmac.new(RAZORPAY_PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
