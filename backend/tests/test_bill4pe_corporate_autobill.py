"""Corporate auto-bill regression: employee expense triggers auto official bill billed to company wallet."""
import os
import uuid
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

CORP_ADMIN = {"email": "abcadmin@bill4pe.com", "password": "Abc@1234"}
CORP_EMP = {"email": "xyz@bill4pe.com", "password": "5U5FP8ZLEE"}
INDIV = {"email": "testowner@bill4pe.com", "password": "Test@1234"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed {creds['email']}: {r.status_code} {r.text}"
    j = r.json()
    tok = j.get("access_token") or j.get("token")
    assert tok
    return tok


def _headers(tok):
    return {"Authorization": f"Bearer {tok}"}


def _sample_expense_payload(txn_suffix=""):
    return {
        "category": "food",
        "sub_category": "TEST_autobill",
        "items": [
            {"name": "TEST_biryani", "quantity": 2, "unit_price": 120.0},
            {"name": "TEST_water", "quantity": 1, "unit_price": 20.0},
        ],
        "payment": {
            "merchant_name": "TEST_ Merchant Auto",
            "merchant_upi": "testmerchant@upi",
            "amount": 260.0,
            "payment_method": "UPI",
            "payment_status": "paid",
            "transaction_id": f"TEST_TXN_auto_{txn_suffix or uuid.uuid4().hex[:8]}",
            "latitude": 12.97,
            "longitude": 77.59,
        },
        "notes": "TEST autobill notes",
    }


# -------------------- Case 1: happy path corporate auto-bill --------------------
def test_corporate_employee_expense_auto_generates_bill_and_debits_company_wallet():
    admin_tok = _login(CORP_ADMIN)
    # Get initial company wallet
    r_me = requests.get(f"{API}/company/me", headers=_headers(admin_tok), timeout=15)
    assert r_me.status_code == 200, r_me.text
    stats = r_me.json().get("stats", {})
    bal0 = float(stats.get("wallet_balance", 0))

    # Ensure wallet has at least ₹10 for the fee (expense total ~260 -> fee = 2.60)
    if bal0 < 10:
        rc = requests.post(
            f"{API}/company/wallet/recharge",
            headers=_headers(admin_tok),
            json={"amount": 500},
            timeout=15,
        )
        assert rc.status_code == 200, rc.text
        bal0 = float(rc.json()["balance"])

    # Employee login and create expense
    emp_tok = _login(CORP_EMP)
    payload = _sample_expense_payload()
    total_expected = 2 * 120.0 + 20.0  # 260
    expected_fee = round(max(1.0, total_expected * 0.01), 2)  # 2.60

    r = requests.post(f"{API}/expenses", headers=_headers(emp_tok), json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    exp = r.json()

    assert exp.get("approval_status") == "approved", exp
    assert exp.get("bill_generated") is True, exp
    assert exp.get("auto_generated") is True, exp
    bill_id = exp.get("bill_id")
    assert isinstance(bill_id, str) and bill_id.startswith("B4P-"), bill_id
    parts = bill_id.split("-")
    assert len(parts) == 3 and len(parts[1]) == 8 and len(parts[2]) == 6, bill_id
    assert float(exp.get("bill_fee", 0)) == expected_fee, exp

    # Company wallet decreased by fee
    r_me2 = requests.get(f"{API}/company/me", headers=_headers(admin_tok), timeout=15)
    bal1 = float(r_me2.json()["stats"]["wallet_balance"])
    assert round(bal0 - bal1, 2) == expected_fee, f"bal0={bal0} bal1={bal1} fee={expected_fee}"


# -------------------- Case 2: insufficient wallet edge case --------------------
def test_corporate_employee_expense_when_company_wallet_insufficient_no_bill():
    # Register a fresh corporate admin with 0 wallet
    unique = uuid.uuid4().hex[:8]
    admin_email = f"TEST_edgeadmin_{unique}@bill4pe.com"
    admin_pw = "Edge@1234"
    r_reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": admin_email,
            "password": admin_pw,
            "name": "TEST Edge Admin",
            "user_type": "corporate",
            "corporate_name": f"TEST Edge Corp {unique}",
            "subscription_plan": "starter",
            "employee_limit": 5,
        },
        timeout=30,
    )
    assert r_reg.status_code in (200, 201), r_reg.text
    admin_tok = r_reg.json().get("token") or r_reg.json().get("access_token")
    assert admin_tok

    # Verify wallet is 0
    r_me = requests.get(f"{API}/company/me", headers=_headers(admin_tok), timeout=15)
    assert r_me.status_code == 200, r_me.text
    assert float(r_me.json()["stats"]["wallet_balance"]) == 0.0

    # Add employee
    emp_email = f"TEST_edgeemp_{unique}@bill4pe.com"
    emp_pw = "EdgeEmp@1234"
    r_emp = requests.post(
        f"{API}/company/employees",
        headers=_headers(admin_tok),
        json={
            "email": emp_email,
            "name": "TEST Edge Emp",
            "phone": "9999999999",
            "department": "TEST",
            "designation": "Tester",
            "temp_password": emp_pw,
        },
        timeout=15,
    )
    assert r_emp.status_code in (200, 201), r_emp.text

    # Login as this employee and create expense
    emp_tok = _login({"email": emp_email, "password": emp_pw})
    payload = _sample_expense_payload(txn_suffix=unique)
    r = requests.post(f"{API}/expenses", headers=_headers(emp_tok), json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    exp = r.json()
    assert exp.get("approval_status") == "approved", exp
    assert exp.get("bill_generated") is False, exp
    assert exp.get("bill_id") in (None, ""), exp
    assert isinstance(exp.get("bill_pending_reason"), str) and exp["bill_pending_reason"], exp

    # Company wallet still 0 (not negative)
    r_me2 = requests.get(f"{API}/company/me", headers=_headers(admin_tok), timeout=15)
    assert float(r_me2.json()["stats"]["wallet_balance"]) == 0.0


# -------------------- Case 3: admin approvals list contains full detail --------------------
def test_admin_approvals_list_has_full_detail_and_submitter():
    admin_tok = _login(CORP_ADMIN)
    r = requests.get(
        f"{API}/company/approvals?status=approved",
        headers=_headers(admin_tok),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    approvals = r.json().get("approvals", [])
    # At least one from earlier test
    assert len(approvals) > 0, "expected at least one approved expense"
    # Find one that was auto-generated recently
    autos = [a for a in approvals if a.get("auto_generated")]
    target = autos[0] if autos else approvals[0]

    pay = target.get("payment") or {}
    assert pay.get("merchant_name"), target
    assert pay.get("merchant_upi") is not None, target  # may be None but key exists
    assert pay.get("transaction_id"), target
    items = target.get("items") or []
    assert isinstance(items, list) and len(items) >= 1
    it = items[0]
    assert "name" in it and "quantity" in it and "unit_price" in it, it
    assert "total" in target
    assert target.get("bill_id")
    submitter = target.get("submitter") or {}
    assert submitter.get("name"), target
    # department may be None but field is expected to exist in response object
    assert "department" in submitter


# -------------------- Case 4: individual user unchanged --------------------
def test_individual_expense_does_not_autogenerate_bill_and_manual_generate_works():
    tok = _login(INDIV)
    # get wallet balance
    w0 = requests.get(f"{API}/wallet", headers=_headers(tok), timeout=15)
    assert w0.status_code == 200, w0.text
    bal0 = float(w0.json().get("balance", 0))

    payload = _sample_expense_payload(txn_suffix=uuid.uuid4().hex[:6])
    r = requests.post(f"{API}/expenses", headers=_headers(tok), json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    exp = r.json()
    eid = exp.get("id")
    assert eid
    assert exp.get("bill_generated") is False, exp
    assert exp.get("bill_id") in (None, ""), exp
    assert not exp.get("auto_generated"), exp

    # Manual generate should work and deduct from individual wallet
    r_gen = requests.post(f"{API}/bills/{eid}/generate", headers=_headers(tok), timeout=30)
    assert r_gen.status_code == 200, r_gen.text

    total_expected = 260.0
    expected_fee = round(max(1.0, total_expected * 0.01), 2)

    w1 = requests.get(f"{API}/wallet", headers=_headers(tok), timeout=15)
    bal1 = float(w1.json().get("balance", 0))
    assert round(bal0 - bal1, 2) == expected_fee, f"bal0={bal0} bal1={bal1} fee={expected_fee}"

    # Verify bill got generated on expense
    r_exp = requests.get(f"{API}/expenses/{eid}", headers=_headers(tok), timeout=15)
    assert r_exp.status_code == 200
    j = r_exp.json()
    assert j.get("bill_generated") is True
    assert isinstance(j.get("bill_id"), str) and j["bill_id"].startswith("B4P-")
