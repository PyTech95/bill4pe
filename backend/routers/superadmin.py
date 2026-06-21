"""Super Admin (platform owner) endpoints.

Routes are guarded by `is_super_admin` flag on the user document. The Super
Admin can view platform-wide KPIs, manage users, companies, and tweak
subscription plans / trial status.
"""
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import get_current_user, now_iso


router = APIRouter(tags=["superadmin"], prefix="/superadmin")


async def require_super_admin(user=Depends(get_current_user)):
    if not user.get("is_super_admin"):
        raise HTTPException(403, "Super admin access required")
    return user


# ---------- Stats ----------

@router.get("/stats")
async def stats(_=Depends(require_super_admin)):
    users_total = await db.users.count_documents({})
    users_individual = await db.users.count_documents({"user_type": {"$ne": "corporate"}})
    users_corporate = await db.users.count_documents({"user_type": "corporate"})
    companies_total = await db.companies.count_documents({})
    expenses_total = await db.expenses.count_documents({})
    bills_total = await db.bills.count_documents({}) if "bills" in await db.list_collection_names() else 0

    # Revenue = sum of bill_fee across expenses (1% fee charged on bill generation)
    cursor = db.expenses.find({"bill_fee": {"$gt": 0}}, {"_id": 0, "bill_fee": 1})
    platform_revenue = 0.0
    async for e in cursor:
        platform_revenue += float(e.get("bill_fee") or 0)

    # Companies on trial vs active
    trial_count = await db.companies.count_documents({"subscription_status": "trial"})
    active_count = await db.companies.count_documents({"subscription_status": "active"})

    # Last 7 days new users
    from datetime import timedelta
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    new_users_7d = await db.users.count_documents({"created_at": {"$gte": seven_days_ago}})

    return {
        "users": {
            "total": users_total,
            "individual": users_individual,
            "corporate": users_corporate,
            "new_last_7d": new_users_7d,
        },
        "companies": {
            "total": companies_total,
            "trial": trial_count,
            "active": active_count,
        },
        "activity": {
            "expenses_total": expenses_total,
            "bills_total": bills_total,
        },
        "revenue": {
            "platform_fees_collected": round(platform_revenue, 2),
        },
    }


# ---------- Users ----------

@router.get("/users")
async def list_users(
    q: Optional[str] = None,
    user_type: Optional[str] = None,
    limit: int = 100,
    _=Depends(require_super_admin),
):
    query = {}
    if q:
        query["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
        ]
    if user_type in ("individual", "corporate"):
        if user_type == "corporate":
            query["user_type"] = "corporate"
        else:
            query["user_type"] = {"$ne": "corporate"}
    cursor = db.users.find(query, {"_id": 0, "password": 0}).sort("created_at", -1).limit(int(limit))
    users = []
    async for u in cursor:
        users.append(u)
    return {"users": users}


class WalletAdjust(BaseModel):
    amount: float
    reason: Optional[str] = "Super admin adjustment"


@router.post("/users/{uid}/wallet/credit")
async def credit_user_wallet(uid: str, body: WalletAdjust, admin=Depends(require_super_admin)):
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    new_bal = round(float(target.get("wallet_balance", 0.0)) + body.amount, 2)
    await db.users.update_one({"id": uid}, {"$set": {"wallet_balance": new_bal}})
    import uuid as _uuid
    await db.wallet_txns.insert_one({
        "id": str(_uuid.uuid4()), "user_id": uid, "type": "credit",
        "amount": body.amount, "reason": body.reason or "Super admin credit",
        "created_at": now_iso(),
    })
    return {"balance": new_bal}


class ToggleActive(BaseModel):
    is_active: bool


@router.post("/users/{uid}/toggle-active")
async def toggle_user_active(uid: str, body: ToggleActive, _=Depends(require_super_admin)):
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("is_super_admin"):
        raise HTTPException(400, "Cannot disable a super admin")
    await db.users.update_one({"id": uid}, {"$set": {"is_active": body.is_active}})
    return {"ok": True, "is_active": body.is_active}


@router.delete("/users/{uid}")
async def delete_user(uid: str, _=Depends(require_super_admin)):
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("is_super_admin"):
        raise HTTPException(400, "Cannot delete a super admin")
    await db.expenses.delete_many({"user_id": uid})
    await db.wallet_txns.delete_many({"user_id": uid})
    await db.reports.delete_many({"user_id": uid})
    await db.users.delete_one({"id": uid})
    return {"ok": True}


# ---------- Companies ----------

@router.get("/companies")
async def list_companies(_=Depends(require_super_admin)):
    cursor = db.companies.find({}, {"_id": 0}).sort("created_at", -1)
    companies = []
    async for c in cursor:
        emp_count = await db.users.count_documents({
            "company_id": c["id"], "role": {"$in": ["employee", "invited"]}
        })
        c["employee_count"] = emp_count
        companies.append(c)
    return {"companies": companies}


class CompanyPatch(BaseModel):
    subscription_plan: Optional[str] = None
    subscription_status: Optional[str] = None  # trial | active | suspended | cancelled
    employee_limit: Optional[int] = None
    trial_ends_at: Optional[str] = None  # ISO date


@router.put("/companies/{cid}")
async def update_company(cid: str, body: CompanyPatch, _=Depends(require_super_admin)):
    company = await db.companies.find_one({"id": cid})
    if not company:
        raise HTTPException(404, "Company not found")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if patch:
        await db.companies.update_one({"id": cid}, {"$set": patch})
    fresh = await db.companies.find_one({"id": cid}, {"_id": 0})
    return fresh


class CompanyWalletCredit(BaseModel):
    amount: float
    reason: Optional[str] = "Super admin credit"


@router.post("/companies/{cid}/wallet/credit")
async def credit_company_wallet(cid: str, body: CompanyWalletCredit, admin=Depends(require_super_admin)):
    company = await db.companies.find_one({"id": cid})
    if not company:
        raise HTTPException(404, "Company not found")
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    new_bal = round(float(company.get("wallet_balance", 0.0)) + body.amount, 2)
    await db.companies.update_one({"id": cid}, {"$set": {"wallet_balance": new_bal}})
    import uuid as _uuid
    await db.wallet_txns.insert_one({
        "id": str(_uuid.uuid4()), "company_id": cid, "user_id": admin["id"],
        "type": "credit", "amount": body.amount,
        "reason": body.reason or "Super admin credit",
        "created_at": now_iso(),
    })
    return {"balance": new_bal}
