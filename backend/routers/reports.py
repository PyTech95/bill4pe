"""Consolidated multi-bill expense reports for reimbursement submissions."""
import io
import uuid
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from core.config import JWT_SECRET
from core.db import db
from core.models import ReportCreate
from core.security import bearer, get_current_user, now_iso
from services.pdf import build_report_pdf

router = APIRouter(tags=["reports"])


@router.post("/reports")
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


@router.get("/reports")
async def list_reports(user=Depends(get_current_user)):
    reports = await db.reports.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"reports": reports}


@router.get("/reports/{rid}/pdf")
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


@router.delete("/reports/{rid}")
async def delete_report(rid: str, user=Depends(get_current_user)):
    res = await db.reports.delete_one({"id": rid, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Report not found")
    return {"ok": True}
