"""Iter-27 receipt-verify overhaul: server-side OCR only, no manual UTR."""
import io
import os
import time

import pytest
import requests
from PIL import Image, ImageDraw

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "meland@mhem.in", "password": "Bill4pe@123"}


# ---------- helpers ----------
def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


_TOKEN_CACHE = []


def _mk_user():
    if _TOKEN_CACHE:
        return _TOKEN_CACHE[0]
    ts = int(time.time() * 1000)
    email = f"test_iter27_{ts}@bill4pe.in"
    pw = "Test@1234"
    time.sleep(4.0)  # avoid rate limit on registration
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": pw, "name": "iter27 tester"},
                      timeout=30)
    assert r.status_code in (200, 201), r.text
    tok = _login(email, pw)
    _TOKEN_CACHE.append(tok)
    return tok


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _uniq_utr():
    # Generate a fresh 12-digit UTR each test run so we never trigger the DB-level
    # duplicate index from prior iterations.
    return str(int(time.time() * 1000))[-12:].rjust(12, "9")


def _receipt_png(*, amount="75", utr=None, upi="sharma2@okhdfcbank",
                 status_line="Transaction Successful"):
    utr = utr or _uniq_utr()
    im = Image.new("RGB", (520, 780), "white")
    d = ImageDraw.Draw(im)
    lines = [
        "PhonePe",
        status_line,
        "Paid to: Sharma Tea Stall",
        f"Amount: Rs.{amount}",
        f"UPI: {upi}",
        f"Transaction ID: T{utr[:12]}",
        f"UTR: {utr}",
        "Date: 02 Sep 2026",
        "Time: 03:15 PM",
    ]
    y = 30
    for ln in lines:
        d.text((30, y), ln, fill="black")
        y += 40
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _start_txn(tok, upi="sharma2@okhdfcbank", amount=75, name="Sharma Tea Stall"):
    r = requests.post(f"{API}/manual-pay/first-scan",
                      json={"payee_upi": upi, "payee_name": name, "merchant_amount": amount},
                      headers=_hdr(tok), timeout=30)
    assert r.status_code == 200, r.text
    tid = r.json()["transaction_id"]
    # confirm merchant payment
    r = requests.post(f"{API}/manual-pay/{tid}/confirm",
                      json={"completed": True}, headers=_hdr(tok), timeout=30)
    assert r.status_code == 200, r.text
    return tid


# ---------- tests ----------
class TestAuth:
    def test_admin_login(self):
        tok = _login(ADMIN["email"], ADMIN["password"])
        assert tok and isinstance(tok, str)


class TestProofValidation:
    """Manual-pay proof endpoint accepts screenshot file ONLY. No client UTR."""

    def setup_method(self):
        self.tok = _mk_user()
        self.tid = _start_txn(self.tok)

    def test_proof_missing_file_returns_422(self):
        r = requests.post(f"{API}/manual-pay/{self.tid}/proof",
                          headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 422, r.text

    def test_proof_with_utr_field_but_no_file_returns_422(self):
        # Even if the client sends legacy utr_full, without the file it must fail.
        r = requests.post(f"{API}/manual-pay/{self.tid}/proof",
                          data={"utr_full": "123456789012"},
                          headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 422, r.text

    def test_bad_content_type_rejected(self):
        r = requests.post(f"{API}/manual-pay/{self.tid}/proof",
                          files={"screenshot": ("x.txt", b"hello", "text/plain")},
                          headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 400, r.text


class TestReceiptOcrFlow:
    """End-to-end OCR verification pipeline via Gemini (real call)."""

    def test_happy_verified_then_generate_needs_fee(self):
        tok = _mk_user()
        tid = _start_txn(tok)
        img = _receipt_png()
        r = requests.post(f"{API}/manual-pay/{tid}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        v = data.get("verification") or {}
        assert v.get("verification_status") == "verified", (v.get("failure_reasons"), v)
        assert v.get("amount_matched") is True
        assert v.get("extracted_utr"), v
        # Generate → either fee is 0 & bill generated, or wallet empty → needs_fee
        r = requests.post(f"{API}/manual-pay/{tid}/generate",
                          headers=_hdr(tok), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # If bill4pe fee > 0 and wallet is empty, we need_fee. Otherwise bill generated.
        assert d.get("generated") is True or (d.get("needs_fee") is True and "wallet_balance" in d), d

    def test_amount_mismatch_rejected_and_generate_blocked(self):
        tok = _mk_user()
        tid = _start_txn(tok, amount=150)
        img = _receipt_png(amount="5")
        r = requests.post(f"{API}/manual-pay/{tid}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        v = r.json().get("verification") or {}
        assert v.get("verification_status") == "rejected", v
        assert v.get("amount_matched") is False
        # generate must be blocked
        r = requests.post(f"{API}/manual-pay/{tid}/generate",
                          headers=_hdr(tok), timeout=30)
        assert r.status_code == 400, r.text

    def test_duplicate_receipt_rejected(self):
        tok = _mk_user()
        # 1st txn — verified
        tid1 = _start_txn(tok)
        utr = _uniq_utr()
        img = _receipt_png(utr=utr)
        r = requests.post(f"{API}/manual-pay/{tid1}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        assert (r.json().get("verification") or {}).get("verification_status") == "verified"

        # 2nd txn — reuse same UTR image
        tid2 = _start_txn(tok)
        r = requests.post(f"{API}/manual-pay/{tid2}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        v = r.json().get("verification") or {}
        assert v.get("verification_status") == "rejected"
        assert v.get("duplicate_check") == "duplicate"
        reasons = " ".join(v.get("failure_reasons") or [])
        assert "already been used" in reasons.lower() or "already" in reasons.lower()
