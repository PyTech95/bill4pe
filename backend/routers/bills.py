"""Bill PDF generation and download."""
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from core.config import calc_bill_fee, JWT_SECRET
from core.db import db
from core.security import bearer, get_current_user, now_iso
from services.pdf import build_pdf_bytes

router = APIRouter(tags=["bills"])


@router.post("/bills/{eid}/generate")
async def generate_bill(eid: str, user=Depends(get_current_user)):
    """Charges the bill fee. Employees must have admin-approved expense.

    - Individual / Admin: deducts from personal wallet.
    - Employee: deducts from the company wallet (centralised billing).
    """
    exp = await db.expenses.find_one({"id": eid, "user_id": user["id"]}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Expense not found")
    if exp.get("bill_generated"):
        return {"bill_id": exp.get("bill_id"), "message": "Already generated"}

    # Employee approval gating
    if user.get("role") == "employee":
        if exp.get("approval_status") != "approved":
            raise HTTPException(403, "Bill is awaiting admin approval")

    bill_id = f"B4P-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{eid[:6].upper()}"
    fee = calc_bill_fee(exp.get("total"))

    if user.get("role") == "employee" and user.get("company_id"):
        company = await db.companies.find_one({"id": user["company_id"]})
        if not company:
            raise HTTPException(404, "Company not found")
        bal = float(company.get("wallet_balance", 0.0))
        if bal < fee:
            raise HTTPException(
                402,
                f"Company wallet has insufficient balance. Need ₹{fee:.2f}, have ₹{bal:.2f}. Ask your admin to recharge."
            )
        new_bal = round(bal - fee, 2)
        await db.companies.update_one({"id": company["id"]}, {"$set": {"wallet_balance": new_bal}})
        await db.wallet_txns.insert_one({
            "id": str(uuid.uuid4()),
            "company_id": company["id"],
            "user_id": user["id"],
            "type": "debit",
            "amount": fee,
            "reason": f"Bill generation by {user.get('name')}: {bill_id}",
            "created_at": now_iso(),
        })
    else:
        u = await db.users.find_one({"id": user["id"]})
        bal = float(u.get("wallet_balance", 0.0))
        if bal < fee:
            raise HTTPException(402, f"Insufficient wallet balance. Need ₹{fee:.2f}, have ₹{bal:.2f}")
        new_bal = round(bal - fee, 2)
        await db.users.update_one({"id": user["id"]}, {"$set": {"wallet_balance": new_bal}})
        await db.wallet_txns.insert_one({
            "id": str(uuid.uuid4()), "user_id": user["id"], "type": "debit",
            "amount": fee, "reason": f"Bill generation: {bill_id}", "created_at": now_iso()
        })

    await db.expenses.update_one({"id": eid}, {"$set": {
        "bill_generated": True, "bill_id": bill_id,
        "bill_fee": fee, "bill_generated_at": now_iso()
    }})
    return {"bill_id": bill_id, "wallet_balance": new_bal, "fee": fee}


@router.get("/bills/{eid}/pdf")
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
