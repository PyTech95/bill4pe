"""Iteration 24 — CORPORATE EMPLOYEE manual double-scan PayNow flow must be
FREE + auto-generated; INDIVIDUAL unchanged (fee snapshot + wallet charge).

Covers:
  * corporate employee: /manual-pay/config -> '0', first-scan -> '0'/0.0,
    confirm -> proof -> generate returns generated bill, NO needs_fee, and the
    created expense has bill_generated=true, bill_fee=0.0 with EMPTY company wallet
  * corporate admin: same manual flow zero fee
  * individual @1%: config '1.0', first-scan '1.00', fee charged from wallet
  * individual wallet-short: generate returns needs_fee (no crash / no 500)
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
    """POST with 429 (rate-limit) backoff — register 5/min, login 10/min per IP."""
    r = None
    for _ in range(8):
        r = s.post(f"{BASE}{path}", **kw)
        if r.status_code != 429:
            return r
        time.sleep(int(r.headers.get("Retry-After", 10)) + 1)
    return r


def set_individual(s, tok, pct):
    r = s.put(f"{BASE}/superadmin/bill-fees", json={"individual": pct}, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


def new_individual(s, tag="indiv"):
    email = uniq(tag)
    r = post_rl(s, "/auth/register", json={"email": email, "password": PW, "name": "TEST Indiv24"})
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
    emp = s.post(f"{BASE}/company/employees", json={"email": eemail, "name": "TEST Emp24"},
                 headers=hdr(atok))
    assert emp.status_code == 200, emp.text
    tpw = temp_pw_of(emp.json())
    assert tpw, emp.json()
    el = post_rl(s, "/auth/login", json={"email": eemail, "password": tpw})
    assert el.status_code == 200, el.text
    return el.json()["token"], eemail, tpw


def first_scan(s, tok, amount, draft=None):
    body = {
        "payee_upi": f"testmerchant{uuid.uuid4().hex[:4]}@ybl",
        "payee_name": "TEST Food Stall",
        "merchant_amount": amount,
    }
    if draft:
        body["expense_draft"] = draft
    r = s.post(f"{BASE}/manual-pay/first-scan", json=body, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


def submit_proof(tok, tid, utr):
    # multipart/form-data — must NOT send a JSON content-type header
    return requests.post(f"{BASE}/manual-pay/{tid}/proof", data={"utr_full": utr},
                         headers={"Authorization": f"Bearer {tok}"}, timeout=60)


def rand_utr():
    return "".join(str(uuid.uuid4().int >> (i * 3) & 9) for i in range(12))


def run_manual_flow(s, tok, amount, draft=None):
    t = first_scan(s, tok, amount, draft)
    tid = t["transaction_id"]
    cf = s.post(f"{BASE}/manual-pay/{tid}/confirm", json={"completed": True}, headers=hdr(tok))
    assert cf.status_code == 200, cf.text
    pr = submit_proof(tok, tid, rand_utr())
    assert pr.status_code == 200, pr.text
    assert pr.json().get("state") == "proof_submitted", pr.json()
    gen = s.post(f"{BASE}/manual-pay/{tid}/generate", json={}, headers=hdr(tok))
    return t, pr.json(), gen


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


# ---------------- PRIMARY: corporate EMPLOYEE manual PayNow flow ----------------
class TestCorporateEmployeeManualFlowFree:
    def test_employee_manual_flow_zero_fee_auto_bill(self, s, super_token):
        set_individual(s, super_token, 1)
        atok, _ = new_corporate(s, "e24")
        # company wallet must be EMPTY (unlimited subscription)
        w0 = s.get(f"{BASE}/company/wallet", headers=hdr(atok))
        assert w0.status_code == 200, w0.text
        assert float(w0.json()["balance"]) == 0.0, w0.json()

        etok, _, _ = make_employee(s, atok, "e24emp")

        cfg = s.get(f"{BASE}/manual-pay/config", headers=hdr(etok))
        assert cfg.status_code == 200, cfg.text
        assert cfg.json()["platform_fee_percent"] == "0", cfg.json()

        draft = {"category": "food", "sub_category": "restaurant",
                 "items": [{"name": "TEST_lunch", "quantity": 1, "unit_price": 500.0}]}
        t, proof, gen = run_manual_flow(s, etok, 500.0, draft)
        assert t["platform_fee_percent"] in ("0", "0.00"), t
        assert t["platform_fee"] == 0.0, t
        assert t["merchant_amount"] == 500.0, t
        # snapshot preserved through proof step
        assert proof.get("platform_fee") == 0.0, proof
        assert not proof.get("needs_fee"), proof

        assert gen.status_code == 200, gen.text
        gd = gen.json()
        assert not gd.get("needs_fee"), f"corporate must never be asked for a fee: {gd}"
        assert gd.get("generated") is True, gd
        assert gd.get("bill_id"), gd
        assert gd.get("platform_fee") == 0.0, gd
        assert gd.get("state") in ("completed",), gd
        assert "_id" not in gd

        # expense created by the flow has an auto-generated, free bill
        eid = gd.get("expense_id")
        assert eid, gd
        rows = s.get(f"{BASE}/expenses", headers=hdr(etok)).json()["expenses"]
        row = next((x for x in rows if x["id"] == eid), None)
        assert row, [x["id"] for x in rows]
        assert row["bill_generated"] is True, row
        assert row["bill_fee"] == 0.0, row
        assert row.get("bill_id") == gd["bill_id"], row

        # no company wallet debit
        w1 = s.get(f"{BASE}/company/wallet", headers=hdr(atok)).json()
        assert float(w1["balance"]) == 0.0, w1
        assert not [x for x in w1.get("transactions", []) if x.get("type") == "debit"], w1

    def test_employee_bill_doc_marked_generated(self, s):
        atok, _ = new_corporate(s, "e24b")
        etok, _, _ = make_employee(s, atok, "e24bemp")
        _, _, gen = run_manual_flow(s, etok, 750.0)
        assert gen.status_code == 200, gen.text
        eid = gen.json()["expense_id"]
        b = s.get(f"{BASE}/bills/{eid}", headers=hdr(etok))
        if b.status_code == 404:
            b = s.get(f"{BASE}/expenses/{eid}", headers=hdr(etok))
        assert b.status_code == 200, f"{b.status_code} {b.text[:300]}"
        d = b.json()
        d = d.get("expense", d)
        assert d.get("bill_generated") is True, d
        assert float(d.get("bill_fee") or 0) == 0.0, d

    def test_employee_multiple_free_bills(self, s):
        atok, _ = new_corporate(s, "e24m")
        etok, _, _ = make_employee(s, atok, "e24memp")
        for amt in (300.0, 1200.0):
            _, _, gen = run_manual_flow(s, etok, amt)
            assert gen.status_code == 200, gen.text
            assert gen.json()["platform_fee"] == 0.0, gen.json()
            assert gen.json()["generated"] is True, gen.json()


# ---------------- Corporate ADMIN same behaviour ----------------
class TestCorporateAdminManualFlowFree:
    def test_admin_manual_flow_zero_fee(self, s):
        atok, _ = new_corporate(s, "a24")
        cfg = s.get(f"{BASE}/manual-pay/config", headers=hdr(atok))
        assert cfg.json()["platform_fee_percent"] == "0", cfg.json()
        bal = float(s.get(f"{BASE}/wallet", headers=hdr(atok)).json()["balance"])
        t, _, gen = run_manual_flow(s, atok, 900.0)
        assert t["platform_fee"] == 0.0, t
        assert gen.status_code == 200, gen.text
        assert not gen.json().get("needs_fee"), gen.json()
        assert gen.json()["generated"] is True, gen.json()
        assert float(s.get(f"{BASE}/wallet", headers=hdr(atok)).json()["balance"]) == bal


# ---------------- INDIVIDUAL regression ----------------
class TestIndividualManualFlowUnchanged:
    def test_individual_fee_snapshot_and_wallet_charge(self, s, super_token):
        set_individual(s, super_token, 1)
        tok, user, _ = new_individual(s, "i24")
        cfg = s.get(f"{BASE}/manual-pay/config", headers=hdr(tok))
        assert cfg.json()["platform_fee_percent"] == "1.0", cfg.json()

        bal_before = float(s.get(f"{BASE}/wallet", headers=hdr(tok)).json()["balance"])
        assert bal_before > 0, "individual should get welcome bonus"

        t, proof, gen = run_manual_flow(s, tok, 500.0)
        assert t["platform_fee_percent"] == "1.00", t
        assert t["platform_fee"] > 0, t
        fee = t["platform_fee"]
        assert gen.status_code == 200, gen.text
        gd = gen.json()
        assert gd.get("generated") is True, gd
        after = float(s.get(f"{BASE}/wallet", headers=hdr(tok)).json()["balance"])
        assert after == round(bal_before - fee, 2), (bal_before, fee, after)

    def test_individual_wallet_short_returns_needs_fee(self, s, super_token):
        set_individual(s, super_token, 1)
        tok, _, _ = new_individual(s, "i24short")
        bal = float(s.get(f"{BASE}/wallet", headers=hdr(tok)).json()["balance"])
        # fee = 1% of amount; pick amount so fee > wallet balance
        amount = round((bal + 50) * 100, 2)
        t, _, gen = run_manual_flow(s, tok, amount)
        assert t["platform_fee"] > bal, (t["platform_fee"], bal)
        assert gen.status_code == 200, f"{gen.status_code} {gen.text[:300]}"
        gd = gen.json()
        assert gd.get("needs_fee") is True, gd
        assert float(gd.get("fee") or 0) == t["platform_fee"], gd
        assert not gd.get("bill_id"), gd
