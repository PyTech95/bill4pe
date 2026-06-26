"""Environment and runtime configuration for BILL4PE."""
from dotenv import load_dotenv
from pathlib import Path
import os
import logging

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

# LLM provider keys (standard SDKs, self-host compatible)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Model names – override via env if needed
OPENAI_WHISPER_MODEL = os.environ.get("OPENAI_WHISPER_MODEL", "whisper-1")
GEMINI_VISION_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-1.5-flash")
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-1.5-flash")

# Business constants
BILL_FEE_PERCENT = 0.01   # 1% of expense total
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
