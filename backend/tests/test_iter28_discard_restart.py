"""Iter-28 discard/restart bug fix: old bill must not resurface.

Covers:
- POST /manual-pay/{tid}/discard on unverified -> success, GET -> 404
- POST /manual-pay/{tid}/restart -> new attempt same amount, old GET -> 404
- Supersede: first_scan while another attempt active -> old GET -> 404
- Verified payment protection: discard 400, restart 400
"""
import io
import os
import time

import pytest
import requests
from PIL import Image, ImageDraw

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


_TOKEN_CACHE = []


def _mk_user():
    if _TOKEN_CACHE:
        return _TOKEN_CACHE[0]
    ts = int(time.time() * 1000)
    email = f"test_iter28_{ts}@bill4pe.in"
    pw = "Test@1234"
    time.sleep(4.0)
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": pw, "name": "iter28 tester"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    tok = _login(email, pw)
    _TOKEN_CACHE.append(tok)
    return tok


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _uniq_utr():
    return str(int(time.time() * 1000000))[-12:].rjust(12, "9")


def _receipt_png(*, amount="10", utr=None, upi="tea@okaxis"):
    utr = utr or _uniq_utr()
    im = Image.new("RGB", (520, 780), "white")
    d = ImageDraw.Draw(im)
    lines = [
        "PhonePe",
        "Transaction Successful",
        "Paid to: Tea Shop",
        f"Amount: Rs.{amount}",
        f"UPI: {upi}",
        f"Transaction ID: T{utr[:12]}",
        f"UTR: {utr}",
        "Date: 03 Sep 2026",
        "Time: 04:40 PM",
    ]
    y = 30
    for ln in lines:
        d.text((30, y), ln, fill="black")
        y += 40
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _start_txn(tok, upi="tea@okaxis", amount=10, name="Tea Shop"):
    r = requests.post(f"{API}/manual-pay/first-scan",
                      json={"payee_upi": upi, "payee_name": name, "merchant_amount": amount},
                      headers=_hdr(tok), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["transaction_id"]


def _confirm(tok, tid):
    r = requests.post(f"{API}/manual-pay/{tid}/confirm",
                      json={"completed": True}, headers=_hdr(tok), timeout=30)
    assert r.status_code == 200, r.text


class TestDiscardUnverified:
    def test_discard_unverified_then_get_404(self):
        tok = _mk_user()
        tid = _start_txn(tok, amount=10)
        # status readable
        r = requests.get(f"{API}/manual-pay/{tid}", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200

        r = requests.post(f"{API}/manual-pay/{tid}/discard", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        assert body.get("state") == "cancelled"

        # discarded -> not visible
        r = requests.get(f"{API}/manual-pay/{tid}", headers=_hdr(tok), timeout=30)
        assert r.status_code == 404, r.text

    def test_discard_after_failed_verification(self):
        """Simulate the exact user story: ₹10 bill, ₹5 receipt mismatch, discard."""
        tok = _mk_user()
        tid = _start_txn(tok, amount=10)
        _confirm(tok, tid)
        img = _receipt_png(amount="5")
        r = requests.post(f"{API}/manual-pay/{tid}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        v = r.json().get("verification") or {}
        assert v.get("verification_status") == "rejected"

        # discard the mismatched bill
        r = requests.post(f"{API}/manual-pay/{tid}/discard", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("state") == "cancelled"

        # 404 after
        r = requests.get(f"{API}/manual-pay/{tid}", headers=_hdr(tok), timeout=30)
        assert r.status_code == 404


class TestRestart:
    def test_restart_creates_new_attempt_same_bill(self):
        tok = _mk_user()
        tid = _start_txn(tok, amount=10)
        _confirm(tok, tid)

        r = requests.post(f"{API}/manual-pay/{tid}/restart", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200, r.text
        new = r.json()
        new_tid = new["transaction_id"]
        assert new_tid != tid
        assert new["state"] == "awaiting_merchant_payment"
        assert new["merchant_amount"] == 10
        assert new["payee_upi"] == "tea@okaxis"
        assert new.get("utr_full") in (None, "")
        assert new.get("verification") is None

        # old is gone
        r = requests.get(f"{API}/manual-pay/{tid}", headers=_hdr(tok), timeout=30)
        assert r.status_code == 404


class TestSupersede:
    def test_first_scan_supersedes_existing_active(self):
        tok = _mk_user()
        tid1 = _start_txn(tok, amount=10)
        # new first_scan while old attempt active
        tid2 = _start_txn(tok, amount=20)
        assert tid1 != tid2

        # old must be gone
        r = requests.get(f"{API}/manual-pay/{tid1}", headers=_hdr(tok), timeout=30)
        assert r.status_code == 404, r.text

        # new one active with new amount
        r = requests.get(f"{API}/manual-pay/{tid2}", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200
        assert r.json()["merchant_amount"] == 20


class TestVerifiedProtection:
    def test_discard_and_restart_blocked_after_verified(self):
        tok = _mk_user()
        tid = _start_txn(tok, upi="verify@okaxis", amount=11, name="Verify Shop")
        _confirm(tok, tid)
        img = _receipt_png(amount="11", upi="verify@okaxis")
        r = requests.post(f"{API}/manual-pay/{tid}/proof",
                          files={"screenshot": ("r.png", img, "image/png")},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        v = r.json().get("verification") or {}
        assert v.get("verification_status") == "verified", (v.get("failure_reasons"), v)

        # discard blocked
        r = requests.post(f"{API}/manual-pay/{tid}/discard", headers=_hdr(tok), timeout=30)
        assert r.status_code == 400, r.text
        msg = r.json().get("detail", "").lower()
        assert "finaliz" in msg or "verified" in msg

        # restart blocked
        r = requests.post(f"{API}/manual-pay/{tid}/restart", headers=_hdr(tok), timeout=30)
        assert r.status_code == 400, r.text
        msg = r.json().get("detail", "").lower()
        assert "verified" in msg or "finaliz" in msg


class TestDiscardEdgeCases:
    def test_discard_nonexistent_returns_404(self):
        tok = _mk_user()
        r = requests.post(f"{API}/manual-pay/B4P-2026-NOTAREAL/discard",
                          headers=_hdr(tok), timeout=30)
        assert r.status_code == 404

    def test_restart_of_cancelled_returns_400(self):
        tok = _mk_user()
        tid = _start_txn(tok, amount=10)
        r = requests.post(f"{API}/manual-pay/{tid}/discard", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200
        # already cancelled - restart should be rejected
        r = requests.post(f"{API}/manual-pay/{tid}/restart", headers=_hdr(tok), timeout=30)
        assert r.status_code == 400, r.text
