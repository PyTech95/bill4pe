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
BILL_FEE = 5.0
REFERRAL_BONUS = 50.0
DEMO_OTP = "123456"
FAV_ALLOWED_CATEGORIES = {"pantry", "grocery"}
FAV_MAX_PER_CATEGORY = 20

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bill4pe")
