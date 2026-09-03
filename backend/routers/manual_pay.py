"""Manual double-scan UPI payment flow (PAYMENT_FLOW_MODE=manual_upi_double_scan).

Merchant is paid directly by the customer; Bill4Pe only handles the service fee.
All money-critical state is computed server-side (spec §39). Secure, authenticated
proof upload with private storage (spec §41).
"""
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.db import db
from core.security import get_current_user
from services import manual_flow_service as mf

router = APIRouter(tags=["manual-pay"])

PROOF_DIR = Path(__file__).resolve().parent.parent / "private_uploads" / "payment_proofs"
PROOF_DIR.mkdir(parents=True, exist_ok=True)
_ALLOWED_CT = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_BYTES = 5 * 1024 * 1024


def _is_admin(user) -> bool:
    return bool(user.get("is_super_admin")) or user.get("role") in ("admin", "superadmin")


class FirstScanReq(BaseModel):
    payee_upi: Optional[str] = None
    payee_name: Optional[str] = None
    merchant_amount: Optional[float] = None
    expense_draft: Optional[dict] = None


class SecondScanReq(BaseModel):
    payee_upi: str


class ConfirmReq(BaseModel):
    completed: bool


class FeeVerifyReq(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.get("/manual-pay/config")
async def config(user=Depends(get_current_user)):
    return {
        "flow_mode": os.environ.get("PAYMENT_FLOW_MODE", "manual_upi_double_scan"),
        "platform_fee_percent": await mf._fee_percent_for_user(user),
    }


@router.post("/manual-pay/first-scan")
async def first_scan(body: FirstScanReq, user=Depends(get_current_user)):
    try:
        return await mf.first_scan(user, body.payee_upi, body.payee_name,
                                   body.merchant_amount, body.expense_draft)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/manual-pay/{tid}/second-scan")
async def second_scan(tid: str, body: SecondScanReq, user=Depends(get_current_user)):
    try:
        return await mf.second_scan(user, tid, body.payee_upi)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/manual-pay/{tid}/confirm")
async def confirm(tid: str, body: ConfirmReq, user=Depends(get_current_user)):
    try:
        return await mf.confirm_payment(user, tid, body.completed)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/manual-pay/{tid}/cancel")
async def cancel(tid: str, user=Depends(get_current_user)):
    try:
        return await mf.cancel(user, tid)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/manual-pay/{tid}/discard")
async def discard(tid: str, user=Depends(get_current_user)):
    """Discard the whole bill: cancel bill + payment attempt (audit record kept,
    never active again). Blocked for finalized/verified payments."""
    try:
        return await mf.discard(user, tid)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/manual-pay/{tid}/restart")
async def restart(tid: str, user=Depends(get_current_user)):
    """New payment attempt for the SAME bill — old attempt cancelled, receipt /
    OCR / UTR / verification state reset, bill amount and payee preserved."""
    try:
        return await mf.restart(user, tid)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/manual-pay/{tid}/proof")
async def submit_proof(
    tid: str,
    screenshot: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Receipt-first proof: the screenshot is the ONLY accepted evidence.
    No client-typed UTR/reference is accepted — values come from server-side OCR."""
    ext = os.path.splitext(screenshot.filename or "")[1].lower()
    if screenshot.content_type not in _ALLOWED_CT or ext not in _ALLOWED_EXT:
        raise HTTPException(400, "Only JPG, PNG or WEBP screenshots are allowed")
    data = await screenshot.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > _MAX_BYTES:
        raise HTTPException(400, "Screenshot must be under 5 MB")
    from services import receipt_verify
    try:
        norm, mime = receipt_verify.prepare_image(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    stored_name = f"{tid}_{uuid.uuid4().hex}{'.jpg' if ext in ('.jpg', '.jpeg') else ext}"
    (PROOF_DIR / stored_name).write_bytes(data)
    try:
        return await mf.submit_proof(user, tid, stored_name, norm, mime)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/manual-pay/{tid}/proof-file")
async def proof_file(tid: str, user=Depends(get_current_user)):
    txn = await db.manual_transactions.find_one({"id": tid})
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.get("user_id") != user["id"] and not _is_admin(user):
        raise HTTPException(403, "Not authorized")
    name = txn.get("proof_file")
    if not name:
        raise HTTPException(404, "No screenshot on file")
    path = PROOF_DIR / name
    if not path.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(str(path))


@router.post("/manual-pay/{tid}/generate")
async def generate(tid: str, user=Depends(get_current_user)):
    try:
        return await mf.generate_receipt(user, tid)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/manual-pay/{tid}/fee-order")
async def fee_order(tid: str, user=Depends(get_current_user)):
    try:
        return await mf.create_fee_order(user, tid)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/manual-pay/{tid}/fee-verify")
async def fee_verify(tid: str, body: FeeVerifyReq, user=Depends(get_current_user)):
    try:
        return await mf.verify_fee_payment(user, tid, body.razorpay_order_id,
                                           body.razorpay_payment_id, body.razorpay_signature)
    except LookupError:
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/manual-pay/history")
async def history(user=Depends(get_current_user)):
    return {"transactions": await mf.history(user)}


@router.get("/manual-pay/{tid}")
async def status(tid: str, user=Depends(get_current_user)):
    res = await mf.get_status(user, tid)
    if not res:
        raise HTTPException(404, "Transaction not found")
    return res


# ---------------- Admin ----------------
@router.get("/manual-pay/admin/transactions")
async def admin_list(user=Depends(get_current_user)):
    if not _is_admin(user):
        raise HTTPException(403, "Admin only")
    rows = await db.manual_transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for r in rows:
        if r.get("utr_full"):
            r["utr_full"] = mf._mask_utr(r["utr_full"])
    return {"transactions": rows}


class ReviewReq(BaseModel):
    action: str  # "reviewed" | "rejected"


@router.post("/manual-pay/admin/{tid}/review")
async def admin_review(tid: str, body: ReviewReq, user=Depends(get_current_user)):
    if not _is_admin(user):
        raise HTTPException(403, "Admin only")
    if body.action not in ("reviewed", "rejected"):
        raise HTTPException(400, "Invalid action")
    status_val = "admin_reviewed" if body.action == "reviewed" else "rejected"
    res = await db.manual_transactions.update_one(
        {"id": tid}, {"$set": {"merchant_verification_status": status_val}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Transaction not found")
    return {"ok": True, "merchant_verification_status": status_val}
