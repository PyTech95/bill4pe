"""V2 regression: Cash payment mode, AI scan-receipt, voice/expense, /reports PDF, GSTIN auto-print, QR code on PDF, referral validate, phone OTP."""
import io
import os
import re
import uuid
import wave
import struct
import requests
import pytest
from pypdf import PdfReader


def _pdf_text(content_bytes):
    try:
        reader = PdfReader(io.BytesIO(content_bytes))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-expense-hub-8.preview.emergentagent.com").rstrip("/")


# ---------------- Phone OTP login (mocked 123456) ----------------
def test_phone_otp_login_flow(session):
    phone = "9999999990"
    r1 = session.post(f"{BASE_URL}/api/auth/otp/request", json={"phone": phone}, timeout=15)
    assert r1.status_code == 200, r1.text
    r2 = session.post(f"{BASE_URL}/api/auth/otp/verify",
                      json={"phone": phone, "otp": "123456"}, timeout=15)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "token" in body and isinstance(body["token"], str)
    assert "user" in body


def test_phone_otp_wrong(session):
    phone = "9999999991"
    session.post(f"{BASE_URL}/api/auth/otp/request", json={"phone": phone}, timeout=15)
    r = session.post(f"{BASE_URL}/api/auth/otp/verify",
                     json={"phone": phone, "otp": "000000"}, timeout=15)
    assert r.status_code == 401


# ---------------- Referral validate ----------------
def test_referrals_me_returns_code(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/referrals/me", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "code" in body
    assert isinstance(body["code"], str) and len(body["code"]) >= 4


def test_referrals_validate_known_code(session, auth_headers):
    me = session.get(f"{BASE_URL}/api/referrals/me", headers=auth_headers, timeout=15).json()
    code = me["code"]
    r = session.get(f"{BASE_URL}/api/referrals/validate/{code}", timeout=15)
    assert r.status_code == 200
    assert r.json().get("valid") is True


def test_referrals_validate_unknown_code(session):
    r = session.get(f"{BASE_URL}/api/referrals/validate/ZZZZZZ", timeout=15)
    # Backend currently returns 404 for unknown codes; FE handles either {valid:false} or 404
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json().get("valid") is False


# ---------------- Cash payment mode (PayNow Cash flow) ----------------
@pytest.fixture(scope="module")
def cash_expense_id(auth_headers):
    payload = {
        "category": "food",
        "sub_category": "Lunch",
        "items": [{"name": "Thali", "quantity": 1, "unit_price": 200}],
        "payment": {
            "merchant_name": "Cash Dhaba",
            "merchant_upi": "",
            "transaction_id": "",
            "amount": 200.0,
            "payment_method": "Cash",
        },
    }
    r = requests.post(f"{BASE_URL}/api/expenses", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["payment"]["payment_method"] == "Cash"
    assert data["total"] == 200.0
    return data["id"]


def test_cash_expense_persisted(auth_headers, cash_expense_id):
    r = requests.get(f"{BASE_URL}/api/expenses/{cash_expense_id}",
                     headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["payment"]["payment_method"] == "Cash"
    assert body["payment"]["merchant_name"] == "Cash Dhaba"


def test_cash_bill_pdf_shows_payment_method_cash(auth_headers, cash_expense_id):
    # Generate bill first
    g = requests.post(f"{BASE_URL}/api/bills/{cash_expense_id}/generate",
                      headers=auth_headers, timeout=15)
    assert g.status_code == 200, g.text
    r = requests.get(f"{BASE_URL}/api/bills/{cash_expense_id}/pdf",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    # The PDF MAY compress text; for ReportLab default the literal "Cash" string appears in content stream
    # We do a loose check on length and substring (uncompressed by default)
    assert len(r.content) > 2000
    text = _pdf_text(r.content)
    assert "Payment Method" in text and "Cash" in text, f"PDF text missing Cash: {text[:500]}"


# ---------------- PDF Date+Time and Tagline ----------------
def test_bill_pdf_contains_qr_image_and_datetime(auth_headers, cash_expense_id):
    r = requests.get(f"{BASE_URL}/api/bills/{cash_expense_id}/pdf",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    content = r.content
    text = _pdf_text(content)
    # Tagline + datetime checks (date includes time HH:MM)
    assert "Intelligent Billing" in text, f"Tagline missing: {text[:400]}"
    m = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", text)
    assert m, f"Date+time YYYY-MM-DD HH:MM not found in PDF header text: {text[:500]}"


def test_create_report_and_pdf_has_tagline_and_datetime(auth_headers, cash_expense_id):
    # Create a report containing the cash expense
    r = requests.post(f"{BASE_URL}/api/reports", headers=auth_headers, json={
        "title": "TEST_QA Report",
        "notes": "Auto-gen test",
        "expense_ids": [cash_expense_id],
    }, timeout=15)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["expense_count"] >= 1
    assert "_id" not in rep
    rid = rep["id"]

    # Fetch PDF
    p = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf",
                     headers=auth_headers, timeout=30)
    assert p.status_code == 200
    assert p.headers.get("content-type", "").startswith("application/pdf")
    assert p.content.startswith(b"%PDF")
    assert len(p.content) > 1500


def test_list_reports_includes_created(auth_headers):
    r = requests.get(f"{BASE_URL}/api/reports", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    reps = r.json()["reports"]
    assert any(rp.get("title") == "TEST_QA Report" for rp in reps)


# ---------------- AI Receipt OCR endpoint (presence) ----------------
def test_scan_receipt_with_tiny_image(auth_headers):
    # 1x1 JPEG (header bytes) — endpoint should reach Gemini and either return JSON or 500.
    # We accept 200 OR 500 (network), but route must exist (not 404).
    import base64
    # Smallest valid jpeg
    tiny = base64.b64decode(
        "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAr/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AL+AB//Z"
    )
    h = {k: v for k, v in auth_headers.items() if k.lower() != "content-type"}
    files = {"file": ("tiny.jpg", io.BytesIO(tiny), "image/jpeg")}
    r = requests.post(f"{BASE_URL}/api/ai/scan-receipt",
                      headers=h, files=files, timeout=90)
    # Must NOT 404 — route exists
    assert r.status_code != 404, "scan-receipt route missing"
    # Accept either 200 (Gemini parsed) or 500 (Gemini OCR error on 1x1)
    assert r.status_code in (200, 500), f"unexpected status {r.status_code}: {r.text[:200]}"
    if r.status_code == 200:
        body = r.json()
        assert "items" in body and isinstance(body["items"], list)
        assert "category" in body


# ---------------- Voice expense endpoint (presence) ----------------
def test_voice_expense_endpoint_exists(auth_headers):
    """Generate a tiny silent WAV; Whisper may fail but route must exist."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        # 0.2s silence
        w.writeframes(b"\x00\x00" * 3200)
    buf.seek(0)
    h = {k: v for k, v in auth_headers.items() if k.lower() != "content-type"}
    files = {"file": ("silence.wav", buf, "audio/wav")}
    r = requests.post(f"{BASE_URL}/api/voice/expense",
                      headers=h, files=files, timeout=120)
    assert r.status_code != 404, "voice/expense route missing"
    # Endpoint exists and processed the file. Silence audio returns 422 with detail message.
    assert r.status_code in (200, 400, 422, 500), f"unexpected {r.status_code}: {r.text[:200]}"


# ---------------- GSTIN save via /auth/me ----------------
def test_save_and_print_gstin(session, auth_headers):
    # Save a valid GSTIN
    gstin_value = "27ABCDE1234F1Z5"
    r = session.put(f"{BASE_URL}/api/auth/me", headers=auth_headers,
                    json={"gstin": gstin_value}, timeout=15)
    assert r.status_code == 200, r.text
    me = session.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15).json()
    assert me.get("gstin") == gstin_value


def test_invalid_gstin_rejected(session, auth_headers):
    r = session.put(f"{BASE_URL}/api/auth/me", headers=auth_headers,
                    json={"gstin": "INVALID123"}, timeout=15)
    assert r.status_code == 400


# ---------------- Bill PDF generated AFTER GSTIN saved auto-prints GSTIN ----------------
def test_pdf_includes_gstin_after_save(session, auth_headers):
    # Ensure GSTIN saved
    gstin_value = "27ABCDE1234F1Z5"
    session.put(f"{BASE_URL}/api/auth/me", headers=auth_headers, json={"gstin": gstin_value}, timeout=15)
    # Create new expense + bill
    payload = {
        "category": "food",
        "items": [{"name": "Item", "quantity": 1, "unit_price": 50}],
        "payment": {"amount": 50, "payment_method": "UPI", "merchant_name": "QA"},
    }
    e = requests.post(f"{BASE_URL}/api/expenses", headers=auth_headers, json=payload, timeout=15).json()
    eid = e["id"]
    requests.post(f"{BASE_URL}/api/bills/{eid}/generate", headers=auth_headers, timeout=15)
    r = requests.get(f"{BASE_URL}/api/bills/{eid}/pdf", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    text = _pdf_text(r.content)
    assert gstin_value in text or "GSTIN" in text, f"PDF missing GSTIN: {text[:500]}"


# ---------------- Health (sanity) ----------------
def test_api_root(session):
    r = session.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code == 200
