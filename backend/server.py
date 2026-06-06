"""BILL4PE - AI-powered expense, invoice and reimbursement platform backend."""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import uuid
import logging
import base64
import io
import json
import bcrypt
import jwt
import tempfile

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
from emergentintegrations.llm.openai import OpenAISpeechToText


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="BILL4PE API")
api = APIRouter(prefix="/api")
bearer = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bill4pe")


# =================== Models ===================
class RegisterReq(BaseModel):
    email: EmailStr
    password: str
    name: str
    referrer_code: Optional[str] = None
    user_type: Optional[str] = "individual"  # "individual" or "corporate"
    corporate_name: Optional[str] = None
    subscription_plan: Optional[str] = None  # "monthly_50" | "monthly_100" | "quarterly_50" | "quarterly_100" | "yearly_50" | "yearly_100"
    employee_limit: Optional[int] = None

class LoginReq(BaseModel):
    email: EmailStr
    password: str

class OtpRequestReq(BaseModel):
    phone: str
    name: Optional[str] = None

class OtpVerifyReq(BaseModel):
    phone: str
    otp: str
    name: Optional[str] = None
    referrer_code: Optional[str] = None

class User(BaseModel):
    id: str
    email: str
    name: str
    wallet_balance: float = 0.0
    created_at: str

class ItemIn(BaseModel):
    name: str
    quantity: float = 1
    unit_price: float

class ExpenseDraft(BaseModel):
    category: str
    sub_category: Optional[str] = None
    items: List[ItemIn]
    notes: Optional[str] = None

class TripInfo(BaseModel):
    from_text: Optional[str] = None
    to_text: Optional[str] = None
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    drop_lat: Optional[float] = None
    drop_lng: Optional[float] = None
    nature_of_business: Optional[str] = None  # e.g. "Auto Driver"

class StayInfo(BaseModel):
    hotel_name: Optional[str] = None
    room_type: Optional[str] = None
    check_in: Optional[str] = None       # YYYY-MM-DD
    check_out: Optional[str] = None      # YYYY-MM-DD
    nights: Optional[int] = None
    per_night_rate: Optional[float] = None
    nature_of_business: Optional[str] = None  # e.g. "Hotel & Lodging"

class PaymentInfo(BaseModel):
    merchant_name: Optional[str] = None
    merchant_upi: Optional[str] = None
    merchant_mobile: Optional[str] = None
    transaction_id: Optional[str] = None
    amount: float
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    payment_method: str = "UPI"  # UPI/Cash/GPay/PhonePe/Paytm/BharatPe/BHIM
    trip: Optional[TripInfo] = None
    stay: Optional[StayInfo] = None

class ExpenseCreate(BaseModel):
    category: str
    sub_category: Optional[str] = None
    items: List[ItemIn]
    payment: PaymentInfo
    notes: Optional[str] = None

class WalletRecharge(BaseModel):
    amount: float

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    company_name: Optional[str] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class ReportCreate(BaseModel):
    title: str
    expense_ids: List[str]
    notes: Optional[str] = None

class ContactMsg(BaseModel):
    name: str
    email: EmailStr
    message: str

class FavouriteItem(BaseModel):
    name: str
    unit_price: float = 0.0

class FavouritesSave(BaseModel):
    category: str
    items: List[FavouriteItem]


# =================== Helpers ===================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def make_token(uid: str) -> str:
    payload = {"uid": uid, "exp": datetime.now(timezone.utc) + timedelta(days=30)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ============== Referral helpers ==============
REFERRAL_BONUS = 50.0
_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/1/I/O

def gen_referral_code() -> str:
    import secrets
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))

async def ensure_referral_code(uid: str) -> str:
    user = await db.users.find_one({"id": uid}, {"_id": 0, "referral_code": 1})
    code = (user or {}).get("referral_code")
    if code:
        return code
    # Generate a unique code
    for _ in range(20):
        candidate = gen_referral_code()
        exists = await db.users.find_one({"referral_code": candidate}, {"_id": 1})
        if not exists:
            await db.users.update_one({"id": uid}, {"$set": {"referral_code": candidate}})
            return candidate
    raise HTTPException(500, "Could not generate referral code")

async def apply_referral(new_user_id: str, referrer_code: Optional[str]) -> Optional[str]:
    """If referrer_code is valid and isn't self, credit ₹50 to both users.
    Returns referrer name or None."""
    if not referrer_code:
        return None
    code = referrer_code.strip().upper()
    if not code:
        return None
    referrer = await db.users.find_one({"referral_code": code})
    if not referrer or referrer["id"] == new_user_id:
        return None
    # Check this user hasn't already been credited
    existing = await db.referrals.find_one({"referee_id": new_user_id})
    if existing:
        return None
    # Credit both
    now = now_iso()
    rid = str(uuid.uuid4())
    await db.referrals.insert_one({
        "id": rid,
        "referrer_id": referrer["id"],
        "referee_id": new_user_id,
        "bonus_each": REFERRAL_BONUS,
        "created_at": now,
    })
    # Referrer
    await db.users.update_one(
        {"id": referrer["id"]},
        {"$inc": {"wallet_balance": REFERRAL_BONUS}},
    )
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": referrer["id"], "type": "credit",
        "amount": REFERRAL_BONUS, "reason": "Referral bonus (friend joined)",
        "created_at": now,
    })
    # Referee
    await db.users.update_one(
        {"id": new_user_id},
        {"$inc": {"wallet_balance": REFERRAL_BONUS}},
    )
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": new_user_id, "type": "credit",
        "amount": REFERRAL_BONUS, "reason": f"Welcome referral bonus (invited by {referrer.get('name','a friend')})",
        "created_at": now,
    })
    return referrer.get("name")

async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
        uid = payload["uid"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": uid}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


# =================== Auth ===================
@api.post("/auth/register")
async def register(body: RegisterReq):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(400, "Email already registered")
    uid = str(uuid.uuid4())
    user_type = (body.user_type or "individual").lower().strip()
    if user_type not in ("individual", "corporate"):
        user_type = "individual"
    doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name,
        "password": hash_pw(body.password),
        "wallet_balance": 50.0,  # 50 INR welcome bonus
        "user_type": user_type,
        "corporate_name": (body.corporate_name or "").strip() if user_type == "corporate" else None,
        "subscription_plan": (body.subscription_plan or "").strip() if user_type == "corporate" else None,
        "employee_limit": int(body.employee_limit) if (user_type == "corporate" and body.employee_limit) else None,
        "subscription_status": "trial" if user_type == "corporate" else None,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    # Welcome wallet transaction
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "type": "credit",
        "amount": 50.0, "reason": "Welcome bonus", "created_at": now_iso()
    })
    # Apply referral if any
    await apply_referral(uid, body.referrer_code)
    # Always ensure code exists for this new user
    await ensure_referral_code(uid)
    # Fetch fresh balance after possible referral bonus
    fresh = await db.users.find_one({"id": uid}, {"_id": 0, "password": 0})
    token = make_token(uid)
    return {"token": token, "user": fresh}

@api.post("/auth/login")
async def login(body: LoginReq):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not check_pw(body.password, user["password"]):
        raise HTTPException(401, "Invalid credentials")
    token = make_token(user["id"])
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return {"token": token, "user": fresh}

@api.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


@api.put("/auth/me")
async def update_profile(body: ProfileUpdate, user=Depends(get_current_user)):
    patch = {}
    if body.name is not None and body.name.strip():
        patch["name"] = body.name.strip()
    if body.phone is not None:
        phone = "".join(c for c in body.phone if c.isdigit())[-10:]
        if phone and len(phone) != 10:
            raise HTTPException(400, "Phone must be a 10-digit Indian number")
        patch["phone"] = f"+91{phone}" if phone else None
    if body.gstin is not None:
        gstin = (body.gstin or "").strip().upper()
        if gstin:
            # GSTIN format: 15 chars - 2 state + 10 PAN + 1 entity + 1 Z + 1 check
            import re as _re
            if not _re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", gstin):
                raise HTTPException(400, "Invalid GSTIN format (must be 15 chars, e.g. 27ABCDE1234F1Z5)")
        patch["gstin"] = gstin or None
    if body.company_name is not None:
        patch["company_name"] = (body.company_name or "").strip() or None
    if patch:
        await db.users.update_one({"id": user["id"]}, {"$set": patch})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return updated


@api.post("/auth/change-password")
async def change_password(body: PasswordChange, user=Depends(get_current_user)):
    full = await db.users.find_one({"id": user["id"]})
    if not full or not check_pw(body.current_password, full["password"]):
        raise HTTPException(401, "Current password is incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")
    await db.users.update_one(
        {"id": user["id"]}, {"$set": {"password": hash_pw(body.new_password)}}
    )
    return {"ok": True}


@api.delete("/auth/me")
async def delete_account(user=Depends(get_current_user)):
    uid = user["id"]
    await db.expenses.delete_many({"user_id": uid})
    await db.wallet_txns.delete_many({"user_id": uid})
    await db.reports.delete_many({"user_id": uid})
    await db.users.delete_one({"id": uid})
    return {"ok": True}


# Phone OTP (demo mode — universal OTP 123456)
DEMO_OTP = "123456"

def _norm_phone(p: str) -> str:
    return "".join(c for c in (p or "") if c.isdigit())[-10:]

@api.post("/auth/otp/request")
async def otp_request(body: OtpRequestReq):
    phone = _norm_phone(body.phone)
    if len(phone) != 10:
        raise HTTPException(400, "Invalid 10-digit phone number")
    # DEMO: no real SMS — log it for transparency. OTP is fixed: 123456
    logger.info(f"OTP requested for +91{phone}. Demo OTP: {DEMO_OTP}")
    return {"ok": True, "demo_hint": "Use OTP 123456 for any number (demo mode)"}

@api.post("/auth/otp/verify")
async def otp_verify(body: OtpVerifyReq):
    phone = _norm_phone(body.phone)
    if len(phone) != 10:
        raise HTTPException(400, "Invalid phone number")
    if (body.otp or "").strip() != DEMO_OTP:
        raise HTTPException(401, "Invalid OTP")
    fake_email = f"+91{phone}@phone.bill4pe.local"
    user = await db.users.find_one({"email": fake_email})
    is_new = user is None
    if is_new:
        uid = str(uuid.uuid4())
        user_doc = {
            "id": uid,
            "email": fake_email,
            "phone": f"+91{phone}",
            "name": (body.name or f"User {phone[-4:]}"),
            "password": hash_pw(str(uuid.uuid4())),  # random unusable password
            "wallet_balance": 50.0,
            "auth_provider": "phone",
            "created_at": now_iso(),
        }
        await db.users.insert_one(user_doc)
        await db.wallet_txns.insert_one({
            "id": str(uuid.uuid4()), "user_id": uid, "type": "credit",
            "amount": 50.0, "reason": "Welcome bonus", "created_at": now_iso()
        })
        await apply_referral(uid, body.referrer_code)
        await ensure_referral_code(uid)
        user = await db.users.find_one({"id": uid})
    token = make_token(user["id"])
    return {"token": token, "user": {
        "id": user["id"], "email": user["email"], "name": user["name"],
        "phone": user.get("phone"),
        "wallet_balance": user.get("wallet_balance", 0.0),
        "referral_code": user.get("referral_code"),
    }}


# =================== Referral program ===================
@api.get("/referrals/me")
async def referrals_me(user=Depends(get_current_user)):
    code = await ensure_referral_code(user["id"])
    refs = await db.referrals.find(
        {"referrer_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    items: List[dict] = []
    for r in refs:
        ref_user = await db.users.find_one(
            {"id": r["referee_id"]}, {"_id": 0, "name": 1, "created_at": 1}
        )
        items.append({
            "id": r["id"],
            "referee_name": (ref_user or {}).get("name", "Friend"),
            "bonus": float(r.get("bonus_each", REFERRAL_BONUS)),
            "joined_at": r.get("created_at"),
        })
    earnings = round(sum(i["bonus"] for i in items), 2)
    return {
        "code": code,
        "bonus_per_referral": REFERRAL_BONUS,
        "total_referrals": len(items),
        "total_earnings": earnings,
        "referrals": items,
    }


@api.get("/referrals/validate/{code}")
async def referrals_validate(code: str):
    code = (code or "").strip().upper()
    if not code:
        raise HTTPException(400, "Empty code")
    ref = await db.users.find_one({"referral_code": code}, {"_id": 0, "name": 1})
    if not ref:
        raise HTTPException(404, "Invalid code")
    return {"valid": True, "referrer_name": ref.get("name", "A friend"), "bonus": REFERRAL_BONUS}



# =================== AI Image Detection ===================
FOOD_PROMPT = """You are an expert Indian thali / food billing assistant. Analyze the photo and detect EVERY visible food item.

For each distinct dish/item, return a JSON object with:
- "name": short Indian food name. Be specific:
    "Roti" / "Naan" / "Tandoori Roti" / "Paratha"
    "Dal" / "Dal Tadka" / "Dal Makhani"
    "Rice" / "Jeera Rice" / "Biryani"
    "Sabji" (or specific: "Paneer", "Bhindi", "Aloo Gobi", "Mixed Veg")
    "Chicken Curry" / "Butter Chicken" / "Mutton Curry"
    "Salad" / "Raita" / "Papad" / "Pickle" / "Chutney"
    "Sweets" (or specific: "Gulab Jamun", "Halwa")
    "Water Bottle" / "Cold Drink" / "Lassi" / "Buttermilk"
- "quantity": realistic count visible. For rotis count individual pieces (e.g. 3).
    For dal/sabji/rice use 1 (one serving bowl). For thali = 1 (the combo plate counts as 1).
- "unit_price": reasonable INR price per unit at a typical mid-range Indian restaurant.
    Rotis ~15, Dal ~50-60, Rice ~50, Sabji ~60-80, Chicken curry ~180-220,
    Paneer dishes ~150-180, Thali ~150-250, Water ~20.

If it's clearly a single combo "thali", return one row {"name":"Thali","quantity":1,"unit_price":<estimated>}
PLUS optionally extra items visible alongside (water bottle, papad, sweets, etc.).

Return ONLY a strict JSON array. No markdown, no prose, no code fences. Example:
[{"name":"Roti","quantity":3,"unit_price":15},{"name":"Dal Tadka","quantity":1,"unit_price":55},{"name":"Jeera Rice","quantity":1,"unit_price":50},{"name":"Paneer Bhurji","quantity":1,"unit_price":150}]

If the image is not food-related, return []."""

GENERIC_PROMPT = """You are an expense bill assistant. Analyze the image (could be receipt, products, bill, items).

Detect each line item. Return ONLY a strict JSON array of {"name": str, "quantity": int, "unit_price": float (INR)}.
No markdown, no prose, no code fences. If nothing detectable, return []."""


GROCERY_PROMPT = """You are an Indian grocery shopping assistant. Look at the photo (could be a kirana store basket, supermarket cart, kitchen counter of bought groceries, or assorted packaged products).

Detect every distinct grocery item visible. For each, return:
- "name": specific Indian grocery item name. Include brand + pack size when readable. Examples:
    "Aashirvaad Atta 5kg" / "Atta 1kg"
    "Basmati Rice 5kg" / "Sona Masoori Rice 1kg"
    "Toor Dal 1kg" / "Moong Dal 500g" / "Chana Dal 1kg"
    "Fortune Sunflower Oil 1L" / "Mustard Oil 1L"
    "Tata Salt 1kg" / "Sugar 1kg"
    "Amul Butter 100g" / "Amul Cheese Slice"
    "Aashirvaad Sugar 1kg" / "Madhusudan Ghee 500g"
    "Onion 1kg" / "Tomato 1kg" / "Potato 2kg" / "Banana 1 dozen"
    "Parle-G 50g" / "Britannia Bourbon" / "Maggi 70g x 4"
    "Surf Excel 1kg" / "Vim Bar 200g" (count as grocery if mixed with food items)
- "quantity": realistic count of that exact pack visible (e.g. 2 packs of Atta = quantity 2)
- "unit_price": typical INR retail price PER PACK at an Indian supermarket
    Atta 5kg ~275, Atta 1kg ~50, Basmati Rice 5kg ~600, Sona Masoori 1kg ~70
    Toor Dal 1kg ~140, Moong Dal 1kg ~130, Sugar 1kg ~45
    Sunflower Oil 1L ~150, Mustard Oil 1L ~180, Salt 1kg ~22
    Amul Butter 100g ~58, Maggi 70g ~14, Parle-G 50g ~10
    Onion ~30/kg, Tomato ~40/kg, Potato ~30/kg

Return ONLY a strict JSON array. No markdown, no prose, no code fences. Example:
[{"name":"Aashirvaad Atta 5kg","quantity":1,"unit_price":275},{"name":"Toor Dal 1kg","quantity":2,"unit_price":140},{"name":"Tata Salt 1kg","quantity":1,"unit_price":22}]

If nothing grocery-like is visible, return []."""


PANTRY_PROMPT = """You are an office pantry / break-room expense assistant. Look at the photo of office snacks, beverages, and pantry supplies.

Detect every distinct item visible. For each, return:
- "name": specific item with brand & pack when readable. Examples:
    "Nescafé Classic 50g" / "Bru Instant Coffee 100g" / "Tata Tea Premium 250g"
    "Amul Tetra Pack Milk 1L" / "Mother Dairy Toned Milk 500ml"
    "Sugar 1kg" / "Sugar Sachet x 100"
    "Britannia Marie Gold" / "Parle-G 250g" / "Oreo 120g"
    "Lays Magic Masala 90g" / "Kurkure Masala Munch 80g" / "Haldiram Bhujia 200g"
    "Aquafina 1L Water" / "Bisleri 2L" / "Coca-Cola 750ml"
    "Real Mixed Fruit Juice 1L" / "Tropicana 200ml"
    "Cake / Pastry" / "Sandwich" / "Samosa" / "Vada Pav"
    "Paper Cups x 100" / "Plastic Spoons x 50" (count if part of pantry restock)
- "quantity": realistic count of that pack visible
- "unit_price": typical INR retail price PER PACK
    Nescafé 50g ~155, Bru 100g ~200, Tata Tea 250g ~120, Amul Milk 1L ~70
    Britannia Marie ~30, Parle-G 250g ~50, Lays 90g ~30, Kurkure 80g ~20
    Bisleri 1L ~20, Coca-Cola 750ml ~40, Real Juice 1L ~110
    Samosa ~15, Vada Pav ~25, Pastry ~80

Return ONLY a strict JSON array. No markdown, no prose, no code fences. Example:
[{"name":"Nescafé Classic 50g","quantity":2,"unit_price":155},{"name":"Britannia Marie Gold","quantity":3,"unit_price":30},{"name":"Bisleri 1L","quantity":12,"unit_price":20}]

If nothing pantry-related is visible, return []."""


STATIONERY_PROMPT = """You are an office stationery expense assistant. Look at the photo of office supplies.

Detect every distinct stationery item visible. For each, return:
- "name": specific item with brand & pack when readable. Examples:
    "Reynolds 045 Blue Pen" / "Cello Butterflow Pen" / "Parker Vector"
    "A4 Sheets 500 sheets" / "Notebook 200 pages" / "Sticky Notes 100 sheets"
    "Stapler" / "Staple Pins box" / "Paper Clips box"
    "Highlighter Set 4" / "Permanent Marker" / "White Board Marker"
    "File Folder" / "Box File" / "Punching Machine"
    "Calculator Casio" / "Scissors" / "Ruler 30cm"
    "Printer Cartridge HP 802" / "Toner"
- "quantity": realistic count visible
- "unit_price": typical INR retail price
    Pen ~10-100, A4 ream ~300, Notebook ~80-150, Stapler ~80
    Marker ~40, Highlighter ~30, Sticky note ~50, File ~25
    Cartridge ~750, Calculator ~250

Return ONLY a strict JSON array. No markdown, no prose, no code fences. If nothing stationery-related, return []."""


def _category_prompt(category: str) -> str:
    c = (category or "").lower().strip()
    if c == "food":
        return FOOD_PROMPT
    if c == "grocery":
        return GROCERY_PROMPT
    if c == "pantry":
        return PANTRY_PROMPT
    if c == "stationery":
        return STATIONERY_PROMPT
    return GENERIC_PROMPT


RECEIPT_PROMPT = """You are an expert OCR receipt parser for Indian printed bills (Swiggy / Zomato / BigBazaar / DMart / Reliance Fresh / restaurants / pharmacies / grocery stores / petrol pumps).

Carefully read the receipt photo. Extract:
- merchant_name: the brand/store at the top of the receipt (e.g. "Swiggy", "BigBazaar", "Saravana Bhavan"). If unclear, return "".
- date: bill date in YYYY-MM-DD if visible, else "".
- items: array of line items. For each: {"name": short str, "quantity": int (default 1), "unit_price": float (INR per unit)}.
    If only line total is printed (no per-unit price), set quantity=1 and unit_price=line_total.
- subtotal: float (before tax) if printed, else 0.
- tax: float (GST/CGST/SGST total) if printed, else 0.
- total: final amount payable (after tax/discount) in INR.
- category: best guess from ["food","travel","hotel","stationery","gift","pantry","flower","grocery","cleaning","other"].

Return ONLY a strict JSON object, no markdown, no prose, no code fences. Example:

{"merchant_name":"BigBazaar","date":"2026-01-15","items":[{"name":"Tata Salt 1kg","quantity":2,"unit_price":28},{"name":"Aashirvaad Atta 5kg","quantity":1,"unit_price":275}],"subtotal":331,"tax":0,"total":331,"category":"grocery"}

If receipt unreadable, return {"merchant_name":"","date":"","items":[],"subtotal":0,"tax":0,"total":0,"category":"other"}."""


@api.post("/ai/detect-items")
async def detect_items(category: str = "food", file: UploadFile = File(...), user=Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 8MB)")
    mime = file.content_type or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        mime = "image/jpeg"
    suffix = ".jpg" if "jpeg" in mime else (".png" if "png" in mime else ".webp")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(raw); tmp.flush(); tmp.close()
    try:
        prompt = _category_prompt(category)
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"detect-{uuid.uuid4()}",
            system_message=prompt,
        ).with_model("gemini", "gemini-3-flash-preview")
        msg = UserMessage(
            text=f"Detect all {category} items in this image. Return strict JSON array only.",
            file_contents=[FileContentWithMimeType(file_path=tmp.name, mime_type=mime)],
        )
        reply = await chat.send_message(msg)
        txt = (reply or "").strip()
        # Strip code fences if present
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        # Find JSON array
        start, end = txt.find("["), txt.rfind("]")
        if start >= 0 and end > start:
            txt = txt[start:end + 1]
        try:
            items = json.loads(txt)
        except Exception:
            items = []
        # Normalize
        cleaned = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            if not name:
                continue
            try:
                qty = float(it.get("quantity", 1) or 1)
                price = float(it.get("unit_price", 0) or 0)
            except Exception:
                qty, price = 1.0, 0.0
            cleaned.append({"name": name, "quantity": qty, "unit_price": round(price, 2)})
        return {"items": cleaned}
    except Exception as e:
        logger.exception("AI detection failed")
        raise HTTPException(500, f"AI detection failed: {str(e)[:200]}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@api.post("/ai/suggest-items")
async def suggest_items(payload: dict, user=Depends(get_current_user)):
    """Suggest item names for manual entry autocomplete."""
    if not EMERGENT_LLM_KEY:
        return {"suggestions": []}
    category = payload.get("category", "food")
    query = payload.get("query", "")
    if len(query) < 2:
        return {"suggestions": []}
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"suggest-{uuid.uuid4()}",
            system_message=(
                f"You suggest short Indian {category} item names for autocomplete. "
                f"Return ONLY a JSON array of 5 short strings, no prose. Example: [\"Roti\",\"Rumali Roti\",\"Romali\",\"Roomali Roti\",\"Tandoori Roti\"]"
            ),
        ).with_model("gemini", "gemini-3-flash-preview")
        reply = await chat.send_message(UserMessage(text=f"Suggest items starting with '{query}'"))
        txt = (reply or "").strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        s, e = txt.find("["), txt.rfind("]")
        if s >= 0 and e > s:
            txt = txt[s:e + 1]
        arr = json.loads(txt)
        return {"suggestions": [str(x) for x in arr if isinstance(x, (str, int, float))][:5]}
    except Exception:
        return {"suggestions": []}
# =================== Receipt OCR (printed bills - Swiggy / BigBazaar / etc.) ===================
@api.post("/ai/scan-receipt")
async def scan_receipt(file: UploadFile = File(...), user=Depends(get_current_user)):
    """OCR a printed receipt photo into structured expense data."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 8MB)")
    mime = file.content_type or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        mime = "image/jpeg"
    suffix = ".jpg" if "jpeg" in mime else (".png" if "png" in mime else ".webp")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(raw); tmp.flush(); tmp.close()
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"receipt-{uuid.uuid4()}",
            system_message=RECEIPT_PROMPT,
        ).with_model("gemini", "gemini-3-flash-preview")
        msg = UserMessage(
            text="Parse this Indian printed receipt. Return strict JSON object only.",
            file_contents=[FileContentWithMimeType(file_path=tmp.name, mime_type=mime)],
        )
        reply = await chat.send_message(msg)
        txt = (reply or "").strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        start, end = txt.find("{"), txt.rfind("}")
        if start >= 0 and end > start:
            txt = txt[start:end + 1]
        try:
            parsed = json.loads(txt)
        except Exception:
            parsed = {}

        valid_cats = {"food", "travel", "hotel", "stationery", "gift", "pantry", "flower", "grocery", "cleaning", "other"}
        category = str(parsed.get("category", "other")).lower().strip()
        if category not in valid_cats:
            category = "other"

        items = []
        for it in (parsed.get("items") or []):
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            if not name:
                continue
            try:
                qty = float(it.get("quantity", 1) or 1)
                price = float(it.get("unit_price", 0) or 0)
            except Exception:
                qty, price = 1.0, 0.0
            items.append({"name": name, "quantity": qty, "unit_price": round(price, 2)})

        def num(v):
            try:
                return round(float(v or 0), 2)
            except Exception:
                return 0.0

        return {
            "merchant_name": str(parsed.get("merchant_name", "")).strip(),
            "date": str(parsed.get("date", "")).strip(),
            "items": items,
            "subtotal": num(parsed.get("subtotal")),
            "tax": num(parsed.get("tax")),
            "total": num(parsed.get("total")),
            "category": category,
        }
    except Exception as e:
        logger.exception("Receipt OCR failed")
        raise HTTPException(500, f"Receipt OCR failed: {str(e)[:200]}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


# =================== Voice Expense Entry (Whisper STT + Gemini parse) ===================
VOICE_PARSE_PROMPT = """Parse this Indian expense voice note (Hindi/English/Hinglish) into STRICT JSON only (no markdown, no fences):
{"category":"food|travel|hotel|stationery|gift|pantry|flower|grocery|cleaning|other","sub_category":"<short>","merchant_name":"<or empty>","total_amount":<INR number>,"items":[{"name":"<str>","quantity":<int>,"unit_price":<float>}]}

If only total mentioned (e.g. "spent 250 on lunch"), create one item: name=sub_category, qty=1, price=total.
Examples:
"Spent 250 on lunch at Saravana Bhavan" -> {"category":"food","sub_category":"Lunch","merchant_name":"Saravana Bhavan","total_amount":250,"items":[{"name":"Lunch","quantity":1,"unit_price":250}]}
"Cab 450 Uber" -> {"category":"travel","sub_category":"Cab","merchant_name":"Uber","total_amount":450,"items":[{"name":"Cab fare","quantity":1,"unit_price":450}]}

If unclear: category="other", sub_category="Misc". Output JSON only."""


@api.post("/voice/expense")
async def voice_expense(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Accept audio file → Whisper transcript → Gemini parse → structured draft expense."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio too large (max 25MB)")
    if not raw:
        raise HTTPException(400, "Empty audio file")

    # Pick suffix based on content_type for Whisper
    ct = (file.content_type or "").lower()
    if "webm" in ct:
        suffix = ".webm"
    elif "mp4" in ct or "m4a" in ct:
        suffix = ".m4a"
    elif "wav" in ct:
        suffix = ".wav"
    elif "mpeg" in ct or "mp3" in ct:
        suffix = ".mp3"
    else:
        suffix = ".webm"  # MediaRecorder default in browsers

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(raw); tmp.flush(); tmp.close()
    transcript = ""
    try:
        # Step 1: Whisper transcription
        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        with open(tmp.name, "rb") as af:
            stt_resp = await stt.transcribe(
                file=af,
                model="whisper-1",
                response_format="json",
                prompt="Indian expense note. Mentions amounts in rupees, food items, cab/flight, merchant names.",
            )
        transcript = (getattr(stt_resp, "text", "") or "").strip()
        if not transcript:
            raise HTTPException(422, "Could not hear anything in the audio")

        # Step 2: Parse to structured JSON via Gemini
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"voice-parse-{uuid.uuid4()}",
            system_message=VOICE_PARSE_PROMPT,
        ).with_model("gemini", "gemini-3-flash-preview")
        reply = await chat.send_message(UserMessage(text=f"Transcript: {transcript}"))
        txt = (reply or "").strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        start, end = txt.find("{"), txt.rfind("}")
        if start >= 0 and end > start:
            txt = txt[start:end + 1]
        try:
            parsed = json.loads(txt)
        except Exception:
            parsed = {}

        # Normalize
        valid_cats = {"food", "travel", "hotel", "stationery", "gift", "pantry", "flower", "grocery", "cleaning", "other"}
        category = str(parsed.get("category", "other")).lower().strip()
        if category not in valid_cats:
            category = "other"
        sub_category = str(parsed.get("sub_category", "Misc")).strip() or "Misc"
        merchant_name = str(parsed.get("merchant_name", "")).strip()
        try:
            total_amount = float(parsed.get("total_amount", 0) or 0)
        except Exception:
            total_amount = 0.0

        items = []
        for it in (parsed.get("items") or []):
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            if not name:
                continue
            try:
                qty = float(it.get("quantity", 1) or 1)
                price = float(it.get("unit_price", 0) or 0)
            except Exception:
                qty, price = 1.0, 0.0
            items.append({"name": name, "quantity": qty, "unit_price": round(price, 2)})

        # Fallback: if no items but we have a total
        if not items and total_amount > 0:
            items = [{"name": sub_category or "Expense", "quantity": 1.0, "unit_price": round(total_amount, 2)}]

        return {
            "transcript": transcript,
            "category": category,
            "sub_category": sub_category,
            "merchant_name": merchant_name,
            "total_amount": round(total_amount, 2),
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Voice parse failed")
        raise HTTPException(500, f"Voice processing failed: {str(e)[:200]}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


# =================== Expenses ===================
@api.post("/expenses")
async def create_expense(body: ExpenseCreate, user=Depends(get_current_user)):
    eid = str(uuid.uuid4())
    total = round(sum(i.quantity * i.unit_price for i in body.items), 2)
    doc = {
        "id": eid,
        "user_id": user["id"],
        "category": body.category,
        "sub_category": body.sub_category,
        "items": [i.model_dump() for i in body.items],
        "payment": body.payment.model_dump(),
        "total": total,
        "notes": body.notes,
        "bill_generated": False,
        "bill_id": None,
        "created_at": now_iso(),
    }
    await db.expenses.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api.get("/expenses")
async def list_expenses(user=Depends(get_current_user), category: Optional[str] = None, days: Optional[int] = None):
    q = {"user_id": user["id"]}
    if category:
        q["category"] = category
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        q["created_at"] = {"$gte": cutoff}
    items = await db.expenses.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"expenses": items}

@api.get("/expenses/stats")
async def stats(user=Depends(get_current_user)):
    cursor = db.expenses.find({"user_id": user["id"]}, {"_id": 0})
    total = 0.0
    by_cat: dict = {}
    count = 0
    async for e in cursor:
        total += float(e.get("total", 0))
        cat = e.get("category", "Other")
        by_cat[cat] = by_cat.get(cat, 0) + float(e.get("total", 0))
        count += 1
    return {
        "total_expenses": round(total, 2),
        "expense_count": count,
        "by_category": [{"category": k, "amount": round(v, 2)} for k, v in by_cat.items()],
    }

@api.get("/expenses/merchants/recent")
async def recent_merchants(user=Depends(get_current_user)):
    """Deduped list of recent merchants for one-tap quick re-pay."""
    cursor = db.expenses.find(
        {"user_id": user["id"], "payment.merchant_name": {"$ne": None}},
        {"_id": 0},
    ).sort("created_at", -1).limit(50)
    seen = set()
    out: List[dict] = []
    async for e in cursor:
        pay = e.get("payment") or {}
        m = pay.get("merchant_name")
        if not m or m in seen:
            continue
        seen.add(m)
        out.append({
            "merchant_name": m,
            "merchant_upi": pay.get("merchant_upi"),
            "category": e.get("category"),
            "sub_category": e.get("sub_category"),
            "last_amount": float(e.get("total", 0)),
            "last_date": (e.get("created_at") or "")[:10],
        })
        if len(out) >= 6:
            break
    return {"merchants": out}


@api.get("/expenses/trips")
async def trips(user=Depends(get_current_user)):
    """Group travel expenses by day as 'trips'. Returns aggregated trip cards."""
    cursor = db.expenses.find(
        {"user_id": user["id"], "category": "travel"}, {"_id": 0}
    ).sort("created_at", -1)
    trips_by_day: dict = {}
    async for e in cursor:
        day = (e.get("created_at") or "")[:10]
        if not day:
            continue
        t = trips_by_day.setdefault(day, {
            "date": day, "total": 0.0, "legs": 0, "merchants": [], "expenses": [],
        })
        t["total"] += float(e.get("total", 0))
        t["legs"] += 1
        m = (e.get("payment") or {}).get("merchant_name")
        if m and m not in t["merchants"]:
            t["merchants"].append(m)
        t["expenses"].append(e)
    out = [{**v, "total": round(v["total"], 2)} for v in trips_by_day.values()]
    out.sort(key=lambda x: x["date"], reverse=True)
    return {"trips": out}


@api.get("/expenses/export.csv")
async def export_csv(
    days: Optional[int] = None,
    category: Optional[str] = None,
    token: Optional[str] = None,
    creds: HTTPAuthorizationCredentials = Depends(bearer),
):
    """CSV export of expenses. Accepts auth via Bearer or ?token= (for direct download)."""
    auth_token = creds.credentials if creds else token
    if not auth_token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(auth_token, JWT_SECRET, algorithms=["HS256"])
        uid = payload["uid"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")

    q = {"user_id": uid}
    if category:
        q["category"] = category
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        q["created_at"] = {"$gte": cutoff}
    rows = await db.expenses.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)

    import csv as csv_mod
    buf = io.StringIO()
    w = csv_mod.writer(buf)
    w.writerow([
        "Date", "Bill ID", "Category", "Sub-category", "Merchant", "UPI ID",
        "Transaction ID", "Items", "Total (INR)", "Latitude", "Longitude",
    ])
    for r in rows:
        pay = r.get("payment") or {}
        items_str = "; ".join(
            f"{i.get('name')} x{i.get('quantity')} @ ₹{i.get('unit_price')}"
            for i in (r.get("items") or [])
        )
        w.writerow([
            (r.get("created_at") or "")[:19].replace("T", " "),
            r.get("bill_id") or "",
            r.get("category", ""),
            r.get("sub_category") or "",
            pay.get("merchant_name") or "",
            pay.get("merchant_upi") or "",
            pay.get("transaction_id") or "",
            items_str,
            f"{float(r.get('total', 0)):.2f}",
            pay.get("latitude") or "",
            pay.get("longitude") or "",
        ])
    buf.seek(0)
    fname = f"bill4pe-expenses-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@api.get("/expenses/{eid}")
async def get_expense(eid: str, user=Depends(get_current_user)):
    doc = await db.expenses.find_one({"id": eid, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Expense not found")
    return doc


# =================== Wallet ===================
BILL_FEE = 5.0

@api.get("/wallet")
async def wallet(user=Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "wallet_balance": 1})
    txns = await db.wallet_txns.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"balance": round(u.get("wallet_balance", 0.0), 2), "transactions": txns}

@api.post("/wallet/recharge")
async def recharge(body: WalletRecharge, user=Depends(get_current_user)):
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if body.amount > 10000:
        raise HTTPException(400, "Max recharge per txn is ₹10,000")
    new_bal = round(user.get("wallet_balance", 0.0) + body.amount, 2)
    await db.users.update_one({"id": user["id"]}, {"$set": {"wallet_balance": new_bal}})
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "type": "credit",
        "amount": body.amount, "reason": "Wallet recharge (mock)", "created_at": now_iso()
    })
    return {"balance": new_bal}


# =================== Favourites / Quick Re-stock ===================
FAV_ALLOWED_CATEGORIES = {"pantry", "grocery"}
FAV_MAX_PER_CATEGORY = 20

def _norm_fav_name(s: str) -> str:
    return (s or "").strip().lower()

@api.get("/favourites")
async def list_favourites(category: str, user=Depends(get_current_user)):
    if category not in FAV_ALLOWED_CATEGORIES:
        raise HTTPException(400, "Favourites available only for pantry/grocery")
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "favourites": 1})
    favs = ((u or {}).get("favourites") or {}).get(category, [])
    favs = sorted(favs, key=lambda x: x.get("last_used", ""), reverse=True)
    return {"category": category, "items": favs}

@api.post("/favourites")
async def save_favourites(body: FavouritesSave, user=Depends(get_current_user)):
    if body.category not in FAV_ALLOWED_CATEGORIES:
        raise HTTPException(400, "Favourites available only for pantry/grocery")
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "favourites": 1})
    existing = ((u or {}).get("favourites") or {}).get(body.category, [])
    by_name = { _norm_fav_name(it.get("name")): it for it in existing if it.get("name") }
    ts = now_iso()
    for it in body.items:
        nm = (it.name or "").strip()
        if not nm:
            continue
        key = _norm_fav_name(nm)
        by_name[key] = {
            "name": nm,
            "unit_price": float(it.unit_price or 0.0),
            "last_used": ts,
        }
    merged = sorted(by_name.values(), key=lambda x: x.get("last_used", ""), reverse=True)
    merged = merged[:FAV_MAX_PER_CATEGORY]
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {f"favourites.{body.category}": merged}},
    )
    return {"category": body.category, "items": merged}

@api.delete("/favourites")
async def delete_favourite(category: str, name: str, user=Depends(get_current_user)):
    if category not in FAV_ALLOWED_CATEGORIES:
        raise HTTPException(400, "Favourites available only for pantry/grocery")
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "favourites": 1})
    existing = ((u or {}).get("favourites") or {}).get(category, [])
    filtered = [it for it in existing if _norm_fav_name(it.get("name")) != _norm_fav_name(name)]
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {f"favourites.{category}": filtered}},
    )
    return {"category": category, "items": filtered}
def build_pdf_bytes(expense: dict, user: dict) -> bytes:
    user_name = (user or {}).get("name", "Customer")
    user_gstin = (user or {}).get("gstin")
    user_company = (user or {}).get("company_name") or (user or {}).get("corporate_name")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#0A1128")
    LIME = colors.HexColor("#D4FF00")
    LIGHT = colors.HexColor("#F4F5F7")
    BORDER = colors.HexColor("#E2E8F0")

    title_st = ParagraphStyle("title", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=22, textColor=NAVY, leading=26, spaceAfter=4)
    sub_st = ParagraphStyle("sub", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=9, textColor=colors.HexColor("#64748B"), leading=12)
    h2_st = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                           fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=4)
    body_st = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica",
                             fontSize=10, leading=14, textColor=colors.black)

    story = []
    # Build a QR for bill authenticity verification
    bill_id_str = expense.get('bill_id') or expense['id'][:8].upper()
    verify_url = f"https://www.bill4pe.com/verify/{bill_id_str}"
    qr_widget = QrCodeWidget(verify_url, barLevel='M')
    qr_bounds = qr_widget.getBounds()
    qr_w = qr_bounds[2] - qr_bounds[0]
    qr_h = qr_bounds[3] - qr_bounds[1]
    qr_size = 22 * mm
    qr_drawing = Drawing(qr_size, qr_size, transform=[qr_size / qr_w, 0, 0, qr_size / qr_h, 0, 0])
    qr_drawing.add(qr_widget)

    # Header with QR on the right
    header_tbl = Table([
        [Paragraph("<b>BILL4PE</b>", title_st),
         Paragraph(f"<b>OFFICIAL INVOICE</b><br/>"
                   f"Bill ID: {bill_id_str}<br/>"
                   f"Date: {expense['created_at'][:16].replace('T', ' ')}", sub_st),
         qr_drawing],
    ], colWidths=[70 * mm, 85 * mm, 25 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("An Intelligent Billing — Scan QR to verify authenticity", sub_st))
    story.append(Spacer(1, 14))

    pay = expense.get("payment", {}) or {}
    trip = pay.get("trip") or None
    stay = pay.get("stay") or None
    # Merchant info
    cat_label = (expense.get("category") or "").title() or "—"
    sub_label = expense.get("sub_category") or ""
    # Prefer trip/stay nature_of_business when present
    nature = None
    if trip:
        nature = trip.get("nature_of_business")
    if stay and not nature:
        nature = stay.get("nature_of_business")
    if not nature:
        nature = f"{cat_label}{' / ' + sub_label if sub_label else ''}"
    story.append(Paragraph("MERCHANT DETAILS", h2_st))
    m_tbl = Table([
        ["Merchant Name", pay.get("merchant_name") or "—"],
        ["Mobile", pay.get("merchant_mobile") or "—"],
        ["UPI ID", pay.get("merchant_upi") or "—"],
        ["Nature of Business", nature],
        ["Transaction ID", pay.get("transaction_id") or "—"],
        ["Payment Method", pay.get("payment_method", "UPI")],
        ["Location (Lat, Lng)", f"{pay.get('latitude', '—')}, {pay.get('longitude', '—')}"],
    ], colWidths=[45 * mm, 135 * mm])
    m_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(m_tbl)
    story.append(Spacer(1, 12))

    # Customer
    story.append(Paragraph("BILLED TO", h2_st))
    story.append(Paragraph(f"<b>{user_name}</b>", body_st))
    if user_company:
        story.append(Paragraph(user_company, sub_st))
    if user_gstin:
        story.append(Paragraph(f"<b>GSTIN:</b> {user_gstin}", sub_st))
    story.append(Paragraph(f"Expense Category: {expense.get('category')}"
                           f"{' / ' + expense['sub_category'] if expense.get('sub_category') else ''}", sub_st))
    story.append(Spacer(1, 12))

    # Items
    story.append(Paragraph("ITEMS", h2_st))
    rows = [["#", "Item", "Qty", "Unit Price (₹)", "Amount (₹)"]]
    for idx, it in enumerate(expense.get("items", []), 1):
        amt = float(it["quantity"]) * float(it["unit_price"])
        rows.append([str(idx), it["name"], f"{it['quantity']:g}",
                     f"{it['unit_price']:.2f}", f"{amt:.2f}"])

    subtotal = float(expense.get("total", 0) or 0)
    # Convenience Fee row (charged when bill is generated)
    show_fee = bool(expense.get("bill_generated"))
    fee_amt = float(BILL_FEE) if show_fee else 0.0
    grand_total = subtotal + fee_amt

    if show_fee:
        rows.append(["", "", "", "Subtotal", f"{subtotal:.2f}"])
        rows.append(["", "Convenience Fee (Bill Generation)", "", "", f"{fee_amt:.2f}"])
        rows.append(["", "", "", "GRAND TOTAL", f"₹ {grand_total:.2f}"])
    else:
        rows.append(["", "", "", "TOTAL", f"₹ {subtotal:.2f}"])

    items_tbl = Table(rows, colWidths=[12 * mm, 88 * mm, 18 * mm, 30 * mm, 32 * mm])
    base_style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if show_fee:
        # last row = Grand Total; -2 = Convenience Fee; -3 = Subtotal
        base_style += [
            ("INNERGRID", (0, 0), (-1, -4), 0.3, BORDER),
            ("FONTNAME", (3, -3), (-1, -3), "Helvetica-Bold"),
            ("BACKGROUND", (3, -3), (-1, -3), LIGHT),
            ("ALIGN", (1, -2), (1, -2), "LEFT"),
            ("FONTNAME", (1, -2), (1, -2), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, -2), (1, -2), colors.HexColor("#64748B")),
            ("BACKGROUND", (1, -2), (-1, -2), LIGHT),
            ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (3, -1), (-1, -1), LIME),
            ("TEXTCOLOR", (3, -1), (-1, -1), NAVY),
        ]
    else:
        base_style += [
            ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
            ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (3, -1), (-1, -1), LIME),
            ("TEXTCOLOR", (3, -1), (-1, -1), NAVY),
        ]
    items_tbl.setStyle(TableStyle(base_style))
    story.append(items_tbl)
    story.append(Spacer(1, 12))

    # Stay details (only for hotel category)
    if stay and (stay.get("hotel_name") or stay.get("check_in") or stay.get("nights")):
        story.append(Paragraph("STAY DETAILS", h2_st))
        try:
            rate = float(stay.get("per_night_rate") or 0)
        except Exception:
            rate = 0.0
        nights = stay.get("nights") or 0
        stay_tbl = Table([
            ["Hotel Name", stay.get("hotel_name") or "—"],
            ["Room Type", stay.get("room_type") or "—"],
            ["Check-in", stay.get("check_in") or "—"],
            ["Check-out", stay.get("check_out") or "—"],
            ["Number of Nights", f"{nights} night{'s' if nights != 1 else ''}"],
            ["Per-night Rate", f"₹ {rate:.2f}" if rate else "—"],
            ["Total Amount", f"₹ {float(expense.get('total', 0)):.2f}"],
        ], colWidths=[55 * mm, 125 * mm])
        stay_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
            ("BACKGROUND", (0, 0), (0, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("FONTNAME", (1, -1), (1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (1, -1), (1, -1), LIME),
            ("TEXTCOLOR", (1, -1), (1, -1), NAVY),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(stay_tbl)
        story.append(Spacer(1, 12))

    # Trip details (only for travel category)
    if trip and (trip.get("from_text") or trip.get("to_text") or trip.get("pickup_lat") is not None):
        story.append(Paragraph("TRIP DETAILS", h2_st))
        trip_tbl = Table([
            ["From", trip.get("from_text") or "—"],
            ["To", trip.get("to_text") or "—"],
            ["Amount", f"₹ {float(expense.get('total', 0)):.2f}"],
        ], colWidths=[45 * mm, 135 * mm])
        trip_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
            ("BACKGROUND", (0, 0), (0, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(trip_tbl)
        story.append(Spacer(1, 10))

        pick_lat = trip.get("pickup_lat")
        pick_lng = trip.get("pickup_lng")
        drop_lat = trip.get("drop_lat")
        drop_lng = trip.get("drop_lng")

        def fmt(v):
            return f"{v:.6f}" if isinstance(v, (int, float)) else "—"

        gps_tbl = Table([
            ["", "Latitude", "Longitude"],
            ["Picking Point", fmt(pick_lat), fmt(pick_lng)],
            ["Dropping Point", fmt(drop_lat), fmt(drop_lng)],
        ], colWidths=[50 * mm, 65 * mm, 65 * mm])
        gps_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 1), (0, -1), colors.HexColor("#64748B")),
            ("BACKGROUND", (0, 1), (0, -1), LIGHT),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(gps_tbl)
        story.append(Spacer(1, 12))

    # Notes (if any)
    note_txt = (expense.get("notes") or "").strip()
    if note_txt:
        story.append(Paragraph("NOTES", h2_st))
        story.append(Paragraph(note_txt.replace("\n", "<br/>"), body_st))
        story.append(Spacer(1, 12))

    # Footer
    story.append(Paragraph(
        "<b>Note:</b> This is a system-generated reimbursement invoice via BILL4PE. "
        "Items, prices and merchant details were captured at point of purchase. "
        "For corporate reimbursement, attach this invoice to your expense report.", sub_st))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Generated: {now_iso()[:19]} UTC | BILL4PE © 2026 | www.bill4pe.com", sub_st))

    doc.build(story)
    buf.seek(0)
    return buf.read()


@api.post("/bills/{eid}/generate")
async def generate_bill(eid: str, user=Depends(get_current_user)):
    """Charges ₹5 from wallet and marks the expense as bill-generated."""
    exp = await db.expenses.find_one({"id": eid, "user_id": user["id"]}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Expense not found")
    if exp.get("bill_generated"):
        return {"bill_id": exp.get("bill_id"), "message": "Already generated"}

    u = await db.users.find_one({"id": user["id"]})
    bal = float(u.get("wallet_balance", 0.0))
    if bal < BILL_FEE:
        raise HTTPException(402, f"Insufficient wallet balance. Need ₹{BILL_FEE}, have ₹{bal:.2f}")

    new_bal = round(bal - BILL_FEE, 2)
    bill_id = f"B4P-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{eid[:6].upper()}"
    await db.users.update_one({"id": user["id"]}, {"$set": {"wallet_balance": new_bal}})
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "type": "debit",
        "amount": BILL_FEE, "reason": f"Bill generation: {bill_id}", "created_at": now_iso()
    })
    await db.expenses.update_one({"id": eid}, {"$set": {
        "bill_generated": True, "bill_id": bill_id, "bill_generated_at": now_iso()
    }})
    return {"bill_id": bill_id, "wallet_balance": new_bal}


@api.get("/bills/{eid}/pdf")
async def get_bill_pdf(eid: str, token: Optional[str] = None, creds: HTTPAuthorizationCredentials = Depends(bearer)):
    # Allow auth via either Bearer header or ?token= (for direct download links)
    auth_token = None
    if creds:
        auth_token = creds.credentials
    elif token:
        auth_token = token
    if not auth_token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(auth_token, JWT_SECRET, algorithms=["HS256"])
        uid = payload["uid"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")

    exp = await db.expenses.find_one({"id": eid, "user_id": uid}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Expense not found")
    user = await db.users.find_one({"id": uid}, {"_id": 0})
    pdf_bytes = build_pdf_bytes(exp, user)
    fname = f"{exp.get('bill_id') or 'bill'}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


# =================== Contact form (landing page) ===================
@api.post("/contact")
async def contact(body: ContactMsg):
    await db.contact_messages.insert_one({
        "id": str(uuid.uuid4()), "name": body.name, "email": body.email,
        "message": body.message, "created_at": now_iso()
    })
    return {"ok": True}


# =================== Consolidated Expense Reports ===================
def build_report_pdf(report: dict, expenses: List[dict], user_name: str) -> bytes:
    """Build a multi-bill expense report PDF — a single sheet per company submission."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#050816")
    BRAND = colors.HexColor("#1F6FEB")
    LIGHT = colors.HexColor("#F4F5F7")
    BORDER = colors.HexColor("#E2E8F0")

    title_st = ParagraphStyle("title", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=22, textColor=NAVY, leading=26, spaceAfter=4)
    sub_st = ParagraphStyle("sub", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=9, textColor=colors.HexColor("#64748B"), leading=12)
    h2_st = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                           fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=4)

    story = []
    total = sum(float(e.get("total", 0)) for e in expenses)
    by_cat: dict = {}
    for e in expenses:
        c = e.get("category", "other")
        by_cat[c] = by_cat.get(c, 0) + float(e.get("total", 0))

    # Header
    header_tbl = Table([
        [Paragraph("<b>BILL4PE</b>", title_st),
         Paragraph(f"<b>EXPENSE REPORT</b><br/>"
                   f"Report ID: {report['id'][:8].upper()}<br/>"
                   f"Date: {report['created_at'][:16].replace('T', ' ')}<br/>"
                   f"Items: {len(expenses)}", sub_st)],
    ], colWidths=[90 * mm, 90 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, BRAND),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 4))
    story.append(Paragraph(report.get("title", "Expense Report"), title_st))
    story.append(Paragraph(f"Submitted by: <b>{user_name}</b>", sub_st))
    if report.get("notes"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<i>{report.get('notes')}</i>", sub_st))
    story.append(Spacer(1, 14))

    # Summary
    story.append(Paragraph("SUMMARY", h2_st))
    sum_rows = [["Category", "Amount (INR)"]]
    for c, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        sum_rows.append([c.title(), f"{v:.2f}"])
    sum_rows.append(["TOTAL", f"{total:.2f}"])
    sum_tbl = Table(sum_rows, colWidths=[120 * mm, 60 * mm])
    sum_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 16))

    # Line items
    story.append(Paragraph("LINE ITEMS", h2_st))
    rows = [["#", "Date", "Category", "Merchant", "Bill ID", "Amount (₹)"]]
    for idx, e in enumerate(expenses, 1):
        pay = e.get("payment") or {}
        rows.append([
            str(idx),
            (e.get("created_at") or "")[:16].replace("T", " "),
            (e.get("category", "") + ("/" + e["sub_category"] if e.get("sub_category") else "")).title(),
            (pay.get("merchant_name") or "—")[:24],
            (e.get("bill_id") or e["id"][:6].upper()),
            f"{float(e.get('total', 0)):.2f}",
        ])
    rows.append(["", "", "", "", "TOTAL", f"₹ {total:.2f}"])
    items_tbl = Table(rows, colWidths=[10 * mm, 28 * mm, 34 * mm, 48 * mm, 30 * mm, 30 * mm])
    items_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
        ("FONTNAME", (4, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (4, -1), (-1, -1), BRAND),
        ("TEXTCOLOR", (4, -1), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 20))

    story.append(Paragraph(
        "<b>Note:</b> This consolidated expense report is generated by BILL4PE based on "
        "individual UPI transactions captured at the point of purchase. Each line item links "
        "to its own audit-trail bill (merchant, UPI ID, transaction ID, geo and timestamp). "
        "Attach this report to your reimbursement claim.", sub_st))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Generated: {now_iso()[:19]} UTC | BILL4PE © 2026 | www.bill4pe.com", sub_st))

    doc.build(story)
    buf.seek(0)
    return buf.read()


@api.post("/reports")
async def create_report(body: ReportCreate, user=Depends(get_current_user)):
    if not body.expense_ids:
        raise HTTPException(400, "Select at least one expense")
    if len(body.expense_ids) > 200:
        raise HTTPException(400, "Max 200 expenses per report")
    expenses = await db.expenses.find(
        {"user_id": user["id"], "id": {"$in": body.expense_ids}}, {"_id": 0}
    ).to_list(200)
    if not expenses:
        raise HTTPException(404, "No matching expenses found")
    total = round(sum(float(e.get("total", 0)) for e in expenses), 2)
    rid = str(uuid.uuid4())
    doc = {
        "id": rid,
        "user_id": user["id"],
        "title": body.title.strip() or "Expense Report",
        "notes": body.notes,
        "expense_ids": [e["id"] for e in expenses],
        "expense_count": len(expenses),
        "total": total,
        "created_at": now_iso(),
    }
    await db.reports.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/reports")
async def list_reports(user=Depends(get_current_user)):
    reports = await db.reports.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"reports": reports}


@api.get("/reports/{rid}/pdf")
async def get_report_pdf(
    rid: str,
    token: Optional[str] = None,
    creds: HTTPAuthorizationCredentials = Depends(bearer),
):
    auth_token = creds.credentials if creds else token
    if not auth_token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(auth_token, JWT_SECRET, algorithms=["HS256"])
        uid = payload["uid"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")

    report = await db.reports.find_one({"id": rid, "user_id": uid}, {"_id": 0})
    if not report:
        raise HTTPException(404, "Report not found")
    expenses = await db.expenses.find(
        {"user_id": uid, "id": {"$in": report["expense_ids"]}}, {"_id": 0}
    ).to_list(200)
    expenses.sort(key=lambda e: e.get("created_at", ""), reverse=False)
    user = await db.users.find_one({"id": uid}, {"_id": 0})
    pdf_bytes = build_report_pdf(report, expenses, user.get("name", "Customer"))
    fname = f"report-{report['id'][:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@api.delete("/reports/{rid}")
async def delete_report(rid: str, user=Depends(get_current_user)):
    res = await db.reports.delete_one({"id": rid, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Report not found")
    return {"ok": True}


# =================== Health ===================
@api.get("/")
async def root():
    return {"app": "BILL4PE", "status": "ok", "time": now_iso()}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown():
    client.close()
