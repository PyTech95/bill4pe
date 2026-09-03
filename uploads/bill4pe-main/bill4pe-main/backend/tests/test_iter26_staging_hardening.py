"""Iteration 26 — staging hardening verification for bill4pe.

Scope (backend only):
  - health + provider diagnostics
  - auth (superadmin login, register, login, JWT protected routes)
  - expense/bill creation + fee math + retrieval
  - server-side input validation on amount fields
  - rate limiting on auth routes
  - payment endpoints degrade gracefully with NO Razorpay keys
  - webhook signature enforcement

NOTE: RateLimitMiddleware keys buckets on X-Forwarded-For, so each test class
sends its own synthetic client IP to avoid cross-test bucket pollution.
"""
import os
import re
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing from env and /app/frontend/.env")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

TIMEOUT = 45


def _client(ip_suffix: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        # unique synthetic IP -> isolated rate-limit bucket per test class
        "X-Forwarded-For": f"10.{ip_suffix}",
    })
    return s


@pytest.fixture(scope="session")
def super_admin_creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("Missing /app/memory/test_credentials.md")
    c = p.read_text(encoding="utf-8")
    e = re.search(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)", c)
    pw = re.search(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)", c)
    if not e or not pw:
        pytest.skip("No email/password found in test_credentials.md")
    return {"email": e.group(1), "password": pw.group(1)}


def _expense_payload(unit_price=250.0, qty=2, amount=500.0):
    return {
        "category": "Travel",
        "sub_category": "Auto",
        "items": [{"name": "TEST_ride", "quantity": qty, "unit_price": unit_price}],
        "payment": {
            "merchant_name": "TEST_Merchant",
            "merchant_upi": "test@upi",
            "amount": amount,
            "payment_method": "UPI",
            "payment_status": "paid",
        },
        "notes": "TEST_iter26",
    }


# ---------------------------------------------------------------- health ----
class TestHealth:
    api = _client("0.0.1")

    def test_health_ok(self):
        r = self.api.get(f"{API}/health", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        assert r.json() == {"status": "ok"}

    def test_providers_staging_posture(self):
        r = self.api.get(f"{API}/health/providers", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # payments must NOT be configured on staging
        assert d["payments"]["razorpay_configured"] is False
        assert d["payments"]["webhook_secret_set"] is False
        # isolated staging DB
        assert d["database"]["db_name"] == "bill4pe_staging"
        # AI available via emergent key
        assert d["ai"]["fallback_emergent_llm"] is True


# ------------------------------------------------------------------ auth ----
class TestAuth:
    api = _client("0.0.2")

    def test_superadmin_login(self, super_admin_creds):
        r = self.api.post(f"{API}/auth/login", json=super_admin_creds, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d.get("token"), str) and len(d["token"]) > 20
        assert d["user"]["email"] == super_admin_creds["email"].lower()
        assert "password" not in d["user"]
        assert "_id" not in d["user"]

    def test_me_with_token(self, super_admin_creds):
        tok = self.api.post(f"{API}/auth/login", json=super_admin_creds, timeout=TIMEOUT).json()["token"]
        r = self.api.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["email"] == super_admin_creds["email"].lower()

    def test_login_wrong_password(self, super_admin_creds):
        r = self.api.post(f"{API}/auth/login",
                          json={"email": super_admin_creds["email"], "password": "definitely-wrong"},
                          timeout=TIMEOUT)
        assert r.status_code == 401, r.text[:300]

    def test_me_without_token_rejected(self):
        r = requests.get(f"{API}/auth/me", timeout=TIMEOUT)
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"

    def test_me_with_bad_token_rejected(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer not.a.jwt"}, timeout=TIMEOUT)
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"

    def test_register_then_login(self):
        email = f"TEST_iter26_{uuid.uuid4().hex[:8]}@example.com"
        r = self.api.post(f"{API}/auth/register",
                          json={"email": email, "password": "TestPass@123", "name": "TEST User"},
                          timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["user"]["email"] == email.lower()
        assert d["user"]["wallet_balance"] == 50.0  # welcome bonus
        assert "password" not in d["user"]
        # duplicate registration blocked
        dup = self.api.post(f"{API}/auth/register",
                            json={"email": email, "password": "TestPass@123", "name": "TEST User"},
                            timeout=TIMEOUT)
        assert dup.status_code == 400, dup.text[:200]
        # login with the new account
        li = self.api.post(f"{API}/auth/login", json={"email": email, "password": "TestPass@123"}, timeout=TIMEOUT)
        assert li.status_code == 200, li.text[:300]
        assert isinstance(li.json()["token"], str)

    def test_register_invalid_email_rejected(self):
        r = self.api.post(f"{API}/auth/register",
                          json={"email": "not-an-email", "password": "x" * 8, "name": "TEST"},
                          timeout=TIMEOUT)
        assert r.status_code == 422, r.text[:200]

    def test_otp_demo_flow(self):
        phone = "9" + str(uuid.uuid4().int)[:9]
        rq = self.api.post(f"{API}/auth/otp/request", json={"phone": phone}, timeout=TIMEOUT)
        assert rq.status_code == 200, rq.text[:200]
        bad = self.api.post(f"{API}/auth/otp/verify", json={"phone": phone, "otp": "000000"}, timeout=TIMEOUT)
        assert bad.status_code == 401, bad.text[:200]
        ok = self.api.post(f"{API}/auth/otp/verify", json={"phone": phone, "otp": "123456"}, timeout=TIMEOUT)
        assert ok.status_code == 200, ok.text[:300]
        assert isinstance(ok.json()["token"], str)


# --------------------------------------------- bills / expenses + fee math ----
class TestBillsAndFees:
    api = _client("0.0.3")

    @pytest.fixture(scope="class")
    def user_token(self):
        email = f"TEST_iter26_bills_{uuid.uuid4().hex[:8]}@example.com"
        r = self.api.post(f"{API}/auth/register",
                          json={"email": email, "password": "TestPass@123", "name": "TEST Bills"},
                          timeout=TIMEOUT)
        if r.status_code != 200:
            pytest.fail(f"register failed: {r.status_code} {r.text[:300]}")
        return r.json()["token"]

    @pytest.fixture(scope="class")
    def auth(self, user_token):
        s = _client("0.0.3")
        s.headers.update({"Authorization": f"Bearer {user_token}"})
        return s

    def test_create_expense_and_retrieve(self, auth):
        r = auth.post(f"{API}/expenses", json=_expense_payload(250.0, 2, 500.0), timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "_id" not in d
        assert d["total"] == 500.0  # 2 * 250
        assert d["bill_generated"] is False
        eid = d["id"]

        g = auth.get(f"{API}/expenses/{eid}", timeout=TIMEOUT)
        assert g.status_code == 200, g.text[:300]
        gd = g.json()
        assert gd["id"] == eid
        assert gd["total"] == 500.0
        assert gd["category"] == "Travel"
        assert gd["payment"]["amount"] == 500.0
        assert "_id" not in gd

        lst = auth.get(f"{API}/expenses", timeout=TIMEOUT)
        assert lst.status_code == 200
        rows = lst.json()["expenses"]
        assert any(x["id"] == eid for x in rows)

    def test_fee_info_and_generate_bill_math(self, auth):
        fi = auth.get(f"{API}/bills/fee-info", timeout=TIMEOUT)
        assert fi.status_code == 200, fi.text[:300]
        fee_percent = fi.json()["percent"]
        assert isinstance(fee_percent, (int, float)) and fee_percent >= 0

        me_before = auth.get(f"{API}/auth/me", timeout=TIMEOUT).json()
        bal_before = float(me_before["wallet_balance"])

        # small bill so the 50 INR welcome bonus covers the fee
        exp = auth.post(f"{API}/expenses", json=_expense_payload(100.0, 1, 100.0), timeout=TIMEOUT).json()
        gen = auth.post(f"{API}/bills/{exp['id']}/generate", json={}, timeout=TIMEOUT)
        assert gen.status_code == 200, f"{gen.status_code} {gen.text[:300]}"
        gd = gen.json()
        assert gd["bill_id"].startswith("B4P-")
        assert gd["fee_paid_via"] == "wallet"
        expected_fee = round(100.0 * gd["fee_percent"] / 100.0, 2)
        assert abs(gd["fee"] - expected_fee) < 0.51, f"fee {gd['fee']} vs expected ~{expected_fee}"
        assert abs(gd["wallet_balance"] - round(bal_before - gd["fee"], 2)) < 0.01

        # persisted?
        after = auth.get(f"{API}/expenses/{exp['id']}", timeout=TIMEOUT).json()
        assert after["bill_generated"] is True
        assert after["bill_id"] == gd["bill_id"]
        assert after["bill_fee"] == gd["fee"]

        # wallet actually debited
        me_after = auth.get(f"{API}/auth/me", timeout=TIMEOUT).json()
        assert abs(float(me_after["wallet_balance"]) - gd["wallet_balance"]) < 0.01

        # idempotent second call
        again = auth.post(f"{API}/bills/{exp['id']}/generate", json={}, timeout=TIMEOUT)
        assert again.status_code == 200
        assert again.json()["bill_id"] == gd["bill_id"]

    def test_generate_bill_unknown_expense_404(self, auth):
        r = auth.post(f"{API}/bills/{uuid.uuid4()}/generate", json={}, timeout=TIMEOUT)
        assert r.status_code == 404, r.text[:200]

    def test_expense_requires_auth(self):
        r = requests.post(f"{API}/expenses", json=_expense_payload(), timeout=TIMEOUT)
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"

    def test_bill_pdf_download(self, auth, user_token):
        exp = auth.post(f"{API}/expenses", json=_expense_payload(50.0, 1, 50.0), timeout=TIMEOUT).json()
        auth.post(f"{API}/bills/{exp['id']}/generate", json={}, timeout=TIMEOUT)
        r = auth.get(f"{API}/bills/{exp['id']}/pdf", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_bill_pdf_other_user_cannot_access(self, auth):
        exp = auth.post(f"{API}/expenses", json=_expense_payload(50.0, 1, 50.0), timeout=TIMEOUT).json()
        other = _client("0.0.3")
        em = f"TEST_iter26_other_{uuid.uuid4().hex[:8]}@example.com"
        tok = other.post(f"{API}/auth/register",
                         json={"email": em, "password": "TestPass@123", "name": "TEST Other"},
                         timeout=TIMEOUT).json()["token"]
        other.headers.update({"Authorization": f"Bearer {tok}"})
        r = other.get(f"{API}/expenses/{exp['id']}", timeout=TIMEOUT)
        assert r.status_code == 404, f"cross-user leak: {r.status_code} {r.text[:200]}"


# ------------------------------------------------- server-side validation ----
class TestServerSideValidation:
    api = _client("0.0.4")

    @pytest.fixture(scope="class")
    def auth(self):
        s = _client("0.0.4")
        em = f"TEST_iter26_val_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{API}/auth/register",
                   json={"email": em, "password": "TestPass@123", "name": "TEST Val"}, timeout=TIMEOUT)
        if r.status_code != 200:
            pytest.fail(f"register failed: {r.status_code} {r.text[:300]}")
        s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        return s

    def test_missing_required_fields_rejected(self, auth):
        r = auth.post(f"{API}/expenses", json={"category": "Travel"}, timeout=TIMEOUT)
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

    def test_non_numeric_amount_rejected(self, auth):
        p = _expense_payload()
        p["payment"]["amount"] = "abcd"
        r = auth.post(f"{API}/expenses", json=p, timeout=TIMEOUT)
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

    def test_missing_payment_amount_rejected(self, auth):
        p = _expense_payload()
        p["payment"].pop("amount")
        r = auth.post(f"{API}/expenses", json=p, timeout=TIMEOUT)
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

    def test_empty_items_rejected(self, auth):
        p = _expense_payload()
        p["items"] = []
        r = auth.post(f"{API}/expenses", json=p, timeout=TIMEOUT)
        assert 400 <= r.status_code < 500, f"empty items accepted: {r.status_code} {r.text[:300]}"

    def test_negative_amount_rejected(self, auth):
        p = _expense_payload(unit_price=-500.0, qty=1, amount=-500.0)
        r = auth.post(f"{API}/expenses", json=p, timeout=TIMEOUT)
        assert 400 <= r.status_code < 500, f"negative amount accepted: {r.status_code} {r.text[:300]}"

    def test_zero_amount_rejected(self, auth):
        p = _expense_payload(unit_price=0.0, qty=1, amount=0.0)
        r = auth.post(f"{API}/expenses", json=p, timeout=TIMEOUT)
        assert 400 <= r.status_code < 500, f"zero amount accepted: {r.status_code} {r.text[:300]}"

    def test_negative_quantity_rejected(self, auth):
        p = _expense_payload(unit_price=100.0, qty=-5, amount=100.0)
        r = auth.post(f"{API}/expenses", json=p, timeout=TIMEOUT)
        assert 400 <= r.status_code < 500, f"negative qty accepted: {r.status_code} {r.text[:300]}"

    def test_fee_preview_rejects_non_positive(self, auth):
        r = auth.get(f"{API}/payments/fee-preview", params={"merchant_amount": -10}, timeout=TIMEOUT)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        r0 = auth.get(f"{API}/payments/fee-preview", params={"merchant_amount": 0}, timeout=TIMEOUT)
        assert r0.status_code == 400, f"{r0.status_code} {r0.text[:200]}"

    def test_wallet_recharge_rejects_non_positive(self, auth):
        r = auth.post(f"{API}/wallet/recharge", json={"amount": -1000}, timeout=TIMEOUT)
        assert 400 <= r.status_code < 500, f"negative recharge accepted: {r.status_code} {r.text[:300]}"

    def test_manual_pay_first_scan_rejects_negative_amount(self, auth):
        r = auth.post(f"{API}/manual-pay/first-scan",
                      json={"payee_upi": "test@upi", "merchant_amount": -100},
                      timeout=TIMEOUT)
        assert 400 <= r.status_code < 500, f"negative merchant_amount accepted: {r.status_code} {r.text[:300]}"


# --------------------------------------------------------- rate limiting ----
class TestRateLimiting:
    def test_login_brute_force_returns_429(self):
        s = _client(f"9.9.{uuid.uuid4().int % 250}")
        codes = []
        for _ in range(14):
            r = s.post(f"{API}/auth/login",
                       json={"email": "TEST_bruteforce@example.com", "password": "wrong"},
                       timeout=TIMEOUT)
            codes.append(r.status_code)
            if r.status_code == 429:
                assert "Retry-After" in r.headers
                break
        assert 429 in codes, f"no 429 after {len(codes)} bad logins: {codes}"
        assert codes.count(401) >= 5, f"unexpected pre-429 codes: {codes}"

    def test_register_rate_limited(self):
        s = _client(f"9.8.{uuid.uuid4().int % 250}")
        codes = []
        for _ in range(9):
            r = s.post(f"{API}/auth/register",
                       json={"email": f"TEST_rl_{uuid.uuid4().hex[:8]}@example.com",
                             "password": "TestPass@123", "name": "TEST RL"},
                       timeout=TIMEOUT)
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"register not rate limited: {codes}"

    def test_health_not_rate_limited(self):
        s = _client("9.7.1")
        for _ in range(15):
            assert s.get(f"{API}/health", timeout=TIMEOUT).status_code == 200


# ------------------------------------------------------- payment safety ----
class TestPaymentSafetyUnconfigured:
    @pytest.fixture(scope="class")
    def auth(self):
        s = _client("0.0.5")
        em = f"TEST_iter26_pay_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{API}/auth/register",
                   json={"email": em, "password": "TestPass@123", "name": "TEST Pay"}, timeout=TIMEOUT)
        if r.status_code != 200:
            pytest.fail(f"register failed: {r.status_code} {r.text[:300]}")
        s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        return s

    def test_payments_config_reports_disabled(self, auth):
        r = auth.get(f"{API}/payments/config", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["enabled"] is False, f"payments reported enabled with no keys: {d}"
        assert d.get("key_id") in (None, ""), f"key_id leaked: {d.get('key_id')}"
        assert d["payout_enabled"] is False

    def test_create_order_degrades_gracefully(self, auth):
        r = auth.post(f"{API}/payments/create-order",
                      json={"purpose": "wallet_recharge", "amount": 100}, timeout=TIMEOUT)
        assert r.status_code != 500, f"500 from create-order: {r.text[:400]}"
        assert 400 <= r.status_code < 600 and r.status_code not in (200, 201), \
            f"order created with no keys: {r.status_code} {r.text[:300]}"

    def test_merchant_create_order_degrades_gracefully(self, auth):
        r = auth.post(f"{API}/payments/merchant/create-order",
                      json={"payee_upi": "test@upi", "merchant_amount": 100}, timeout=TIMEOUT)
        assert r.status_code != 500, f"500 from merchant/create-order: {r.text[:400]}"
        assert r.status_code != 200, f"order created with no keys: {r.text[:300]}"

    def test_legacy_order_degrades_gracefully(self, auth):
        r = auth.post(f"{API}/payments/razorpay/order",
                      json={"purpose": "wallet_recharge", "amount": 100}, timeout=TIMEOUT)
        assert r.status_code != 500, f"500 from legacy order: {r.text[:400]}"
        assert r.status_code != 200, f"order created with no keys: {r.text[:300]}"

    def test_verify_with_fake_signature_never_credits(self, auth):
        before = float(auth.get(f"{API}/auth/me", timeout=TIMEOUT).json()["wallet_balance"])
        r = auth.post(f"{API}/payments/verify",
                      json={"razorpay_order_id": "order_FAKE123",
                            "razorpay_payment_id": "pay_FAKE123",
                            "razorpay_signature": "deadbeef"},
                      timeout=TIMEOUT)
        assert r.status_code != 500, f"500 from verify: {r.text[:400]}"
        assert r.status_code != 200 or r.json().get("success") is False, \
            f"fake signature accepted: {r.status_code} {r.text[:300]}"
        after = float(auth.get(f"{API}/auth/me", timeout=TIMEOUT).json()["wallet_balance"])
        assert after == before, f"wallet changed on fake verify: {before} -> {after}"

    def test_legacy_verify_fake_signature_rejected(self, auth):
        r = auth.post(f"{API}/payments/razorpay/verify",
                      json={"razorpay_order_id": "order_FAKE123",
                            "razorpay_payment_id": "pay_FAKE123",
                            "razorpay_signature": "deadbeef"},
                      timeout=TIMEOUT)
        assert r.status_code in (400, 404, 503), f"{r.status_code} {r.text[:300]}"

    def test_payment_status_unknown_txn_404(self, auth):
        r = auth.get(f"{API}/payments/{uuid.uuid4()}/status", timeout=TIMEOUT)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_payments_require_auth(self):
        for path, method in [("/payments/create-order", "post"),
                             ("/payments/merchant/create-order", "post"),
                             ("/payments/history", "get"),
                             ("/manual-pay/config", "get")]:
            r = getattr(requests, method)(f"{API}{path}", json={}, timeout=TIMEOUT)
            assert r.status_code in (401, 403), f"{path} unauthenticated -> {r.status_code}"

    def test_manual_pay_config_and_first_scan(self, auth):
        c = auth.get(f"{API}/manual-pay/config", timeout=TIMEOUT)
        assert c.status_code == 200, c.text[:300]
        cd = c.json()
        assert cd["flow_mode"] == "manual_upi_double_scan"
        # fee percent is intentionally returned as a decimal-safe string
        assert float(cd["platform_fee_percent"]) >= 0

        r = auth.post(f"{API}/manual-pay/first-scan",
                      json={"payee_upi": "test@upi", "payee_name": "TEST Payee", "merchant_amount": 200},
                      timeout=TIMEOUT)
        assert r.status_code != 500, f"500 from first-scan: {r.text[:400]}"
        # manual flow needs no gateway keys -> should work
        assert r.status_code == 200, f"manual first-scan failed: {r.status_code} {r.text[:300]}"
        d = r.json()
        tid = d.get("transaction_id") or d.get("id")
        assert tid, f"no transaction id: {d}"

        # second scan must not be able to swap the locked payee (soft-mismatch
        # contract: 200 + match=false, snapshot unchanged)
        bad = auth.post(f"{API}/manual-pay/{tid}/second-scan", json={"payee_upi": "attacker@upi"}, timeout=TIMEOUT)
        assert bad.status_code in (200, 400, 409), f"{bad.status_code} {bad.text[:300]}"
        if bad.status_code == 200:
            bd = bad.json()
            assert bd.get("match") is False, f"attacker UPI accepted as match: {bd}"
            assert bd["payee_upi"] == "test@upi", f"payee UPI overwritten: {bd}"

        ok = auth.post(f"{API}/manual-pay/{tid}/second-scan", json={"payee_upi": "test@upi"}, timeout=TIMEOUT)
        assert ok.status_code == 200, f"{ok.status_code} {ok.text[:300]}"
        assert ok.json().get("match") is not False

    def test_wallet_recharge_must_not_self_credit_without_payment(self, auth):
        """Staging posture: no payment gateway configured, so an authenticated
        user must NOT be able to mint wallet balance (wallet pays bill fees)."""
        before = float(auth.get(f"{API}/auth/me", timeout=TIMEOUT).json()["wallet_balance"])
        r = auth.post(f"{API}/wallet/recharge", json={"amount": 5000}, timeout=TIMEOUT)
        after = float(auth.get(f"{API}/auth/me", timeout=TIMEOUT).json()["wallet_balance"])
        assert after == before, (
            f"free wallet credit: {before} -> {after} via {r.status_code} {r.text[:200]}"
        )

    def test_manual_pay_unknown_txn_404(self, auth):
        r = auth.post(f"{API}/manual-pay/{uuid.uuid4()}/second-scan",
                      json={"payee_upi": "test@upi"}, timeout=TIMEOUT)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"


# ------------------------------------------------------------- webhooks ----
class TestWebhookSecurity:
    api = _client("0.0.6")
    EVENT = {"event": "payment.captured",
             "payload": {"payment": {"entity": {"id": "pay_FAKE", "order_id": "order_FAKE", "amount": 100000}}}}

    @pytest.mark.parametrize("path", [
        "/webhooks/razorpay",
        "/webhooks/razorpay/payments",
        "/webhooks/razorpayx/payouts",
    ])
    def test_unsigned_webhook_rejected(self, path):
        r = self.api.post(f"{API}{path}", json=self.EVENT, timeout=TIMEOUT)
        assert r.status_code in (400, 503), f"{path} unsigned -> {r.status_code} {r.text[:300]}"
        assert r.status_code != 200

    @pytest.mark.parametrize("path", [
        "/webhooks/razorpay",
        "/webhooks/razorpay/payments",
        "/webhooks/razorpayx/payouts",
    ])
    def test_invalid_signature_webhook_rejected(self, path):
        r = self.api.post(f"{API}{path}", json=self.EVENT,
                          headers={"X-Razorpay-Signature": "0" * 64,
                                   "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}"},
                          timeout=TIMEOUT)
        assert r.status_code in (400, 503), f"{path} bad sig -> {r.status_code} {r.text[:300]}"
        assert r.status_code != 200
