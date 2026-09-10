"""Email+password registration/login, profile management, phone OTP (demo)."""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException

from core.config import DEMO_OTP, logger
from core.db import db
from core.models import (
    RegisterReq, LoginReq, ProfileUpdate, PasswordChange,
    OtpRequestReq, OtpVerifyReq, EmployeeLoginReq,
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
        "wallet_pin_set": False,
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
    fresh = await db.users.find_one(
        {"id": uid}, {"_id": 0, "password": 0, "wallet_pin_hash": 0}
    )
    token = make_token(uid)
    return {"token": token, "user": fresh}


@router.post("/auth/login")
async def login(body: LoginReq):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not check_pw(body.password, user["password"]):
        raise HTTPException(401, "Invalid credentials")
    token = make_token(user["id"])
    fresh = await db.users.find_one(
        {"id": user["id"]}, {"_id": 0, "password": 0, "wallet_pin_hash": 0}
    )
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
    updated = await db.users.find_one(
        {"id": user["id"]}, {"_id": 0, "password": 0, "wallet_pin_hash": 0}
    )
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


# ---- Phone OTP (MSG91 live mode or explicit development demo mode) ----

def _norm_phone(p: str) -> str:
    return "".join(c for c in (p or "") if c.isdigit())[-10:]


@router.post("/auth/otp/request")
async def otp_request(body: OtpRequestReq):
    phone = _norm_phone(body.phone)
    if len(phone) != 10:
        raise HTTPException(400, "Invalid 10-digit phone number")

    # Production/live OTP requires a real email for first-time signup. Demo mode
    # stays backwards-compatible for local automated testing only.
    from services.otp import send_otp, is_demo
    existing = await db.users.find_one({"phone": f"+91{phone}"})
    if not existing and not body.email and not is_demo():
        raise HTTPException(400, "Email is required for first-time phone signup")
    if not existing and body.email:
        by_email = await db.users.find_one({"email": str(body.email).lower()})
        if by_email:
            raise HTTPException(400, "This email already has an account. Sign in with email and add/verify your phone from Profile.")

    try:
        return await send_otp(phone)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.post("/auth/otp/verify")
async def otp_verify(body: OtpVerifyReq):
    phone = _norm_phone(body.phone)
    if len(phone) != 10:
        raise HTTPException(400, "Invalid phone number")
    if len((body.otp or "").strip()) != 6 or not (body.otp or "").strip().isdigit():
        raise HTTPException(401, "Invalid OTP")

    from services.otp import verify_otp, is_demo
    try:
        valid = await verify_otp(phone, body.otp)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    if not valid:
        raise HTTPException(401, "Invalid or expired OTP")

    user = await db.users.find_one({"phone": f"+91{phone}"})
    is_new = user is None
    if is_new:
        if not body.email and not is_demo():
            raise HTTPException(400, "Email is required for first-time phone signup")
        email = str(body.email).lower() if body.email else f"dev-{phone}@phone.bill4pe.local"
        if await db.users.find_one({"email": email}):
            raise HTTPException(400, "Email already registered")
        uid = str(uuid.uuid4())
        user_doc = {
            "id": uid,
            "email": email,
            "phone": f"+91{phone}",
            "phone_verified": True,
            "name": (body.name or f"User {phone[-4:]}").strip(),
            "password": hash_pw(str(uuid.uuid4())),
            "wallet_balance": 50.0,
            "wallet_pin_set": False,
            "auth_provider": "phone",
            "user_type": "individual",
            "role": "individual",
            "company_id": None,
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
    else:
        await db.users.update_one({"id": user["id"]}, {"$set": {"phone_verified": True}})
        user = await db.users.find_one({"id": user["id"]})

    token = make_token(user["id"])
    fresh = await db.users.find_one(
        {"id": user["id"]}, {"_id": 0, "password": 0, "wallet_pin_hash": 0}
    )
    return {"token": token, "user": fresh}


@router.post("/auth/employee-login")
async def employee_login(body: EmployeeLoginReq):
    """Corporate employee login using a memorable 6-digit employee code + 6-digit PIN.

    Email/password login remains available for backwards compatibility.
    """
    code = "".join(c for c in (body.employee_code or "") if c.isdigit())
    pin = (body.pin or "").strip()
    if len(code) != 6 or len(pin) != 6 or not pin.isdigit():
        raise HTTPException(401, "Enter a valid 6-digit employee code and 6-digit PIN")
    user = await db.users.find_one({
        "employee_code": code, "role": "employee", "user_type": "corporate",
    })
    if not user or user.get("is_active", True) is False or not user.get("password") or not check_pw(pin, user["password"]):
        raise HTTPException(401, "Invalid employee code or PIN")
    token = make_token(user["id"])
    fresh = await db.users.find_one(
        {"id": user["id"]}, {"_id": 0, "password": 0, "wallet_pin_hash": 0}
    )
    return {"token": token, "user": fresh}
