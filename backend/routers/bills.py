"""Bill PDF generation and download."""
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from core.config import BILL_FEE, JWT_SECRET
from core.db import db
from core.security import bearer, get_current_user, now_iso
from services.pdf import build_pdf_bytes

router = APIRouter(tags=["bills"])


@router.post("/bills/{eid}/generate")
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
