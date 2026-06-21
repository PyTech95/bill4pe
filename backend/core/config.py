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
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

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
