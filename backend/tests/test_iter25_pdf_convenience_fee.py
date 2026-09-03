"""Iteration 25 — PDF convenience-fee bug.

CORPORATE (subscription) bills must NOT print a 'Convenience Fee' / 'GRAND TOTAL'
line; they print a single 'TOTAL Rs X' row equal to the subtotal.
INDIVIDUAL bills (fee > 0) must still print Subtotal + Convenience Fee + GRAND TOTAL.
"""
import io
import os
import time
import uuid

import pdfplumber
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


def new_corporate(s, tag="corp"):
    email = uniq(tag)
    r = post_rl(s, "/auth/register", json={
        "email": email, "password": PW, "name": f"TEST {tag} Admin",
        "user_type": "corporate", "corporate_name": f"TEST {tag} Pvt Ltd",
        "subscription_plan": "monthly_50", "employee_limit": 50,
    })
    assert r.status_code == 200, r.text
    return r.json()["token"], email


def new_individual(s, tag="indiv"):
    email = uniq(tag)
    r = post_rl(s, "/auth/register", json={"email": email, "password": PW, "name": "TEST Indiv25"})
    assert r.status_code == 200, r.text
    return r.json()["token"], email


def make_employee(s, atok, tag="emp"):
    eemail = uniq(tag)
    emp = s.post(f"{BASE}/company/employees", json={"email": eemail, "name": "TEST Emp25"},
                 headers=hdr(atok))
    assert emp.status_code == 200, emp.text
    j = emp.json()
    tpw = ((j.get("credentials") or {}).get("temp_password")
           or j.get("temp_password") or j.get("password"))
    assert tpw, j
    el = post_rl(s, "/auth/login", json={"email": eemail, "password": tpw})
    assert el.status_code == 200, el.text
    return el.json()["token"], eemail


def rand_utr():
    return "".join(str(uuid.uuid4().int >> (i * 3) & 9) for i in range(12))


def run_manual_flow(s, tok, amount, draft=None):
    body = {
        "payee_upi": f"testmerchant{uuid.uuid4().hex[:4]}@ybl",
        "payee_name": "TEST Food Stall",
        "merchant_amount": amount,
    }
    if draft:
        body["expense_draft"] = draft
    t = s.post(f"{BASE}/manual-pay/first-scan", json=body, headers=hdr(tok))
    assert t.status_code == 200, t.text
    tid = t.json()["transaction_id"]
    cf = s.post(f"{BASE}/manual-pay/{tid}/confirm", json={"completed": True}, headers=hdr(tok))
    assert cf.status_code == 200, cf.text
    pr = requests.post(f"{BASE}/manual-pay/{tid}/proof", data={"utr_full": rand_utr()},
                       headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    assert pr.status_code == 200, pr.text
    gen = s.post(f"{BASE}/manual-pay/{tid}/generate", json={}, headers=hdr(tok))
    assert gen.status_code == 200, gen.text
    return t.json(), gen.json()


def expense_row(s, tok, eid):
    r = s.get(f"{BASE}/expenses", headers=hdr(tok))
    assert r.status_code == 200, r.text
    rows = r.json()["expenses"]
    return next((x for x in rows if x["id"] == eid), None)


def pdf_text(s, tok, eid):
    r = s.get(f"{BASE}/bills/{eid}/pdf", headers=hdr(tok), timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    assert r.content[:4] == b"%PDF", r.content[:20]
    assert len(r.content) > 1000, len(r.content)
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
    print(f"---- PDF text for {eid} ----\n{txt}\n----")
    return txt


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


# ---------------- CORPORATE EMPLOYEE PDF: no convenience fee ----------------
class TestCorporatePdfNoConvenienceFee:
    def test_employee_pdf_has_no_fee_rows(self, s, super_token):
        # individual rate 1% globally, corporate must still be free
        r = s.put(f"{BASE}/superadmin/bill-fees", json={"individual": 1}, headers=hdr(super_token))
        assert r.status_code == 200, r.text

        atok, _ = new_corporate(s, "p25")
        etok, _ = make_employee(s, atok, "p25emp")
        draft = {"category": "food", "sub_category": "restaurant",
                 "items": [{"name": "TEST_lunch", "quantity": 1, "unit_price": 490.0}]}
        t, gd = run_manual_flow(s, etok, 490.0, draft)
        assert gd.get("generated") is True, gd
        eid = gd["expense_id"]

        row = expense_row(s, etok, eid)
        assert row, "expense not found"
        assert float(row["bill_fee"]) == 0.0, row
        assert float(row["total"]) == 490.0, row

        txt = pdf_text(s, etok, eid)
        assert "Convenience Fee" not in txt, "corporate PDF must not show Convenience Fee"
        assert "GRAND TOTAL" not in txt, "corporate PDF must not show GRAND TOTAL"
        assert "Subtotal" not in txt, "corporate PDF must not show Subtotal row"
        flat = " ".join(txt.split())
        assert "TOTAL" in flat
        assert "490.00" in flat, flat[-400:]
        # no stray 4.90 (1% fee) anywhere
        assert "4.90" not in flat, "1% fee value 4.90 leaked into corporate PDF"

    def test_corporate_admin_pdf_has_no_fee_rows(self, s):
        atok, _ = new_corporate(s, "pa25")
        draft = {"category": "food", "sub_category": "restaurant",
                 "items": [{"name": "TEST_dinner", "quantity": 2, "unit_price": 245.0}]}
        t, gd = run_manual_flow(s, atok, 490.0, draft)
        assert gd.get("generated") is True, gd
        eid = gd["expense_id"]
        row = expense_row(s, atok, eid)
        assert row and float(row["bill_fee"]) == 0.0, row

        txt = pdf_text(s, atok, eid)
        assert "Convenience Fee" not in txt, txt[-500:]
        assert "GRAND TOTAL" not in txt, txt[-500:]
        flat = " ".join(txt.split())
        assert "TOTAL" in flat and "490.00" in flat, flat[-400:]


# ---------------- INDIVIDUAL PDF regression: fee still shown ----------------
class TestIndividualPdfShowsFee:
    def test_individual_pdf_shows_convenience_fee(self, s, super_token):
        r = s.put(f"{BASE}/superadmin/bill-fees", json={"individual": 1}, headers=hdr(super_token))
        assert r.status_code == 200, r.text

        tok, _ = new_individual(s, "p25i")
        bal = float(s.get(f"{BASE}/wallet", headers=hdr(tok)).json()["balance"])
        assert bal >= 10.0, f"welcome balance too low: {bal}"

        draft = {"category": "food", "sub_category": "restaurant",
                 "items": [{"name": "TEST_party", "quantity": 1, "unit_price": 1000.0}]}
        t, gd = run_manual_flow(s, tok, 1000.0, draft)
        assert gd.get("generated") is True, gd
        eid = gd["expense_id"]

        row = expense_row(s, tok, eid)
        assert row, "expense not found"
        assert float(row["bill_fee"]) == 10.0, row

        txt = pdf_text(s, tok, eid)
        flat = " ".join(txt.split())
        assert "Convenience Fee" in flat, flat[-500:]
        assert "Subtotal 1000.00" in flat, flat[-500:]
        assert "GRAND TOTAL" in flat and "1010.00" in flat, flat[-500:]
