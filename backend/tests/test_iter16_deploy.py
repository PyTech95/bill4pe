"""Iteration 16 backend smoke — verify the ported BILL4PE app end-to-end
core journeys: health, auth (register/login/me + super admin), expenses
create->persist->retrieve, reports listing, validation (422), and Razorpay
graceful degradation (payments/config + create-order without keys)."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback to frontend/.env inline read (test infra guarantees this env)
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"


# Unique per-run email to avoid rate-limit + already-registered clashes.
_RUN_ID = uuid.uuid4().hex[:8]
INDIV_EMAIL = f"qa_iter16_{_RUN_ID}@bill4petest.com"
INDIV_PASS = "Test@1234"
SUPER_EMAIL = "admin@newbill.com"
SUPER_PASS = "NewBill@2026"


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def indiv_token(s):
    r = s.post(f"{API}/auth/register", json={
        "name": "QA Iter16",
        "email": INDIV_EMAIL,
        "password": INDIV_PASS,
    })
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    body = r.json()
    assert "token" in body and "user" in body
    assert body["user"]["email"] == INDIV_EMAIL
    assert float(body["user"].get("wallet_balance", 0)) == 50.0, "welcome bonus missing"
    return body["token"]


@pytest.fixture(scope="session")
def super_token(s):
    r = s.post(f"{API}/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PASS})
    assert r.status_code == 200, f"super admin login failed: {r.status_code} {r.text}"
    return r.json()["token"], r.json()["user"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---- Health -----------------------------------------------------------------

def test_health_root(s):
    r = s.get(f"{API}/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("app") == "BILL4PE"


# ---- Auth -------------------------------------------------------------------

def test_register_gives_token_and_wallet_bonus(indiv_token):
    assert isinstance(indiv_token, str) and len(indiv_token) > 20


def test_login_registered_user(s):
    r = s.post(f"{API}/auth/login", json={"email": INDIV_EMAIL, "password": INDIV_PASS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "token" in body
    assert body["user"]["email"] == INDIV_EMAIL


def test_super_admin_login_role(super_token):
    _tok, user = super_token
    assert user.get("role") == "superadmin", f"expected superadmin, got {user.get('role')}"


def test_me_requires_auth(s):
    r = s.get(f"{API}/auth/me")
    assert r.status_code == 401


def test_me_with_token(s, indiv_token):
    r = s.get(f"{API}/auth/me", headers=_h(indiv_token))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == INDIV_EMAIL
    assert "password" not in body


# ---- Expenses: create -> persist -> retrieve --------------------------------

def _sample_expense_body(amount=123.45):
    return {
        "category": "food",
        "sub_category": "lunch",
        "items": [
            {"name": "Thali", "quantity": 1, "unit_price": amount},
        ],
        "payment": {
            "merchant_name": "TEST_Cafe_Iter16",
            "merchant_upi": "testcafe@ybl",
            "amount": amount,
            "payment_method": "UPI",
            "payment_status": "paid",
        },
        "notes": "iter16 create->retrieve",
    }


@pytest.fixture(scope="session")
def created_expense(s, indiv_token):
    r = s.post(f"{API}/expenses", json=_sample_expense_body(), headers=_h(indiv_token))
    assert r.status_code == 200, f"create expense failed: {r.status_code} {r.text}"
    doc = r.json()
    assert doc.get("id")
    assert doc.get("total") == 123.45
    assert doc["payment"]["merchant_name"] == "TEST_Cafe_Iter16"
    return doc


def test_expense_created_persists_via_get_by_id(s, indiv_token, created_expense):
    eid = created_expense["id"]
    r = s.get(f"{API}/expenses/{eid}", headers=_h(indiv_token))
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["id"] == eid
    assert got["total"] == 123.45
    assert got["category"] == "food"


def test_expense_appears_in_list(s, indiv_token, created_expense):
    r = s.get(f"{API}/expenses", headers=_h(indiv_token))
    assert r.status_code == 200
    ids = [e["id"] for e in r.json().get("expenses", [])]
    assert created_expense["id"] in ids


def test_expenses_list_requires_auth(s):
    r = s.get(f"{API}/expenses")
    assert r.status_code == 401


# ---- Reports ----------------------------------------------------------------

def test_reports_list_authenticated(s, indiv_token):
    r = s.get(f"{API}/reports", headers=_h(indiv_token))
    assert r.status_code == 200
    assert isinstance(r.json().get("reports"), list)


def test_reports_create_and_retrieve(s, indiv_token, created_expense):
    r = s.post(
        f"{API}/reports",
        json={"title": "TEST_Iter16 Report", "expense_ids": [created_expense["id"]], "notes": "ok"},
        headers=_h(indiv_token),
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["expense_count"] == 1
    assert rep["total"] == 123.45
    # Verify persistence via GET
    r2 = s.get(f"{API}/reports", headers=_h(indiv_token))
    assert r2.status_code == 200
    assert rep["id"] in [x["id"] for x in r2.json()["reports"]]


# ---- Input validation -------------------------------------------------------

def test_expense_empty_body_returns_422(s, indiv_token):
    r = s.post(f"{API}/expenses", json={}, headers=_h(indiv_token))
    assert r.status_code == 422, f"expected 422 pydantic, got {r.status_code} {r.text}"


def test_register_invalid_email_returns_422(s):
    r = s.post(f"{API}/auth/register", json={
        "name": "x", "email": "not-an-email", "password": "Test@1234"
    })
    assert r.status_code == 422


# ---- Razorpay graceful degradation -----------------------------------------

def test_payments_config_reports_disabled(s):
    r = s.get(f"{API}/payments/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg.get("provider") == "razorpay"
    assert cfg.get("enabled") is False, f"Razorpay should be disabled when no keys: {cfg}"


def test_create_order_without_razorpay_is_graceful(s, indiv_token):
    """Without Razorpay keys the server must NOT return a 500 crash — 400/402/
    502/503 with a JSON body is the acceptable graceful degradation."""
    r = s.post(
        f"{API}/payments/razorpay/order",
        json={"amount": 100, "purpose": "wallet_recharge"},
        headers=_h(indiv_token),
    )
    assert r.status_code != 500, f"Razorpay unconfigured should not 500: {r.status_code} {r.text}"
    assert r.status_code in (400, 402, 502, 503), f"unexpected status {r.status_code}: {r.text}"
    # Body must be valid JSON with a message/detail
    body = r.json()
    assert body.get("detail") or body.get("message"), f"no error detail: {body}"


def test_merchant_create_order_without_razorpay_is_graceful(s, indiv_token):
    r = s.post(
        f"{API}/payments/merchant/create-order",
        json={"payee_upi": "test@ybl", "merchant_amount": 100},
        headers=_h(indiv_token),
    )
    assert r.status_code != 500, f"should not 500: {r.status_code} {r.text}"
    assert r.status_code in (400, 402, 502, 503), f"unexpected {r.status_code}: {r.text}"
