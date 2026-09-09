"""Iteration 21 — Super-Admin-configurable BILL GENERATION FEE % per user type.

Covers:
  * GET/PUT /api/superadmin/bill-fees (persistence, validation, 403 for non-super)
  * Individual rate applied on POST /api/bills/{id}/generate (+ persistence on /expenses)
  * Corporate EMPLOYEE auto-bill debits COMPANY wallet at the CORPORATE rate
  * GET /api/bills/fee-info per caller type
  * Zero rate (no Rs.1 min) and Rs.1 minimum for tiny totals
  * Regression: /superadmin/stats
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
        "notes": "TEST expense iter21",
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


def set_fees(s, tok, **kw):
    r = s.put(f"{BASE}/superadmin/bill-fees", json=kw, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


def post_rl(s, path, **kw):
    """POST that respects the app's 429 rate limiter (auth routes: 5-10/min)."""
    for _ in range(8):
        r = s.post(f"{BASE}{path}", **kw)
        if r.status_code != 429:
            return r
        time.sleep(int(r.headers.get("Retry-After", 10)) + 1)
    return r


def new_individual(s, tag="indiv"):
    email = uniq(tag)
    r = post_rl(s, "/auth/register", json={"email": email, "password": PW, "name": "TEST Indiv"})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"], email


def new_corporate(s, tag="corp"):
    email = uniq(tag)
    r = post_rl(s, "/auth/register", json={
        "email": email, "password": PW, "name": f"TEST {tag} Admin",
        "user_type": "corporate", "corporate_name": f"TEST {tag} Pvt Ltd",
        "subscription_plan": "monthly_50", "employee_limit": 50,
    })
    assert r.status_code == 200, r.text
    return r.json()["token"], email


def temp_pw_of(resp_json):
    return ((resp_json.get("credentials") or {}).get("temp_password")
            or resp_json.get("temp_password") or resp_json.get("password"))


# ---------------- Super admin bill-fee API ----------------
class TestSuperAdminBillFeeAPI:
    def test_get_returns_both_rates(self, s, super_token):
        r = s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(super_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["individual", "corporate"]).issubset(d.keys())
        assert isinstance(d["individual"], (int, float))
        assert isinstance(d["corporate"], (int, float))

    def test_put_persists_and_reflected_on_get(self, s, super_token):
        upd = set_fees(s, super_token, individual=3, corporate=7)
        assert upd["individual"] == 3.0 and upd["corporate"] == 7.0
        g = s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(super_token))
        assert g.status_code == 200
        assert g.json()["individual"] == 3.0
        assert g.json()["corporate"] == 7.0

    def test_partial_update_keeps_other(self, s, super_token):
        set_fees(s, super_token, individual=3, corporate=7)
        upd = set_fees(s, super_token, individual=4)
        assert upd["individual"] == 4.0 and upd["corporate"] == 7.0
        set_fees(s, super_token, individual=3)

    @pytest.mark.parametrize("payload", [
        {"individual": -1}, {"corporate": -0.5}, {"individual": 101}, {"corporate": 100.5},
    ])
    def test_out_of_range_rejected(self, s, super_token, payload):
        r = s.put(f"{BASE}/superadmin/bill-fees", json=payload, headers=hdr(super_token))
        assert r.status_code == 400, f"{payload} -> {r.status_code} {r.text[:200]}"
        # rejected value must not have been persisted
        g = s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(super_token)).json()
        assert g["individual"] == 3.0 and g["corporate"] == 7.0, g

    def test_empty_body_rejected(self, s, super_token):
        r = s.put(f"{BASE}/superadmin/bill-fees", json={}, headers=hdr(super_token))
        assert r.status_code == 400, r.text

    def test_non_superadmin_forbidden(self, s, super_token):
        itok, _, _ = new_individual(s, "nonadmin")
        assert s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(itok)).status_code == 403
        assert s.put(f"{BASE}/superadmin/bill-fees", json={"individual": 99},
                     headers=hdr(itok)).status_code == 403
        # corporate admin also forbidden
        ctok, _ = new_corporate(s, "corpnonadmin")
        assert s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(ctok)).status_code == 403
        assert s.put(f"{BASE}/superadmin/bill-fees", json={"corporate": 99},
                     headers=hdr(ctok)).status_code == 403
        # unauthenticated
        assert s.get(f"{BASE}/superadmin/bill-fees").status_code in (401, 403)

    def test_rates_unchanged_after_forbidden_attempts(self, s, super_token):
        g = s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(super_token)).json()
        assert g["individual"] == 3.0 and g["corporate"] == 7.0, g


# ---------------- fee-info endpoint ----------------
class TestFeeInfo:
    def test_individual_gets_individual_rate(self, s, super_token):
        set_fees(s, super_token, individual=3, corporate=7)
        itok, _, _ = new_individual(s, "feeinfo")
        r = s.get(f"{BASE}/bills/fee-info", headers=hdr(itok))
        assert r.status_code == 200, r.text
        assert r.json() == {"kind": "individual", "percent": 3.0}

    @pytest.mark.skip(reason="Superseded by iter23: corporate accounts are on a monthly subscription -> per-bill fee is always 0")
    def test_corporate_admin_and_employee_get_corporate_rate(self, s, super_token):
        set_fees(s, super_token, individual=3, corporate=7)
        atok, _ = new_corporate(s, "corpfi")
        r = s.get(f"{BASE}/bills/fee-info", headers=hdr(atok))
        assert r.status_code == 200, r.text
        assert r.json() == {"kind": "corporate", "percent": 7.0}

        eemail = uniq("empfi")
        emp = s.post(f"{BASE}/company/employees", json={"email": eemail, "name": "TEST Emp FI"},
                     headers=hdr(atok))
        assert emp.status_code == 200, emp.text
        temp_pw = temp_pw_of(emp.json())
        assert temp_pw, emp.json()
        el = post_rl(s, "/auth/login", json={"email": eemail, "password": temp_pw})
        assert el.status_code == 200, el.text
        r2 = s.get(f"{BASE}/bills/fee-info", headers=hdr(el.json()["token"]))
        assert r2.status_code == 200, r2.text
        assert r2.json() == {"kind": "corporate", "percent": 7.0}

    def test_fee_info_requires_auth(self, s):
        assert s.get(f"{BASE}/bills/fee-info").status_code in (401, 403)


# ---------------- Individual rate applied ----------------
class TestIndividualRateApplied:
    def test_individual_bill_charged_at_configured_rate(self, s, super_token):
        set_fees(s, super_token, individual=3, corporate=7)
        tok, user, _ = new_individual(s, "rate3")
        assert user["wallet_balance"] == 50.0

        e = s.post(f"{BASE}/expenses", json=expense_payload(1000.0), headers=hdr(tok))
        assert e.status_code == 200, e.text
        eid = e.json()["id"]
        assert e.json()["total"] == 1000.0

        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(tok))
        assert g.status_code == 200, g.text
        d = g.json()
        assert d["fee"] == 30.0, d
        assert d["fee_percent"] == 3.0, d
        assert d["fee_paid_via"] == "wallet"
        assert d["wallet_balance"] == 20.0, d
        assert d["bill_id"].startswith("B4P-")

        # persisted on expense
        lst = s.get(f"{BASE}/expenses", headers=hdr(tok))
        assert lst.status_code == 200
        rows = lst.json() if isinstance(lst.json(), list) else lst.json().get("expenses", [])
        row = next(x for x in rows if x["id"] == eid)
        assert row["bill_fee"] == 30.0
        assert row["bill_fee_percent"] == 3.0
        assert row["bill_generated"] is True

        # wallet txn records the debit
        w = s.get(f"{BASE}/wallet", headers=hdr(tok))
        assert w.status_code == 200, w.text
        assert float(w.json()["balance"]) == 20.0
        txns = w.json().get("txns") or w.json().get("transactions") or []
        assert any(t["type"] == "debit" and float(t["amount"]) == 30.0 for t in txns), txns

    def test_rate_change_affects_next_bill_immediately(self, s, super_token):
        tok, _, _ = new_individual(s, "ratechg")
        # first bill at 3%
        e1 = s.post(f"{BASE}/expenses", json=expense_payload(100.0), headers=hdr(tok)).json()["id"]
        set_fees(s, super_token, individual=3)
        g1 = s.post(f"{BASE}/bills/{e1}/generate", json={}, headers=hdr(tok)).json()
        assert g1["fee"] == 3.0 and g1["fee_percent"] == 3.0, g1
        # change rate -> next bill uses new rate
        set_fees(s, super_token, individual=10)
        e2 = s.post(f"{BASE}/expenses", json=expense_payload(100.0), headers=hdr(tok)).json()["id"]
        g2 = s.post(f"{BASE}/bills/{e2}/generate", json={}, headers=hdr(tok)).json()
        assert g2["fee"] == 10.0 and g2["fee_percent"] == 10.0, g2
        set_fees(s, super_token, individual=3)


# ---------------- Corporate employee rate applied ----------------
class TestCorporateEmployeeRateApplied:
    @pytest.mark.skip(reason="Superseded by iter23: corporate accounts are on a monthly subscription -> per-bill fee is always 0")
    def test_employee_autobill_uses_corporate_rate_on_company_wallet(self, s, super_token):
        set_fees(s, super_token, individual=3, corporate=7)
        atok, aemail = new_corporate(s, "corp21")

        rc = s.post(f"{BASE}/company/wallet/recharge", json={"amount": 1000.0}, headers=hdr(atok))
        assert rc.status_code == 200, rc.text
        bal_before = float(s.get(f"{BASE}/company/wallet", headers=hdr(atok)).json()["balance"])

        eemail = uniq("emp21")
        emp = s.post(f"{BASE}/company/employees", json={"email": eemail, "name": "TEST Emp21"},
                     headers=hdr(atok))
        assert emp.status_code == 200, emp.text
        temp_pw = temp_pw_of(emp.json())
        assert temp_pw, emp.json()
        el = post_rl(s, "/auth/login", json={"email": eemail, "password": temp_pw})
        assert el.status_code == 200, el.text
        etok = el.json()["token"]

        e = s.post(f"{BASE}/expenses", json=expense_payload(1000.0), headers=hdr(etok))
        assert e.status_code == 200, e.text
        ed = e.json()
        assert ed["bill_generated"] is True, f"employee bill should auto-generate: {ed}"
        assert ed["bill_fee"] == 70.0, ed
        assert ed["bill_fee_percent"] == 7.0, ed

        wal = s.get(f"{BASE}/company/wallet", headers=hdr(atok))
        assert wal.status_code == 200, wal.text
        wd = wal.json()
        assert float(wd["balance"]) == round(bal_before - 70.0, 2), wd
        txns = wd.get("txns") or wd.get("transactions") or []
        debits = [t for t in txns if t["type"] == "debit"]
        assert any(float(t["amount"]) == 70.0 for t in debits), debits
        assert not any(float(t["amount"]) == 30.0 for t in debits), \
            "company wallet debited at INDIVIDUAL rate — wrong rate applied"

    @pytest.mark.skip(reason="Superseded by iter23: corporate accounts are on a monthly subscription -> per-bill fee is always 0")
    def test_corporate_admin_own_bill_uses_corporate_rate(self, s, super_token):
        set_fees(s, super_token, individual=3, corporate=7)
        atok, _ = new_corporate(s, "corpown")
        # keep fee <= personal wallet (Rs.50): total 500 @7% = 35
        e = s.post(f"{BASE}/expenses", json=expense_payload(500.0), headers=hdr(atok))
        assert e.status_code == 200, e.text
        eid = e.json()["id"]
        if e.json().get("bill_generated"):
            assert e.json()["bill_fee_percent"] == 7.0
            return
        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(atok))
        assert g.status_code == 200, g.text
        assert g.json()["fee_percent"] == 7.0, g.json()
        assert g.json()["fee"] == 35.0, g.json()


# ---------------- Zero rate & minimum ----------------
class TestZeroRateAndMinimum:
    def test_zero_rate_generates_free_bill(self, s, super_token):
        set_fees(s, super_token, individual=0)
        assert s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(super_token)).json()["individual"] == 0.0
        tok, _, _ = new_individual(s, "zero")
        r = s.get(f"{BASE}/bills/fee-info", headers=hdr(tok)).json()
        assert r == {"kind": "individual", "percent": 0.0}
        eid = s.post(f"{BASE}/expenses", json=expense_payload(1000.0), headers=hdr(tok)).json()["id"]
        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(tok))
        assert g.status_code == 200, g.text
        assert g.json()["fee"] == 0.0, g.json()
        assert g.json()["fee_percent"] == 0.0
        assert g.json()["wallet_balance"] == 50.0, "no debit expected at 0%"
        assert g.json()["bill_id"].startswith("B4P-")

    def test_min_one_rupee_applies_for_nonzero_rate(self, s, super_token):
        set_fees(s, super_token, individual=1)
        tok, _, _ = new_individual(s, "minfee")
        eid = s.post(f"{BASE}/expenses", json=expense_payload(10.0), headers=hdr(tok)).json()["id"]
        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(tok))
        assert g.status_code == 200, g.text
        assert g.json()["fee"] == 1.0, f"raw 0.10 should be floored to Rs.1: {g.json()}"
        assert g.json()["wallet_balance"] == 49.0

    def test_restore_demo_values(self, s, super_token):
        upd = set_fees(s, super_token, individual=3, corporate=7)
        assert upd == {"individual": 3.0, "corporate": 7.0}


# ---------------- Regression ----------------
class TestRegression:
    def test_superadmin_stats(self, s, super_token):
        r = s.get(f"{BASE}/superadmin/stats", headers=hdr(super_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["activity"]["bills_total"] > 0
        assert d["revenue"]["platform_fees_collected"] > 0
        assert "_id" not in str(d)
