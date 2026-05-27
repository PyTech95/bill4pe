"""End-to-end backend tests for BILL4PE: auth, AI, expenses, wallet, bills, contact."""
import os
import io
import uuid
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-payment-workflow.preview.emergentagent.com").rstrip("/")
FOOD_IMAGE_PATH = "/tmp/thali.jpg"


# ------------------ Health ------------------
def test_health_root(session):
    r = session.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("app") == "BILL4PE"


# ------------------ Auth ------------------
def test_register_returns_token_and_welcome_bonus(session):
    email = f"test_{uuid.uuid4().hex[:10]}@bill4pe-qa.com"
    r = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "Secret@12345", "name": "Welcome User"
    }, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 20
    assert data["user"]["email"] == email
    assert data["user"]["name"] == "Welcome User"
    assert data["user"]["wallet_balance"] == 50.0


def test_register_duplicate_email_rejected(session, registered_user):
    r = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": registered_user["email"], "password": "Other@12345", "name": "Dup"
    }, timeout=15)
    assert r.status_code == 400


def test_login_success(session, registered_user):
    r = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": registered_user["email"], "password": registered_user["password"]
    }, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data
    assert data["user"]["email"] == registered_user["email"]
    assert data["user"]["wallet_balance"] >= 0


def test_login_invalid_credentials(session, registered_user):
    r = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": registered_user["email"], "password": "WrongPass!9"
    }, timeout=15)
    assert r.status_code == 401


def test_me_with_token(session, auth_headers, registered_user):
    r = session.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == registered_user["email"]
    assert body["id"] == registered_user["user"]["id"]
    assert "password" not in body
    assert "_id" not in body


def test_me_without_token_returns_401(session):
    r = session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 401


def test_protected_endpoints_require_auth(session):
    # Sample protected endpoints should reject unauthenticated requests
    endpoints = [
        ("GET", "/api/expenses"),
        ("GET", "/api/expenses/stats"),
        ("GET", "/api/wallet"),
        ("POST", "/api/wallet/recharge"),
        ("POST", "/api/expenses"),
    ]
    for method, ep in endpoints:
        r = session.request(method, f"{BASE_URL}{ep}", json={}, timeout=15)
        assert r.status_code == 401, f"{method} {ep} expected 401 got {r.status_code}"


# ------------------ Wallet ------------------
def test_wallet_initial_balance(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/wallet", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] == 50.0
    assert isinstance(body["transactions"], list)
    assert len(body["transactions"]) >= 1
    assert any(t.get("reason") == "Welcome bonus" for t in body["transactions"])


def test_wallet_recharge_positive(session, auth_headers):
    r = session.post(f"{BASE_URL}/api/wallet/recharge", headers=auth_headers,
                     json={"amount": 100}, timeout=15)
    assert r.status_code == 200, r.text
    bal = r.json()["balance"]
    assert bal >= 150.0
    # verify GET reflects new balance
    g = session.get(f"{BASE_URL}/api/wallet", headers=auth_headers, timeout=15).json()
    assert g["balance"] == bal


def test_wallet_recharge_invalid_amounts(session, auth_headers):
    r1 = session.post(f"{BASE_URL}/api/wallet/recharge", headers=auth_headers,
                      json={"amount": 0}, timeout=15)
    assert r1.status_code == 400
    r2 = session.post(f"{BASE_URL}/api/wallet/recharge", headers=auth_headers,
                      json={"amount": -10}, timeout=15)
    assert r2.status_code == 400
    r3 = session.post(f"{BASE_URL}/api/wallet/recharge", headers=auth_headers,
                      json={"amount": 20000}, timeout=15)
    assert r3.status_code == 400


# ------------------ Expenses ------------------
@pytest.fixture(scope="module")
def created_expense_id(auth_headers):
    payload = {
        "category": "food",
        "sub_category": "Restaurant",
        "items": [
            {"name": "Roti", "quantity": 3, "unit_price": 15},
            {"name": "Dal", "quantity": 1, "unit_price": 50},
        ],
        "payment": {
            "merchant_name": "Test Dhaba",
            "merchant_upi": "test@upi",
            "merchant_mobile": "9999999999",
            "transaction_id": "TXN123456",
            "amount": 95.0,
            "payment_method": "UPI",
        },
        "notes": "lunch",
    }
    r = requests.post(f"{BASE_URL}/api/expenses", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 95.0
    assert data["category"] == "food"
    assert len(data["items"]) == 2
    assert "_id" not in data
    return data["id"]


def test_create_expense_total_computed(created_expense_id):
    assert created_expense_id  # fixture asserts


def test_get_expense_by_id(auth_headers, created_expense_id):
    r = requests.get(f"{BASE_URL}/api/expenses/{created_expense_id}",
                     headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == created_expense_id
    assert body["total"] == 95.0


def test_get_expense_404(auth_headers):
    r = requests.get(f"{BASE_URL}/api/expenses/does-not-exist",
                     headers=auth_headers, timeout=15)
    assert r.status_code == 404


def test_list_expenses_and_filters(auth_headers, created_expense_id):
    r = requests.get(f"{BASE_URL}/api/expenses", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    items = r.json()["expenses"]
    assert any(e["id"] == created_expense_id for e in items)

    r2 = requests.get(f"{BASE_URL}/api/expenses?category=food",
                      headers=auth_headers, timeout=15)
    assert r2.status_code == 200
    assert all(e["category"] == "food" for e in r2.json()["expenses"])

    r3 = requests.get(f"{BASE_URL}/api/expenses?days=30",
                      headers=auth_headers, timeout=15)
    assert r3.status_code == 200


def test_expenses_stats(auth_headers, created_expense_id):
    r = requests.get(f"{BASE_URL}/api/expenses/stats",
                     headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["expense_count"] >= 1
    assert body["total_expenses"] >= 95.0
    assert isinstance(body["by_category"], list)
    assert any(c["category"] == "food" for c in body["by_category"])


# ------------------ Bills ------------------
def test_generate_bill_deducts_5_and_idempotent(auth_headers, created_expense_id):
    # Pre balance
    pre = requests.get(f"{BASE_URL}/api/wallet", headers=auth_headers, timeout=15).json()["balance"]
    r = requests.post(f"{BASE_URL}/api/bills/{created_expense_id}/generate",
                      headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    bill_id = data["bill_id"]
    assert bill_id.startswith("B4P-")
    assert data["wallet_balance"] == round(pre - 5.0, 2)

    # Idempotent
    r2 = requests.post(f"{BASE_URL}/api/bills/{created_expense_id}/generate",
                       headers=auth_headers, timeout=15)
    assert r2.status_code == 200
    assert r2.json()["bill_id"] == bill_id

    # Balance unchanged after 2nd call
    post = requests.get(f"{BASE_URL}/api/wallet", headers=auth_headers, timeout=15).json()["balance"]
    assert post == data["wallet_balance"]


def test_bill_pdf_via_bearer(auth_headers, created_expense_id):
    r = requests.get(f"{BASE_URL}/api/bills/{created_expense_id}/pdf",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 1000


def test_bill_pdf_via_query_token(registered_user, created_expense_id):
    r = requests.get(
        f"{BASE_URL}/api/bills/{created_expense_id}/pdf?token={registered_user['token']}",
        timeout=30,
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")


def test_bill_pdf_unauthenticated(created_expense_id):
    r = requests.get(f"{BASE_URL}/api/bills/{created_expense_id}/pdf", timeout=15)
    assert r.status_code == 401


def test_generate_bill_insufficient_balance(session):
    # Fresh user → ₹50 → spend down to <₹5 by generating multiple bills
    email = f"low_{uuid.uuid4().hex[:8]}@bill4pe-qa.com"
    reg = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "Secret@12345", "name": "Low Bal"
    }, timeout=15).json()
    hdr = {"Authorization": f"Bearer {reg['token']}", "Content-Type": "application/json"}

    # Create 10 expenses → generate 10 bills (₹50/5 = 10 bills exactly), 11th should 402
    expense_ids = []
    for _ in range(11):
        e = requests.post(f"{BASE_URL}/api/expenses", headers=hdr, json={
            "category": "food",
            "items": [{"name": "X", "quantity": 1, "unit_price": 10}],
            "payment": {"amount": 10},
        }, timeout=15).json()
        expense_ids.append(e["id"])

    # Generate 10 bills successfully
    for i in range(10):
        rr = requests.post(f"{BASE_URL}/api/bills/{expense_ids[i]}/generate",
                           headers=hdr, timeout=15)
        assert rr.status_code == 200, f"bill {i} expected 200 got {rr.status_code}"

    # 11th should fail with 402
    rfail = requests.post(f"{BASE_URL}/api/bills/{expense_ids[10]}/generate",
                          headers=hdr, timeout=15)
    assert rfail.status_code == 402, f"expected 402 got {rfail.status_code}: {rfail.text}"


# ------------------ AI ------------------
def test_ai_detect_items_food(auth_headers):
    assert os.path.exists(FOOD_IMAGE_PATH), "Food test image missing"
    with open(FOOD_IMAGE_PATH, "rb") as f:
        files = {"file": ("thali.jpg", f, "image/jpeg")}
        data = {"category": "food"}
        # Multipart - remove Content-Type from headers
        h = {k: v for k, v in auth_headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{BASE_URL}/api/ai/detect-items",
                          headers=h, data=data, files=files, timeout=90)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    # Validate items structure (Gemini may or may not detect — at least field shape)
    for it in body["items"]:
        assert "name" in it and "quantity" in it and "unit_price" in it
    print(f"AI detected {len(body['items'])} items: {body['items']}")


def test_ai_suggest_items(session, auth_headers):
    r = session.post(f"{BASE_URL}/api/ai/suggest-items",
                     headers=auth_headers, json={"category": "food", "query": "Rot"},
                     timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert "suggestions" in body and isinstance(body["suggestions"], list)


def test_ai_suggest_short_query_returns_empty(session, auth_headers):
    r = session.post(f"{BASE_URL}/api/ai/suggest-items",
                     headers=auth_headers, json={"category": "food", "query": "a"},
                     timeout=15)
    assert r.status_code == 200
    assert r.json()["suggestions"] == []


# ------------------ Contact ------------------
def test_contact_form(session):
    r = session.post(f"{BASE_URL}/api/contact", json={
        "name": "Tester", "email": "tester@example.com", "message": "Hello B4P"
    }, timeout=15)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_contact_invalid_email(session):
    r = session.post(f"{BASE_URL}/api/contact", json={
        "name": "Tester", "email": "not-an-email", "message": "Hi"
    }, timeout=15)
    assert r.status_code == 422
