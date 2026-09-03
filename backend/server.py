from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
import jwt
from bson import ObjectId
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_ALGORITHM = "HS256"
LOCK_THRESHOLD = 5
LOCK_MINUTES = 15

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bill4pe")

app = FastAPI()
api = APIRouter(prefix="/api")


def utcnow():
    return datetime.now(timezone.utc)


def pub(doc):
    doc["id"] = str(doc.pop("_id"))
    return doc


# ---------------- Auth helpers ----------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "exp": utcnow() + timedelta(minutes=15), "type": "access"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": utcnow() + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, user_id: str, email: str):
    response.set_cookie("access_token", create_access_token(user_id, email), httponly=True, secure=True, samesite="none", max_age=900, path="/")
    response.set_cookie("refresh_token", create_refresh_token(user_id), httponly=True, secure=True, samesite="none", max_age=604800, path="/")


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": str(user["_id"]), "email": user["email"], "name": user.get("name", ""), "role": user.get("role", "owner")}


async def seed_admin():
    admin_email = os.environ["ADMIN_EMAIL"].strip().lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Owner",
            "role": "admin",
            "created_at": utcnow(),
        })
        logger.info("Seeded admin user %s", admin_email)
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        logger.info("Updated admin password for %s", admin_email)


# ---------------- Auth schemas ----------------

class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    role: str = "owner"


class LoginIn(BaseModel):
    email: str
    password: str


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    password: str


# ---------------- Auth routes ----------------

@api.get("/")
async def root():
    return {"message": "bill4pe API", "status": "ok"}


@api.post("/auth/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    role = body.role if body.role in ("owner", "staff") else "owner"
    doc = {"name": body.name.strip(), "email": email, "password_hash": hash_password(body.password), "role": role, "created_at": utcnow()}
    res = await db.users.insert_one(doc)
    set_auth_cookies(response, str(res.inserted_id), email)
    return {"id": str(res.inserted_id), "name": doc["name"], "email": email, "role": role}


@api.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    identifier = f"{request.client.host}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= LOCK_THRESHOLD:
        last = attempt.get("last_attempt")
        if last and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last and utcnow() - last < timedelta(minutes=LOCK_MINUTES):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
        await db.login_attempts.delete_one({"identifier": identifier})
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"last_attempt": utcnow()}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": identifier})
    set_auth_cookies(response, str(user["_id"]), email)
    return {"id": str(user["_id"]), "name": user.get("name", ""), "email": email, "role": user.get("role", "owner")}


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    response.set_cookie("access_token", create_access_token(str(user["_id"]), user["email"]), httponly=True, secure=True, samesite="none", max_age=900, path="/")
    return {"ok": True}


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotIn):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token, "email": email, "used": False,
            "expires_at": utcnow() + timedelta(hours=1), "created_at": utcnow(),
        })
        logger.info("Password reset link for %s: /reset-password?token=%s", email, token)
    return {"ok": True, "message": "If the email exists, a reset link has been generated."}


@api.post("/auth/reset-password")
async def reset_password(body: ResetIn):
    rec = await db.password_reset_tokens.find_one({"token": body.token})
    if not rec or rec.get("used"):
        raise HTTPException(status_code=400, detail="Invalid or used reset token")
    exp = rec["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if utcnow() > exp:
        raise HTTPException(status_code=400, detail="Reset token expired")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    await db.users.update_one({"email": rec["email"]}, {"$set": {"password_hash": hash_password(body.password)}})
    await db.password_reset_tokens.update_one({"token": body.token}, {"$set": {"used": True}})
    return {"ok": True}


# ---------------- Settings ----------------

SETTINGS_DEFAULTS = {
    "business_name": "", "trade_name": "", "gstin": "", "state": "", "address": "",
    "upi_id": "", "bank_account": "", "bank_ifsc": "", "bank_branch": "",
    "invoice_prefix": "INV", "terms": "Payment due within 14 days.",
}


class SettingsIn(BaseModel):
    business_name: str = ""
    trade_name: str = ""
    gstin: str = ""
    state: str = ""
    address: str = ""
    upi_id: str = ""
    bank_account: str = ""
    bank_ifsc: str = ""
    bank_branch: str = ""
    invoice_prefix: str = "INV"
    terms: str = ""


@api.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    doc = await db.settings.find_one({"user_id": user["id"]})
    if not doc:
        return dict(SETTINGS_DEFAULTS)
    doc.pop("_id", None)
    doc.pop("user_id", None)
    return {**SETTINGS_DEFAULTS, **doc}


@api.put("/settings")
async def put_settings(body: SettingsIn, user: dict = Depends(get_current_user)):
    data = {k: v.strip() if isinstance(v, str) else v for k, v in body.model_dump().items()}
    data["invoice_prefix"] = (data.get("invoice_prefix") or "INV").upper()
    await db.settings.update_one({"user_id": user["id"]}, {"$set": data}, upsert=True)
    return await get_settings(user)


# ---------------- Customers ----------------

class CustomerIn(BaseModel):
    business_name: str
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    state: str = ""
    gstin: str = ""


def serialize_customer(doc, outstanding=0.0, invoice_count=0):
    pub(doc)
    doc["outstanding"] = round(outstanding, 2)
    doc["invoice_count"] = invoice_count
    return doc


@api.get("/customers")
async def list_customers(user: dict = Depends(get_current_user)):
    customers = await db.customers.find({"user_id": user["id"]}).sort("created_at", -1).to_list(5000)
    invoices = await db.invoices.find({"user_id": user["id"]}, {"customer_id": 1, "total": 1, "paid_amount": 1, "status": 1, "due_date": 1}).to_list(10000)
    agg = {}
    for inv in invoices:
        a = agg.setdefault(inv["customer_id"], {"count": 0, "outstanding": 0.0})
        a["count"] += 1
        if eff_status(inv) in ("pending", "overdue"):
            a["outstanding"] += inv["total"] - inv.get("paid_amount", 0)
    return [serialize_customer(c, agg.get(str(c["_id"]), {}).get("outstanding", 0.0), agg.get(str(c["_id"]), {}).get("count", 0)) for c in customers]


@api.post("/customers")
async def create_customer(body: CustomerIn, user: dict = Depends(get_current_user)):
    if not body.business_name.strip():
        raise HTTPException(status_code=400, detail="Business name is required")
    doc = {k: v.strip() if isinstance(v, str) else v for k, v in body.model_dump().items()}
    doc["user_id"] = user["id"]
    doc["created_at"] = utcnow()
    res = await db.customers.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize_customer(doc)


@api.put("/customers/{customer_id}")
async def update_customer(customer_id: str, body: CustomerIn, user: dict = Depends(get_current_user)):
    data = {k: v.strip() if isinstance(v, str) else v for k, v in body.model_dump().items()}
    res = await db.customers.update_one({"_id": ObjectId(customer_id), "user_id": user["id"]}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    doc = await db.customers.find_one({"_id": ObjectId(customer_id)})
    return serialize_customer(doc)


@api.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, user: dict = Depends(get_current_user)):
    res = await db.customers.delete_one({"_id": ObjectId(customer_id), "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"ok": True}


# ---------------- Invoices ----------------

class ItemIn(BaseModel):
    description: str
    hsn: str = ""
    qty: float = 1
    rate: float = 0
    gst_rate: float = 18


class InvoiceIn(BaseModel):
    customer_id: str
    invoice_number: Optional[str] = None
    issue_date: str
    due_date: str
    items: List[ItemIn]
    discount_pct: float = 0
    inter_state: bool = False
    notes: str = ""
    status: str = "draft"


class PaymentIn(BaseModel):
    amount: float
    mode: str = "upi"
    reference: str = ""
    note: str = ""


def compute_totals(items, discount_pct, inter_state):
    subtotal = 0.0
    tax = 0.0
    for it in items:
        net = it["qty"] * it["rate"] * (1 - discount_pct / 100)
        subtotal += net
        tax += net * it["gst_rate"] / 100
    subtotal = round(subtotal, 2)
    tax = round(tax, 2)
    total = round(subtotal + tax, 2)
    if inter_state:
        return subtotal, 0.0, 0.0, tax, total
    half = round(tax / 2, 2)
    return subtotal, half, round(tax - half, 2), 0.0, total


def eff_status(inv) -> str:
    if inv.get("status") == "paid" or inv.get("paid_amount", 0) >= inv.get("total", 0) > 0:
        return "paid"
    if inv.get("status") == "draft":
        return "draft"
    today = utcnow().date().isoformat()
    if inv.get("due_date", "") < today:
        return "overdue"
    return "pending"


def serialize_invoice(inv):
    pub(inv)
    inv["status"] = eff_status(inv)
    inv["balance_due"] = round(inv["total"] - inv.get("paid_amount", 0), 2)
    return inv


async def next_invoice_number(user_id: str, settings: dict) -> str:
    prefix = ((settings or {}).get("invoice_prefix") or "INV").strip().upper() or "INV"
    n = await db.invoices.count_documents({"user_id": user_id}) + 1
    while await db.invoices.find_one({"user_id": user_id, "invoice_number": f"{prefix}-{n:04d}"}):
        n += 1
    return f"{prefix}-{n:04d}"


@api.get("/invoices")
async def list_invoices(status: str = "", search: str = "", user: dict = Depends(get_current_user)):
    invs = await db.invoices.find({"user_id": user["id"]}).sort("created_at", -1).to_list(5000)
    out = [serialize_invoice(i) for i in invs]
    if status and status != "all":
        out = [i for i in out if i["status"] == status]
    if search:
        s = search.lower()
        out = [i for i in out if s in i.get("invoice_number", "").lower() or s in i.get("customer_name", "").lower()]
    return out


@api.post("/invoices")
async def create_invoice(body: InvoiceIn, user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"_id": ObjectId(body.customer_id), "user_id": user["id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    items = [it.model_dump() for it in body.items if it.description.strip()]
    if not items:
        raise HTTPException(status_code=400, detail="At least one line item is required")
    settings = await db.settings.find_one({"user_id": user["id"]})
    number = (body.invoice_number or "").strip() or await next_invoice_number(user["id"], settings)
    if await db.invoices.find_one({"user_id": user["id"], "invoice_number": number}):
        raise HTTPException(status_code=400, detail="Invoice number already exists")
    subtotal, cgst, sgst, igst, total = compute_totals(items, body.discount_pct, body.inter_state)
    doc = {
        "user_id": user["id"],
        "invoice_number": number,
        "customer_id": body.customer_id,
        "customer_name": customer["business_name"],
        "customer_gstin": customer.get("gstin", ""),
        "customer_state": customer.get("state", ""),
        "customer_address": customer.get("address", ""),
        "issue_date": body.issue_date,
        "due_date": body.due_date,
        "items": items,
        "discount_pct": body.discount_pct,
        "inter_state": body.inter_state,
        "subtotal": subtotal, "cgst": cgst, "sgst": sgst, "igst": igst, "total": total,
        "paid_amount": 0.0,
        "payments": [],
        "notes": body.notes.strip(),
        "status": "sent" if body.status == "sent" else "draft",
        "created_at": utcnow(),
    }
    res = await db.invoices.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize_invoice(doc)


@api.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["id"]})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return serialize_invoice(inv)


@api.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, body: InvoiceIn, user: dict = Depends(get_current_user)):
    inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["id"]})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if eff_status(inv) == "paid":
        raise HTTPException(status_code=400, detail="Paid invoices cannot be edited")
    customer = await db.customers.find_one({"_id": ObjectId(body.customer_id), "user_id": user["id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    items = [it.model_dump() for it in body.items if it.description.strip()]
    if not items:
        raise HTTPException(status_code=400, detail="At least one line item is required")
    number = (body.invoice_number or "").strip() or inv["invoice_number"]
    if number != inv["invoice_number"] and await db.invoices.find_one({"user_id": user["id"], "invoice_number": number}):
        raise HTTPException(status_code=400, detail="Invoice number already exists")
    subtotal, cgst, sgst, igst, total = compute_totals(items, body.discount_pct, body.inter_state)
    paid = inv.get("paid_amount", 0)
    status = "paid" if paid >= total and total > 0 else ("sent" if body.status == "sent" else "draft")
    await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {
        "invoice_number": number, "customer_id": body.customer_id,
        "customer_name": customer["business_name"], "customer_gstin": customer.get("gstin", ""),
        "customer_state": customer.get("state", ""), "customer_address": customer.get("address", ""),
        "issue_date": body.issue_date, "due_date": body.due_date, "items": items,
        "discount_pct": body.discount_pct, "inter_state": body.inter_state,
        "subtotal": subtotal, "cgst": cgst, "sgst": sgst, "igst": igst, "total": total,
        "notes": body.notes.strip(), "status": status,
    }})
    updated = await db.invoices.find_one({"_id": inv["_id"]})
    return serialize_invoice(updated)


@api.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    res = await db.invoices.delete_one({"_id": ObjectId(invoice_id), "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"ok": True}


@api.post("/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    res = await db.invoices.update_one(
        {"_id": ObjectId(invoice_id), "user_id": user["id"], "status": "draft"},
        {"$set": {"status": "sent"}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=400, detail="Invoice not found or already sent")
    inv = await db.invoices.find_one({"_id": ObjectId(invoice_id)})
    return serialize_invoice(inv)


@api.post("/invoices/{invoice_id}/payments")
async def record_payment(invoice_id: str, body: PaymentIn, user: dict = Depends(get_current_user)):
    inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["id"]})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    amount = round(body.amount, 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    remaining = round(inv["total"] - inv.get("paid_amount", 0), 2)
    if amount > remaining + 0.01:
        raise HTTPException(status_code=400, detail=f"Amount exceeds balance due ({remaining})")
    reference = body.reference.strip()
    if reference and any(p.get("reference") == reference for p in inv.get("payments", [])):
        raise HTTPException(status_code=409, detail="Duplicate payment reference")
    payment = {
        "id": str(ObjectId()), "amount": amount,
        "mode": body.mode if body.mode in ("upi", "neft", "cash", "cheque", "other") else "other",
        "reference": reference, "note": body.note.strip(), "date": utcnow(),
    }
    paid = round(inv.get("paid_amount", 0) + amount, 2)
    status = "paid" if paid >= inv["total"] - 0.001 else ("sent" if inv["status"] == "draft" else inv["status"])
    await db.invoices.update_one({"_id": inv["_id"]}, {"$push": {"payments": payment}, "$set": {"paid_amount": paid, "status": status}})
    logger.info("Payment recorded invoice=%s amount=%s mode=%s ref=%s", inv["invoice_number"], amount, payment["mode"], reference)
    updated = await db.invoices.find_one({"_id": inv["_id"]})
    return serialize_invoice(updated)


# ---------------- Dashboard ----------------

@api.get("/dashboard/stats")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    invs = await db.invoices.find({"user_id": user["id"]}).to_list(10000)
    total_invoiced = collected = pending = overdue = 0.0
    counts = {"draft": 0, "pending": 0, "paid": 0, "overdue": 0}
    monthly = {}
    per_customer = {}
    for inv in invs:
        st = eff_status(inv)
        counts[st] += 1
        if st == "draft":
            continue
        total_invoiced += inv["total"]
        collected += inv.get("paid_amount", 0)
        due = inv["total"] - inv.get("paid_amount", 0)
        if st == "pending":
            pending += due
        elif st == "overdue":
            overdue += due
        m = inv.get("issue_date", "")[:7]
        if m:
            monthly[m] = monthly.get(m, 0) + inv["total"]
        c = per_customer.setdefault(inv["customer_id"], {"name": inv.get("customer_name", ""), "total": 0.0})
        c["total"] += inv["total"]
    series = []
    d = utcnow().date().replace(day=1)
    months = []
    for _ in range(6):
        months.append(d)
        d = (d - timedelta(days=1)).replace(day=1)
    for md in reversed(months):
        key = md.isoformat()[:7]
        series.append({"month": md.strftime("%b"), "total": round(monthly.get(key, 0), 2)})
    recent = sorted(invs, key=lambda i: i.get("created_at", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)[:5]
    top = sorted(per_customer.values(), key=lambda c: c["total"], reverse=True)[:5]
    return {
        "total_invoiced": round(total_invoiced, 2),
        "collected": round(collected, 2),
        "pending": round(pending, 2),
        "overdue": round(overdue, 2),
        "counts": counts,
        "monthly": series,
        "recent_invoices": [serialize_invoice(i) for i in recent],
        "top_customers": top,
    }


app.include_router(api)

origins = [o for o in [os.environ.get("FRONTEND_URL"), "http://localhost:3000"] if o]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.customers.create_index("user_id")
    await db.invoices.create_index([("user_id", 1), ("created_at", -1)])
    await seed_admin()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
