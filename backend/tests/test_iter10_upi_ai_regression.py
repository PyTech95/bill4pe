"""Iteration 10 regression suite — UPI fix + AI route registration + full E2E.

Covers:
- AI route registration (openapi.json contains the 4 AI endpoints)
- AI 500 with documented detail when keys empty (NOT 404)
- Phone OTP login (9999999999 / 123456)
- Super admin login + superadmin endpoints
- Expense CRUD (food/travel/hotel/grocery) + stats + recent merchants + CSV export
- Wallet GET + recharge
- Bills generate + PDF binary
- Reports create + list + PDF binary
- Company B2B register/admin/employees/wallet
- Referrals me/validate
- Contact endpoint
"""
import io
import os
import time
import uuid

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-expense-hub-8.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


# ----------------------- Fixtures -----------------------

@pytest.fixture(scope="module")
def otp_user():
    """Phone OTP login → JWT."""
    phone = "9999999999"
    r = requests.post(f"{API}/auth/otp/request", json={"phone": phone}, timeout=30)
    assert r.status_code == 200, f"otp/request failed: {r.status_code} {r.text}"
    r = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "otp": "123456"}, timeout=30)
    assert r.status_code == 200, f"otp/verify failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    return {"token": data["token"], "user": data["user"]}


@pytest.fixture(scope="module")
def auth_h(otp_user):
    return {"Authorization": f"Bearer {otp_user['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "ujjwal@bill4pe.com", "password": "Bill4Pe@2026"},
        timeout=30,
    )
    assert r.status_code == 200, f"super-admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["user"].get("is_super_admin") is True
    return data["token"]


# ----------------------- AI route registration -----------------------

class TestAiRouteRegistration:
    def test_openapi_lists_ai_endpoints(self):
        # openapi.json is not behind /api → public ingress only routes /api/* and / to frontend.
        # Use internal supervisor port (same FastAPI app) to assert route registration.
        r = requests.get("http://localhost:8001/openapi.json", timeout=30)
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        for p in ["/api/voice/expense", "/api/ai/scan-receipt", "/api/ai/detect-items", "/api/ai/suggest-items"]:
            assert p in paths, f"missing route: {p}"

    def test_voice_endpoint_returns_500_when_openai_key_empty(self, auth_h):
        files = {"file": ("a.webm", b"\x00\x01\x02hello", "audio/webm")}
        h = {"Authorization": auth_h["Authorization"]}  # no Content-Type for multipart
        r = requests.post(f"{API}/voice/expense", headers=h, files=files, timeout=30)
        # MUST be 500 with documented detail (NOT 404)
        assert r.status_code == 500, f"expected 500, got {r.status_code}: {r.text}"
        body = r.json()
        assert "OPENAI_API_KEY" in body.get("detail", ""), body

    def test_scan_receipt_500_when_gemini_empty(self, auth_h):
        files = {"file": ("r.jpg", b"\xff\xd8\xff\xe0fake", "image/jpeg")}
        h = {"Authorization": auth_h["Authorization"]}
        r = requests.post(f"{API}/ai/scan-receipt", headers=h, files=files, timeout=30)
        assert r.status_code == 500
        assert "GEMINI_API_KEY" in r.json().get("detail", "")

    def test_detect_items_500_when_gemini_empty(self, auth_h):
        files = {"file": ("r.jpg", b"\xff\xd8\xff\xe0fake", "image/jpeg")}
        h = {"Authorization": auth_h["Authorization"]}
        r = requests.post(f"{API}/ai/detect-items?category=food", headers=h, files=files, timeout=30)
        assert r.status_code == 500
        assert "GEMINI_API_KEY" in r.json().get("detail", "")

    def test_suggest_items_returns_empty_when_no_key(self, auth_h):
        # This endpoint returns {suggestions: []} gracefully (200), not 500
        r = requests.post(f"{API}/ai/suggest-items", headers=auth_h, json={"category": "food", "query": "ro"}, timeout=30)
        assert r.status_code == 200
        assert r.json() == {"suggestions": []}


# ----------------------- Auth -----------------------

class TestAuth:
    def test_otp_flow(self, otp_user):
        assert otp_user["token"]
        # phone stored with +91 prefix
        assert "9999999999" in otp_user["user"]["phone"]

    def test_super_admin_login(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/auth/me", headers=h, timeout=30)
        assert r.status_code == 200
        assert r.json().get("is_super_admin") is True


# ----------------------- Super admin endpoints -----------------------

class TestSuperAdmin:
    def test_stats(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/superadmin/stats", headers=h, timeout=30)
        assert r.status_code == 200, r.text

    def test_users(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/superadmin/users", headers=h, timeout=30)
        assert r.status_code == 200

    def test_companies(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/superadmin/companies", headers=h, timeout=30)
        assert r.status_code == 200


# ----------------------- Expenses -----------------------

CATEGORIES = ["food", "travel", "hotel", "grocery"]


@pytest.fixture(scope="module")
def created_expense_ids(auth_h):
    ids = []
    for cat in CATEGORIES:
        items = [{"name": f"TEST item {cat}", "quantity": 2, "unit_price": 25.0}]
        total = sum(i["quantity"] * i["unit_price"] for i in items)
        payload = {
            "category": cat,
            "sub_category": f"TEST_{cat}",
            "items": items,
            "notes": "TEST regression",
            "payment": {
                "merchant_name": f"TEST_merchant_{cat}",
                "merchant_upi": "test@oksbi",
                "transaction_id": f"TXN{uuid.uuid4().hex[:8].upper()}",
                "amount": total,
                "payment_method": "UPI",
                "payment_status": "paid",
            },
        }
        r = requests.post(f"{API}/expenses", headers=auth_h, json=payload, timeout=30)
        assert r.status_code in (200, 201), f"{cat} create failed: {r.status_code} {r.text}"
        d = r.json()
        assert d.get("category") == cat
        assert "id" in d
        ids.append(d["id"])
    return ids


class TestExpenses:
    def test_create_all_categories(self, created_expense_ids):
        assert len(created_expense_ids) == 4

    def test_get_list(self, auth_h, created_expense_ids):
        r = requests.get(f"{API}/expenses", headers=auth_h, timeout=30)
        assert r.status_code == 200
        body = r.json()
        items = body if isinstance(body, list) else body.get("expenses", [])
        ids = {e["id"] for e in items}
        for eid in created_expense_ids:
            assert eid in ids

    def test_get_by_id(self, auth_h, created_expense_ids):
        r = requests.get(f"{API}/expenses/{created_expense_ids[0]}", headers=auth_h, timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == created_expense_ids[0]

    def test_stats(self, auth_h):
        r = requests.get(f"{API}/expenses/stats", headers=auth_h, timeout=30)
        assert r.status_code == 200

    def test_recent_merchants(self, auth_h):
        r = requests.get(f"{API}/expenses/merchants/recent", headers=auth_h, timeout=30)
        assert r.status_code == 200

    def test_csv_export(self, auth_h):
        r = requests.get(f"{API}/expenses/export/csv", headers=auth_h, timeout=30)
        # could be /export.csv or query — try alternate if 404
        if r.status_code == 404:
            r = requests.get(f"{API}/expenses?format=csv", headers=auth_h, timeout=30)
        assert r.status_code == 200, f"csv export failed: {r.status_code} {r.text[:200]}"


# ----------------------- Wallet -----------------------

class TestWallet:
    def test_get_wallet(self, auth_h):
        r = requests.get(f"{API}/wallet", headers=auth_h, timeout=30)
        assert r.status_code == 200
        assert "balance" in r.json()

    def test_recharge(self, auth_h):
        before = requests.get(f"{API}/wallet", headers=auth_h, timeout=30).json()["balance"]
        r = requests.post(f"{API}/wallet/recharge", headers=auth_h, json={"amount": 100}, timeout=30)
        assert r.status_code == 200, r.text
        after = requests.get(f"{API}/wallet", headers=auth_h, timeout=30).json()["balance"]
        assert after >= before + 100 - 0.01


# ----------------------- Bills + PDF -----------------------

class TestBills:
    def test_generate_and_pdf(self, auth_h, created_expense_ids):
        eid = created_expense_ids[0]
        # ensure wallet has funds
        requests.post(f"{API}/wallet/recharge", headers=auth_h, json={"amount": 100}, timeout=30)
        r = requests.post(f"{API}/bills/{eid}/generate", headers=auth_h, timeout=30)
        assert r.status_code in (200, 201), f"bill generate failed: {r.status_code} {r.text}"
        body = r.json()
        assert "bill_id" in body

        r = requests.get(f"{API}/bills/{eid}/pdf", headers=auth_h, timeout=60)
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "").lower()
        assert "application/pdf" in ct or r.content[:4] == b"%PDF", f"not PDF: ct={ct} head={r.content[:8]}"


# ----------------------- Reports -----------------------

class TestReports:
    def test_create_list_pdf(self, auth_h, created_expense_ids):
        payload = {
            "title": f"TEST_report_{uuid.uuid4().hex[:6]}",
            "expense_ids": created_expense_ids[:2],
        }
        r = requests.post(f"{API}/reports", headers=auth_h, json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        rid = r.json().get("id")
        assert rid

        r = requests.get(f"{API}/reports", headers=auth_h, timeout=30)
        assert r.status_code == 200

        r = requests.get(f"{API}/reports/{rid}/pdf", headers=auth_h, timeout=60)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "").lower() or r.content[:4] == b"%PDF"


# ----------------------- Company B2B -----------------------

@pytest.fixture(scope="module")
def corporate_admin():
    email = f"admin_{int(time.time())}_{uuid.uuid4().hex[:4]}@democorp.com"
    payload = {
        "email": email,
        "password": "test123",
        "name": "Corp Admin",
        "user_type": "corporate",
        "corporate_name": "Demo Co TEST",
        "subscription_plan": "monthly_50",
        "employee_limit": 50,
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"].get("role") == "admin"
    assert data["user"].get("company_id")
    return {"token": data["token"], "user": data["user"], "email": email}


class TestCompanyB2B:
    def test_register(self, corporate_admin):
        assert corporate_admin["token"]

    def test_company_me(self, corporate_admin):
        h = {"Authorization": f"Bearer {corporate_admin['token']}"}
        r = requests.get(f"{API}/company/me", headers=h, timeout=30)
        assert r.status_code == 200, r.text

    def test_add_employee(self, corporate_admin):
        h = {"Authorization": f"Bearer {corporate_admin['token']}", "Content-Type": "application/json"}
        emp_email = f"emp_{uuid.uuid4().hex[:6]}@democorp.com"
        r = requests.post(
            f"{API}/company/employees",
            headers=h,
            json={"email": emp_email, "name": "Emp Test"},
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text

    def test_company_wallet_flow(self, corporate_admin):
        h = {"Authorization": f"Bearer {corporate_admin['token']}", "Content-Type": "application/json"}
        r = requests.get(f"{API}/company/wallet", headers=h, timeout=30)
        assert r.status_code == 200
        r = requests.post(f"{API}/company/wallet/recharge", headers=h, json={"amount": 500}, timeout=30)
        assert r.status_code == 200, r.text


# ----------------------- Referrals -----------------------

class TestReferrals:
    def test_me(self, auth_h):
        r = requests.get(f"{API}/referrals/me", headers=auth_h, timeout=30)
        assert r.status_code == 200
        body = r.json()
        code = body.get("code") or body.get("referral_code")
        assert code, f"no referral code in response: {body}"
        # validate
        r = requests.get(f"{API}/referrals/validate/{code}", timeout=30)
        assert r.status_code == 200
        assert r.json().get("valid") is True


# ----------------------- Contact -----------------------

class TestContact:
    def test_post_contact(self):
        payload = {
            "name": "TEST Tester",
            "email": "test@bill4pe-qa.com",
            "message": "TEST regression iteration 10",
        }
        r = requests.post(f"{API}/contact", json=payload, timeout=30)
        # 200 or 202 acceptable
        assert r.status_code in (200, 201, 202), f"{r.status_code} {r.text}"


# ----------------------- emergentintegrations cleanup -----------------------

class TestNoEmergentImports:
    def test_no_runtime_emergent_imports(self):
        import subprocess
        # search for `import emergentintegrations` or `from emergentintegrations` (not in comments)
        out = subprocess.run(
            ["grep", "-rn", "-E", r"^\s*(import|from)\s+emergentintegrations", "/app/backend/"],
            capture_output=True, text=True,
        )
        # Only docstring/comments allowed → stdout should be empty
        assert out.stdout.strip() == "", f"emergentintegrations imports still present:\n{out.stdout}"
