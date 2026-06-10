"""Corporate / B2B endpoints: company info, employee management, approvals, wallet."""
import secrets
import string
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.db import db
from core.models import (
    EmployeeCreate, EmployeeInvite, EmployeeUpdate,
    AcceptInviteReq, ApprovalDecision, WalletRecharge,
)
from core.security import get_current_user, hash_pw, make_token, now_iso

router = APIRouter(tags=["company"])


# ----------------- helpers -----------------

async def _require_admin(user):
    if user.get("role") != "admin" or not user.get("company_id"):
        raise HTTPException(403, "Only corporate admins can access this resource")
    company = await db.companies.find_one({"id": user["company_id"]}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")
    return company


async def _require_company_member(user):
    if not user.get("company_id"):
        raise HTTPException(403, "Not part of any company")
    return user


def _gen_password(n: int = 10) -> str:
    alpha = string.ascii_letters + string.digits
    return "".join(secrets.choice(alpha) for _ in range(n))


def _gen_token() -> str:
    return secrets.token_urlsafe(24)


def _public_employee(u: dict) -> dict:
    return {
        "id": u.get("id"),
        "name": u.get("name"),
        "email": u.get("email"),
        "phone": u.get("phone"),
        "department": u.get("department"),
        "designation": u.get("designation"),
        "employee_id": u.get("employee_id"),
        "monthly_cap": u.get("monthly_cap"),
        "is_active": u.get("is_active", True),
        "status": u.get("invite_status", "active"),  # active|pending_invite
        "created_at": u.get("created_at"),
    }


def _month_iso_prefix() -> str:
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m")


# ----------------- company info -----------------

@router.get("/company/me")
async def company_me(user=Depends(get_current_user)):
    company = await _require_admin(user)
    # KPIs
    emp_count = await db.users.count_documents({"company_id": company["id"], "role": "employee"})
    pending = await db.expenses.count_documents({
        "company_id": company["id"], "approval_status": "pending"
    })
    # spend this month
    prefix = _month_iso_prefix()
    cursor = db.expenses.find({
        "company_id": company["id"],
        "approval_status": {"$in": ["approved", "pending"]},
        "created_at": {"$regex": f"^{prefix}"},
    }, {"_id": 0, "total": 1})
    month_spend = 0.0
    async for e in cursor:
        month_spend += float(e.get("total", 0))
    return {
        "company": company,
        "stats": {
            "employees": emp_count,
            "pending_approvals": pending,
            "month_spend": round(month_spend, 2),
            "wallet_balance": round(company.get("wallet_balance", 0.0), 2),
        }
    }


# ----------------- employees -----------------

@router.get("/company/employees")
async def list_employees(user=Depends(get_current_user)):
    company = await _require_admin(user)
    cursor = db.users.find(
        {"company_id": company["id"], "role": {"$in": ["employee", "invited"]}},
        {"_id": 0, "password": 0},
    ).sort("created_at", -1)
    out = []
    async for u in cursor:
        out.append(_public_employee(u))
    return {"employees": out}


@router.post("/company/employees")
async def create_employee(body: EmployeeCreate, user=Depends(get_current_user)):
    company = await _require_admin(user)
    # employee limit check
    limit = company.get("employee_limit")
    if limit:
        count = await db.users.count_documents({
            "company_id": company["id"], "role": {"$in": ["employee", "invited"]}
        })
        if count >= int(limit):
            raise HTTPException(400, f"Employee limit reached ({limit}). Upgrade plan to add more.")

    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(400, "An account with this email already exists")

    temp_pw = (body.temp_password or "").strip() or _gen_password(10)
    uid = str(uuid.uuid4())
    phone = "".join(c for c in (body.phone or "") if c.isdigit())[-10:]
    doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name,
        "phone": f"+91{phone}" if phone else None,
        "password": hash_pw(temp_pw),
        "wallet_balance": 0.0,
        "user_type": "corporate",
        "role": "employee",
        "company_id": company["id"],
        "corporate_name": company.get("name"),
        "department": body.department,
        "designation": body.designation,
        "employee_id": body.employee_id,
        "monthly_cap": float(body.monthly_cap) if body.monthly_cap else None,
        "is_active": True,
        "invite_status": "active",
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    return {
        "employee": _public_employee(doc),
        "credentials": {"email": body.email.lower(), "temp_password": temp_pw},
    }


@router.post("/company/employees/invite")
async def invite_employee(body: EmployeeInvite, user=Depends(get_current_user)):
    company = await _require_admin(user)
    limit = company.get("employee_limit")
    if limit:
        count = await db.users.count_documents({
            "company_id": company["id"], "role": {"$in": ["employee", "invited"]}
        })
        if count >= int(limit):
            raise HTTPException(400, f"Employee limit reached ({limit}). Upgrade plan to add more.")

    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(400, "An account with this email already exists")

    invite_token = _gen_token()
    uid = str(uuid.uuid4())
    phone = "".join(c for c in (body.phone or "") if c.isdigit())[-10:]
    expires = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name,
        "phone": f"+91{phone}" if phone else None,
        "password": None,
        "wallet_balance": 0.0,
        "user_type": "corporate",
        "role": "invited",
        "company_id": company["id"],
        "corporate_name": company.get("name"),
        "department": body.department,
        "designation": body.designation,
        "employee_id": body.employee_id,
        "monthly_cap": float(body.monthly_cap) if body.monthly_cap else None,
        "is_active": True,
        "invite_status": "pending_invite",
        "invite_token": invite_token,
        "invite_expires": expires,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    # The frontend builds a magic link from this token: /accept-invite?token=...
    return {
        "employee": _public_employee(doc),
        "invite": {"token": invite_token, "expires": expires},
    }


@router.put("/company/employees/{eid}")
async def update_employee(eid: str, body: EmployeeUpdate, user=Depends(get_current_user)):
    company = await _require_admin(user)
    emp = await db.users.find_one({"id": eid, "company_id": company["id"]})
    if not emp:
        raise HTTPException(404, "Employee not found")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not patch:
        return _public_employee(emp)
    await db.users.update_one({"id": eid}, {"$set": patch})
    fresh = await db.users.find_one({"id": eid}, {"_id": 0, "password": 0})
    return _public_employee(fresh)


@router.delete("/company/employees/{eid}")
async def remove_employee(eid: str, user=Depends(get_current_user)):
    company = await _require_admin(user)
    emp = await db.users.find_one({"id": eid, "company_id": company["id"]})
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.get("role") == "admin":
        raise HTTPException(400, "Cannot remove the admin account")
    await db.users.delete_one({"id": eid})
    return {"ok": True}


# ----------------- accept invite (public) -----------------

@router.get("/company/invite/{token}")
async def invite_lookup(token: str):
    inv = await db.users.find_one({"invite_token": token, "role": "invited"}, {"_id": 0, "password": 0})
    if not inv:
        raise HTTPException(404, "Invite not found or already used")
    expires = inv.get("invite_expires")
    if expires and expires < now_iso():
        raise HTTPException(410, "Invite has expired")
    company = await db.companies.find_one({"id": inv["company_id"]}, {"_id": 0, "name": 1})
    return {
        "name": inv.get("name"),
        "email": inv.get("email"),
        "company_name": (company or {}).get("name", inv.get("corporate_name")),
    }


@router.post("/company/invite/accept")
async def invite_accept(body: AcceptInviteReq):
    inv = await db.users.find_one({"invite_token": body.token, "role": "invited"})
    if not inv:
        raise HTTPException(404, "Invite not found or already used")
    if (inv.get("invite_expires") or "") < now_iso():
        raise HTTPException(410, "Invite has expired")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    await db.users.update_one({"id": inv["id"]}, {
        "$set": {
            "password": hash_pw(body.password),
            "role": "employee",
            "invite_status": "active",
        },
        "$unset": {"invite_token": "", "invite_expires": ""}
    })
    fresh = await db.users.find_one({"id": inv["id"]}, {"_id": 0, "password": 0})
    return {"token": make_token(inv["id"]), "user": fresh}


# ----------------- approvals -----------------

@router.get("/company/approvals")
async def list_approvals(status: Optional[str] = "pending", user=Depends(get_current_user)):
    company = await _require_admin(user)
    q = {"company_id": company["id"]}
    if status in ("pending", "approved", "rejected"):
        q["approval_status"] = status
    cursor = db.expenses.find(q, {"_id": 0}).sort("created_at", -1).limit(200)
    items = []
    async for e in cursor:
        # attach submitter name for UI
        submitter = await db.users.find_one(
            {"id": e.get("user_id")}, {"_id": 0, "name": 1, "email": 1, "department": 1}
        )
        e["submitter"] = submitter or None
        items.append(e)
    return {"approvals": items}


@router.post("/company/approvals/{eid}/approve")
async def approve(eid: str, body: ApprovalDecision, user=Depends(get_current_user)):
    company = await _require_admin(user)
    exp = await db.expenses.find_one({"id": eid, "company_id": company["id"]})
    if not exp:
        raise HTTPException(404, "Expense not found")
    if exp.get("approval_status") != "pending":
        raise HTTPException(400, f"Already {exp.get('approval_status')}")
    await db.expenses.update_one({"id": eid}, {"$set": {
        "approval_status": "approved",
        "approval_actor_id": user["id"],
        "approval_actor_name": user.get("name"),
        "approval_note": (body.reason or "").strip() or None,
        "approval_at": now_iso(),
    }})
    return {"ok": True}


@router.post("/company/approvals/{eid}/reject")
async def reject(eid: str, body: ApprovalDecision, user=Depends(get_current_user)):
    company = await _require_admin(user)
    exp = await db.expenses.find_one({"id": eid, "company_id": company["id"]})
    if not exp:
        raise HTTPException(404, "Expense not found")
    if exp.get("approval_status") != "pending":
        raise HTTPException(400, f"Already {exp.get('approval_status')}")
    if not (body.reason or "").strip():
        raise HTTPException(400, "Rejection reason is required")
    await db.expenses.update_one({"id": eid}, {"$set": {
        "approval_status": "rejected",
        "approval_actor_id": user["id"],
        "approval_actor_name": user.get("name"),
        "approval_note": body.reason.strip(),
        "approval_at": now_iso(),
    }})
    return {"ok": True}


# ----------------- company wallet -----------------

@router.get("/company/wallet")
async def company_wallet(user=Depends(get_current_user)):
    company = await _require_admin(user)
    txns = await db.wallet_txns.find(
        {"company_id": company["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"balance": round(company.get("wallet_balance", 0.0), 2), "transactions": txns}


@router.post("/company/wallet/recharge")
async def company_recharge(body: WalletRecharge, user=Depends(get_current_user)):
    company = await _require_admin(user)
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if body.amount > 100000:
        raise HTTPException(400, "Max recharge per txn is ₹1,00,000")
    new_bal = round(float(company.get("wallet_balance", 0.0)) + body.amount, 2)
    await db.companies.update_one({"id": company["id"]}, {"$set": {"wallet_balance": new_bal}})
    await db.wallet_txns.insert_one({
        "id": str(uuid.uuid4()),
        "company_id": company["id"],
        "user_id": user["id"],
        "type": "credit",
        "amount": body.amount,
        "reason": "Company wallet recharge (mock)",
        "created_at": now_iso(),
    })
    return {"balance": new_bal}
