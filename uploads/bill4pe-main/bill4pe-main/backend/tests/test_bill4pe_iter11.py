"""Iteration 11 regression: AI, Razorpay (order/verify/history/webhook), Email invoice."""
import base64
import hashlib
import hmac
import io
import os
import struct
import zlib

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback: read frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

OWNER = {"email": "testowner@bill4pe.com", "password": "Test@1234"}
RAZORPAY_SECRET = "DREvdsZu402J05gcPRW7UYkD"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json=OWNER, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token in {r.json()}"
    return tok


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# tiny valid JPEG (1x1 white) - use PNG bytes actually since JPEG bytes are more complex; backend accepts image/jpeg mime
def _tiny_jpeg_bytes() -> bytes:
    # smallest valid JPEG ~ base64
    return base64.b64decode(
        "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q=="
    )


def _wav_silence_bytes(seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate a valid WAV with silence (Gemini may return empty transcript on pure silence)."""
    n_samples = int(seconds * sample_rate)
    data = b"\x00\x00" * n_samples
    # PCM WAV header
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + data


# ---------- Auth ----------
def test_login_returns_jwt():
    r = requests.post(f"{API}/auth/login", json=OWNER, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    tok = j.get("access_token") or j.get("token")
    assert tok and isinstance(tok, str) and len(tok) > 20


# ---------- AI ----------
def test_ai_scan_receipt(auth_headers):
    files = {"file": ("r.jpg", _tiny_jpeg_bytes(), "image/jpeg")}
    r = requests.post(f"{API}/ai/scan-receipt", headers=auth_headers, files=files, timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    # Structural assertions
    assert "merchant_name" in data
    assert "items" in data and isinstance(data["items"], list)
    assert "total" in data


def test_ai_suggest_items(auth_headers):
    r = requests.post(
        f"{API}/ai/suggest-items",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={"category": "food", "query": "ro"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "suggestions" in data and isinstance(data["suggestions"], list)
    assert len(data["suggestions"]) >= 1  # AI should return something for "ro"


def test_voice_expense_wav_silence(auth_headers):
    """Gemini may return empty/422 for pure silence; accept 422 as valid rejection or 200 with transcript field."""
    files = {"file": ("a.wav", _wav_silence_bytes(1.0), "audio/wav")}
    r = requests.post(f"{API}/voice/expense", headers=auth_headers, files=files, timeout=90)
    assert r.status_code in (200, 422), r.text
    if r.status_code == 200:
        data = r.json()
        assert "transcript" in data
        assert "category" in data


# ---------- Razorpay ----------
def test_payments_config(auth_headers):
    r = requests.get(f"{API}/payments/config", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("enabled") is True
    assert j.get("key_id")


@pytest.fixture
def wallet_order(auth_headers):
    r = requests.post(
        f"{API}/payments/razorpay/order",
        headers=auth_headers,
        json={"amount": 250, "purpose": "wallet_recharge"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("order_id", "").startswith("order_")
    assert j.get("amount") == 25000
    assert j.get("currency") == "INR"
    return j


def test_razorpay_order_created(wallet_order):
    assert wallet_order["amount"] == 25000


def _sign(order_id: str, payment_id: str) -> str:
    msg = f"{order_id}|{payment_id}".encode()
    return hmac.new(RAZORPAY_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def test_razorpay_verify_bad_signature(auth_headers, wallet_order):
    r = requests.post(
        f"{API}/payments/razorpay/verify",
        headers=auth_headers,
        json={
            "razorpay_order_id": wallet_order["order_id"],
            "razorpay_payment_id": "pay_TEST_bad",
            "razorpay_signature": "deadbeef" * 8,
            "purpose": "wallet_recharge",
        },
        timeout=15,
    )
    assert r.status_code == 400, r.text


def test_razorpay_verify_good_signature_credits_wallet(auth_headers):
    # get initial balance
    w0 = requests.get(f"{API}/wallet", headers=auth_headers, timeout=15).json()
    bal0 = float(w0.get("balance", 0))

    # create order
    r = requests.post(
        f"{API}/payments/razorpay/order",
        headers=auth_headers,
        json={"amount": 100, "purpose": "wallet_recharge"},
        timeout=30,
    )
    assert r.status_code == 200
    order = r.json()

    payment_id = "pay_TEST_" + os.urandom(6).hex()
    sig = _sign(order["order_id"], payment_id)

    v = requests.post(
        f"{API}/payments/razorpay/verify",
        headers=auth_headers,
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": payment_id,
            "razorpay_signature": sig,
            "purpose": "wallet_recharge",
        },
        timeout=15,
    )
    assert v.status_code == 200, v.text
    j = v.json()
    assert j.get("verified") is True
    assert "balance" in j
    assert round(float(j["balance"]) - bal0, 2) == 100.0

    # Re-verify same order should not double credit
    v2 = requests.post(
        f"{API}/payments/razorpay/verify",
        headers=auth_headers,
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": payment_id,
            "razorpay_signature": sig,
            "purpose": "wallet_recharge",
        },
        timeout=15,
    )
    assert v2.status_code == 200
    assert round(float(v2.json()["balance"]) - bal0, 2) == 100.0  # unchanged


def test_payments_history(auth_headers):
    r = requests.get(f"{API}/payments/history", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert "payments" in j and isinstance(j["payments"], list)
    if j["payments"]:
        p = j["payments"][0]
        assert "order_id" in p and "amount" in p and "purpose" in p and "status" in p


def test_razorpay_webhook_no_secret_returns_503():
    r = requests.post(
        f"{API}/payments/razorpay/webhook",
        headers={"X-Razorpay-Signature": "x"},
        data=b"{}",
        timeout=15,
    )
    # webhook secret is intentionally empty -> 503
    assert r.status_code == 503, r.text


# ---------- Email invoice ----------
def test_email_invoice_flow(auth_headers):
    # create an expense
    payload = {
        "category": "food",
        "sub_category": "TEST_iter11",
        "items": [{"name": "TEST_item", "quantity": 1, "unit_price": 50.0}],
        "payment": {
            "merchant_name": "TEST Merchant",
            "amount": 50.0,
            "payment_method": "UPI",
            "payment_status": "paid",
            "transaction_id": "TEST_TXN_iter11",
        },
    }
    r = requests.post(f"{API}/expenses", headers=auth_headers, json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    eid = r.json().get("id") or r.json().get("expense", {}).get("id")
    assert eid, r.text

    # Emailing non-generated bill should be 400
    r_bad = requests.post(
        f"{API}/bills/{eid}/email",
        headers=auth_headers,
        json={"recipient_email": "delivered@resend.dev"},
        timeout=30,
    )
    assert r_bad.status_code == 400, r_bad.text

    # generate bill
    r_gen = requests.post(f"{API}/bills/{eid}/generate", headers=auth_headers, timeout=30)
    assert r_gen.status_code == 200, r_gen.text

    # now email it
    r_email = requests.post(
        f"{API}/bills/{eid}/email",
        headers=auth_headers,
        json={
            "recipient_email": "delivered@resend.dev",
            "verify_url": "https://example.com/verify/X",
        },
        timeout=60,
    )
    assert r_email.status_code == 200, r_email.text
    j = r_email.json()
    assert j.get("ok") is True
    assert j.get("email_id")
