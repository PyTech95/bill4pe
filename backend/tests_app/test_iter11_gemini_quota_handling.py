"""Iteration 11 — Gemini quota-exhausted error handling verification.

Context: The Gemini free-tier daily quota (~20/day) is currently EXHAUSTED, so
live AI calls will return 429. This suite verifies that:
  - AI endpoints return a CLEAN JSON error (429/504/422), never a raw 500 with
    a stack trace and never leaking OpenAI/API-key/file-path strings.
  - The clear daily-limit message is returned when quota is exhausted.
  - /api/ai/suggest-items degrades to {"suggestions": []} instead of 500.
  - /api/health and /api/health/providers report Gemini-only (no 'openai' key,
    ai.using_own_keys.gemini is true).
  - No OpenAI imports / OPENAI_API_KEY / whisper-1 references in llm.py or ai.py.
  - voice_expense() source contains only ONE gemini_transcribe call and NO
    gemini_text call (single-Gemini-call optimisation).
"""
import io
import os
import re

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"


# ------------------------------ fixtures ------------------------------

@pytest.fixture(scope="module")
def user_token():
    r = requests.post(f"{API}/auth/otp/request", json={"phone": "9999999999"}, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/auth/otp/verify",
                      json={"phone": "9999999999", "otp": "123456"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_h(user_token):
    return {"Authorization": f"Bearer {user_token}"}


# --------------------------- helpers ---------------------------

FORBIDDEN_LEAKS = ("openai", "OPENAI_API_KEY", "traceback", "/app/backend/", "AIzaSy")


def _assert_clean_detail(r: requests.Response):
    """Common assertions: JSON body, has 'detail', no secret/stack/openai leak."""
    assert r.headers.get("content-type", "").startswith("application/json"), \
        f"non-JSON body: ct={r.headers.get('content-type')} body={r.text[:200]}"
    body = r.json()
    detail = str(body.get("detail", ""))
    lower = detail.lower()
    for tok in FORBIDDEN_LEAKS:
        assert tok.lower() not in lower, f"leaked '{tok}' in detail: {detail}"
    # never a raw stacktrace shape
    assert "at line" not in lower
    assert "\n  File \"" not in detail
    return body, detail


# --------------------------- health ---------------------------

class TestHealth:
    def test_health_ok(self):
        r = requests.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_providers_gemini_only(self):
        r = requests.get(f"{API}/health/providers", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["ai"]["using_own_keys"]["gemini"] is True
        # No 'openai' key anywhere under ai.*
        assert "openai" not in j["ai"], j["ai"]
        assert "openai" not in j["ai"]["using_own_keys"], j["ai"]["using_own_keys"]


# --------------------------- AI endpoints under quota ---------------------------

VOICE_HI = "/tmp/voice_hi.mp3"
VOICE_EN = "/tmp/voice_en.mp3"
RECEIPT = "/tmp/receipt.png"


class TestVoiceExpenseQuotaHandling:
    """POST /api/voice/expense must return a clean 429/504/422 with clear detail
    when Gemini daily quota is exhausted — never a raw 500, never leak OpenAI."""

    @pytest.mark.parametrize("path,ctype", [
        (VOICE_HI, "audio/mpeg"),
        (VOICE_EN, "audio/mpeg"),
    ])
    def test_voice_returns_clean_error_or_success(self, auth_h, path, ctype):
        if not os.path.exists(path):
            pytest.skip(f"missing sample audio {path}")
        with open(path, "rb") as f:
            data = f.read()
        files = {"file": (os.path.basename(path), data, ctype)}
        r = requests.post(f"{API}/voice/expense", headers=auth_h, files=files, timeout=120)

        # Success (quota may have reset) or a clean handled error
        assert r.status_code in (200, 400, 422, 429, 502, 504), \
            f"unexpected status={r.status_code} body={r.text[:400]}"
        body, detail = _assert_clean_detail(r) if r.status_code >= 400 else (r.json(), "")

        if r.status_code == 200:
            # response contract preserved
            for k in ("transcript", "category", "sub_category", "merchant_name",
                      "total_amount", "items"):
                assert k in body, body
        elif r.status_code == 429:
            # verify the human-readable daily-limit message
            low = detail.lower()
            assert ("daily" in low and "gemini" in low and "billing" in low) or \
                   ("rate limit" in low), f"429 detail not clear: {detail}"


class TestReceiptOcrQuotaHandling:
    def test_scan_receipt_clean_error_or_success(self, auth_h):
        if not os.path.exists(RECEIPT):
            pytest.skip("no receipt.png sample")
        with open(RECEIPT, "rb") as f:
            data = f.read()
        files = {"file": ("receipt.png", data, "image/png")}
        r = requests.post(f"{API}/ai/scan-receipt", headers=auth_h, files=files, timeout=120)
        assert r.status_code in (200, 400, 429, 502, 504), \
            f"unexpected status={r.status_code} body={r.text[:300]}"
        if r.status_code >= 400:
            _, detail = _assert_clean_detail(r)
            if r.status_code == 429:
                low = detail.lower()
                assert "daily" in low or "rate limit" in low, detail


class TestDetectItemsQuotaHandling:
    def test_detect_items_clean_error_or_success(self, auth_h):
        if not os.path.exists(RECEIPT):
            pytest.skip("no sample image")
        with open(RECEIPT, "rb") as f:
            data = f.read()
        files = {"file": ("r.png", data, "image/png")}
        r = requests.post(f"{API}/ai/detect-items?category=food",
                          headers=auth_h, files=files, timeout=120)
        assert r.status_code in (200, 400, 429, 502, 504), \
            f"unexpected status={r.status_code} body={r.text[:300]}"
        if r.status_code >= 400:
            _, detail = _assert_clean_detail(r)
            if r.status_code == 429:
                low = detail.lower()
                assert "daily" in low or "rate limit" in low, detail


class TestSuggestItemsNever500:
    def test_suggest_items_returns_200_even_on_quota(self, auth_h):
        r = requests.post(f"{API}/ai/suggest-items",
                          headers={**auth_h, "Content-Type": "application/json"},
                          json={"category": "food", "query": "ro"}, timeout=60)
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert isinstance(body.get("suggestions"), list)  # may be empty when quota out


# ------------------- Code inspection: no OpenAI, single Gemini call -------------------

class TestCodeInspection:
    def test_llm_and_ai_have_no_openai(self):
        for p in ("/app/backend/services/llm.py", "/app/backend/routers/ai.py"):
            with open(p) as f:
                src = f.read()
            forbidden = ["from openai", "import openai", "OPENAI_API_KEY",
                         "has_openai", "openai_transcribe", "whisper-1"]
            for tok in forbidden:
                assert tok not in src, f"{p} still contains {tok!r}"

    def test_voice_expense_uses_single_gemini_call(self):
        with open("/app/backend/routers/ai.py") as f:
            src = f.read()
        # extract voice_expense function body
        m = re.search(r"async def voice_expense\(.*?(?=\n@router\.|\nasync def |\Z)",
                      src, flags=re.DOTALL)
        assert m, "voice_expense() function not found"
        body = m.group(0)
        assert body.count("gemini_transcribe(") == 1, \
            f"expected exactly 1 gemini_transcribe call, got {body.count('gemini_transcribe(')}"
        assert "gemini_text(" not in body, \
            "voice_expense() must not call gemini_text() — should be a single audio call"
