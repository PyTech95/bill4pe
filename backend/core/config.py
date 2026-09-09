"""Environment and runtime configuration for BILL4PE.

BILL4PE uses Google Gemini for AI functionality.

GEMINI_API_KEY is used for:
- vision
- text generation
- receipt analysis
- expense parsing
- audio transcription

No OpenAI API key is required.
"""
from dotenv import load_dotenv
from pathlib import Path
import os
import logging

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
# Fail fast in production: a missing/weak signing secret must never silently
# fall back to a shared default for a billing app.
JWT_SECRET = os.environ["JWT_SECRET"]
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

# Active payment flow. "manual_upi_double_scan" = customer pays merchant directly
# in their own UPI app (double QR scan + proof); Bill4Pe only collects the fee.
# RazorpayX merchant payout is DISABLED while this mode is active.
PAYMENT_FLOW_MODE = os.environ.get("PAYMENT_FLOW_MODE", "manual_upi_double_scan")

# ----------------------------------------------------------------------------
# AI configuration — Gemini is the ONLY AI provider.
# GEMINI_API_KEY powers ALL AI features: vision, text generation and audio/voice.
# On the VPS, GEMINI_API_KEY is the only AI key required.
# ----------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# EMERGENT_LLM_KEY is an OPTIONAL fallback for the Emergent preview environment.
# It routes to Gemini and introduces no OpenAI dependency. Not required in prod.
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Gemini model names – override via env if needed.
# `gemini-flash-latest` is Google's always-current Flash alias (vision + text +
# audio). Pinned versioned models like `gemini-2.5-flash` can become restricted
# to existing users; the -latest alias stays available and up to date.
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-flash-latest")
GEMINI_VISION_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-flash-latest")
# Audio uses the lighter/faster Flash-Lite alias — voice transcription is latency
# sensitive and flash-lite responds noticeably quicker for short clips.
GEMINI_AUDIO_MODEL = os.environ.get("GEMINI_AUDIO_MODEL", "gemini-flash-lite-latest")
# UTR/reference OCR from a payment screenshot is a trivial extraction task, so it
# uses the lighter/faster Flash-Lite alias — resolves in ~1-3s vs the heavier Flash.
GEMINI_UTR_MODEL = os.environ.get("GEMINI_UTR_MODEL", "gemini-flash-lite-latest")

# ----------------------------------------------------------------------------
# COLLECT-AND-PAYOUT model (v2): customer pays merchant_amount + platform fee to
# BILL4PE's Razorpay PG account; RazorpayX then pays the merchant_amount to the
# scanned UPI. RazorpayX reuses the SAME Razorpay key id/secret (Basic auth).
# ----------------------------------------------------------------------------
RAZORPAYX_ACCOUNT_NUMBER = os.environ.get("RAZORPAYX_ACCOUNT_NUMBER", "").strip()
# Dedicated webhook secrets for the v2 endpoints. Fall back to the legacy shared
# RAZORPAY_WEBHOOK_SECRET so a single-secret setup still works.
RAZORPAY_PAYMENT_WEBHOOK_SECRET = (
    os.environ.get("RAZORPAY_PAYMENT_WEBHOOK_SECRET", "").strip()
    or os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
)
RAZORPAYX_WEBHOOK_SECRET = (
    os.environ.get("RAZORPAYX_WEBHOOK_SECRET", "").strip()
    or os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
)
# BILL4PE platform/service fee. Configurable; DB admin setting overrides this at
# runtime (see payment_service.get_fee_percent). Historical txns snapshot their own.
DEFAULT_PLATFORM_FEE_PERCENT = os.environ.get("BILL4PE_PLATFORM_FEE_PERCENT", "10")
# Optional future minimum fee (paise). 0 = disabled.
MIN_PLATFORM_FEE_PAISE = int(os.environ.get("BILL4PE_MIN_PLATFORM_FEE_PAISE", "0") or 0)

from decimal import Decimal, ROUND_HALF_UP  # noqa: E402


def compute_fee_breakdown(merchant_amount_paise: int, fee_percent) -> dict:
    """Safe integer-paise money math for the collect-and-payout model.

    platform_fee = merchant_amount * fee_percent / 100  (ROUND_HALF_UP, paise)
    customer_total = merchant_amount + platform_fee
    merchant_payout = merchant_amount  (never the total)
    """
    mp = Decimal(int(merchant_amount_paise))
    pct = Decimal(str(fee_percent))
    fee_paise = int((mp * pct / Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))
    if MIN_PLATFORM_FEE_PAISE and fee_paise < MIN_PLATFORM_FEE_PAISE:
        fee_paise = MIN_PLATFORM_FEE_PAISE
    total = int(mp) + fee_paise
    return {
        "merchant_amount_paise": int(mp),
        "platform_fee_percent_snapshot": f"{pct:.2f}",
        "platform_fee_paise": fee_paise,
        "customer_total_paise": total,
        "merchant_payout_amount_paise": int(mp),
    }


# Business constants
BILL_FEE_PERCENT = 0.01   # 1% of expense total (LEGACY reimbursement fee)
BILL_FEE_MIN = 1.0        # Minimum convenience fee (₹)
REFERRAL_BONUS = 50.0
DEMO_OTP = "123456"
FAV_ALLOWED_CATEGORIES = {"pantry", "grocery"}
FAV_MAX_PER_CATEGORY = 20


def calc_bill_fee(total: float) -> float:
    """Convenience fee for generating a bill = 1% of expense total, min ₹1."""
    try:
        amt = float(total or 0)
    except (TypeError, ValueError):
        amt = 0.0
    return round(max(BILL_FEE_MIN, amt * BILL_FEE_PERCENT), 2)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bill4pe")
