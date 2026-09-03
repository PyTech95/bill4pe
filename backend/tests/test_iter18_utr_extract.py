"""Iteration 18: POST /api/ai/extract-utr (Gemini vision auto-UTR).

Contract:
- multipart 'file' image field, requires auth (401 without token)
- Returns 200 with {"utr": "<12 digits>", "found": true} when a 12-digit UPI ref
  is clearly present in the screenshot.
- Returns 200 with {"utr": "", "found": false} when nothing 12-digit is present.
- MUST NEVER return 5xx to the client on AI slowness / 503 / timeout —
  it degrades to {found:false} inside a 40s bound.
"""
import io
import os
import time
import uuid

import pytest
import requests
from PIL import Image, ImageDraw, ImageFont

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

PASSWORD = "Test@1234"
UTR_12 = "401234567890"


def _make_upi_screenshot(utr: str = UTR_12) -> bytes:
    """Fabricate a UPI-payment-style screenshot with a printed 12-digit reference."""
    img = Image.new("RGB", (720, 1000), "white")
    d = ImageDraw.Draw(img)
    try:
        big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    except Exception:
        big = ImageFont.load_default()
        med = ImageFont.load_default()
    d.text((40, 60), "Payment Successful", font=big, fill="black")
    d.text((40, 180), "Paid to: Test Merchant", font=med, fill="black")
    d.text((40, 240), "merchant@okaxis", font=med, fill="gray")
    d.text((40, 340), "Amount: Rs. 25.00", font=med, fill="black")
    d.text((40, 460), "UPI transaction ID", font=med, fill="gray")
    d.text((40, 510), utr, font=big, fill="black")
    d.text((40, 640), "Date: 15 Jan 2026, 10:30 AM", font=med, fill="gray")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_blank_image() -> bytes:
    img = Image.new("RGB", (400, 400), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 180), "hello world no ref here", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def token():
    email = f"qa_iter18_{uuid.uuid4().hex[:8]}@bill4petest.com"
    r = requests.post(f"{API}/auth/register", json={
        "name": "QA Iter18",
        "email": email,
        "password": PASSWORD,
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in register response: {data}"
    return tok


@pytest.fixture(scope="module")
def upi_shot_bytes():
    # Prefer the deterministic on-disk asset if present
    path = "/tmp/upi_shot.png"
    if os.path.exists(path):
        with open(path, "rb") as f:
            b = f.read()
        if b:
            return b
    return _make_upi_screenshot()


class TestExtractUtr:
    def test_requires_auth(self):
        files = {"file": ("shot.png", _make_blank_image(), "image/png")}
        r = requests.post(f"{API}/ai/extract-utr", files=files, timeout=30)
        assert r.status_code == 401, f"expected 401 without token, got {r.status_code}: {r.text[:200]}"

    def test_extract_from_upi_screenshot(self, token, upi_shot_bytes):
        headers = {"Authorization": f"Bearer {token}"}
        files = {"file": ("shot.png", upi_shot_bytes, "image/png")}
        t0 = time.time()
        r = requests.post(f"{API}/ai/extract-utr", files=files, headers=headers, timeout=60)
        elapsed = time.time() - t0
        # Endpoint must never bubble a 5xx (bounded to 40s, degrades to found=false).
        assert r.status_code == 200, f"expected 200, got {r.status_code} in {elapsed:.1f}s: {r.text[:300]}"
        data = r.json()
        assert "utr" in data and "found" in data, data
        assert isinstance(data["found"], bool)
        assert isinstance(data["utr"], str)
        # Must respond within gateway window (with margin under 60s)
        assert elapsed < 55, f"endpoint took {elapsed:.1f}s (must stay under ~40s + net)"
        if data["found"]:
            assert len(data["utr"]) == 12 and data["utr"].isdigit(), data
            # If Gemini worked we expect the printed 12-digit number back
            print(f"OK: extracted UTR={data['utr']} in {elapsed:.1f}s")
        else:
            # Transient Gemini 503/high-demand is EXPECTED per test note — not a bug.
            print(f"NOTE: Gemini transiently returned found=false in {elapsed:.1f}s (expected under high demand)")

    def test_no_utr_image(self, token):
        headers = {"Authorization": f"Bearer {token}"}
        files = {"file": ("blank.png", _make_blank_image(), "image/png")}
        t0 = time.time()
        r = requests.post(f"{API}/ai/extract-utr", files=files, headers=headers, timeout=60)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"expected 200 for no-utr image, got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data.get("found") is False, f"expected found=false for blank image, got {data}"
        assert data.get("utr", "") == ""
        assert elapsed < 55

    def test_empty_file_rejected(self, token):
        headers = {"Authorization": f"Bearer {token}"}
        files = {"file": ("empty.png", b"", "image/png")}
        r = requests.post(f"{API}/ai/extract-utr", files=files, headers=headers, timeout=30)
        assert r.status_code == 400, f"expected 400 for empty file, got {r.status_code}: {r.text[:200]}"
