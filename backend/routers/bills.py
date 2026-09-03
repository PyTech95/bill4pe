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
from services.email import build_invoice_html, send_email, has_email
from services import payment_service
from pydantic import BaseModel, EmailStr
import os
import razorpay

router = APIRouter(tags=["bills"])

_RZP_ID = os.environ.get("RAZORPAY_KEY_ID")
_RZP_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
_RZP = razorpay.Client(auth=(_RZP_ID, _RZP_SECRET)) if (_RZP_ID and _RZP_SECRET) else None


class GenerateReq(BaseModel):
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None


@router.post("/bills/{eid}/generate")
async def generate_bill(eid: str, body: Optional[GenerateReq] = None, user=Depends(get_current_user)):
    """Charges the bill fee, then marks the official bill generated.

    - Employee: deducts from the COMPANY wallet (centralised billing).
    - Individual / Admin: deducts from the personal wallet; if the wallet is
      short, the frontend collects the fee via Razorpay and re-calls this
      endpoint with the razorpay_* proof (verified here → no wallet debit).
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
    fee, fee_percent = await payment_service.bill_fee_for_user(user, exp.get("total"))
    fee_paid_via = "wallet"
    new_bal = None

    # Did the client pay the fee via Razorpay? Verify the signature.
    razorpay_ok = False
    if body and body.razorpay_order_id and body.razorpay_payment_id and body.razorpay_signature:
        if not _RZP:
            raise HTTPException(503, "Razorpay not configured")
        try:
            _RZP.utility.verify_payment_signature({
                "razorpay_order_id": body.razorpay_order_id,
                "razorpay_payment_id": body.razorpay_payment_id,
                "razorpay_signature": body.razorpay_signature,
            })
        except Exception:
            raise HTTPException(400, "Fee payment verification failed")
        ord_doc = await db.payment_orders.find_one(
            {"order_id": body.razorpay_order_id, "user_id": user["id"], "purpose": "bill_fee"}
        )
        if not ord_doc:
            raise HTTPException(404, "Fee payment order not found")
        await db.payment_orders.update_one(
            {"order_id": body.razorpay_order_id},
            {"$set": {"status": "paid", "payment_id": body.razorpay_payment_id, "paid_at": now_iso()}},
        )
        razorpay_ok = True
        fee_paid_via = "razorpay"

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
        if razorpay_ok:
            # Fee already collected via Razorpay — no wallet debit.
            new_bal = bal
        else:
            if bal < fee:
                # Signal the frontend to collect the fee via Razorpay.
                raise HTTPException(402, f"Insufficient wallet balance. Need ₹{fee:.2f}, have ₹{bal:.2f}")
            new_bal = round(bal - fee, 2)
            await db.users.update_one({"id": user["id"]}, {"$set": {"wallet_balance": new_bal}})
            await db.wallet_txns.insert_one({
                "id": str(uuid.uuid4()), "user_id": user["id"], "type": "debit",
                "amount": fee, "reason": f"Bill generation: {bill_id}", "created_at": now_iso()
            })

    await db.expenses.update_one({"id": eid}, {"$set": {
        "bill_generated": True, "bill_id": bill_id,
        "bill_fee": fee, "bill_fee_percent": fee_percent,
        "bill_generated_at": now_iso(), "bill_fee_paid_via": fee_paid_via,
    }})
    return {"bill_id": bill_id, "wallet_balance": new_bal, "fee": fee, "fee_percent": fee_percent, "fee_paid_via": fee_paid_via}


@router.get("/bills/fee-info")
async def bill_fee_info(user=Depends(get_current_user)):
    """The bill-generation fee % that applies to the CURRENT user (for display
    before generation). Corporate accounts are on a subscription -> 0% per bill."""
    kind = payment_service.bill_fee_kind_for_user(user)
    if kind == "corporate":
        return {"kind": kind, "percent": 0.0}
    percents = await payment_service.get_bill_fee_percents()
    return {"kind": kind, "percent": percents["individual"]}


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


class EmailBillReq(BaseModel):
    recipient_email: EmailStr
    verify_url: Optional[str] = None
    note: Optional[str] = None


@router.post("/bills/{eid}/email")
async def email_bill(eid: str, body: EmailBillReq, user=Depends(get_current_user)):
    if not has_email():
        raise HTTPException(503, "Email is not configured (EMERGENT_EMAIL_KEY)")
    exp = await db.expenses.find_one({"id": eid, "user_id": user["id"]}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Expense not found")
    if not exp.get("bill_generated"):
        raise HTTPException(400, "Generate the official bill first, then email it")
    html = build_invoice_html(exp, user, verify_url=body.verify_url, note=body.note)
    subject = f"Invoice {exp.get('bill_id')} — ₹{float(exp.get('total', 0)):.2f}"
    try:
        email_id = await send_email(body.recipient_email, subject, html, reply_to=user.get("email"))
    except Exception as e:
        raise HTTPException(502, f"Failed to send email: {str(e)[:150]}")
    await db.expenses.update_one(
        {"id": eid},
        {"$set": {"emailed_to": body.recipient_email, "emailed_at": now_iso()}},
    )
    return {"ok": True, "email_id": email_id, "recipient": body.recipient_email}
