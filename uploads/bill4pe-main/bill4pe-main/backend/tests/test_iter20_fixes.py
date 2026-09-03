"""Iteration 20 — focused re-test.

FIX 1: GET /api/superadmin/stats -> activity.bills_total must reflect real
count of expenses with bill_generated=True (was hardcoded 0).
Regression: individual expense + wallet bill generation still works.
"""
import os
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
        "notes": "TEST expense iter20",
    }


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def super_token(s):
    r = s.post(f"{BASE}/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PW})
    if r.status_code != 200:
        pytest.fail(f"super admin login failed {r.status_code} {r.text[:300]}")
    return r.json()["token"]


class TestSuperAdminBillsTotalFix:
    def test_stats_shape(self, s, super_token):
        r = s.get(f"{BASE}/superadmin/stats", headers=hdr(super_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert "activity" in d and "revenue" in d
        assert isinstance(d["activity"]["bills_total"], int)
        assert d["activity"]["bills_total"] > 0, "bills_total should be >0 given existing revenue"
        assert d["revenue"]["platform_fees_collected"] > 0
        # no contradiction: fees collected implies bills exist
        assert not (d["revenue"]["platform_fees_collected"] > 0 and d["activity"]["bills_total"] == 0)

    def test_bills_total_increments_after_bill_generation(self, s, super_token):
        before = s.get(f"{BASE}/superadmin/stats", headers=hdr(super_token)).json()
        b_bills = before["activity"]["bills_total"]
        b_fees = before["revenue"]["platform_fees_collected"]
        b_exp = before["activity"]["expenses_total"]

        # fresh individual
        email = uniq("indiv20")
        reg = s.post(f"{BASE}/auth/register", json={"email": email, "password": PW, "name": "TEST Indiv20"})
        assert reg.status_code == 200, reg.text
        tok = reg.json()["token"]
        assert reg.json()["user"]["wallet_balance"] == 50.0

        e = s.post(f"{BASE}/expenses", json=expense_payload(1000.0), headers=hdr(tok))
        assert e.status_code == 200, e.text
        eid = e.json()["id"]
        assert e.json()["bill_generated"] is False

        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(tok))
        assert g.status_code == 200, g.text
        gd = g.json()
        assert gd["bill_id"].startswith("B4P-")
        assert gd["fee"] == 10.0
        assert gd["fee_paid_via"] == "wallet"

        after = s.get(f"{BASE}/superadmin/stats", headers=hdr(super_token)).json()
        assert after["activity"]["bills_total"] == b_bills + 1, (
            f"bills_total {b_bills} -> {after['activity']['bills_total']}")
        assert after["activity"]["expenses_total"] == b_exp + 1
        assert after["revenue"]["platform_fees_collected"] == round(b_fees + 10.0, 2)

    def test_stats_requires_super_admin(self, s):
        email = uniq("nonadmin20")
        reg = s.post(f"{BASE}/auth/register", json={"email": email, "password": PW, "name": "TEST NonAdmin"})
        assert reg.status_code == 200, reg.text
        r = s.get(f"{BASE}/superadmin/stats", headers=hdr(reg.json()["token"]))
        assert r.status_code == 403, r.text
        assert s.get(f"{BASE}/superadmin/stats").status_code in (401, 403)


class TestCorporateRegression:
    def test_corporate_dashboard_and_employee_autobill(self, s):
        aemail = uniq("corp20")
        ra = s.post(f"{BASE}/auth/register", json={
            "email": aemail, "password": PW, "name": "TEST Corp20 Admin",
            "user_type": "corporate", "corporate_name": "TEST Corp20 Pvt Ltd",
            "subscription_plan": "monthly_50", "employee_limit": 50,
        })
        assert ra.status_code == 200, ra.text
        atok = ra.json()["token"]

        me = s.get(f"{BASE}/company/me", headers=hdr(atok))
        assert me.status_code == 200, me.text
        assert "_id" not in me.json()["company"]
        for k in ("employees", "pending_approvals", "month_spend", "wallet_balance"):
            assert k in me.json()["stats"]

        rc = s.post(f"{BASE}/company/wallet/recharge", json={"amount": 1000.0}, headers=hdr(atok))
        assert rc.status_code == 200, rc.text
        bal_before = float(s.get(f"{BASE}/company/wallet", headers=hdr(atok)).json()["balance"])

        emp = s.post(f"{BASE}/company/employees", json={"email": uniq("emp20"), "name": "TEST Emp20"},
                     headers=hdr(atok))
        assert emp.status_code == 200, emp.text
        creds = emp.json()["credentials"]
        lg = s.post(f"{BASE}/auth/login", json={"email": creds["email"], "password": creds["temp_password"]})
        assert lg.status_code == 200, lg.text
        etok = lg.json()["token"]

        ex = s.post(f"{BASE}/expenses", json=expense_payload(2000.0, "travel"), headers=hdr(etok))
        assert ex.status_code == 200, ex.text
        ed = ex.json()
        assert ed["bill_generated"] is True, ed
        assert ed["bill_fee"] == 20.0
        w = s.get(f"{BASE}/company/wallet", headers=hdr(atok))
        assert float(w.json()["balance"]) == round(bal_before - 20.0, 2)
