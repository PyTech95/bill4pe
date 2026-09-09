"""Iteration 17: single-scan manual UPI flow + 12-digit UTR validation + LIVE Razorpay config.

Verifies:
- POST /api/manual-pay/first-scan returns state='awaiting_merchant_payment' with
  second_qr_verified=True and payment_session_locked=True (SINGLE SCAN).
- POST /api/manual-pay/{tid}/confirm {completed:true} -> merchant_payment_claimed.
- POST /api/manual-pay/{tid}/proof rejects non-12-digit UTR with HTTP 400.
- Valid 12-digit UTR accepted -> state=proof_submitted, utr_last4 correct, fee_status=due.
- POST /api/manual-pay/{tid}/generate uses wallet-first path (welcome bonus ₹50
  covers ₹2.5 fee for a ₹25 bill) -> bill_id returned, state=completed.
- GET /api/payments/config returns enabled=true, mode='live', key_id starts with rzp_live_.
"""
import os
import uuid
import pytest
import requests

def _read_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE_URL = _read_base_url()
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def user_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"qa_iter17_{uuid.uuid4().hex[:8]}@bill4petest.com"
    r = s.post(f"{API}/auth/register", json={
        "name": "Iter17 Tester", "email": email, "password": "Test@1234",
    })
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    me = s.get(f"{API}/auth/me").json()
    assert float(me.get("wallet_balance", 0)) >= 50.0, f"welcome bonus missing: {me}"
    return s


# ---------- Payments config: LIVE Razorpay ----------
def test_payments_config_live():
    r = requests.get(f"{API}/payments/config")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("enabled") is True, f"payments not enabled: {data}"
    assert data.get("mode") == "live", f"mode not live: {data}"
    kid = data.get("key_id") or ""
    assert kid.startswith("rzp_live_"), f"key_id not live: {kid}"


# ---------- Single-scan: first_scan directly locks to awaiting_merchant_payment ----------
def test_first_scan_single_scan(user_session):
    r = user_session.post(f"{API}/manual-pay/first-scan", json={
        "payee_upi": "merchant@okaxis",
        "payee_name": "Test Merchant",
        "merchant_amount": 25,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "awaiting_merchant_payment", f"expected single-scan, got {d['state']}"
    assert d["state"] != "second_qr_required"
    assert d["first_qr_verified"] is True
    assert d["second_qr_verified"] is True
    assert d["payment_session_locked"] is True
    assert d["merchant_amount"] == 25.0
    assert d["payee_upi"] == "merchant@okaxis"
    # keep tid for chained tests
    pytest.tid_singlescan = d["transaction_id"]


# ---------- Confirm merchant payment ----------
def test_confirm_marks_claimed(user_session):
    tid = pytest.tid_singlescan
    r = user_session.post(f"{API}/manual-pay/{tid}/confirm", json={"completed": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "merchant_payment_claimed", d


def _form_post(sess, url, data):
    # bypass session's application/json Content-Type so FastAPI parses form
    return requests.post(url, data=data,
                         headers={"Authorization": sess.headers["Authorization"]})


# ---------- UTR: 11 digits rejected ----------
def test_proof_utr_11_digits_rejected(user_session):
    tid = pytest.tid_singlescan
    r = _form_post(user_session, f"{API}/manual-pay/{tid}/proof",
                   {"utr_full": "12345678901"})
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    assert "12 digits" in r.text, r.text


# ---------- UTR: 13 digits rejected ----------
def test_proof_utr_13_digits_rejected(user_session):
    tid = pytest.tid_singlescan
    r = _form_post(user_session, f"{API}/manual-pay/{tid}/proof",
                   {"utr_full": "1234567890123"})
    assert r.status_code == 400, r.text
    assert "12 digits" in r.text


# ---------- UTR: non-numeric rejected (stripped -> too short) ----------
def test_proof_utr_non_numeric_rejected(user_session):
    tid = pytest.tid_singlescan
    r = _form_post(user_session, f"{API}/manual-pay/{tid}/proof",
                   {"utr_full": "ABCDEFGHIJKL"})
    assert r.status_code == 400, r.text


# ---------- UTR: valid 12 digits accepted ----------
def test_proof_utr_12_digits_ok(user_session):
    tid = pytest.tid_singlescan
    r = _form_post(user_session, f"{API}/manual-pay/{tid}/proof",
                   {"utr_full": "401234567890"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "proof_submitted", d
    assert d["utr_last4"] == "7890", d
    assert d["fee_status"] == "due", d


# ---------- Generate: wallet-first, ₹50 covers ₹2.5 fee ----------
def test_generate_wallet_first(user_session):
    tid = pytest.tid_singlescan
    r = user_session.post(f"{API}/manual-pay/{tid}/generate", json={})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("generated") is True, f"receipt not generated: {d}"
    assert d.get("bill_id"), f"no bill_id: {d}"
    assert d.get("state") == "completed", d
    # verify persisted via GET
    r2 = user_session.get(f"{API}/manual-pay/{tid}")
    assert r2.status_code == 200
    assert r2.json().get("bill_id") == d["bill_id"]
