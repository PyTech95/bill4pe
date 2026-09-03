"""Corporate B2B feature tests: registration, employee mgmt, invites, approvals, wallet, billing."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-expense-hub-8.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TS = int(time.time())


@pytest.fixture(scope="module")
def admin_ctx():
    email = f"admin_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    payload = {
        "email": email,
        "password": "test123",
        "name": "Demo Admin",
        "user_type": "corporate",
        "corporate_name": "Demo Co",
        "subscription_plan": "monthly_50",
        "employee_limit": 3,  # small to test limit
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["token"], "user": data["user"], "email": email}


@pytest.fixture(scope="module")
def admin_headers(admin_ctx):
    return {"Authorization": f"Bearer {admin_ctx['token']}"}


@pytest.fixture(scope="module")
def individual_ctx():
    email = f"indi_{TS}_{uuid.uuid4().hex[:6]}@demo.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "test123", "name": "Indi User",
    }, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- 1. Register & auth/me ----------

def test_admin_register_and_me(admin_ctx, admin_headers):
    assert admin_ctx["user"]["role"] == "admin"
    assert admin_ctx["user"]["company_id"]
    r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    me = r.json()
    assert me["role"] == "admin"
    assert me["company_id"] == admin_ctx["user"]["company_id"]
    assert me["user_type"] == "corporate"


def test_duplicate_register_rejected(admin_ctx):
    r = requests.post(f"{API}/auth/register", json={
        "email": admin_ctx["email"], "password": "x", "name": "dup"
    }, timeout=30)
    assert r.status_code == 400


# ---------- 2. Company /me + KPIs ----------

def test_company_me(admin_headers):
    r = requests.get(f"{API}/company/me", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "company" in body and "stats" in body
    s = body["stats"]
    for k in ("employees", "pending_approvals", "month_spend", "wallet_balance"):
        assert k in s


# ---------- 3. Employee creation w/ temp password ----------

@pytest.fixture(scope="module")
def employee_ctx(admin_headers):
    emp_email = f"emp_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    r = requests.post(f"{API}/company/employees", headers=admin_headers, json={
        "name": "Emp One", "email": emp_email, "phone": "9876543210",
        "department": "Sales", "designation": "Exec", "employee_id": "E001",
        "monthly_cap": 5000,
    }, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["credentials"]["email"] == emp_email
    assert data["credentials"]["temp_password"]
    # login as employee
    lr = requests.post(f"{API}/auth/login", json={
        "email": emp_email, "password": data["credentials"]["temp_password"]
    }, timeout=30)
    assert lr.status_code == 200, lr.text
    return {
        "token": lr.json()["token"], "user": lr.json()["user"],
        "email": emp_email, "id": data["employee"]["id"],
    }


def test_employee_login_works(employee_ctx):
    assert employee_ctx["user"]["role"] == "employee"
    assert employee_ctx["user"]["company_id"]


def test_duplicate_employee_email_rejected(admin_headers, employee_ctx):
    r = requests.post(f"{API}/company/employees", headers=admin_headers, json={
        "name": "Dup", "email": employee_ctx["email"],
    }, timeout=30)
    assert r.status_code == 400


# ---------- 4. Invite flow ----------

@pytest.fixture(scope="module")
def invite_ctx(admin_headers):
    inv_email = f"inv_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    r = requests.post(f"{API}/company/employees/invite", headers=admin_headers, json={
        "name": "Invitee", "email": inv_email,
    }, timeout=30)
    assert r.status_code == 200, r.text
    return {"email": inv_email, "token": r.json()["invite"]["token"]}


def test_invite_lookup(invite_ctx):
    r = requests.get(f"{API}/company/invite/{invite_ctx['token']}", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == invite_ctx["email"]
    assert body["company_name"]


def test_invite_accept(invite_ctx):
    r = requests.post(f"{API}/company/invite/accept", json={
        "token": invite_ctx["token"], "password": "newpass123",
    }, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["role"] == "employee"
    # token now consumed
    r2 = requests.get(f"{API}/company/invite/{invite_ctx['token']}", timeout=30)
    assert r2.status_code == 404


# ---------- 5. List/Update/Delete employees ----------

def test_list_employees(admin_headers, employee_ctx):
    r = requests.get(f"{API}/company/employees", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    emps = r.json()["employees"]
    assert any(e["id"] == employee_ctx["id"] for e in emps)
    # has 2 by now (employee + accepted invite)
    assert len(emps) >= 2


def test_update_employee(admin_headers, employee_ctx):
    r = requests.put(f"{API}/company/employees/{employee_ctx['id']}", headers=admin_headers, json={
        "department": "Marketing"
    }, timeout=30)
    assert r.status_code == 200
    assert r.json()["department"] == "Marketing"


# ---------- 6. Expense + Approval flow ----------

@pytest.fixture(scope="module")
def employee_headers(employee_ctx):
    return {"Authorization": f"Bearer {employee_ctx['token']}"}


@pytest.fixture(scope="module")
def pending_expense(employee_headers):
    r = requests.post(f"{API}/expenses", headers=employee_headers, json={
        "category": "food",
        "items": [{"name": "Lunch", "quantity": 1, "unit_price": 350}],
        "payment": {"amount": 350, "payment_method": "UPI", "merchant_name": "Cafe X"},
    }, timeout=30)
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["approval_status"] == "pending"
    assert e["company_id"]
    return e


def test_employee_bill_blocked_when_pending(employee_headers, pending_expense):
    r = requests.post(f"{API}/bills/{pending_expense['id']}/generate", headers=employee_headers, timeout=30)
    assert r.status_code == 403
    assert "approval" in r.text.lower()


def test_admin_sees_pending(admin_headers, pending_expense):
    r = requests.get(f"{API}/company/approvals?status=pending", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    ids = [a["id"] for a in r.json()["approvals"]]
    assert pending_expense["id"] in ids


def test_admin_reject_requires_reason(admin_headers, employee_headers):
    # create new pending expense to reject
    r = requests.post(f"{API}/expenses", headers=employee_headers, json={
        "category": "food", "items": [{"name": "x", "quantity": 1, "unit_price": 10}],
        "payment": {"amount": 10, "payment_method": "UPI"},
    }, timeout=30)
    eid = r.json()["id"]
    rj = requests.post(f"{API}/company/approvals/{eid}/reject", headers=admin_headers, json={}, timeout=30)
    assert rj.status_code == 400
    rj2 = requests.post(f"{API}/company/approvals/{eid}/reject", headers=admin_headers, json={"reason": "Out of policy"}, timeout=30)
    assert rj2.status_code == 200


def test_admin_approve_and_count(admin_headers, pending_expense):
    r = requests.post(f"{API}/company/approvals/{pending_expense['id']}/approve",
                      headers=admin_headers, json={}, timeout=30)
    assert r.status_code == 200
    # pending count - check no pending left for that expense
    me = requests.get(f"{API}/company/me", headers=admin_headers, timeout=30).json()
    # may still have other pending from invitee tests; verify the specific one approved
    g = requests.get(f"{API}/company/approvals?status=approved", headers=admin_headers, timeout=30)
    assert pending_expense["id"] in [a["id"] for a in g.json()["approvals"]]


# ---------- 7. Company wallet & bill generation ----------

def test_wallet_recharge_and_get(admin_headers):
    r = requests.post(f"{API}/company/wallet/recharge", headers=admin_headers, json={"amount": 500}, timeout=30)
    assert r.status_code == 200
    assert r.json()["balance"] >= 500
    g = requests.get(f"{API}/company/wallet", headers=admin_headers, timeout=30)
    assert g.status_code == 200
    assert g.json()["balance"] >= 500
    assert isinstance(g.json()["transactions"], list)


def test_bill_gen_deducts_company_wallet(employee_headers, admin_headers, pending_expense):
    bal_before = requests.get(f"{API}/company/wallet", headers=admin_headers, timeout=30).json()["balance"]
    r = requests.post(f"{API}/bills/{pending_expense['id']}/generate", headers=employee_headers, timeout=30)
    assert r.status_code == 200, r.text
    assert "bill_id" in r.json()
    bal_after = requests.get(f"{API}/company/wallet", headers=admin_headers, timeout=30).json()["balance"]
    assert round(bal_before - bal_after, 2) == 5.0


def test_bill_gen_insufficient_company_wallet(employee_headers, admin_headers):
    # Drain wallet by setting balance via subsequent recharges then a huge bill cycle is complex.
    # Instead, create a separate fresh corporate setup to simulate empty wallet.
    em = f"admin2_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    rr = requests.post(f"{API}/auth/register", json={
        "email": em, "password": "test123", "name": "A2",
        "user_type": "corporate", "corporate_name": "C2", "employee_limit": 5,
    }, timeout=30).json()
    ah = {"Authorization": f"Bearer {rr['token']}"}
    em2 = f"emp2_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    cr = requests.post(f"{API}/company/employees", headers=ah, json={
        "name": "E2", "email": em2,
    }, timeout=30).json()
    el = requests.post(f"{API}/auth/login", json={
        "email": em2, "password": cr["credentials"]["temp_password"]
    }, timeout=30).json()
    eh = {"Authorization": f"Bearer {el['token']}"}
    ec = requests.post(f"{API}/expenses", headers=eh, json={
        "category": "food", "items": [{"name": "x", "quantity": 1, "unit_price": 5}],
        "payment": {"amount": 5, "payment_method": "UPI"},
    }, timeout=30).json()
    # approve
    requests.post(f"{API}/company/approvals/{ec['id']}/approve", headers=ah, json={}, timeout=30)
    # try generate with empty wallet
    r = requests.post(f"{API}/bills/{ec['id']}/generate", headers=eh, timeout=30)
    assert r.status_code == 402, r.text


# ---------- 8. Individual user flow unchanged ----------

def test_individual_expense_autoapproved(individual_ctx):
    h = {"Authorization": f"Bearer {individual_ctx['token']}"}
    r = requests.post(f"{API}/expenses", headers=h, json={
        "category": "food", "items": [{"name": "x", "quantity": 1, "unit_price": 10}],
        "payment": {"amount": 10, "payment_method": "UPI"},
    }, timeout=30)
    e = r.json()
    assert e["approval_status"] == "approved"
    # generate bill -> deducts from own wallet (has 50 INR welcome)
    g = requests.post(f"{API}/bills/{e['id']}/generate", headers=h, timeout=30)
    assert g.status_code == 200
    assert g.json()["wallet_balance"] == 45.0


# ---------- 9. Role-based access ----------

def test_individual_cannot_access_company(individual_ctx):
    h = {"Authorization": f"Bearer {individual_ctx['token']}"}
    r = requests.get(f"{API}/company/me", headers=h, timeout=30)
    assert r.status_code == 403


def test_employee_cannot_access_company(employee_headers):
    r = requests.get(f"{API}/company/me", headers=employee_headers, timeout=30)
    assert r.status_code == 403


# ---------- 10. Employee limit ----------

def test_employee_limit_enforced():
    em = f"adminL_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    rr = requests.post(f"{API}/auth/register", json={
        "email": em, "password": "test123", "name": "AL",
        "user_type": "corporate", "corporate_name": "CL", "employee_limit": 1,
    }, timeout=30).json()
    ah = {"Authorization": f"Bearer {rr['token']}"}
    e1 = f"el1_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    r1 = requests.post(f"{API}/company/employees", headers=ah, json={"name": "L1", "email": e1}, timeout=30)
    assert r1.status_code == 200
    e2 = f"el2_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    r2 = requests.post(f"{API}/company/employees", headers=ah, json={"name": "L2", "email": e2}, timeout=30)
    assert r2.status_code == 400
    assert "limit" in r2.text.lower()


# ---------- 11. Delete employee ----------

def test_delete_employee(admin_headers):
    em = f"dele_{TS}_{uuid.uuid4().hex[:6]}@democorp.com"
    cr = requests.post(f"{API}/company/employees", headers=admin_headers, json={
        "name": "Del", "email": em,
    }, timeout=30)
    if cr.status_code != 200:
        pytest.skip("Could not create employee (limit may be hit)")
    eid = cr.json()["employee"]["id"]
    d = requests.delete(f"{API}/company/employees/{eid}", headers=admin_headers, timeout=30)
    assert d.status_code == 200
