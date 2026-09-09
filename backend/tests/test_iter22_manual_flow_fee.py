"""Iteration 22 — BUG FIX: manual_upi_double_scan flow must snapshot the
Super-Admin-configured per-user-type BILL FEE %, not the flat 10% platform fee.

Covers:
  * GET /api/manual-pay/config auth + per-user-type percent
  * POST /api/manual-pay/first-scan fee snapshot at configured individual rate
  * Rate change -> NEW first-scan uses new rate; OLD txn keeps its snapshot
  * Corporate rate differs from individual in the same flow
  * End-to-end manual receipt (confirm -> proof -> generate) debits the
    CONFIGURED fee from the wallet; short wallet returns needs_fee (no crash)
  * Regression: /bills/fee-info, /bills/{id}/generate, employee auto-bill
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
    """POST that respects the app's 429 rate limiter (auth routes: 5-10/min)."""
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
        "notes": "TEST expense iter22",
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


def set_fees(s, tok, **kw):
    r = s.put(f"{BASE}/superadmin/bill-fees", json=kw, headers=hdr(tok))
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


def temp_pw_of(j):    return ((j.get("credentials") or {}).get("temp_password")
            or j.get("temp_password") or j.get("password"))


def submit_proof(tok, tid, utr):
    """Multipart form post — must NOT carry the session's application/json header."""
    return requests.post(f"{BASE}/manual-pay/{tid}/proof", data={"utr_full": utr},
                         headers={"Authorization": f"Bearer {tok}"}, timeout=60)


def first_scan(s, tok, amount=1000.0, name="TEST Merchant"):
    r = s.post(f"{BASE}/manual-pay/first-scan", json={
        "payee_upi": f"testmerchant{uuid.uuid4().hex[:4]}@ybl",
        "payee_name": name,
        "merchant_amount": amount,
    }, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- PRIMARY BUG: manual flow honors configured % ----------------
class TestManualFlowIndividualRate:
    def test_config_requires_auth(self, s):
        r = s.get(f"{BASE}/manual-pay/config")
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"

    def test_individual_2_percent(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        tok, _, _ = new_individual(s, "mf2")

        c = s.get(f"{BASE}/manual-pay/config", headers=hdr(tok))
        assert c.status_code == 200, c.text
        assert c.json()["platform_fee_percent"] == "2.0", c.json()
        assert c.json()["flow_mode"] == "manual_upi_double_scan"

        t = first_scan(s, tok, 1000.0)
        assert t["platform_fee_percent"] == "2.00", t
        assert t["platform_fee"] == 20.0, t
        assert t["platform_fee_paise"] == 2000, t
        assert t["merchant_amount"] == 1000.0

        # status read returns the same snapshot
        st = s.get(f"{BASE}/manual-pay/{t['transaction_id']}", headers=hdr(tok))
        assert st.status_code == 200, st.text
        assert st.json()["platform_fee"] == 20.0
        assert '"_id"' not in st.text

    def test_rate_change_to_4_applies_to_new_scan_only(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        tok, _, _ = new_individual(s, "mf4")
        old = first_scan(s, tok, 1000.0)
        assert old["platform_fee"] == 20.0, old

        set_fees(s, super_token, individual=4)
        c = s.get(f"{BASE}/manual-pay/config", headers=hdr(tok))
        assert c.json()["platform_fee_percent"] == "4.0", c.json()

        new = first_scan(s, tok, 1000.0)
        assert new["platform_fee_percent"] == "4.00", new
        assert new["platform_fee"] == 40.0, new

        # old transaction keeps its original snapshot (expected)
        st = s.get(f"{BASE}/manual-pay/{old['transaction_id']}", headers=hdr(tok)).json()
        assert st["platform_fee"] == 20.0, st

        set_fees(s, super_token, individual=2)

    def test_flat_ten_percent_is_gone(self, s, super_token):
        """Even when the flat platform fee is 10%, the manual flow must use the
        configured bill fee for the user's type."""
        set_fees(s, super_token, individual=2, corporate=8)
        tok, _, _ = new_individual(s, "mfnot10")
        t = first_scan(s, tok, 1000.0)
        assert t["platform_fee"] != 100.0, f"still charging flat 10%: {t}"
        assert t["platform_fee"] == 20.0, t


# ---------------- Corporate rate in manual flow ----------------
class TestManualFlowCorporateRate:
    @pytest.mark.skip(reason="Superseded by iter23: corporate accounts are on a monthly subscription -> per-bill fee is always 0")
    def test_corporate_admin_gets_corporate_rate(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        atok, _ = new_corporate(s, "mfcorp")
        c = s.get(f"{BASE}/manual-pay/config", headers=hdr(atok))
        assert c.status_code == 200, c.text
        assert c.json()["platform_fee_percent"] == "8.0", c.json()
        t = first_scan(s, atok, 1000.0)
        assert t["platform_fee_percent"] == "8.00", t
        assert t["platform_fee"] == 80.0, t

    @pytest.mark.skip(reason="Superseded by iter23: corporate accounts are on a monthly subscription -> per-bill fee is always 0")
    def test_corporate_employee_gets_corporate_rate(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        atok, _ = new_corporate(s, "mfcorpemp")
        eemail = uniq("mfemp")
        emp = s.post(f"{BASE}/company/employees", json={"email": eemail, "name": "TEST Emp22"},
                     headers=hdr(atok))
        assert emp.status_code == 200, emp.text
        tpw = temp_pw_of(emp.json())
        assert tpw, emp.json()
        el = post_rl(s, "/auth/login", json={"email": eemail, "password": tpw})
        assert el.status_code == 200, el.text
        etok = el.json()["token"]
        c = s.get(f"{BASE}/manual-pay/config", headers=hdr(etok))
        assert c.status_code == 200, c.text
        assert c.json()["platform_fee_percent"] == "8.0", c.json()
        t = first_scan(s, etok, 1000.0)
        assert t["platform_fee"] == 80.0, t

    @pytest.mark.skip(reason="Superseded by iter23: corporate accounts are on a monthly subscription -> per-bill fee is always 0")
    def test_individual_and_corporate_differ(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        itok, _, _ = new_individual(s, "mfdiff")
        ctok, _ = new_corporate(s, "mfdiffc")
        i = s.get(f"{BASE}/manual-pay/config", headers=hdr(itok)).json()["platform_fee_percent"]
        c = s.get(f"{BASE}/manual-pay/config", headers=hdr(ctok)).json()["platform_fee_percent"]
        assert float(i) == 2.0 and float(c) == 8.0, (i, c)


# ---------------- End-to-end manual receipt at configured fee ----------------
class TestManualFlowEndToEnd:
    def test_receipt_debits_configured_fee(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        tok, _, _ = new_individual(s, "mfe2e")
        # welcome bonus Rs.50 + top up to comfortably cover Rs.20
        rc = s.post(f"{BASE}/wallet/recharge", json={"amount": 100.0}, headers=hdr(tok))
        assert rc.status_code == 200, rc.text
        bal_before = float(rc.json()["balance"])

        t = first_scan(s, tok, 1000.0)
        tid = t["transaction_id"]
        assert t["platform_fee"] == 20.0, t

        cf = s.post(f"{BASE}/manual-pay/{tid}/confirm", json={"completed": True}, headers=hdr(tok))
        assert cf.status_code == 200, cf.text
        assert cf.json()["merchant_payment_status"] == "user_confirmed"

        utr = "".join(str((i * 7 + 3) % 10) for i in range(12))
        pr = submit_proof(tok, tid, utr)
        assert pr.status_code == 200, pr.text
        assert pr.json()["proof_status"] == "proof_submitted"

        gen = s.post(f"{BASE}/manual-pay/{tid}/generate", json={}, headers=hdr(tok))
        assert gen.status_code == 200, gen.text
        gd = gen.json()
        assert gd.get("generated") is True, gd
        assert gd.get("bill_id"), gd
        assert gd["platform_fee"] == 20.0, gd

        w = s.get(f"{BASE}/wallet", headers=hdr(tok))
        assert w.status_code == 200, w.text
        assert float(w.json()["balance"]) == round(bal_before - 20.0, 2), w.json()
        debits = [x for x in w.json().get("transactions", []) if x["type"] == "debit"]
        assert any(float(x["amount"]) == 20.0 for x in debits), debits
        assert not any(float(x["amount"]) == 100.0 for x in debits), \
            "wallet debited at flat 10% instead of configured 2%"

        # stored expense/receipt carries the configured fee
        lst = s.get(f"{BASE}/expenses", headers=hdr(tok))
        assert lst.status_code == 200, lst.text
        rows = lst.json() if isinstance(lst.json(), list) else lst.json().get("expenses", [])
        row = next((x for x in rows if x.get("transaction_id") == tid), None)
        assert row, f"no expense created for {tid}"
        assert row["bill_fee"] == 20.0, row
        assert row["bill_id"] == gd["bill_id"]
        assert (row.get("bill_snapshot") or {}).get("bill4pe_service_fee") == 20.0, row.get("bill_snapshot")

        # idempotent re-generate
        again = s.post(f"{BASE}/manual-pay/{tid}/generate", json={}, headers=hdr(tok))
        assert again.status_code == 200, again.text
        assert again.json()["bill_id"] == gd["bill_id"]
        assert float(s.get(f"{BASE}/wallet", headers=hdr(tok)).json()["balance"]) \
            == round(bal_before - 20.0, 2), "double debit on retry"

    def test_short_wallet_returns_needs_fee_with_configured_amount(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        tok, user, _ = new_individual(s, "mfshort")
        assert float(user["wallet_balance"]) == 50.0
        # 2% of 100000 = Rs.2000 > wallet
        t = first_scan(s, tok, 100000.0)
        tid = t["transaction_id"]
        assert t["platform_fee"] == 2000.0, t

        assert s.post(f"{BASE}/manual-pay/{tid}/confirm", json={"completed": True},
                      headers=hdr(tok)).status_code == 200
        utr = "".join(str((i * 3 + 1) % 10) for i in range(12))
        assert submit_proof(tok, tid, utr).status_code == 200

        gen = s.post(f"{BASE}/manual-pay/{tid}/generate", json={}, headers=hdr(tok))
        assert gen.status_code == 200, gen.text
        gd = gen.json()
        assert gd.get("needs_fee") is True, gd
        assert gd.get("generated") is False, gd
        assert gd["fee"] == 2000.0, gd
        assert gd["wallet_balance"] == 50.0, gd


# ---------------- Regression: other fee paths ----------------
class TestRegressionOtherFeePaths:
    @pytest.mark.skip(reason="Superseded by iter23: corporate accounts are on a monthly subscription -> per-bill fee is always 0")
    def test_fee_info_per_type(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        itok, _, _ = new_individual(s, "regfi")
        assert s.get(f"{BASE}/bills/fee-info", headers=hdr(itok)).json() == \
            {"kind": "individual", "percent": 2.0}
        ctok, _ = new_corporate(s, "regfic")
        assert s.get(f"{BASE}/bills/fee-info", headers=hdr(ctok)).json() == \
            {"kind": "corporate", "percent": 8.0}

    def test_individual_bill_generate_uses_individual_rate(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        tok, _, _ = new_individual(s, "regbill")
        eid = s.post(f"{BASE}/expenses", json=expense_payload(1000.0), headers=hdr(tok)).json()["id"]
        g = s.post(f"{BASE}/bills/{eid}/generate", json={}, headers=hdr(tok))
        assert g.status_code == 200, g.text
        assert g.json()["fee"] == 20.0 and g.json()["fee_percent"] == 2.0, g.json()
        assert g.json()["wallet_balance"] == 30.0, g.json()

    @pytest.mark.skip(reason="Superseded by iter23: corporate accounts are on a monthly subscription -> per-bill fee is always 0")
    def test_employee_autobill_debits_company_at_corporate_rate(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        atok, _ = new_corporate(s, "regcorp")
        assert s.post(f"{BASE}/company/wallet/recharge", json={"amount": 1000.0},
                      headers=hdr(atok)).status_code == 200
        before = float(s.get(f"{BASE}/company/wallet", headers=hdr(atok)).json()["balance"])
        eemail = uniq("regemp")
        emp = s.post(f"{BASE}/company/employees", json={"email": eemail, "name": "TEST RegEmp"},
                     headers=hdr(atok))
        assert emp.status_code == 200, emp.text
        el = post_rl(s, "/auth/login", json={"email": eemail, "password": temp_pw_of(emp.json())})
        assert el.status_code == 200, el.text
        e = s.post(f"{BASE}/expenses", json=expense_payload(1000.0), headers=hdr(el.json()["token"]))
        assert e.status_code == 200, e.text
        assert e.json()["bill_fee"] == 80.0, e.json()
        assert e.json()["bill_fee_percent"] == 8.0, e.json()
        assert float(s.get(f"{BASE}/company/wallet", headers=hdr(atok)).json()["balance"]) \
            == round(before - 80.0, 2)

    def test_superadmin_bill_fees_persist(self, s, super_token):
        set_fees(s, super_token, individual=2, corporate=8)
        g = s.get(f"{BASE}/superadmin/bill-fees", headers=hdr(super_token))
        assert g.status_code == 200, g.text
        assert g.json()["individual"] == 2.0 and g.json()["corporate"] == 8.0, g.json()
