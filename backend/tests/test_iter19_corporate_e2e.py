"""Iteration 19 — E2E: individual, corporate admin, employee, invite flow, role guards.

Covers: /api/auth/register|login, /api/company/* (me, wallet, employees, invite,
approvals), /api/expenses (employee auto-bill), /api/bills/{id}/generate (wallet fee),
/api/payments/config graceful degradation.
"""
import os
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

SUPER_EMAIL = "ujjwal@bill4pe.com"
SUPER_PW = "03PfTZY6W76PrZAa1!"
PW = "Test@1234"


def uniq(p):
    return f"TEST_{p}_{uuid.uuid4().hex[:8]}@example.com"


def hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def expense_payload(amount=1000.0, category="food"):
    return {
        "category": category,
        "sub_category": "restaurant",
        "items": [{"name": "TEST_item", "quantity": 1, "unit_price": amount}],
        "payment": {
            "merchant_name": "TEST Merchant",
            "merchant_upi": "test@upi",
            "transaction_id": f"TXN{uuid.uuid4().hex[:10].upper()}",
            "amount": amount,
            "payment_method": "UPI",
            "payment_status": "paid",
        },
        "notes": "TEST expense",
    }


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def individual(s):
    email = uniq("indiv")
    r = s.post(f"{BASE}/auth/register", json={"email": email, "password": PW, "name": "TEST Individual"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"]["role"] == "individual"
    assert d["user"]["wallet_balance"] == 50.0
    return {"token": d["token"], "user": d["user"], "email": email}


@pytest.fixture(scope="module")
def corporate(s):
    email = uniq("corpadmin")
    r = s.post(f"{BASE}/auth/register", json={
        "email": email, "password": PW, "name": "TEST Corp Admin",
        "user_type": "corporate", "corporate_name": "TEST Corp Pvt Ltd",
        "subscription_plan": "monthly_50", "employee_limit": 50,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"]["role"] == "admin"
    assert d["user"]["company_id"]
    return {"token": d["token"], "user": d["user"], "email": email}


# ---------------- health / payments config ----------------

class TestHealthAndConfig:
    def test_payments_config_disabled_gracefully(self, s, individual):
        r = s.get(f"{BASE}/payments/config", headers=hdr(individual["token"]))
        assert r.status_code == 200, r.text
        assert r.json().get("enabled") is False

    def test_super_admin_login(self, s):
        r = s.post(f"{BASE}/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PW})
        assert r.status_code == 200, r.text
        u = r.json()["user"]
        assert u["email"] == SUPER_EMAIL
        assert r.json()["token"]
        assert u.get("role") in ("super_admin", "superadmin", "admin"), u.get("role")

    def test_login_wrong_password(self, s, individual):
        r = s.post(f"{BASE}/auth/login", json={"email": individual["email"], "password": "wrongpw"})
        assert r.status_code == 401


# ---------------- individual expense + wallet bill generation ----------------

class TestIndividualFlow:
    def test_expense_create_and_generate_bill_from_wallet(self, s, individual):
        tok = individual["token"]
        # wallet has Rs 50; use an expense whose 1% fee is affordable
        r = s.post(f"{BASE}/expenses", json=expense_payload(1000.0), headers=hdr(tok))
        assert r.status_code == 200, r.text
        exp = r.json()
        assert exp["total"] == 1000.0
        assert exp["bill_generated"] is False
        assert exp.get("company_id") is None
        eid = exp["id"]

        wallet_before = s.get(f"{BASE}/wallet", headers=hdr(tok))
        assert wallet_before.status_code == 200, wallet_before.text
        bal_before = float(wallet_before.json()["balance"])

        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(tok))
        assert g.status_code == 200, g.text
        gd = g.json()
        assert gd["bill_id"].startswith("B4P-")
        assert gd["fee"] == 10.0
        assert gd["fee_paid_via"] == "wallet"
        assert gd["wallet_balance"] == round(bal_before - 10.0, 2)

        # persistence
        gv = s.get(f"{BASE}/expenses/{eid}", headers=hdr(tok))
        assert gv.status_code == 200
        assert gv.json()["bill_generated"] is True
        assert gv.json()["bill_id"] == gd["bill_id"]

        # pdf downloadable
        p = s.get(f"{BASE}/bills/{eid}/pdf", headers=hdr(tok))
        assert p.status_code == 200, p.text
        assert p.content[:4] == b"%PDF"

    def test_generate_bill_insufficient_wallet_returns_402(self, s, individual):
        tok = individual["token"]
        r = s.post(f"{BASE}/expenses", json=expense_payload(500000.0), headers=hdr(tok))
        assert r.status_code == 200, r.text
        eid = r.json()["id"]
        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(tok))
        assert g.status_code == 402, g.text
        assert "Insufficient wallet balance" in g.json().get("detail", "")

    def test_razorpay_order_disabled_graceful(self, s, individual):
        r = s.post(f"{BASE}/payments/razorpay/order",
                   json={"amount": 10, "purpose": "bill_fee"}, headers=hdr(individual["token"]))
        assert r.status_code in (400, 503), f"{r.status_code} {r.text}"


# ---------------- corporate admin ----------------

class TestCorporateAdmin:
    def test_company_me_stats(self, s, corporate):
        r = s.get(f"{BASE}/company/me", headers=hdr(corporate["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["company"]["name"] == "TEST Corp Pvt Ltd"
        assert "_id" not in d["company"]
        for k in ("employees", "pending_approvals", "month_spend", "wallet_balance"):
            assert k in d["stats"]
        assert d["stats"]["employees"] == 0

    def test_wallet_recharge_and_balance(self, s, corporate):
        tok = corporate["token"]
        before = s.get(f"{BASE}/company/wallet", headers=hdr(tok))
        assert before.status_code == 200, before.text
        b0 = float(before.json()["balance"])
        r = s.post(f"{BASE}/company/wallet/recharge", json={"amount": 500.0}, headers=hdr(tok))
        assert r.status_code == 200, r.text
        assert r.json()["balance"] == round(b0 + 500.0, 2)
        after = s.get(f"{BASE}/company/wallet", headers=hdr(tok))
        assert float(after.json()["balance"]) == round(b0 + 500.0, 2)
        txns = after.json()["transactions"]
        assert any(t["type"] == "credit" and t["amount"] == 500.0 for t in txns)
        assert all("_id" not in t for t in txns)

    def test_recharge_validation(self, s, corporate):
        tok = corporate["token"]
        assert s.post(f"{BASE}/company/wallet/recharge", json={"amount": 0}, headers=hdr(tok)).status_code == 400
        assert s.post(f"{BASE}/company/wallet/recharge", json={"amount": 200000}, headers=hdr(tok)).status_code == 400

    def test_create_employee_returns_credentials(self, s, corporate):
        tok = corporate["token"]
        email = uniq("emp")
        r = s.post(f"{BASE}/company/employees", json={
            "email": email, "name": "TEST Employee One",
            "phone": "9876543210", "department": "Sales", "designation": "Exec",
            "employee_id": "E001", "monthly_cap": 5000,
        }, headers=hdr(tok))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["credentials"]["email"] == email.lower()
        assert len(d["credentials"]["temp_password"]) >= 8
        assert d["employee"]["status"] == "active"
        # appears in list
        lst = s.get(f"{BASE}/company/employees", headers=hdr(tok))
        assert lst.status_code == 200
        emails = [e["email"] for e in lst.json()["employees"]]
        assert email.lower() in emails
        # duplicate email rejected
        dup = s.post(f"{BASE}/company/employees", json={"email": email, "name": "dup"}, headers=hdr(tok))
        assert dup.status_code == 400

    def test_approvals_endpoint_shape(self, s, corporate):
        r = s.get(f"{BASE}/company/approvals", headers=hdr(corporate["token"]))
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["approvals"], list)
        # documented finding: pending is always empty because create_expense forces 'approved'
        assert r.json()["approvals"] == []
        appr = s.get(f"{BASE}/company/approvals?status=approved", headers=hdr(corporate["token"]))
        assert appr.status_code == 200


# ---------------- employee auto-bill ----------------

class TestEmployeeAutoBill:
    def test_employee_login_and_autobill_to_company_wallet(self, s, corporate):
        atok = corporate["token"]
        # fund the company wallet
        s.post(f"{BASE}/company/wallet/recharge", json={"amount": 1000.0}, headers=hdr(atok))
        bal_before = float(s.get(f"{BASE}/company/wallet", headers=hdr(atok)).json()["balance"])

        email = uniq("empauto")
        r = s.post(f"{BASE}/company/employees", json={"email": email, "name": "TEST Emp Auto"},
                   headers=hdr(atok))
        assert r.status_code == 200, r.text
        creds = r.json()["credentials"]

        lg = s.post(f"{BASE}/auth/login", json={"email": creds["email"], "password": creds["temp_password"]})
        assert lg.status_code == 200, lg.text
        emp = lg.json()["user"]
        assert emp["role"] == "employee"
        assert emp["company_id"] == corporate["user"]["company_id"]
        etok = lg.json()["token"]

        e = s.post(f"{BASE}/expenses", json=expense_payload(2000.0, "travel"), headers=hdr(etok))
        assert e.status_code == 200, e.text
        ed = e.json()
        assert ed["bill_generated"] is True, ed
        assert ed["bill_id"].startswith("B4P-")
        assert ed["bill_fee"] == 20.0
        assert ed["auto_generated"] is True
        assert ed["approval_status"] == "approved"
        assert ed["company_id"] == corporate["user"]["company_id"]

        w = s.get(f"{BASE}/company/wallet", headers=hdr(atok))
        assert float(w.json()["balance"]) == round(bal_before - 20.0, 2)
        assert any(t["type"] == "debit" and t["amount"] == 20.0 and ed["bill_id"] in (t.get("reason") or "")
                   for t in w.json()["transactions"])

        # company stats month_spend picks it up
        me = s.get(f"{BASE}/company/me", headers=hdr(atok))
        assert me.json()["stats"]["month_spend"] >= 2000.0

    def test_employee_expense_when_company_wallet_empty(self, s):
        # separate company with an empty wallet
        aemail = uniq("corp2")
        ra = s.post(f"{BASE}/auth/register", json={
            "email": aemail, "password": PW, "name": "TEST Corp2 Admin",
            "user_type": "corporate", "corporate_name": "TEST Corp2", "employee_limit": 50,
        })
        assert ra.status_code == 200, ra.text
        atok = ra.json()["token"]
        assert float(s.get(f"{BASE}/company/wallet", headers=hdr(atok)).json()["balance"]) == 0.0

        r = s.post(f"{BASE}/company/employees", json={"email": uniq("emp2"), "name": "TEST Emp2"},
                   headers=hdr(atok))
        creds = r.json()["credentials"]
        etok = s.post(f"{BASE}/auth/login", json={"email": creds["email"],
                                                 "password": creds["temp_password"]}).json()["token"]
        e = s.post(f"{BASE}/expenses", json=expense_payload(1500.0), headers=hdr(etok))
        assert e.status_code == 200, e.text
        ed = e.json()
        assert ed["bill_generated"] is False
        assert "bill_pending_reason" in ed

        # manual generate must 402 (company wallet short), not crash
        g = s.post(f"{BASE}/bills/{ed['id']}/generate", json={}, headers=hdr(etok))
        assert g.status_code == 402, g.text
        assert "Company wallet" in g.json().get("detail", "")


# ---------------- invite flow ----------------

class TestInviteFlow:
    def test_invite_lookup_accept_and_login(self, s, corporate):
        atok = corporate["token"]
        email = uniq("invitee")
        r = s.post(f"{BASE}/company/employees/invite", json={
            "email": email, "name": "TEST Invitee", "department": "Ops",
        }, headers=hdr(atok))
        assert r.status_code == 200, r.text
        token = r.json()["invite"]["token"]
        assert r.json()["employee"]["status"] == "pending_invite"

        look = s.get(f"{BASE}/company/invite/{token}")
        assert look.status_code == 200, look.text
        assert look.json()["email"] == email.lower()
        assert look.json()["company_name"] == "TEST Corp Pvt Ltd"

        short = s.post(f"{BASE}/company/invite/accept", json={"token": token, "password": "abc"})
        assert short.status_code == 400, short.text

        acc = s.post(f"{BASE}/company/invite/accept", json={"token": token, "password": PW})
        assert acc.status_code == 200, acc.text
        assert acc.json()["user"]["role"] == "employee"
        assert acc.json()["token"]

        # token now consumed
        assert s.get(f"{BASE}/company/invite/{token}").status_code == 404
        lg = s.post(f"{BASE}/auth/login", json={"email": email.lower(), "password": PW})
        assert lg.status_code == 200, lg.text
        assert lg.json()["user"]["role"] == "employee"

    def test_invite_bad_token(self, s):
        assert s.get(f"{BASE}/company/invite/nonexistent-token").status_code == 404
        assert s.post(f"{BASE}/company/invite/accept",
                      json={"token": "nope", "password": PW}).status_code == 404


# ---------------- role guards ----------------

class TestRoleGuards:
    ADMIN_GETS = ["/company/me", "/company/employees", "/company/approvals", "/company/wallet"]

    def test_individual_blocked_from_admin_endpoints(self, s, individual):
        for ep in self.ADMIN_GETS:
            r = s.get(f"{BASE}{ep}", headers=hdr(individual["token"]))
            assert r.status_code == 403, f"{ep} -> {r.status_code} {r.text[:120]}"
        r = s.post(f"{BASE}/company/wallet/recharge", json={"amount": 100}, headers=hdr(individual["token"]))
        assert r.status_code == 403, r.text

    def test_employee_blocked_from_admin_endpoints(self, s, corporate):
        r = s.post(f"{BASE}/company/employees", json={"email": uniq("guard"), "name": "TEST Guard"},
                   headers=hdr(corporate["token"]))
        creds = r.json()["credentials"]
        etok = s.post(f"{BASE}/auth/login", json={"email": creds["email"],
                                                 "password": creds["temp_password"]}).json()["token"]
        for ep in self.ADMIN_GETS:
            resp = s.get(f"{BASE}{ep}", headers=hdr(etok))
            assert resp.status_code == 403, f"{ep} -> {resp.status_code} {resp.text[:120]}"
        assert s.post(f"{BASE}/company/wallet/recharge", json={"amount": 100},
                      headers=hdr(etok)).status_code == 403

    def test_unauthenticated_rejected(self, s):
        assert s.get(f"{BASE}/company/me").status_code in (401, 403)
