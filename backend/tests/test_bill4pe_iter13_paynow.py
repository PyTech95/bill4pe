"""Iteration 13: PayNow test-mode warning + bill generate wallet/razorpay fee paths."""
import hmac
import hashlib
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as _f:
        for line in _f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"
RZP_SECRET = "DREvdsZu402J05gcPRW7UYkD"
OWNER_EMAIL = "testowner@bill4pe.com"
OWNER_PWD = "Test@1234"


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PWD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


def _create_expense(headers, total=100.0):
    payload = {
        "category": "food",
        "sub_category": "lunch",
        "items": [{"name": f"TEST_item_{uuid.uuid4().hex[:6]}", "quantity": 1, "unit_price": total}],
        "notes": "TEST_iter13",
        "payment": {"amount": total, "merchant_name": "TEST Cafe", "merchant_upi": "cafe@okhdfcbank", "method": "upi", "transaction_id": f"TEST_{uuid.uuid4().hex[:8]}"},
    }
    r = requests.post(f"{API}/expenses", json=payload, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


# ---- payments/config ----
def test_payments_config_returns_test_mode(headers):
    r = requests.get(f"{API}/payments/config", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is True
    assert data["mode"] == "test"
    assert isinstance(data["key_id"], str) and data["key_id"].startswith("rzp_test_")


# ---- wallet path ----
def test_bill_generate_wallet_path_deducts_fee(headers):
    # Ensure sufficient wallet - check first
    w0 = requests.get(f"{API}/wallet", headers=headers).json()
    bal_before = float(w0.get("balance", 0.0))
    if bal_before < 5:
        pytest.skip(f"Owner wallet too low ({bal_before}) to test wallet path")

    exp = _create_expense(headers, total=100.0)
    eid = exp["id"]
    r = requests.post(f"{API}/bills/{eid}/generate", json={}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("fee_paid_via") == "wallet"
    assert body.get("bill_id", "").startswith("B4P-")
    fee = float(body["fee"])

    w1 = requests.get(f"{API}/wallet", headers=headers).json()
    bal_after = float(w1["balance"])
    assert round(bal_before - bal_after, 2) == round(fee, 2), (bal_before, bal_after, fee)


# ---- razorpay fee path ----
def test_bill_generate_razorpay_fee_path_no_wallet_debit(headers):
    exp = _create_expense(headers, total=250.0)
    eid = exp["id"]

    # Create fee order
    r = requests.post(f"{API}/payments/razorpay/order",
                      json={"amount": 5, "purpose": "bill_fee"}, headers=headers)
    assert r.status_code == 200, r.text
    order_id = r.json()["order_id"]

    # Compute valid HMAC signature
    payment_id = "pay_TEST"
    msg = f"{order_id}|{payment_id}".encode()
    signature = hmac.new(RZP_SECRET.encode(), msg, hashlib.sha256).hexdigest()

    # Wallet balance before
    w0 = float(requests.get(f"{API}/wallet", headers=headers).json()["balance"])

    r = requests.post(f"{API}/bills/{eid}/generate",
                      json={"razorpay_order_id": order_id,
                            "razorpay_payment_id": payment_id,
                            "razorpay_signature": signature},
                      headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("fee_paid_via") == "razorpay"

    w1 = float(requests.get(f"{API}/wallet", headers=headers).json()["balance"])
    assert w0 == w1, f"wallet changed: {w0} -> {w1}"


def test_bill_generate_bad_signature_rejected(headers):
    exp = _create_expense(headers, total=150.0)
    eid = exp["id"]
    r = requests.post(f"{API}/payments/razorpay/order",
                      json={"amount": 5, "purpose": "bill_fee"}, headers=headers)
    assert r.status_code == 200
    order_id = r.json()["order_id"]

    r = requests.post(f"{API}/bills/{eid}/generate",
                      json={"razorpay_order_id": order_id,
                            "razorpay_payment_id": "pay_TEST",
                            "razorpay_signature": "0" * 64},
                      headers=headers)
    assert r.status_code == 400, r.text
