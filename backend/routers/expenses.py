"""Expense CRUD, stats, trip grouping, recent merchants, CSV export."""
import csv as csv_mod
import io
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from core.config import JWT_SECRET
from core.db import db
from core.models import ExpenseCreate
from core.security import bearer, get_current_user, now_iso

router = APIRouter(tags=["expenses"])


@router.post("/expenses")
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


@router.get("/expenses")
async def list_expenses(user=Depends(get_current_user), category: Optional[str] = None, days: Optional[int] = None):
    q = {"user_id": user["id"]}
    if category:
        q["category"] = category
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        q["created_at"] = {"$gte": cutoff}
    items = await db.expenses.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"expenses": items}


@router.get("/expenses/stats")
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


@router.get("/expenses/merchants/recent")
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


@router.get("/expenses/trips")
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


@router.get("/expenses/export.csv")
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


@router.get("/expenses/{eid}")
async def get_expense(eid: str, user=Depends(get_current_user)):
    doc = await db.expenses.find_one({"id": eid, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Expense not found")
    return doc
