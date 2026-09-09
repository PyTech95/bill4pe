"""Manual double-scan UPI payment flow (PAYMENT_FLOW_MODE=manual_upi_double_scan).

Merchant is paid directly by the customer; Bill4Pe only handles the service fee.
All money-critical state is computed server-side (spec §39). Secure, authenticated
proof upload with private storage (spec §41).
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from core.db import db
from core.security import get_current_user
from services import manual_flow_service as mf

router = APIRouter(tags=["manual-pay"])

LEGACY_PROOF_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "private_uploads", "payment_proofs")
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

class GenerateReceiptReq(BaseModel):
    wallet_pin: Optional[str] = None


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
    from services import receipt_verify, payment_proof_storage
    try:
        norm, mime = receipt_verify.prepare_image(data)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Store the ORIGINAL customer receipt inside MongoDB before verification.
    # No new payment proof is written to backend/private_uploads or any other
    # application folder, so future code deployments cannot delete it.
    try:
        stored = await payment_proof_storage.store_payment_proof(
            data=data,
            filename=screenshot.filename,
            content_type=screenshot.content_type or mime,
            transaction_id=tid,
            user_id=user["id"],
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, "Unable to store payment receipt securely") from e

    try:
        return await mf.submit_proof(
            user, tid, image_bytes=norm, mime=mime, proof_record=stored
        )
    except LookupError:
        # Do not leave an unattached MongoDB blob when the transaction is invalid.
        await payment_proof_storage.delete_payment_proof(stored["id"])
        raise HTTPException(404, "Transaction not found")
    except ValueError as e:
        await payment_proof_storage.delete_payment_proof(stored["id"])
        raise HTTPException(400, str(e))


@router.get("/manual-pay/{tid}/proof-file")
async def proof_file(tid: str, user=Depends(get_current_user)):
    txn = await db.manual_transactions.find_one({"id": tid})
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.get("user_id") != user["id"] and not _is_admin(user):
        raise HTTPException(403, "Not authorized")
    # New receipts live in MongoDB.  Legacy filesystem fallback is retained only
    # so old bills remain viewable until the one-time migration has run.
    proof_db_id = txn.get("proof_db_id")
    if proof_db_id:
        from services import payment_proof_storage
        proof = await payment_proof_storage.get_payment_proof(
            proof_db_id, transaction_id=tid
        )
        if not proof:
            raise HTTPException(404, "Payment receipt is missing from database")
        headers = {
            "Content-Disposition": f'inline; filename="{proof["filename"]}"',
            "Cache-Control": "private, no-store",
        }
        return Response(
            content=proof["data"],
            media_type=proof["content_type"],
            headers=headers,
        )

    # Backward-compatible read of pre-migration receipts only.
    name = txn.get("proof_file")
    if not name:
        raise HTTPException(404, "No screenshot on file")
    from pathlib import Path
    path = Path(LEGACY_PROOF_DIR) / Path(name).name
    if not path.exists():
        raise HTTPException(404, "Legacy receipt file missing; run the MongoDB proof migration")
    return FileResponse(str(path), headers={"Cache-Control": "private, no-store"})


@router.post("/manual-pay/{tid}/generate")
async def generate(tid: str, body: Optional[GenerateReceiptReq] = None, user=Depends(get_current_user)):
    try:
        return await mf.generate_receipt(user, tid, wallet_pin=(body.wallet_pin if body else None))
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
