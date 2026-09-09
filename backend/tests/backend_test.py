"""Targeted regression tests for Razorpay LIVE configuration and safe merchant order creation.

Safety: these tests create an order only. They never submit payment details or complete a payment.
"""
import os
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


def _credentials():
    """Use the documented QA account without embedding production/admin credentials."""
    path = Path("/app/memory/test_credentials.md")
    if not path.exists():
        pytest.skip("Missing /app/memory/test_credentials.md")
    content = path.read_text(encoding="utf-8")
    email = "qa.iter2.1787052341@gmail.com"
    password = "TestPass123!"
    if email not in content:
        pytest.skip("Documented QA account is unavailable")
    return email, password


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def authenticated_client(api_client):
    email, password = _credentials()
    response = api_client.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if response.status_code != 200:
        pytest.fail(f"Authentication failed: {response.status_code} {response.text[:300]}")
    data = response.json()
    assert isinstance(data.get("token"), str) and data["token"]
    client = requests.Session()
    client.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {data['token']}",
    })
    return client


class TestRazorpayMerchantPayment:
    """LIVE config and safe order-only merchant-payment API behavior."""

    def test_config_is_enabled_live(self, api_client):
        response = api_client.get(f"{API}/payments/config", timeout=30)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["provider"] == "razorpay"
        assert data["enabled"] is True
        assert data["mode"] == "live"
        assert isinstance(data["key_id"], str)
        assert data["key_id"].startswith("rzp_live_")

    def test_order_requires_authentication(self, api_client):
        response = api_client.post(
            f"{API}/payments/razorpay/order",
            json={"amount": 250, "purpose": "merchant_payment"},
            timeout=30,
        )
        assert response.status_code in (401, 403), response.text
        data = response.json()
        assert isinstance(data.get("detail"), str) and data["detail"]

    def test_invalid_merchant_order_amount_is_rejected(self, authenticated_client):
        response = authenticated_client.post(
            f"{API}/payments/razorpay/order",
            json={"amount": 0, "purpose": "merchant_payment"},
            timeout=30,
        )
        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "Amount must be positive"

    def test_invalid_order_purpose_is_rejected(self, authenticated_client):
        response = authenticated_client.post(
            f"{API}/payments/razorpay/order",
            json={"amount": 250, "purpose": "unsupported"},
            timeout=30,
        )
        assert response.status_code == 422, response.text
        detail = response.json().get("detail")
        assert isinstance(detail, list) and detail

    def test_create_merchant_payment_order_exact_amount(self, authenticated_client):
        # Safe operation: creates a Razorpay order but does not authorize/capture any payment.
        response = authenticated_client.post(
            f"{API}/payments/razorpay/order",
            json={"amount": 250, "purpose": "merchant_payment"},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data.get("order_id"), str) and data["order_id"].startswith("order_")
        assert data["amount"] == 25000
        assert data["currency"] == "INR"
        assert isinstance(data.get("key_id"), str) and data["key_id"].startswith("rzp_live_")

        history = authenticated_client.get(f"{API}/payments/history", timeout=30)
        assert history.status_code == 200, history.text
        rows = history.json().get("payments")
        assert isinstance(rows, list)
        created = next((row for row in rows if row.get("order_id") == data["order_id"]), None)
        assert created is not None
        assert created["purpose"] == "merchant_payment"
        assert created["amount"] == 250
        assert created["status"] == "created"
        assert created["credited"] is False
        assert "_id" not in created
