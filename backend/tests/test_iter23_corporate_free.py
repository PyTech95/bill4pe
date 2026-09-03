"""Iteration 23 — Corporate subscription => ZERO per-bill convenience fee.

Covers:
  * Corporate EMPLOYEE: expense auto-generates a bill directly, fee 0, EMPTY
    company wallet, no company wallet debit, no bill_pending_reason
  * Corporate ADMIN: fee-info 0, manual-pay config/first-scan 0, full manual
    flow to receipt with NO wallet deduction, /bills/{id}/generate fee 0
  * INDIVIDUAL: still charged the Super-Admin-configured %
  * Regression: role guards, superadmin stats
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


def post_rl(s, path, **kw):
    r = None
    for _ in range(8):
        r = s.post(f"{BASE}{path}", **kw)
        if r.status_code != 429:
            return r
        time.sleep(int(r.headers.get("Retry-After", 10)) + 1)
    return r


def expense_payload(amount=1000.0):
    return {
        "category": "food",
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
        "notes": "TEST expense iter23",
    }


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def super_token(s):
    r = post_rl(s, "/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PW})
    if r.status_code != 200:
        pytest.fail(f"super admin login failed {r.status_code} {r.text[:300]}")
    return r.json()["token"]


def set_individual(s, tok, pct):
    r = s.put(f"{BASE}/superadmin/bill-fees", json={"individual": pct}, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


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


def temp_pw_of(j):
    return ((j.get("credentials") or {}).get("temp_password")
            or j.get("temp_password") or j.get("password"))


def make_employee(s, atok, tag="emp"):
    eemail = uniq(tag)
    emp = s.post(f"{BASE}/company/employees", json={"email": eemail, "name": "TEST Emp23"},
                 headers=hdr(atok))
    assert emp.status_code == 200, emp.text
    tpw = temp_pw_of(emp.json())
    assert tpw, emp.json()
    el = post_rl(s, "/auth/login", json={"email": eemail, "password": tpw})
    assert el.status_code == 200, el.text
    return el.json()["token"], eemail


def first_scan(s, tok, amount=1000.0):
    r = s.post(f"{BASE}/manual-pay/first-scan", json={
        "payee_upi": f"testmerchant{uuid.uuid4().hex[:4]}@ybl",
        "payee_name": "TEST Merchant",
        "merchant_amount": amount,
    }, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


def submit_proof(tok, tid, utr):
    return requests.post(f"{BASE}/manual-pay/{tid}/proof", data={"utr_full": utr},
                         headers={"Authorization": f"Bearer {tok}"}, timeout=60)


# ---------------- CORE: corporate employee free + direct ----------------
class TestCorporateEmployeeFree:
    def test_employee_bill_free_with_empty_company_wallet(self, s, super_token):
        set_individual(s, super_token, 3)
        atok, _ = new_corporate(s, "empfree")

        w0 = s.get(f"{BASE}/company/wallet", headers=hdr(atok))
        assert w0.status_code == 200, w0.text
        bal_before = float(w0.json()["balance"])
        assert bal_before == 0.0, f"company wallet should start empty: {w0.json()}"

        etok, _ = make_employee(s, atok, "empfreeemp")
        e = s.post(f"{BASE}/expenses", json=expense_payload(5000.0), headers=hdr(etok))
        assert e.status_code == 200, e.text
        d = e.json()
        assert d.get("bill_generated") is True, d
        assert d.get("bill_id"), d
        assert d.get("bill_fee") == 0, d
        assert d.get("bill_fee_percent") == 0, d
        assert not d.get("bill_pending_reason"), d
        assert "_id" not in d

        w1 = s.get(f"{BASE}/company/wallet", headers=hdr(atok))
        assert float(w1.json()["balance"]) == bal_before, w1.json()
        txns = w1.json().get("transactions", [])
        assert not [t for t in txns if t.get("type") == "debit"], f"unexpected wallet debit: {txns}"

    def test_employee_unlimited_multiple_bills(self, s, super_token):
        atok, _ = new_corporate(s, "unlim")
        etok, _ = make_employee(s, atok, "unlimemp")
        bill_ids = set()
        for amt in (2500.0, 7000.0, 12000.0):
            e = s.post(f"{BASE}/expenses", json=expense_payload(amt), headers=hdr(etok))
            assert e.status_code == 200, e.text
            assert e.json()["bill_generated"] is True, e.json()
            assert e.json()["bill_fee"] == 0, e.json()
            bill_ids.add(e.json()["bill_id"])
        assert len(bill_ids) == 3, bill_ids
        assert float(s.get(f"{BASE}/company/wallet", headers=hdr(atok)).json()["balance"]) == 0.0

    def test_employee_fee_info_zero(self, s):
        atok, _ = new_corporate(s, "empfi")
        etok, _ = make_employee(s, atok, "empfiemp")
        r = s.get(f"{BASE}/bills/fee-info", headers=hdr(etok))
        assert r.status_code == 200, r.text
        assert r.json() == {"kind": "corporate", "percent": 0.0}, r.json()

    def test_employee_expense_persisted_with_bill(self, s):
        atok, _ = new_corporate(s, "emppers")
        etok, _ = make_employee(s, atok, "emppersemp")
        e = s.post(f"{BASE}/expenses", json=expense_payload(3000.0), headers=hdr(etok)).json()
        lst = s.get(f"{BASE}/expenses", headers=hdr(etok))
        assert lst.status_code == 200, lst.text
        rows = lst.json().get("expenses", [])
        row = next((x for x in rows if x["id"] == e["id"]), None)
        assert row, rows
        assert row["bill_generated"] is True and row["bill_id"] == e["bill_id"]
        assert row["bill_fee"] == 0


# ---------------- Corporate admin: zero fee everywhere ----------------
class TestCorporateAdminZeroFee:
    def test_fee_info_and_manual_config_zero(self, s, super_token):
        set_individual(s, super_token, 3)
        atok, _ = new_corporate(s, "cadmin")
        fi = s.get(f"{BASE}/bills/fee-info", headers=hdr(atok))
        assert fi.status_code == 200, fi.text
        assert fi.json() == {"kind": "corporate", "percent": 0.0}, fi.json()

        c = s.get(f"{BASE}/manual-pay/config", headers=hdr(atok))
        assert c.status_code == 200, c.text
        assert c.json()["platform_fee_percent"] == "0", c.json()

        t = first_scan(s, atok, 1000.0)
        assert t["platform_fee_percent"] in ("0", "0.00"), t
        assert t["platform_fee"] == 0.0, t
        assert t["merchant_amount"] == 1000.0, t

    def test_manual_flow_end_to_end_no_wallet_deduction(self, s):
        atok, _ = new_corporate(s, "cadmine2e")
        w = s.get(f"{BASE}/wallet", headers=hdr(atok))
        assert w.status_code == 200, w.text
        bal_before = float(w.json()["balance"])

        t = first_scan(s, atok, 1000.0)
        tid = t["transaction_id"]
        cf = s.post(f"{BASE}/manual-pay/{tid}/confirm", json={"completed": True}, headers=hdr(atok))
        assert cf.status_code == 200, cf.text
        utr = "".join(str((i * 7 + 3) % 10) for i in range(12))
        pr = submit_proof(atok, tid, utr)
        assert pr.status_code == 200, pr.text
        gen = s.post(f"{BASE}/manual-pay/{tid}/generate", json={}, headers=hdr(atok))
        assert gen.status_code == 200, gen.text
        gd = gen.json()
        assert gd.get("generated") is True, gd
        assert gd.get("bill_id"), gd
        assert gd.get("platform_fee") == 0.0, gd

        w2 = s.get(f"{BASE}/wallet", headers=hdr(atok))
        assert float(w2.json()["balance"]) == bal_before, w2.json()
        debits = [x for x in w2.json().get("transactions", []) if x.get("type") == "debit"
                  and float(x.get("amount") or 0) > 0]
        assert not debits, f"corporate admin was debited: {debits}"

    def test_generate_bill_zero_fee_without_wallet_balance(self, s):
        atok, _ = new_corporate(s, "cadmingen")
        eid = s.post(f"{BASE}/expenses", json=expense_payload(9000.0), headers=hdr(atok)).json()["id"]
        bal_before = float(s.get(f"{BASE}/wallet", headers=hdr(atok)).json()["balance"])
        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(atok))
        assert g.status_code == 200, g.text
        gd = g.json()
        assert gd["fee"] == 0.0 and gd["fee_percent"] == 0.0, gd
        assert gd["bill_id"], gd
        assert float(s.get(f"{BASE}/wallet", headers=hdr(atok)).json()["balance"]) == bal_before

        # persisted
        rows = s.get(f"{BASE}/expenses", headers=hdr(atok)).json()["expenses"]
        row = next(x for x in rows if x["id"] == eid)
        assert row["bill_generated"] is True and row["bill_fee"] == 0.0


# ---------------- Individual still charged ----------------
class TestIndividualStillCharged:
    def test_individual_fee_info_and_generate(self, s, super_token):
        set_individual(s, super_token, 3)
        tok, user, _ = new_individual(s, "ind3")
        fi = s.get(f"{BASE}/bills/fee-info", headers=hdr(tok))
        assert fi.json() == {"kind": "individual", "percent": 3.0}, fi.json()

        bal_before = float(user["wallet_balance"])
        eid = s.post(f"{BASE}/expenses", json=expense_payload(1000.0), headers=hdr(tok)).json()["id"]
        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(tok))
        assert g.status_code == 200, g.text
        gd = g.json()
        assert gd["fee"] == 30.0 and gd["fee_percent"] == 3.0, gd
        assert gd["wallet_balance"] == round(bal_before - 30.0, 2), gd
        wt = s.get(f"{BASE}/wallet", headers=hdr(tok)).json()
        assert float(wt["balance"]) == round(bal_before - 30.0, 2), wt
        assert any(float(x["amount"]) == 30.0 for x in wt["transactions"] if x["type"] == "debit"), wt

    def test_individual_manual_first_scan_charged(self, s, super_token):
        set_individual(s, super_token, 3)
        tok, _, _ = new_individual(s, "indms")
        c = s.get(f"{BASE}/manual-pay/config", headers=hdr(tok))
        assert c.json()["platform_fee_percent"] == "3.0", c.json()
        t = first_scan(s, tok, 1000.0)
        assert t["platform_fee_percent"] == "3.00", t
        assert t["platform_fee"] == 30.0, t


# ---------------- Regression ----------------
class TestRegression:
    def test_superadmin_bill_fees_persist_individual(self, s, super_token):
        set_individual(s, super_token, 4)
        g = s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(super_token))
        assert g.status_code == 200, g.text
        assert g.json()["individual"] == 4.0, g.json()
        set_individual(s, super_token, 3)
        assert s.get(f"{BASE}/superadmin/bill-fees",
                     headers=hdr(super_token)).json()["individual"] == 3.0

    def test_bill_fees_validation(self, s, super_token):
        r = s.put(f"{BASE}/superadmin/bill-fees", json={"individual": 150}, headers=hdr(super_token))
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
        set_individual(s, super_token, 3)

    def test_role_guards(self, s):
        itok, _, _ = new_individual(s, "guard")
        r = s.get(f"{BASE}/company/employees", headers=hdr(itok))
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"

        atok, _ = new_corporate(s, "guardc")
        etok, _ = make_employee(s, atok, "guardemp")
        r2 = s.get(f"{BASE}/company/employees", headers=hdr(etok))
        assert r2.status_code in (401, 403), f"{r2.status_code} {r2.text[:200]}"
        r3 = s.post(f"{BASE}/company/employees", json={"email": uniq("x"), "name": "X"},
                    headers=hdr(etok))
        assert r3.status_code in (401, 403), f"{r3.status_code} {r3.text[:200]}"

    def test_superadmin_overview_stats(self, s, super_token):
        r = s.get(f"{BASE}/superadmin/stats", headers=hdr(super_token))
        assert r.status_code == 200, r.text
        assert '"_id"' not in r.text
        assert isinstance(r.json(), dict) and r.json(), r.json()

    def test_superadmin_bill_fees_forbidden_for_individual(self, s):
        itok, _, _ = new_individual(s, "fbid")
        r = s.put(f"{BASE}/superadmin/bill-fees", json={"individual": 9}, headers=hdr(itok))
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"
