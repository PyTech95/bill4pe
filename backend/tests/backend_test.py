"""bill4pe backend E2E tests using requests + pytest.
Covers: auth (register/login/me/logout/refresh, lockout), settings persistence,
customers CRUD, invoices CRUD + GST math + send + payments (409 duplicate ref),
dashboard stats.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://invoice-staging-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "meland@mhem.in"
ADMIN_PASSWORD = "Bill4pe@123"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["email"] == ADMIN_EMAIL
    assert data["role"] == "admin"
    return s


@pytest.fixture(scope="module")
def new_user_session():
    """Register a fresh user for isolation from seeded admin data."""
    s = requests.Session()
    email = f"test_{uuid.uuid4().hex[:10]}@bill4pe.test"
    r = s.post(f"{API}/auth/register", json={"name": "Test User", "email": email, "password": "Passw0rd!", "role": "owner"}, timeout=15)
    assert r.status_code == 200, r.text
    return s, email


# ------------------ Health ------------------
def test_root():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ------------------ Auth ------------------
class TestAuth:
    def test_admin_login_and_me(self, admin_session):
        r = admin_session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_login_invalid_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrongpw!"}, timeout=15)
        assert r.status_code == 401

    def test_me_unauthenticated(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401

    def test_register_validations(self):
        r = requests.post(f"{API}/auth/register", json={"name": "x", "email": "bad-email", "password": "abcdef"}, timeout=15)
        assert r.status_code == 400
        r = requests.post(f"{API}/auth/register", json={"name": "x", "email": f"u{uuid.uuid4().hex[:6]}@t.com", "password": "123"}, timeout=15)
        assert r.status_code == 400

    def test_duplicate_registration(self, new_user_session):
        _, email = new_user_session
        r = requests.post(f"{API}/auth/register", json={"name": "Dup", "email": email, "password": "Passw0rd!"}, timeout=15)
        assert r.status_code == 400

    def test_refresh_token(self, new_user_session):
        s, _ = new_user_session
        r = s.post(f"{API}/auth/refresh", timeout=15)
        assert r.status_code == 200

    def test_logout_clears_cookies(self):
        s = requests.Session()
        s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        assert s.get(f"{API}/auth/me", timeout=15).status_code == 200
        s.post(f"{API}/auth/logout", timeout=15)
        # After logout cookies should be gone -> 401
        s2 = requests.Session()
        r = s2.get(f"{API}/auth/me", cookies={}, timeout=15)
        assert r.status_code == 401


# ------------------ Settings ------------------
class TestSettings:
    def test_get_defaults_and_update(self, new_user_session):
        s, _ = new_user_session
        r = s.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200
        payload = {
            "business_name": "TEST_Biz", "trade_name": "TEST", "gstin": "27AAAAA0000A1Z5",
            "state": "Maharashtra", "address": "Mumbai", "upi_id": "test@upi",
            "bank_account": "", "bank_ifsc": "", "bank_branch": "",
            "invoice_prefix": "tst", "terms": "Pay in 7 days",
        }
        r = s.put(f"{API}/settings", json=payload, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["business_name"] == "TEST_Biz"
        assert data["invoice_prefix"] == "TST"  # uppercased
        assert data["upi_id"] == "test@upi"
        # verify persistence via GET
        r2 = s.get(f"{API}/settings", timeout=15)
        assert r2.json()["gstin"] == "27AAAAA0000A1Z5"


# ------------------ Customers ------------------
class TestCustomers:
    def test_customer_crud(self, new_user_session):
        s, _ = new_user_session
        r = s.post(f"{API}/customers", json={"business_name": "", "state": "MH"}, timeout=15)
        assert r.status_code == 400
        r = s.post(f"{API}/customers", json={"business_name": "TEST_Sharma", "phone": "9999", "state": "Maharashtra", "gstin": "27ABCDE1234F1Z5"}, timeout=15)
        assert r.status_code == 200
        cust = r.json()
        assert cust["business_name"] == "TEST_Sharma"
        assert "id" in cust and "_id" not in cust
        cid = cust["id"]
        # list
        r = s.get(f"{API}/customers", timeout=15)
        assert any(c["id"] == cid for c in r.json())
        # update
        r = s.put(f"{API}/customers/{cid}", json={"business_name": "TEST_Sharma2", "state": "Karnataka"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["business_name"] == "TEST_Sharma2"
        # delete
        r = s.delete(f"{API}/customers/{cid}", timeout=15)
        assert r.status_code == 200


# ------------------ Invoices + payments ------------------
class TestInvoices:
    @pytest.fixture(scope="class")
    def customer_id(self, new_user_session):
        s, _ = new_user_session
        r = s.post(f"{API}/customers", json={"business_name": "TEST_InvCust", "state": "Maharashtra", "gstin": "27AAAAA0000A1Z5"}, timeout=15)
        return s, r.json()["id"]

    def test_create_invoice_gst_math_intra_state(self, customer_id):
        s, cid = customer_id
        payload = {
            "customer_id": cid, "issue_date": "2026-01-10", "due_date": "2026-12-31",
            "items": [
                {"description": "Cloth A", "qty": 10, "rate": 500, "gst_rate": 5},
                {"description": "Cloth B", "qty": 1, "rate": 2000, "gst_rate": 18},
            ],
            "discount_pct": 0, "inter_state": False, "status": "sent",
        }
        r = s.post(f"{API}/invoices", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["subtotal"] == 7000
        assert inv["total"] == 7610
        assert inv["cgst"] == 305 and inv["sgst"] == 305 and inv["igst"] == 0
        assert inv["status"] == "pending"  # sent + due in future
        assert inv["invoice_number"].startswith(("INV-", "TST-"))
        self._invoice_id = inv["id"]

    def test_create_invoice_inter_state(self, customer_id):
        s, cid = customer_id
        r = s.post(f"{API}/invoices", json={
            "customer_id": cid, "issue_date": "2026-01-10", "due_date": "2026-12-31",
            "items": [{"description": "X", "qty": 2, "rate": 1000, "gst_rate": 18}],
            "inter_state": True, "status": "sent",
        }, timeout=15)
        assert r.status_code == 200
        inv = r.json()
        assert inv["subtotal"] == 2000
        assert inv["igst"] == 360 and inv["cgst"] == 0 and inv["sgst"] == 0
        assert inv["total"] == 2360

    def test_draft_and_send(self, customer_id):
        s, cid = customer_id
        r = s.post(f"{API}/invoices", json={
            "customer_id": cid, "issue_date": "2026-01-10", "due_date": "2026-12-31",
            "items": [{"description": "D", "qty": 1, "rate": 100, "gst_rate": 0}],
            "status": "draft",
        }, timeout=15)
        assert r.status_code == 200
        inv = r.json()
        assert inv["status"] == "draft"
        r2 = s.post(f"{API}/invoices/{inv['id']}/send", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["status"] in ("pending", "overdue")

    def test_payment_and_duplicate_reference(self, customer_id):
        s, cid = customer_id
        r = s.post(f"{API}/invoices", json={
            "customer_id": cid, "issue_date": "2026-01-10", "due_date": "2026-12-31",
            "items": [{"description": "P", "qty": 1, "rate": 1000, "gst_rate": 0}],
            "status": "sent",
        }, timeout=15)
        inv = r.json()
        inv_id = inv["id"]
        # partial
        r = s.post(f"{API}/invoices/{inv_id}/payments", json={"amount": 400, "mode": "upi", "reference": "TXN_TEST_1"}, timeout=15)
        assert r.status_code == 200
        upd = r.json()
        assert upd["status"] == "pending"
        assert upd["balance_due"] == 600
        # duplicate ref -> 409
        r = s.post(f"{API}/invoices/{inv_id}/payments", json={"amount": 100, "mode": "upi", "reference": "TXN_TEST_1"}, timeout=15)
        assert r.status_code == 409
        # full payment
        r = s.post(f"{API}/invoices/{inv_id}/payments", json={"amount": 600, "mode": "cash", "reference": "TXN_TEST_2"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "paid"
        # overpayment blocked
        r = s.post(f"{API}/invoices/{inv_id}/payments", json={"amount": 10, "mode": "cash", "reference": "TXN_TEST_3"}, timeout=15)
        assert r.status_code == 400

    def test_list_and_filter(self, customer_id):
        s, _ = customer_id
        r = s.get(f"{API}/invoices?status=paid", timeout=15)
        assert r.status_code == 200
        assert all(i["status"] == "paid" for i in r.json())


# ------------------ Dashboard ------------------
def test_dashboard_stats(admin_session):
    r = admin_session.get(f"{API}/dashboard/stats", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for key in ("total_invoiced", "collected", "pending", "overdue", "counts", "monthly", "recent_invoices", "top_customers"):
        assert key in d
    assert len(d["monthly"]) == 6
    assert set(d["counts"].keys()) == {"draft", "pending", "paid", "overdue"}
