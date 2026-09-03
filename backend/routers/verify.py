"""Public bill authenticity verification.

Anyone with the QR scan / bill ID can call this endpoint to check whether
the bill is real, the merchant, amount, and the issued date. No PII beyond
the customer first name is exposed.
"""
from fastapi import APIRouter, HTTPException

from core.db import db

router = APIRouter(tags=["verify"])


def _first_name(name: str | None) -> str | None:
    if not name:
        return None
    return name.strip().split(" ")[0]


@router.get("/public/verify/{bill_id}")
async def verify_bill(bill_id: str):
    """Public lookup. `bill_id` is the human-readable `B4P-...` id printed on
    the bill (also encoded into the PDF QR). Returns minimal, non-sensitive
    info so the receiver can cross-check before reimbursing.
    """
    bill_id = (bill_id or "").strip()
    if not bill_id:
        raise HTTPException(400, "Bill ID required")

    exp = await db.expenses.find_one({"bill_id": bill_id}, {"_id": 0})
    if not exp or not exp.get("bill_generated"):
        return {"valid": False, "bill_id": bill_id}

    user = await db.users.find_one({"id": exp.get("user_id")}, {"_id": 0}) or {}
    pay = exp.get("payment") or {}
    total = float(exp.get("total", 0) or 0)
    fee = float(exp.get("bill_fee", 0) or 0)

    return {
        "valid": True,
        "bill_id": bill_id,
        "issued_at": exp.get("bill_generated_at") or exp.get("created_at"),
        "created_at": exp.get("created_at"),
        "merchant_name": pay.get("merchant_name"),
        "merchant_upi": pay.get("merchant_upi"),
        "category": exp.get("category"),
        "sub_category": exp.get("sub_category"),
        "amount": round(total, 2),
        "fee": round(fee, 2),
        "grand_total": round(total + fee, 2),
        "customer_name": _first_name(user.get("name")),
        "approval_status": exp.get("approval_status"),
    }
