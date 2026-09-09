"""Bill4Pe deployment-readiness backend regression tests (iter 4).

Covers: health, providers, auth (register/login/me), critical billing path
(create expense -> generate bill -> download PDF -> wallet debit), wallet
endpoints, security gates (401 on unauthenticated), Razorpay graceful degrade,
super admin login + stats.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback: read frontend/.env directly
    from pathlib import Path
    envp = Path("/app/frontend/.env")
    for line in envp.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
            break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

SUPER_EMAIL = "ujjwal@bill4pe.com"
SUPER_PW = "Bill4Pe@2026"


# ---------------- Fixtures ----------------

@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def new_user(client):
    email = f"test_deploy_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(f"{API}/auth/register", json={
        "email": email, "password": "Test@1234", "name": "Deploy Tester",
    })
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    return {"email": email, "password": "Test@1234", "token": data["token"], "user": data["user"]}


@pytest.fixture(scope="module")
def user_client(client, new_user):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json",
                      "Authorization": f"Bearer {new_user['token']}"})
    return s


@pytest.fixture(scope="module")
def super_token(client):
    r = client.post(f"{API}/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PW})
    assert r.status_code == 200, f"super admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


# ---------------- Health & providers ----------------

def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_health_providers(client):
    r = client.get(f"{API}/health/providers")
    assert r.status_code == 200
    j = r.json()
    # Payments must be marked not configured
    assert j["payments"]["razorpay_configured"] is False
    # AI: gemini should be available via emergent fallback
    assert j["ai"]["fallback_emergent_llm"] is True or j["ai"]["using_own_keys"]["gemini"] is True


# ---------------- Payments graceful degrade ----------------

def test_payments_config_disabled(client):
    r = client.get(f"{API}/payments/config")
    assert r.status_code == 200
    j = r.json()
    assert j["enabled"] is False
    assert j["mode"] is None


def test_razorpay_order_returns_503(user_client):
    r = user_client.post(f"{API}/payments/razorpay/order",
                         json={"amount": 100, "purpose": "wallet_recharge"})
    assert r.status_code == 503
    assert "not configured" in r.text.lower()


# ---------------- Auth ----------------

def test_register_gives_welcome_bonus(new_user):
    assert new_user["user"]["wallet_balance"] == 50.0
    assert new_user["token"]


def test_login_ok(client, new_user):
    r = client.post(f"{API}/auth/login",
                    json={"email": new_user["email"], "password": new_user["password"]})
    assert r.status_code == 200
    assert "token" in r.json()


def test_login_bad_password(client, new_user):
    r = client.post(f"{API}/auth/login",
                    json={"email": new_user["email"], "password": "WrongPw!"})
    assert r.status_code == 401


def test_me_returns_profile(user_client, new_user):
    r = user_client.get(f"{API}/auth/me")
    assert r.status_code == 200
    j = r.json()
    assert j["email"] == new_user["email"]
    assert j["wallet_balance"] == 50.0


# ---------------- Security gates ----------------

@pytest.mark.parametrize("path,method", [
    ("/auth/me", "get"),
    ("/expenses", "get"),
    ("/wallet", "get"),
    ("/superadmin/stats", "get"),
])
def test_unauth_rejected(client, path, method):
    r = getattr(client, method)(f"{API}{path}")
    assert r.status_code in (401, 403), f"{path} returned {r.status_code}"


# ---------------- Critical billing path ----------------

@pytest.fixture(scope="module")
def created_expense(user_client):
    payload = {
        "category": "food",
        "sub_category": "lunch",
        "items": [
            {"name": "Meal", "quantity": 1, "unit_price": 250.0},
            {"name": "Tea", "quantity": 2, "unit_price": 15.0},
        ],
        "payment": {
            "merchant_name": "Test Cafe",
            "merchant_upi": "cafe@upi",
            "amount": 280.0,
            "payment_method": "UPI",
        },
        "notes": "deploy test",
    }
    r = user_client.post(f"{API}/expenses", json=payload)
    assert r.status_code == 200, f"expense create failed: {r.status_code} {r.text}"
    j = r.json()
    assert j["total"] == 280.0
    assert j["bill_generated"] is False
    return j


def test_generate_bill_debits_wallet(user_client, created_expense):
    eid = created_expense["id"]
    # Wallet pre
    pre = user_client.get(f"{API}/wallet").json()
    pre_bal = pre["balance"]

    r = user_client.post(f"{API}/bills/{eid}/generate", json={})
    assert r.status_code == 200, f"generate bill failed: {r.status_code} {r.text}"
    j = r.json()
    # 1% of 280 = 2.8, min 1 => fee should be 2.8
    assert j["fee"] == 2.8, f"expected fee 2.8, got {j['fee']}"
    assert j["bill_id"].startswith("B4P-")
    assert j["fee_paid_via"] == "wallet"
    assert j["wallet_balance"] == round(pre_bal - 2.8, 2)


def test_bill_persistence(user_client, created_expense):
    eid = created_expense["id"]
    r = user_client.get(f"{API}/expenses/{eid}")
    assert r.status_code == 200
    j = r.json()
    assert j["bill_generated"] is True
    assert j["bill_id"] is not None
    assert j["bill_fee"] == 2.8


def test_bill_pdf_download(user_client, new_user, created_expense):
    eid = created_expense["id"]
    r = user_client.get(f"{API}/bills/{eid}/pdf")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"

    # Also verify token-in-query variant works
    r2 = requests.get(f"{API}/bills/{eid}/pdf", params={"token": new_user["token"]})
    assert r2.status_code == 200
    assert r2.content[:4] == b"%PDF"


def test_bill_generate_min_fee():
    """1 INR minimum fee for tiny expense — verify via a fresh user."""
    email = f"tiny_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Test@1234", "name": "Tiny",
    })
    assert r.status_code == 200
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    exp = requests.post(f"{API}/expenses", headers=h, json={
        "category": "food",
        "items": [{"name": "Candy", "quantity": 1, "unit_price": 10.0}],
        "payment": {"amount": 10.0, "payment_method": "UPI"},
    })
    assert exp.status_code == 200
    eid = exp.json()["id"]
    g = requests.post(f"{API}/bills/{eid}/generate", headers=h, json={})
    assert g.status_code == 200
    # 1% of 10 = 0.1 -> min applied = 1.0
    assert g.json()["fee"] == 1.0


# ---------------- Wallet ----------------

def test_wallet_reflects_bonus_and_debit(user_client):
    r = user_client.get(f"{API}/wallet")
    assert r.status_code == 200
    j = r.json()
    # 50 welcome - 2.8 fee = 47.2
    assert j["balance"] == 47.2
    txn_types = [t["type"] for t in j["transactions"]]
    assert "credit" in txn_types
    assert "debit" in txn_types
    reasons = " ".join(t.get("reason", "") for t in j["transactions"])
    assert "Welcome" in reasons
    assert "Bill generation" in reasons


# ---------------- Super admin ----------------

def test_super_admin_stats(client, super_token):
    r = client.get(f"{API}/superadmin/stats",
                   headers={"Authorization": f"Bearer {super_token}"})
    assert r.status_code == 200, f"stats failed: {r.status_code} {r.text}"
    j = r.json()
    assert "users" in j and "revenue" in j and "activity" in j
    assert j["users"]["total"] >= 1
    assert j["revenue"]["platform_fees_collected"] >= 0.0  # >=0; billing tests may not have run yet under xdist


def test_super_admin_gated_for_regular_user(user_client):
    r = user_client.get(f"{API}/superadmin/stats")
    assert r.status_code == 403
