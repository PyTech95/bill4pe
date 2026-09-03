"""Manual double-scan: receipt PDF title + no RazorpayX payout records in manual mode."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE_URL}/api"
DRAFT = {"category": "Food", "items": [{"name": "Lunch", "quantity": 1, "unit_price": 200}]}


@pytest.fixture(scope="module")
def client_and_bill():
    email = f"TEST_pdf_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test@12345", "name": "TEST PDF"}, timeout=30)
    assert r.status_code in (200, 201), r.text[:200]
    token = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    t = s.post(f"{API}/manual-pay/first-scan", json={"payee_upi": "abcstore@ybl", "payee_name": "ABC STORE", "expense_draft": DRAFT}, timeout=30).json()
    tid = t["transaction_id"]
    s.post(f"{API}/manual-pay/{tid}/second-scan", json={"payee_upi": "abcstore@ybl"}, timeout=30)
    s.post(f"{API}/manual-pay/{tid}/confirm", json={"completed": True}, timeout=30)
    s.post(f"{API}/manual-pay/{tid}/proof", data={"utr_full": "776655443322"}, timeout=30)
    g = s.post(f"{API}/manual-pay/{tid}/generate", timeout=60).json()
    assert g.get("generated") is True, g
    return s, tid, g


def test_pdf_title_and_fee_snapshot(client_and_bill):
    s, tid, g = client_and_bill
    ex = s.get(f"{API}/expenses", timeout=30).json()
    rows = ex if isinstance(ex, list) else ex.get("expenses", [])
    exp = next(e for e in rows if e.get("transaction_id") == tid)
    snap = exp.get("bill_snapshot") or {}
    assert snap.get("document_title") == "BILL4PE DIGITAL EXPENSE RECEIPT", snap.get("document_title")
    assert snap.get("bill4pe_service_fee") == 2.0
    assert snap.get("model") == "manual_upi_double_scan"
    assert snap.get("utr") == "XXXXXXXX3322", snap.get("utr")
    pdf = s.get(f"{API}/bills/{exp['id']}/pdf", timeout=60)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
    assert len(pdf.content) > 1000


def test_no_payout_for_merchant_amount(client_and_bill):
    """Manual mode must not create RazorpayX payouts for this transaction."""
    s, tid, g = client_and_bill
    # payout listing endpoint if available; else assert manual txn has no payout fields
    st = s.get(f"{API}/manual-pay/{tid}", timeout=30).json()
    assert "payout_id" not in st and "razorpay_payout_id" not in st
    assert st["fee_payment_method"] == "wallet"
    assert st["merchant_verification_status"] in ("unverified", "admin_reviewed")
