"""Email+password registration/login, profile management, phone OTP (demo)."""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException

from core.config import DEMO_OTP, logger
from core.db import db
from core.models import (
    RegisterReq, LoginReq, ProfileUpdate, PasswordChange,
    OtpRequestReq, OtpVerifyReq,
)
from core.security import (
    get_current_user, hash_pw, check_pw, make_token, now_iso,
)
from services.referrals import apply_referral, ensure_referral_code

router = APIRouter(tags=["auth"])


@router.post("/auth/register")
async def register(body: RegisterReq):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(400, "Email already registered")
    uid = str(uuid.uuid4())
    user_type = (body.user_type or "individual").lower().strip()
    if user_type not in ("individual", "corporate"):
        user_type = "individual"

    company_id = None
    if user_type == "corporate":
        company_id = str(uuid.uuid4())
        await db.companies.insert_one({
            "id": company_id,
            "name": (body.corporate_name or "").strip() or "My Company",
            "admin_id": uid,
            "wallet_balance": 0.0,
            "subscription_plan": (body.subscription_plan or "").strip() or None,
            "employee_limit": int(body.employee_limit) if body.employee_limit else None,
            "subscription_status": "trial",
            "created_at": now_iso(),
        })

    doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name,
        "password": hash_pw(body.password),
        "wallet_balance": 50.0,  # 50 INR welcome bonus
        "user_type": user_type,
        "role": "admin" if user_type == "corporate" else "individual",
        "company_id": company_id,
        "corporate_name": (body.corporate_name or "").strip() if user_type == "corporate" else None,
        "subscription_plan": (body.subscription_plan or "").strip() if user_type == "corporate" else None,
        "employee_limit": int(body.employee_limit) if (user_type == "corporate" and body.employee_limit) else None,
        "subscription_status": "trial" if user_type == "corporate" else None,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "type": "credit",
        "amount": 50.0, "reason": "Welcome bonus", "created_at": now_iso()
    })
    await apply_referral(uid, body.referrer_code)
    await ensure_referral_code(uid)
    fresh = await db.users.find_one({"id": uid}, {"_id": 0, "password": 0})
    token = make_token(uid)
    return {"token": token, "user": fresh}


@router.post("/auth/login")
async def login(body: LoginReq):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not check_pw(body.password, user["password"]):
        raise HTTPException(401, "Invalid credentials")
    token = make_token(user["id"])
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return {"token": token, "user": fresh}


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


@router.put("/auth/me")
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
            if not re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", gstin):
                raise HTTPException(400, "Invalid GSTIN format (must be 15 chars, e.g. 27ABCDE1234F1Z5)")
        patch["gstin"] = gstin or None
    if body.company_name is not None:
        patch["company_name"] = (body.company_name or "").strip() or None
    if patch:
        await db.users.update_one({"id": user["id"]}, {"$set": patch})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return updated


@router.post("/auth/change-password")
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


@router.delete("/auth/me")
async def delete_account(user=Depends(get_current_user)):
    uid = user["id"]
    await db.expenses.delete_many({"user_id": uid})
    await db.wallet_txns.delete_many({"user_id": uid})
    await db.reports.delete_many({"user_id": uid})
    await db.users.delete_one({"id": uid})
    return {"ok": True}


# ---- Phone OTP (demo mode — universal OTP 123456) ----

def _norm_phone(p: str) -> str:
    return "".join(c for c in (p or "") if c.isdigit())[-10:]


@router.post("/auth/otp/request")
async def otp_request(body: OtpRequestReq):
    phone = _norm_phone(body.phone)
    if len(phone) != 10:
        raise HTTPException(400, "Invalid 10-digit phone number")
    logger.info(f"OTP requested for +91{phone}. Demo OTP: {DEMO_OTP}")
    return {"ok": True, "demo_hint": "Use OTP 123456 for any number (demo mode)"}


@router.post("/auth/otp/verify")
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
            "password": hash_pw(str(uuid.uuid4())),
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
