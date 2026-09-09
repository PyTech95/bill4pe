"""BILL4PE manual double-scan UPI flow (PAYMENT_FLOW_MODE=manual_upi_double_scan).

Covers: first-scan freeze + 1% fee, second-scan match/mismatch, confirm,
proof (UTR/last4/screenshot validation + authz), wallet-first generate with
idempotency, IDOR, recovery, admin endpoints, and core regressions.
"""
import io
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
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "dhiraj@callnman.com", "password": "Bill4Pe@2026"}
DRAFT = {"category": "Food", "items": [{"name": "Lunch", "quantity": 1, "unit_price": 200}]}


def _register():
    """Register a fresh individual user (retries on the API rate limiter)."""
    email = f"TEST_mds_{uuid.uuid4().hex[:10]}@example.com"
    r = None
    for attempt in range(6):
        r = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "Test@12345", "name": "TEST Manual Scan"}, timeout=30)
        if r.status_code != 429:
            break
        time.sleep(10)
    assert r.status_code in (200, 201), f"register failed {r.status_code} {r.text[:300]}"
    data = r.json()
    token = data.get("token")
    assert token, f"no token in register response: {data}"
    return {"email": email, "token": token, "id": (data.get("user") or {}).get("id")}


def _client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def user_a():
    return _register()


@pytest.fixture(scope="module")
def user_b():
    return _register()


@pytest.fixture(scope="module")
def ca(user_a):
    return _client(user_a["token"])


@pytest.fixture(scope="module")
def cb(user_b):
    return _client(user_b["token"])


@pytest.fixture(scope="module")
def admin_client():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code} {r.text[:300]}")
    token = r.json().get("token")
    assert token
    return _client(token)


def _first_scan(client, upi="abcstore@ybl", name="ABC STORE", draft=DRAFT):
    r = client.post(f"{API}/manual-pay/first-scan", json={
        "payee_upi": upi, "payee_name": name, "expense_draft": draft}, timeout=30)
    assert r.status_code == 200, f"first-scan {r.status_code} {r.text[:300]}"
    return r.json()


# ---------- config ----------
class TestConfig:
    def test_config(self):
        r = requests.get(f"{API}/manual-pay/config", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["flow_mode"] == "manual_upi_double_scan"
        assert str(d["platform_fee_percent"]) in ("1", "1.0")


# ---------- first scan freeze + fee math ----------
class TestFirstScan:
    def test_first_scan_freezes_merchant_and_fee(self, ca):
        t = _first_scan(ca)
        assert t["payee_upi"] == "abcstore@ybl"
        assert t["payee_name"] == "ABC STORE"
        assert t["merchant_amount_paise"] == 20000
        assert t["merchant_amount"] == 200.0
        assert t["platform_fee_paise"] == 200, f"expected 1% = 200 paise, got {t}"
        assert t["platform_fee"] == 2.0
        assert t["state"] == "second_qr_required"
        assert t["first_qr_verified"] is True
        assert t["second_qr_verified"] is False
        assert t["payment_session_locked"] is False
        assert t["fee_status"] == "not_started"
        assert t["merchant_verification_status"] == "unverified"

    def test_first_scan_invalid_upi(self, ca):
        r = ca.post(f"{API}/manual-pay/first-scan", json={"payee_upi": "notaupi", "expense_draft": DRAFT}, timeout=30)
        assert r.status_code == 400, r.text[:200]

    def test_first_scan_zero_amount(self, ca):
        r = ca.post(f"{API}/manual-pay/first-scan",
                    json={"payee_upi": "abc@ybl", "merchant_amount": 0}, timeout=30)
        assert r.status_code == 400, r.text[:200]

    def test_first_scan_requires_auth(self):
        r = requests.post(f"{API}/manual-pay/first-scan", json={"payee_upi": "abc@ybl", "merchant_amount": 10}, timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------- second scan ----------
class TestSecondScan:
    def test_second_scan_case_insensitive_match_locks(self, ca):
        t = _first_scan(ca)
        tid = t["transaction_id"]
        r = ca.post(f"{API}/manual-pay/{tid}/second-scan", json={"payee_upi": "ABCSTORE@YBL"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["match"] is True
        assert d["payment_session_locked"] is True
        assert d["second_qr_verified"] is True
        assert d["state"] == "awaiting_merchant_payment"
        # persisted
        g = ca.get(f"{API}/manual-pay/{tid}", timeout=30).json()
        assert g["payment_session_locked"] is True
        assert g["state"] == "awaiting_merchant_payment"

    def test_second_scan_mismatch_blocks(self, ca):
        t = _first_scan(ca)
        tid = t["transaction_id"]
        r = ca.post(f"{API}/manual-pay/{tid}/second-scan", json={"payee_upi": "other@ybl"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["match"] is False
        assert d["payment_session_locked"] is False
        assert d["payee_upi"] == "abcstore@ybl", "frozen merchant must not change"
        assert d["state"] == "second_qr_required"

    def test_confirm_before_second_scan_rejected(self, ca):
        t = _first_scan(ca)
        r = ca.post(f"{API}/manual-pay/{t['transaction_id']}/confirm", json={"completed": True}, timeout=30)
        assert r.status_code == 400, r.text[:200]


# ---------- confirm ----------
class TestConfirm:
    def test_not_yet_keeps_awaiting_then_yes_claims(self, ca):
        t = _first_scan(ca)
        tid = t["transaction_id"]
        ca.post(f"{API}/manual-pay/{tid}/second-scan", json={"payee_upi": "abcstore@ybl"}, timeout=30)
        r = ca.post(f"{API}/manual-pay/{tid}/confirm", json={"completed": False}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["merchant_payment_status"] == "awaiting_payment"
        assert d["fee_status"] == "not_started"
        assert d["bill_id"] is None
        # generate must be blocked without proof
        g = ca.post(f"{API}/manual-pay/{tid}/generate", timeout=30)
        assert g.status_code == 400, g.text[:200]

        r2 = ca.post(f"{API}/manual-pay/{tid}/confirm", json={"completed": True}, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["merchant_payment_status"] == "user_confirmed"
        assert d2["state"] == "merchant_payment_claimed"


# ---------- proof ----------
def _ready(client, upi="abcstore@ybl"):
    t = _first_scan(client, upi=upi)
    tid = t["transaction_id"]
    client.post(f"{API}/manual-pay/{tid}/second-scan", json={"payee_upi": upi}, timeout=30)
    client.post(f"{API}/manual-pay/{tid}/confirm", json={"completed": True}, timeout=30)
    return tid


PNG = (b"\x89PNG\r\n\x1a\n" + b"0" * 200)


class TestProof:
    def test_proof_full_utr(self, ca):
        tid = _ready(ca)
        r = ca.post(f"{API}/manual-pay/{tid}/proof", data={"utr_full": "123456789012"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["proof_status"] == "proof_submitted"
        assert d["merchant_payment_status"] == "proof_submitted"
        assert d["merchant_verification_status"] == "unverified"
        assert d["utr_last4"] == "9012"
        assert d["utr_full"] == "XXXXXXXX9012", f"UTR must be masked: {d['utr_full']}"
        assert d["fee_status"] == "due"

    def test_proof_last4_only(self, ca):
        tid = _ready(ca)
        r = ca.post(f"{API}/manual-pay/{tid}/proof", data={"utr_last4": "4321"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["proof_status"] == "partial_reference"
        assert d["merchant_payment_status"] == "user_confirmed"
        assert d["merchant_verification_status"] == "unverified"

    def test_proof_empty_rejected(self, ca):
        tid = _ready(ca)
        r = ca.post(f"{API}/manual-pay/{tid}/proof", data={}, timeout=30)
        assert r.status_code == 400, r.text[:200]

    def test_proof_screenshot_png_ok_and_owner_only_download(self, ca, cb, admin_client):
        tid = _ready(ca)
        r = ca.post(f"{API}/manual-pay/{tid}/proof",
                    files={"screenshot": ("p.png", io.BytesIO(PNG), "image/png")}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["has_screenshot"] is True
        # owner can fetch
        own = ca.get(f"{API}/manual-pay/{tid}/proof-file", timeout=30)
        assert own.status_code == 200, own.status_code
        # other user forbidden
        other = cb.get(f"{API}/manual-pay/{tid}/proof-file", timeout=30)
        assert other.status_code == 403, f"expected 403 got {other.status_code}"
        # admin allowed
        adm = admin_client.get(f"{API}/manual-pay/{tid}/proof-file", timeout=30)
        assert adm.status_code == 200, adm.status_code

    def test_proof_screenshot_jpg_webp_ok(self, ca):
        for fname, ct in (("p.jpg", "image/jpeg"), ("p.webp", "image/webp")):
            tid = _ready(ca)
            r = ca.post(f"{API}/manual-pay/{tid}/proof",
                        files={"screenshot": (fname, io.BytesIO(b"x" * 500), ct)}, timeout=60)
            assert r.status_code == 200, f"{ct} rejected: {r.status_code} {r.text[:200]}"

    def test_proof_bad_content_type_rejected(self, ca):
        tid = _ready(ca)
        r = ca.post(f"{API}/manual-pay/{tid}/proof",
                    files={"screenshot": ("evil.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}, timeout=60)
        assert r.status_code == 400, f"expected 400 got {r.status_code}"

    def test_proof_oversize_rejected(self, ca):
        tid = _ready(ca)
        big = io.BytesIO(b"0" * (5 * 1024 * 1024 + 1024))
        r = ca.post(f"{API}/manual-pay/{tid}/proof",
                    files={"screenshot": ("big.png", big, "image/png")}, timeout=120)
        assert r.status_code in (400, 413), f"expected 400/413 got {r.status_code}"


# ---------- generate / wallet / idempotency ----------
class TestGenerate:
    def test_wallet_debit_once_and_idempotent_generate(self, ca):
        w0 = ca.get(f"{API}/wallet", timeout=30)
        assert w0.status_code == 200, w0.text[:200]
        bal0 = float(w0.json().get("balance", w0.json().get("wallet_balance")))
        assert bal0 >= 2, f"fresh user should have welcome bonus, got {bal0}"

        tid = _ready(ca)
        ca.post(f"{API}/manual-pay/{tid}/proof", data={"utr_full": "998877665544"}, timeout=30)
        g = ca.post(f"{API}/manual-pay/{tid}/generate", timeout=60)
        assert g.status_code == 200, g.text[:300]
        d = g.json()
        assert d["generated"] is True, d
        assert d["fee_status"] == "paid"
        assert d["fee_payment_method"] == "wallet"
        bill_id = d["bill_id"]
        assert bill_id and bill_id.startswith("BILL-"), bill_id
        parts = bill_id.split("-")
        assert len(parts) == 3 and len(parts[2]) == 6 and parts[2].isdigit(), bill_id

        bal1 = float(ca.get(f"{API}/wallet", timeout=30).json().get("balance"))
        assert round(bal0 - bal1, 2) == 2.0, f"expected exactly 2.00 debit, {bal0}->{bal1}"

        # idempotent re-generate
        g2 = ca.post(f"{API}/manual-pay/{tid}/generate", timeout=60)
        assert g2.status_code == 200
        assert g2.json().get("bill_id") == bill_id
        bal2 = float(ca.get(f"{API}/wallet", timeout=30).json().get("balance"))
        assert bal2 == bal1, f"second generate debited again {bal1}->{bal2}"

        # exactly one expense for this txn
        ex = ca.get(f"{API}/expenses", timeout=30)
        assert ex.status_code == 200
        rows = ex.json() if isinstance(ex.json(), list) else ex.json().get("expenses", [])
        matches = [e for e in rows if e.get("transaction_id") == tid]
        assert len(matches) == 1, f"expected 1 expense for txn, got {len(matches)}"
        eid = matches[0].get("id")
        assert matches[0].get("bill_id") == bill_id
        assert "_id" not in matches[0]
        # receipt PDF
        pdf = ca.get(f"{API}/bills/{eid}/pdf", timeout=60)
        assert pdf.status_code == 200, f"pdf {pdf.status_code} {pdf.text[:200]}"
        assert pdf.content[:4] == b"%PDF", pdf.content[:20]

    def test_needs_fee_when_wallet_insufficient(self, ca):
        # drain wallet by repeated generates until insufficient
        bal = float(ca.get(f"{API}/wallet", timeout=30).json().get("balance"))
        last = None
        guard = 0
        while bal >= 2 and guard < 40:
            guard += 1
            tid = _ready(ca)
            ca.post(f"{API}/manual-pay/{tid}/proof", data={"utr_full": "111122223333"}, timeout=30)
            last = ca.post(f"{API}/manual-pay/{tid}/generate", timeout=60).json()
            bal = float(ca.get(f"{API}/wallet", timeout=30).json().get("balance"))
        tid = _ready(ca)
        ca.post(f"{API}/manual-pay/{tid}/proof", data={"utr_full": "444455556666"}, timeout=30)
        r = ca.post(f"{API}/manual-pay/{tid}/generate", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("generated") is False, d
        assert d.get("needs_fee") is True, d
        assert d.get("fee") == 2.0
        assert "wallet_balance" in d and d["wallet_balance"] < 2
        assert d.get("bill_id") is None
        # fee-order without Razorpay -> expected graceful 400
        fo = ca.post(f"{API}/manual-pay/{tid}/fee-order", timeout=30)
        assert fo.status_code == 400, fo.status_code


# ---------- IDOR / recovery ----------
class TestSecurity:
    def test_idor_cross_user(self, ca, cb):
        t = _first_scan(ca)
        tid = t["transaction_id"]
        assert cb.get(f"{API}/manual-pay/{tid}", timeout=30).status_code == 404
        assert cb.post(f"{API}/manual-pay/{tid}/second-scan", json={"payee_upi": "abcstore@ybl"}, timeout=30).status_code == 404
        assert cb.post(f"{API}/manual-pay/{tid}/confirm", json={"completed": True}, timeout=30).status_code == 404
        assert cb.post(f"{API}/manual-pay/{tid}/generate", timeout=30).status_code == 404
        assert cb.post(f"{API}/manual-pay/{tid}/cancel", timeout=30).status_code == 404

    def test_recovery_status_and_history(self, ca):
        tid = _ready(ca)
        r = ca.get(f"{API}/manual-pay/{tid}", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["transaction_id"] == tid
        assert d["payment_session_locked"] is True
        assert d["merchant_payment_status"] == "user_confirmed"
        h = ca.get(f"{API}/manual-pay/history", timeout=30)
        assert h.status_code == 200
        txns = h.json()["transactions"]
        assert any(x["transaction_id"] == tid for x in txns)

    def test_unknown_tid_404(self, ca):
        assert ca.get(f"{API}/manual-pay/B4P-2026-NOPE1234", timeout=30).status_code == 404


# ---------- admin ----------
class TestAdmin:
    def test_admin_list_masked_and_review(self, ca, cb, admin_client):
        tid = _ready(ca)
        ca.post(f"{API}/manual-pay/{tid}/proof", data={"utr_full": "555566667777"}, timeout=30)
        r = admin_client.get(f"{API}/manual-pay/admin/transactions", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        rows = r.json()["transactions"]
        row = next((x for x in rows if x["id"] == tid), None)
        assert row, "txn missing from admin list"
        assert "_id" not in row
        assert row["utr_full"] == "XXXXXXXX7777", row["utr_full"]

        rv = admin_client.post(f"{API}/manual-pay/admin/{tid}/review", json={"action": "reviewed"}, timeout=30)
        assert rv.status_code == 200, rv.text[:200]
        assert rv.json()["merchant_verification_status"] == "admin_reviewed"
        assert ca.get(f"{API}/manual-pay/{tid}", timeout=30).json()["merchant_verification_status"] == "admin_reviewed"

        bad = admin_client.post(f"{API}/manual-pay/admin/{tid}/review", json={"action": "bogus"}, timeout=30)
        assert bad.status_code == 400

    def test_non_admin_forbidden(self, cb):
        assert cb.get(f"{API}/manual-pay/admin/transactions", timeout=30).status_code == 403
        r = cb.post(f"{API}/manual-pay/admin/B4P-x/review", json={"action": "reviewed"}, timeout=30)
        assert r.status_code == 403, r.status_code


# ---------- payout disabled in manual mode ----------
class TestNoPayout:
    def test_no_payout_records_for_manual_txns(self, ca):
        r = requests.get(f"{API}/manual-pay/config", timeout=30)
        assert r.json()["flow_mode"] == "manual_upi_double_scan"


# ---------- regressions ----------
class TestRegression:
    def test_login_and_me(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200, r.text[:200]
        token = r.json()["token"]
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert me.status_code == 200
        assert me.json().get("email") == ADMIN["email"] or me.json().get("user", {}).get("email") == ADMIN["email"]

    def test_bad_login(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN["email"], "password": "wrong-pass-xyz"}, timeout=30)
        assert r.status_code in (401, 400, 423, 429), r.status_code

    def test_wallet_and_expenses(self, cb):
        w = cb.get(f"{API}/wallet", timeout=30)
        assert w.status_code == 200, w.text[:200]
        assert "balance" in w.json()
        e = cb.get(f"{API}/expenses", timeout=30)
        assert e.status_code == 200, e.text[:200]
