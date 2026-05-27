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

from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType


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

class PaymentInfo(BaseModel):
    merchant_name: Optional[str] = None
    merchant_upi: Optional[str] = None
    merchant_mobile: Optional[str] = None
    transaction_id: Optional[str] = None
    amount: float
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    payment_method: str = "UPI"  # GPay/PhonePe/Paytm/BharatPe/BHIM

class ExpenseCreate(BaseModel):
    category: str
    sub_category: Optional[str] = None
    items: List[ItemIn]
    payment: PaymentInfo
    notes: Optional[str] = None

class WalletRecharge(BaseModel):
    amount: float

class ContactMsg(BaseModel):
    name: str
    email: EmailStr
    message: str


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
    doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name,
        "password": hash_pw(body.password),
        "wallet_balance": 50.0,  # 50 INR welcome bonus
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    # Welcome wallet transaction
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "type": "credit",
        "amount": 50.0, "reason": "Welcome bonus", "created_at": now_iso()
    })
    token = make_token(uid)
    return {"token": token, "user": {"id": uid, "email": doc["email"], "name": doc["name"], "wallet_balance": 50.0}}

@api.post("/auth/login")
async def login(body: LoginReq):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not check_pw(body.password, user["password"]):
        raise HTTPException(401, "Invalid credentials")
    token = make_token(user["id"])
    return {"token": token, "user": {
        "id": user["id"], "email": user["email"], "name": user["name"],
        "wallet_balance": user.get("wallet_balance", 0.0),
    }}

@api.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


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
    if not user:
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
        user = user_doc
    token = make_token(user["id"])
    return {"token": token, "user": {
        "id": user["id"], "email": user["email"], "name": user["name"],
        "phone": user.get("phone"),
        "wallet_balance": user.get("wallet_balance", 0.0),
    }}


# =================== AI Image Detection ===================
FOOD_PROMPT = """You are an expert Indian food billing assistant. Analyze the food image and detect EVERY visible item.

For each item, return a JSON object with:
- "name": short Indian food name (e.g., "Roti", "Dal", "Rice", "Sabji", "Thali", "Paneer", "Water Bottle", "Snacks")
- "quantity": integer count visible
- "unit_price": reasonable INR price per unit (typical mid-range Indian restaurant pricing)

Return ONLY a strict JSON array. No markdown, no prose, no code fences. Example:
[{"name":"Roti","quantity":3,"unit_price":15},{"name":"Dal","quantity":1,"unit_price":50}]

If the image is not food, return an empty array []."""

GENERIC_PROMPT = """You are an expense bill assistant. Analyze the image (could be receipt, products, bill, items).

Detect each line item. Return ONLY a strict JSON array of {"name": str, "quantity": int, "unit_price": float (INR)}.
No markdown, no prose, no code fences. If nothing detectable, return []."""


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
        prompt = FOOD_PROMPT if category.lower() == "food" else GENERIC_PROMPT
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


# =================== Bill Generation ===================
def build_pdf_bytes(expense: dict, user_name: str) -> bytes:
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
    # Header
    header_tbl = Table([
        [Paragraph("<b>BILL4PE</b>", title_st),
         Paragraph(f"<b>OFFICIAL INVOICE</b><br/>"
                   f"Bill ID: {expense.get('bill_id') or expense['id'][:8].upper()}<br/>"
                   f"Date: {expense['created_at'][:10]}", sub_st)],
    ], colWidths=[90 * mm, 90 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Pay Your Bill — AI Powered Expense & Invoice Platform", sub_st))
    story.append(Spacer(1, 14))

    pay = expense.get("payment", {}) or {}
    # Merchant info
    story.append(Paragraph("MERCHANT DETAILS", h2_st))
    m_tbl = Table([
        ["Merchant Name", pay.get("merchant_name") or "—"],
        ["Merchant UPI ID", pay.get("merchant_upi") or "—"],
        ["Mobile", pay.get("merchant_mobile") or "—"],
        ["Business Type", expense.get("category", "—")],
        ["Transaction ID", pay.get("transaction_id") or "—"],
        ["Payment Method", pay.get("payment_method", "UPI")],
        ["Location", f"{pay.get('latitude', '—')}, {pay.get('longitude', '—')}"],
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
    rows.append(["", "", "", "TOTAL", f"₹ {float(expense['total']):.2f}"])
    items_tbl = Table(rows, colWidths=[12 * mm, 88 * mm, 18 * mm, 30 * mm, 32 * mm])
    items_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
        ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (3, -1), (-1, -1), LIME),
        ("TEXTCOLOR", (3, -1), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 18))

    # Footer
    story.append(Paragraph(
        "<b>Note:</b> This is a system-generated reimbursement invoice via BILL4PE. "
        "Items, prices and merchant details were captured at point of purchase. "
        "For corporate reimbursement, attach this invoice to your expense report.", sub_st))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Generated: {now_iso()[:19]} UTC | BILL4PE © 2026 | billforpay.com", sub_st))

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
    pdf_bytes = build_pdf_bytes(exp, user.get("name", "Customer"))
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
