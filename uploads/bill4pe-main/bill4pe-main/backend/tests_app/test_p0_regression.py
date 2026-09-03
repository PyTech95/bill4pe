"""P0 regression for iteration_8:
  (1) PayNow 'Save Unpaid' — POST /api/expenses with payment_status='unpaid' succeeds.
  (2) Corporate happy path E2E: admin->employee->expense(pending)->approve->bill from COMPANY wallet.
  (3) Employee personal wallet recharge BLOCKED.
  (4) Backend regression: OTP, /expenses, /wallet, /bills generate for individual.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

TS = int(time.time())
RUN = uuid.uuid4().hex[:6]


# -------------------- helpers --------------------
def H(token):
    return {"Authorization": f"Bearer {token}"}


def make_food_expense_payload(skipped=False):
    return {
        "category": "food",
        "sub_category": "lunch",
        "items": [{"name": "Test Meal", "quantity": 1, "unit_price": 250.0}],
        "notes": "regression p0",
        "payment": {
            "merchant_name": "Test Cafe",
            "merchant_upi": "" if skipped else "test@upi",
            "merchant_mobile": "9999999999",
            "transaction_id": f"UNPAID-{TS}" if skipped else f"TXN-{TS}-{uuid.uuid4().hex[:6]}",
            "payment_status": "unpaid" if skipped else "paid",
            "amount": 250.0,
            "latitude": 12.97,
            "longitude": 77.59,
            "payment_method": "Unpaid" if skipped else "UPI",
        },
    }


# -------------------- fixtures --------------------
@pytest.fixture(scope="module")
def individual_token():
    """Login via phone OTP — individual user lands on /app/ flow."""
    phone = f"99999{TS % 100000:05d}"[-10:]
    requests.post(f"{API}/auth/otp/request", json={"phone": phone}, timeout=15)
    r = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "otp": "123456"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_ctx():
    email = f"admin_p0_{TS}_{RUN}@democorp.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "test123", "name": "P0 Admin",
        "user_type": "corporate", "corporate_name": "P0 Corp",
        "subscription_plan": "monthly_50", "employee_limit": 5,
    }, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    return {"token": d["token"], "user": d["user"], "email": email}


# -------------------- 1. PayNow Save-Unpaid --------------------
class TestPayNowSaveUnpaid:
    def test_save_unpaid_expense_creates_with_unpaid_status(self, individual_token):
        payload = make_food_expense_payload(skipped=True)
        r = requests.post(f"{API}/expenses", json=payload, headers=H(individual_token), timeout=20)
        assert r.status_code == 200, f"Save unpaid failed: {r.status_code} {r.text}"
        body = r.json()
        assert "id" in body
        # verify persistence via GET
        g = requests.get(f"{API}/expenses/{body['id']}", headers=H(individual_token), timeout=15)
        assert g.status_code == 200
        exp = g.json()
        assert exp["payment"]["payment_status"] == "unpaid", exp["payment"]
        assert exp["payment"]["payment_method"] == "Unpaid"

    def test_save_paid_expense_marks_paid(self, individual_token):
        payload = make_food_expense_payload(skipped=False)
        r = requests.post(f"{API}/expenses", json=payload, headers=H(individual_token), timeout=20)
        assert r.status_code == 200, r.text
        eid = r.json()["id"]
        g = requests.get(f"{API}/expenses/{eid}", headers=H(individual_token), timeout=15)
        assert g.json()["payment"]["payment_status"] == "paid"


# -------------------- 2. Corporate E2E --------------------
class TestCorporateE2E:
    def test_full_flow_admin_employee_expense_approval_bill(self, admin_ctx):
        admin_h = H(admin_ctx["token"])

        # (a) admin landed correctly
        assert admin_ctx["user"]["role"] == "admin"
        assert admin_ctx["user"]["company_id"]

        # (b) admin creates employee
        emp_email = f"emp_p0_{TS}_{RUN}@democorp.com"
        r = requests.post(f"{API}/company/employees", json={
            "email": emp_email, "name": "Emp P0", "phone": "9000000001",
        }, headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text
        emp_data = r.json()
        temp_password = emp_data["credentials"]["temp_password"]
        assert temp_password

        # (c) employee logs in -> should be role=employee with company_id
        login = requests.post(f"{API}/auth/login", json={
            "email": emp_email, "password": temp_password,
        }, timeout=20)
        assert login.status_code == 200, login.text
        emp_token = login.json()["token"]
        emp_user = login.json()["user"]
        assert emp_user["role"] == "employee"
        assert emp_user["company_id"] == admin_ctx["user"]["company_id"]
        emp_h = H(emp_token)

        # capture employee personal wallet balance
        w0 = requests.get(f"{API}/wallet", headers=emp_h, timeout=15).json()
        emp_wallet_before = float(w0.get("balance", 0))

        # recharge company wallet so bill can be generated
        rch = requests.post(f"{API}/company/wallet/recharge", json={"amount": 100},
                            headers=admin_h, timeout=20)
        assert rch.status_code == 200, rch.text
        cw_before = float(rch.json().get("balance", rch.json().get("new_balance", 0)))
        assert cw_before >= 100  # ≥100 after at least one recharge

        # (d) employee creates Food expense
        r = requests.post(f"{API}/expenses", json=make_food_expense_payload(skipped=False),
                          headers=emp_h, timeout=20)
        assert r.status_code == 200, r.text
        eid = r.json()["id"]
        g = requests.get(f"{API}/expenses/{eid}", headers=emp_h, timeout=15)
        assert g.status_code == 200
        assert g.json()["approval_status"] == "pending", g.json()

        # employee cannot generate bill yet (pending approval)
        b_pre = requests.post(f"{API}/bills/{eid}/generate", headers=emp_h, timeout=15)
        assert b_pre.status_code in (400, 402, 403), f"Expected gating, got {b_pre.status_code} {b_pre.text}"

        # (e) admin approves
        ap = requests.post(f"{API}/company/approvals/{eid}/approve",
                           json={"notes": "ok"}, headers=admin_h, timeout=20)
        assert ap.status_code == 200, ap.text
        g2 = requests.get(f"{API}/expenses/{eid}", headers=emp_h, timeout=15)
        assert g2.json()["approval_status"] == "approved"

        # (f) employee generates bill — COMPANY wallet debited ₹5
        b = requests.post(f"{API}/bills/{eid}/generate", headers=emp_h, timeout=30)
        assert b.status_code == 200, f"Bill generate failed: {b.status_code} {b.text}"

        # check company wallet decreased by 5
        cw_after_r = requests.get(f"{API}/company/wallet", headers=admin_h, timeout=15)
        assert cw_after_r.status_code == 200
        cw_after = float(cw_after_r.json().get("balance", 0))
        assert abs((cw_before - cw_after) - 5.0) < 0.01, f"Company wallet delta want 5.00, got {cw_before - cw_after}"

        # (g) employee personal wallet unchanged
        w_after = requests.get(f"{API}/wallet", headers=emp_h, timeout=15).json()
        assert float(w_after.get("balance", 0)) == emp_wallet_before, \
            f"Employee personal wallet changed: {emp_wallet_before} -> {w_after.get('balance')}"


# -------------------- 3. Employee personal recharge blocked --------------------
class TestEmployeeWalletRechargeBlocked:
    def test_employee_personal_recharge_blocked(self, admin_ctx):
        admin_h = H(admin_ctx["token"])
        emp_email = f"emp_block_{TS}_{RUN}@democorp.com"
        r = requests.post(f"{API}/company/employees", json={
            "email": emp_email, "name": "Block Emp", "phone": "9000000002",
        }, headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text
        temp_password = r.json()["credentials"]["temp_password"]

        login = requests.post(f"{API}/auth/login", json={
            "email": emp_email, "password": temp_password,
        }, timeout=20)
        emp_token = login.json()["token"]

        r2 = requests.post(f"{API}/wallet/recharge", json={"amount": 100},
                           headers=H(emp_token), timeout=15)
        assert 400 <= r2.status_code < 500, f"Expected 4xx for employee personal recharge, got {r2.status_code}"

    def test_admin_company_wallet_recharge_ok(self, admin_ctx):
        r = requests.post(f"{API}/company/wallet/recharge", json={"amount": 250},
                          headers=H(admin_ctx["token"]), timeout=20)
        assert r.status_code == 200, r.text
        assert "new_balance" in r.json() or "balance" in r.json()


# -------------------- 4. Backend regression --------------------
class TestBackendRegression:
    def test_otp_verify_returns_token(self):
        phone = f"98765{TS % 100000:05d}"[-10:]
        requests.post(f"{API}/auth/otp/request", json={"phone": phone}, timeout=15)
        r = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "otp": "123456"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("token")
        assert d.get("user", {}).get("role") in ("user", "employee", "admin", None) or "user" in d

    def test_individual_wallet_get(self, individual_token):
        r = requests.get(f"{API}/wallet", headers=H(individual_token), timeout=15)
        assert r.status_code == 200
        assert "balance" in r.json()

    def test_individual_expense_list(self, individual_token):
        r = requests.get(f"{API}/expenses", headers=H(individual_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Response can be list or {expenses: []}
        if isinstance(data, dict):
            assert "expenses" in data and isinstance(data["expenses"], list)
        else:
            assert isinstance(data, list)

    def test_individual_bill_generate(self, individual_token):
        # recharge first to ensure balance
        requests.post(f"{API}/wallet/recharge", json={"amount": 50},
                      headers=H(individual_token), timeout=15)
        # create paid expense
        r = requests.post(f"{API}/expenses",
                          json=make_food_expense_payload(skipped=False),
                          headers=H(individual_token), timeout=20)
        assert r.status_code == 200
        eid = r.json()["id"]
        b = requests.post(f"{API}/bills/{eid}/generate", headers=H(individual_token), timeout=30)
        assert b.status_code == 200, f"Individual bill gen failed: {b.status_code} {b.text}"
