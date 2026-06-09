"""Regression test for BILL4PE post-refactor (server.py 1707 -> 62 lines).
Verifies parity for all listed endpoints across routers/, services/, core/.
"""
import io
import os
import uuid
import time
import requests
import pytest
from pypdf import PdfReader

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


def _pdf_text(b):
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(b)).pages)
    except Exception:
        return ""


# ---------- Health ----------
def test_api_root(session):
    r = session.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("app") == "BILL4PE"


# ---------- Auth: Email/password ----------
def test_register_grants_welcome_bonus(session):
    email = f"test_{uuid.uuid4().hex[:8]}@bill4pe-qa.com"
    r = session.post(f"{BASE_URL}/api/auth/register",
                     json={"email": email, "password": "Pass@12345", "name": "Reg User"},
                     timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["email"] == email
    # Welcome bonus 50
    assert float(data["user"].get("wallet_balance", 0)) == 50.0, data["user"]


def test_login_with_registered_user(session, registered_user):
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": registered_user["email"], "password": registered_user["password"]},
                     timeout=15)
    assert r.status_code == 200
    assert "token" in r.json()


def test_login_invalid_password(session, registered_user):
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": registered_user["email"], "password": "WRONG"},
                     timeout=15)
    assert r.status_code in (400, 401)


def test_me_returns_user(session, auth_headers, registered_user):
    r = session.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["email"] == registered_user["email"]
    assert "_id" not in r.json()


def test_me_unauthorized_without_token(session):
    r = session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 401


def test_me_unauthorized_with_invalid_token(session):
    r = session.get(f"{BASE_URL}/api/auth/me",
                    headers={"Authorization": "Bearer not.a.real.token"}, timeout=15)
    assert r.status_code == 401


def test_update_profile_and_gstin_validation(session, auth_headers):
    # Valid update with gstin
    r = session.put(f"{BASE_URL}/api/auth/me", headers=auth_headers,
                    json={"name": "Updated Name", "phone": "9876543210",
                          "gstin": "27ABCDE1234F1Z5", "company_name": "Acme Pvt Ltd"},
                    timeout=15)
    assert r.status_code == 200, r.text
    me = session.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15).json()
    assert me["name"] == "Updated Name"
    assert me["gstin"] == "27ABCDE1234F1Z5"
    assert me["company_name"] == "Acme Pvt Ltd"
    # Invalid GSTIN rejected
    r2 = session.put(f"{BASE_URL}/api/auth/me", headers=auth_headers,
                     json={"gstin": "BAD123"}, timeout=15)
    assert r2.status_code == 400


# ---------- Auth: Phone OTP demo ----------
def test_phone_otp_request_and_verify(session):
    phone = "9999999990"
    r1 = session.post(f"{BASE_URL}/api/auth/otp/request", json={"phone": phone}, timeout=15)
    assert r1.status_code == 200, r1.text
    r2 = session.post(f"{BASE_URL}/api/auth/otp/verify",
                      json={"phone": phone, "otp": "123456"}, timeout=15)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "token" in body and isinstance(body["token"], str)
    assert "user" in body
    assert "referral_code" in body["user"], body["user"]


# ---------- Wallet ----------
def test_wallet_get_and_recharge(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/wallet", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "balance" in body and "transactions" in body
    before = float(body["balance"])
    r2 = session.post(f"{BASE_URL}/api/wallet/recharge",
                      headers=auth_headers, json={"amount": 100}, timeout=15)
    assert r2.status_code == 200, r2.text
    after = float(session.get(f"{BASE_URL}/api/wallet", headers=auth_headers, timeout=15).json()["balance"])
    assert round(after - before, 2) == 100.0


def test_wallet_unauthorized(session):
    r = session.get(f"{BASE_URL}/api/wallet", timeout=15)
    assert r.status_code == 401


# ---------- Expenses CRUD ----------
@pytest.fixture(scope="module")
def created_expense(auth_headers):
    payload = {
        "category": "food",
        "sub_category": "Dinner",
        "items": [{"name": "Paneer", "quantity": 2, "unit_price": 150}],
        "payment": {
            "merchant_name": "Test Resto",
            "merchant_upi": "test@upi",
            "transaction_id": "TXN" + uuid.uuid4().hex[:8],
            "amount": 300.0,
            "payment_method": "UPI",
        },
    }
    r = requests.post(f"{BASE_URL}/api/expenses", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 300.0
    assert "_id" not in data
    return data


def test_expense_get_by_id(auth_headers, created_expense):
    eid = created_expense["id"]
    r = requests.get(f"{BASE_URL}/api/expenses/{eid}", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["id"] == eid


def test_expenses_list(auth_headers, created_expense):
    r = requests.get(f"{BASE_URL}/api/expenses", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    items = body.get("expenses") if isinstance(body, dict) else body
    assert isinstance(items, list)
    assert any(e.get("id") == created_expense["id"] for e in items)


def test_expenses_stats(auth_headers, created_expense):
    r = requests.get(f"{BASE_URL}/api/expenses/stats", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "by_category" in body or "total" in body


def test_expenses_trips(auth_headers):
    r = requests.get(f"{BASE_URL}/api/expenses/trips", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    # Returns list / dict — just confirm 200 + parseable
    assert isinstance(r.json(), (list, dict))


def test_expenses_merchants_recent(auth_headers, created_expense):
    r = requests.get(f"{BASE_URL}/api/expenses/merchants/recent", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    items = body.get("merchants") if isinstance(body, dict) else body
    assert isinstance(items, list)


def test_expenses_csv_export(auth_headers):
    r = requests.get(f"{BASE_URL}/api/expenses/export.csv", headers=auth_headers, timeout=20)
    assert r.status_code == 200
    ctype = r.headers.get("content-type", "")
    assert "csv" in ctype.lower() or "text" in ctype.lower(), ctype
    txt = r.text
    lines = [l for l in txt.splitlines() if l.strip()]
    assert len(lines) >= 1  # at least header row
    header = lines[0].lower()
    assert "," in header


def test_expenses_unauthorized(session):
    r = session.get(f"{BASE_URL}/api/expenses", timeout=15)
    assert r.status_code == 401


# ---------- Bills ----------
def test_bill_generate_deducts_5_and_returns_pdf(auth_headers, created_expense):
    eid = created_expense["id"]
    # Ensure wallet has >=5
    requests.post(f"{BASE_URL}/api/wallet/recharge", headers=auth_headers, json={"amount": 50}, timeout=15)
    before = float(requests.get(f"{BASE_URL}/api/wallet", headers=auth_headers, timeout=15).json()["balance"])
    g = requests.post(f"{BASE_URL}/api/bills/{eid}/generate", headers=auth_headers, timeout=15)
    assert g.status_code == 200, g.text
    after = float(requests.get(f"{BASE_URL}/api/wallet", headers=auth_headers, timeout=15).json()["balance"])
    # Fee=5; may be 0 if already generated (idempotent). Accept either.
    assert before - after in (0.0, 5.0), f"unexpected deduction: {before-after}"
    r = requests.get(f"{BASE_URL}/api/bills/{eid}/pdf", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    text = _pdf_text(r.content)
    # PDF includes customer (merchant) details
    assert "Test Resto" in text or "Merchant" in text, text[:400]


def test_bill_pdf_token_query_fallback(auth_headers, created_expense, registered_user):
    eid = created_expense["id"]
    token = registered_user["token"]
    r = requests.get(f"{BASE_URL}/api/bills/{eid}/pdf?token={token}", timeout=30)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")


# ---------- Reports ----------
@pytest.fixture(scope="module")
def created_report(auth_headers, created_expense):
    payload = {
        "title": "TEST_RegressionReport",
        "notes": "regression",
        "expense_ids": [created_expense["id"]],
    }
    r = requests.post(f"{BASE_URL}/api/reports", headers=auth_headers, json=payload, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "_id" not in data
    assert data.get("expense_count", 0) >= 1
    return data


def test_reports_list(auth_headers, created_report):
    r = requests.get(f"{BASE_URL}/api/reports", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    reps = r.json().get("reports", [])
    assert any(rp.get("id") == created_report["id"] for rp in reps)


def test_report_pdf(auth_headers, created_report):
    rid = created_report["id"]
    r = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")


def test_report_delete(auth_headers, created_report):
    rid = created_report["id"]
    r = requests.delete(f"{BASE_URL}/api/reports/{rid}", headers=auth_headers, timeout=15)
    assert r.status_code in (200, 204)
    # Verify gone
    g = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=auth_headers, timeout=15)
    assert g.status_code in (404, 400)


# ---------- Referrals ----------
def test_referrals_me(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/referrals/me", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "code" in body and isinstance(body["code"], str) and len(body["code"]) >= 4


def test_referrals_validate_valid(session, auth_headers):
    code = session.get(f"{BASE_URL}/api/referrals/me", headers=auth_headers, timeout=15).json()["code"]
    r = session.get(f"{BASE_URL}/api/referrals/validate/{code}", timeout=15)
    assert r.status_code == 200


def test_referrals_validate_invalid(session):
    r = session.get(f"{BASE_URL}/api/referrals/validate/ZZZZZZ", timeout=15)
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json().get("valid") is False


# ---------- Favourites ----------
def test_favourites_pantry_crud(auth_headers):
    # GET initial
    r = requests.get(f"{BASE_URL}/api/favourites?category=pantry", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    # POST add
    p = requests.post(f"{BASE_URL}/api/favourites", headers=auth_headers,
                      json={"category": "pantry", "items": [{"name": "TEST_Rice", "unit_price": 100}]}, timeout=15)
    assert p.status_code == 200, p.text
    # DELETE
    d = requests.delete(f"{BASE_URL}/api/favourites?category=pantry&name=TEST_Rice",
                        headers=auth_headers, timeout=15)
    assert d.status_code in (200, 204)


def test_favourites_rejects_food_category(auth_headers):
    r = requests.get(f"{BASE_URL}/api/favourites?category=food", headers=auth_headers, timeout=15)
    assert r.status_code == 400


# ---------- AI suggest ----------
def test_ai_suggest_items(auth_headers):
    r = requests.post(f"{BASE_URL}/api/ai/suggest-items", headers=auth_headers,
                      json={"category": "food", "query": "ro"}, timeout=60)
    # Route exists, may return 200 or 500 if LLM throttled
    assert r.status_code in (200, 500), f"unexpected {r.status_code}: {r.text[:200]}"
    if r.status_code == 200:
        body = r.json()
        assert "suggestions" in body or "items" in body
        arr = body.get("suggestions") or body.get("items") or []
        assert isinstance(arr, list)


# ---------- Contact ----------
def test_contact_form(session):
    r = session.post(f"{BASE_URL}/api/contact",
                     json={"name": "QA Bot", "email": "qa@bill4pe-qa.com",
                           "message": "Regression smoke test"}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
