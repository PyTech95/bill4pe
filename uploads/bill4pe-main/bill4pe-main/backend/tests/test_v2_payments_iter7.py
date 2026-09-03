"""Backend integration tests for v2 collect-and-payout money flow (iter 7).

Covers: fee-preview math, payments/config, admin platform-fee, outbound-ip,
admin payments list + alerts, graceful degradation (no Razorpay keys),
and auth-required endpoints.
"""
import os
import time
import uuid

import pytest
import requests

def _load_frontend_env():
    env_path = "/app/frontend/.env"
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("REACT_APP_BACKEND_URL")

BASE_URL = (_load_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"

SUPER_EMAIL = "ujjwal@bill4pe.com"
SUPER_PASS = "Bill4Pe@2026"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def super_token():
    r = requests.post(f"{API}/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PASS}, timeout=15)
    assert r.status_code == 200, f"super admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    email = f"test_v2_{uuid.uuid4().hex[:8]}@bill4pe.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test@1234", "name": "Iter7 User"}, timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return r.json()["token"]


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- Fee math ----------------
@pytest.mark.parametrize("amt,fee,total", [(200, 20, 220), (100, 10, 110), (500, 50, 550)])
def test_fee_preview_math(user_token, amt, fee, total):
    r = requests.get(f"{API}/payments/fee-preview", params={"merchant_amount": amt}, headers=auth(user_token), timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["merchant_amount"] == amt
    assert d["platform_fee"] == fee
    assert d["customer_total"] == total
    assert d["merchant_amount_paise"] == amt * 100
    assert d["platform_fee_paise"] == fee * 100
    assert d["customer_total_paise"] == total * 100


def test_fee_preview_requires_auth():
    r = requests.get(f"{API}/payments/fee-preview", params={"merchant_amount": 200}, timeout=10)
    assert r.status_code in (401, 403)


# ---------------- Payments config ----------------
def test_payments_config_graceful():
    r = requests.get(f"{API}/payments/config", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["provider"] == "razorpay"
    assert d["enabled"] is False
    assert d["payout_enabled"] is False
    # accept "10", 10, or 10.0
    assert str(d["platform_fee_percent"]).startswith("10")


# ---------------- Admin platform fee ----------------
def test_admin_platform_fee_get_update(super_token):
    r = requests.get(f"{API}/admin/settings/platform-fee", headers=auth(super_token), timeout=10)
    assert r.status_code == 200, r.text
    original = r.json()["percent"]

    r2 = requests.post(f"{API}/admin/settings/platform-fee", json={"percent": 12}, headers=auth(super_token), timeout=10)
    assert r2.status_code == 200, r2.text
    assert str(r2.json()["percent"]).startswith("12")

    # verify via preview: 200 -> fee 24
    p = requests.get(f"{API}/payments/fee-preview", params={"merchant_amount": 200}, headers=auth(super_token), timeout=10).json()
    assert p["platform_fee"] == 24

    # revert
    r3 = requests.post(f"{API}/admin/settings/platform-fee", json={"percent": 10}, headers=auth(super_token), timeout=10)
    assert r3.status_code == 200
    assert str(r3.json()["percent"]).startswith("10")


def test_admin_platform_fee_requires_super(user_token):
    r = requests.get(f"{API}/admin/settings/platform-fee", headers=auth(user_token), timeout=10)
    assert r.status_code == 403


# ---------------- Outbound IP ----------------
def test_outbound_ip(super_token):
    r = requests.get(f"{API}/admin/system/outbound-ip", headers=auth(super_token), timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d.get("outbound_ip"), str) and len(d["outbound_ip"]) >= 7


def test_outbound_ip_requires_super(user_token):
    r = requests.get(f"{API}/admin/system/outbound-ip", headers=auth(user_token), timeout=10)
    assert r.status_code == 403


# ---------------- Admin payments list ----------------
def test_admin_payments_list_alerts(super_token):
    r = requests.get(f"{API}/admin/payments", headers=auth(super_token), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "payments" in d and isinstance(d["payments"], list)
    a = d.get("alerts") or {}
    for k in ("bill_missing", "payout_failed", "payout_pending"):
        assert k in a, f"missing alert key {k}"


def test_admin_payments_requires_auth():
    r = requests.get(f"{API}/admin/payments", timeout=10)
    assert r.status_code in (401, 403)


def test_admin_payments_requires_super(user_token):
    r = requests.get(f"{API}/admin/payments", headers=auth(user_token), timeout=10)
    assert r.status_code == 403


# ---------------- Graceful degradation (no Razorpay keys) ----------------
def test_create_merchant_order_no_keys(user_token):
    r = requests.post(
        f"{API}/payments/merchant/create-order",
        json={"payee_upi": "x@ybl", "merchant_amount": 200},
        headers=auth(user_token), timeout=15,
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    assert "razorpay" in r.text.lower() and "not configured" in r.text.lower()


def test_webhook_razorpay_payments_no_keys():
    r = requests.post(f"{API}/webhooks/razorpay/payments", json={}, timeout=10)
    assert r.status_code == 503


def test_webhook_razorpayx_payouts_no_keys():
    r = requests.post(f"{API}/webhooks/razorpayx/payouts", json={}, timeout=10)
    assert r.status_code == 503
