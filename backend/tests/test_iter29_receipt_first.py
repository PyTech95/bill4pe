"""Iter-29: receipt-first payment flow (no payee questions, no confirm step).

Covers:
- first-scan with only merchant_amount (no payee_upi) → 200
- proof upload WITHOUT prior /confirm → verified, payee backfilled from OCR
- GET after verified → verification.payee_name present
- proof without file → 422
- duplicate UTR on different txn → rejected
- discard verified txn → 400
- login / dashboard / wallet endpoints unaffected
"""
import io
import os
import time

import pytest
import requests
from PIL import Image, ImageDraw

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

_TOK = []


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


def _mk_user():
    if _TOK:
        return _TOK[0]
    ts = int(time.time() * 1000)
    email = f"iter29_{ts}@bill4pe.in"
    time.sleep(4.0)
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Test@1234", "name": "iter29"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Test@1234"}, timeout=30)
    assert r.status_code == 200, r.text
    _TOK.append(r.json()["token"])
    return _TOK[0]


def _uniq_utr():
    return str(int(time.time() * 1_000_000))[-12:].rjust(12, "9")


def _receipt(*, amount="10", utr=None, upi="tea@okaxis", name="Tea Stall"):
    utr = utr or _uniq_utr()
    im = Image.new("RGB", (520, 800), "white")
    d = ImageDraw.Draw(im)
    lines = [
        "PhonePe",
        "Transaction Successful",
        f"Paid to: {name}",
        f"Amount: Rs.{amount}",
        f"UPI: {upi}",
        f"Transaction ID: T{utr[:12]}",
        f"UTR: {utr}",
        "Date: 03 Sep 2026",
        "Time: 06:00 PM",
    ]
    y = 30
    for ln in lines:
        d.text((30, y), ln, fill="black")
        y += 40
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue(), utr


class TestFirstScanNoPayee:
    def test_first_scan_amount_only_returns_200(self):
        tok = _mk_user()
        r = requests.post(f"{API}/manual-pay/first-scan",
                          json={"merchant_amount": 10}, headers=_hdr(tok), timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["state"] == "awaiting_merchant_payment"
        assert b["merchant_amount"] == 10
        # payee not yet collected — snapshot may be None
        assert b.get("payee_upi") in (None, "")
        assert b.get("transaction_id")

    def test_first_scan_zero_amount_rejected(self):
        tok = _mk_user()
        r = requests.post(f"{API}/manual-pay/first-scan",
                          json={"merchant_amount": 0}, headers=_hdr(tok), timeout=30)
        assert r.status_code == 400

    def test_first_scan_invalid_upi_still_rejected_when_supplied(self):
        tok = _mk_user()
        r = requests.post(f"{API}/manual-pay/first-scan",
                          json={"merchant_amount": 10, "payee_upi": "notaupi"},
                          headers=_hdr(tok), timeout=30)
        assert r.status_code == 400


class TestDirectProofUploadNoConfirm:
    def test_upload_without_confirm_verifies_and_backfills_payee(self):
        tok = _mk_user()
        r = requests.post(f"{API}/manual-pay/first-scan",
                          json={"merchant_amount": 10}, headers=_hdr(tok), timeout=30)
        assert r.status_code == 200
        tid = r.json()["transaction_id"]

        img, utr = _receipt(amount="10", upi="teastall@okaxis", name="Tea Stall")
        r = requests.post(f"{API}/manual-pay/{tid}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        body = r.json()
        v = body.get("verification") or {}
        assert v.get("verification_status") == "verified", (v.get("failure_reasons"), v)
        # payee backfilled from OCR
        assert body.get("payee_name"), body
        assert body.get("payee_upi"), body

        # GET returns verification.payee_name
        r = requests.get(f"{API}/manual-pay/{tid}", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200
        g = r.json()
        assert (g.get("verification") or {}).get("payee_name")


class TestProofValidation:
    def test_proof_without_file_returns_422(self):
        tok = _mk_user()
        r = requests.post(f"{API}/manual-pay/first-scan",
                          json={"merchant_amount": 15}, headers=_hdr(tok), timeout=30)
        tid = r.json()["transaction_id"]
        r = requests.post(f"{API}/manual-pay/{tid}/proof",
                          headers=_hdr(tok), timeout=30)
        assert r.status_code == 422, r.text


class TestDuplicateUTR:
    def test_duplicate_utr_on_different_txn_rejected(self):
        tok = _mk_user()
        # txn A verified
        r = requests.post(f"{API}/manual-pay/first-scan",
                          json={"merchant_amount": 12}, headers=_hdr(tok), timeout=30)
        tid_a = r.json()["transaction_id"]
        img, utr = _receipt(amount="12", upi="dup@okaxis", name="Dup Shop")
        r = requests.post(f"{API}/manual-pay/{tid_a}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200
        assert (r.json().get("verification") or {}).get("verification_status") == "verified"

        # txn B with SAME utr
        r = requests.post(f"{API}/manual-pay/first-scan",
                          json={"merchant_amount": 12}, headers=_hdr(tok), timeout=30)
        tid_b = r.json()["transaction_id"]
        img2, _ = _receipt(amount="12", upi="dup@okaxis", name="Dup Shop", utr=utr)
        r = requests.post(f"{API}/manual-pay/{tid_b}/proof",
                          files={"screenshot": ("r.png", img2, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        v = r.json().get("verification") or {}
        assert v.get("verification_status") == "rejected"
        assert v.get("duplicate_check") == "duplicate" or any(
            "duplicate" in (x or "").lower() for x in (v.get("failure_reasons") or [])
        )


class TestDiscardVerified:
    def test_discard_verified_400(self):
        tok = _mk_user()
        r = requests.post(f"{API}/manual-pay/first-scan",
                          json={"merchant_amount": 13}, headers=_hdr(tok), timeout=30)
        tid = r.json()["transaction_id"]
        img, _ = _receipt(amount="13", upi="verify29@okaxis", name="Verify29")
        r = requests.post(f"{API}/manual-pay/{tid}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200
        v = r.json().get("verification") or {}
        assert v.get("verification_status") == "verified", v

        r = requests.post(f"{API}/manual-pay/{tid}/discard", headers=_hdr(tok), timeout=30)
        assert r.status_code == 400


class TestUnaffectedEndpoints:
    def test_dashboard_and_wallet_ok(self):
        tok = _mk_user()
        r = requests.get(f"{API}/wallet/balance", headers=_hdr(tok), timeout=30)
        assert r.status_code in (200, 404)  # endpoint may vary; not 500
        r = requests.get(f"{API}/expenses", headers=_hdr(tok), timeout=30)
        assert r.status_code in (200, 404)

    def test_login_still_works(self):
        # sanity: super admin login returns 200
        r = requests.post(f"{API}/auth/login",
                          json={"email": "meland@mhem.in", "password": "Bill4pe@123"}, timeout=30)
        assert r.status_code == 200, r.text
