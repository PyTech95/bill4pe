"""Server-side payment-receipt extraction & verification.

The uploaded screenshot is the ONLY source of truth for payment evidence:
amount, UTR, transaction id, payee and status are read from the image by
Gemini vision and verified here. Client-typed reference numbers are never
accepted (no manual UTR entry, no user-modified OCR values).
"""
import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from io import BytesIO

from PIL import Image, ImageOps
from pymongo.errors import DuplicateKeyError

from core.config import logger
from core.db import db
from core.security import now_iso
from services.llm import gemini_vision, has_gemini
from services.prompts import PAYMENT_RECEIPT_PROMPT

SUCCESS_MARKERS = ("success", "completed", "complete", "paid", "done", "sent")
FAIL_MARKERS = ("fail", "declin", "cancel", "reject")
PENDING_MARKERS = ("pending", "process", "initiat", "progress", "wait")

DUP_MSG = "This payment reference has already been used"


def normalize_upi(v) -> str:
    """Trim, lowercase, and strip OCR-introduced spaces."""
    return re.sub(r"\s+", "", (v or "")).strip().lower()


def prepare_image(raw: bytes) -> tuple[bytes, str]:
    """Validate + normalize the upload. Raises ValueError on corrupted files."""
    try:
        im = Image.open(BytesIO(raw))
        im.load()
    except Exception:
        raise ValueError("The uploaded file is corrupted or not a valid image")
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((1280, 1280))
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), "image/jpeg"


def _money_to_paise(v):
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v).replace(",", "").replace("₹", "").strip())
    except (InvalidOperation, ValueError):
        return None
    if d <= 0 or d > Decimal("100000000"):
        return None
    return int((d * 100).to_integral_value())


def _classify_status(raw) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "unknown"
    if any(k in s for k in FAIL_MARKERS):
        return "failed"
    if any(k in s for k in PENDING_MARKERS):
        return "pending"
    if any(k in s for k in SUCCESS_MARKERS):
        return "success"
    return "unknown"


def _clean_str(v):
    v = ("" if v is None else str(v)).strip()
    return v or None


def _digits(v, min_len=8, max_len=22):
    d = "".join(c for c in str(v or "") if c.isdigit())
    return d if min_len <= len(d) <= max_len else None


def parse_extraction(parsed: dict) -> dict:
    return {
        "status": _classify_status(parsed.get("status")),
        "amount_paise": _money_to_paise(parsed.get("amount")),
        "currency": _clean_str(parsed.get("currency")) or "INR",
        "utr": _digits(parsed.get("utr")),
        "transaction_id": _clean_str(parsed.get("transaction_id")),
        "transaction_date": _clean_str(parsed.get("transaction_date")),
        "transaction_time": _clean_str(parsed.get("transaction_time")),
        "payee_name": _clean_str(parsed.get("payee_name")),
        "payee_upi": normalize_upi(parsed.get("payee_upi")) or None,
        "payer_name": _clean_str(parsed.get("payer_name")),
        "payer_upi": normalize_upi(parsed.get("payer_upi")) or None,
        "bank_name": _clean_str(parsed.get("bank_name")),
        "bank_account_masked": _clean_str(parsed.get("bank_account_masked")),
        "provider": _clean_str(parsed.get("provider")),
        "extra_reference": _clean_str(parsed.get("extra_reference")),
    }


def upi_match(expected, got):
    """True / False / None (inconclusive). Mask-aware: receipts often show a
    masked handle like 'XXXXXXX7534@ptyes', so the visible tail is compared as
    a suffix of the full handle and the domain must match."""
    e, g = normalize_upi(expected), normalize_upi(got)
    if not e or not g:
        return None
    if e == g:
        return True
    eu, _, ed = e.partition("@")
    gu, _, gd = g.partition("@")
    if ed and gd and ed != gd:
        return False
    et = re.sub(r"[x*•]+", "", eu)
    gt = re.sub(r"[x*•]+", "", gu)
    if not et or not gt:
        return None
    full, tail = (eu, gt) if len(et) >= len(gt) else (gu, et)
    return full.endswith(tail)


async def extract_receipt(image_bytes: bytes, mime: str) -> tuple[dict, dict]:
    """Gemini vision → structured receipt fields + raw OCR JSON."""
    if not has_gemini():
        raise ValueError("Receipt verification is unavailable (AI key not configured)")
    reply = await gemini_vision(
        system_prompt=PAYMENT_RECEIPT_PROMPT,
        user_text="Read this UPI payment receipt screenshot completely and return strict JSON only.",
        image_bytes=image_bytes,
        mime=mime,
    )
    txt = (reply or "").strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0 or e <= s:
        return {}, {}
    try:
        raw = json.loads(txt[s:e + 1])
    except Exception:
        return {}, {}
    if not isinstance(raw, dict):
        return {}, {}
    return parse_extraction(raw), raw


async def _duplicate_field(extracted: dict, tid: str):
    """Return 'utr' / 'transaction_id' when the reference already backs a
    VERIFIED payment elsewhere, else None. Only verified records block reuse —
    a rejected or misread OCR attempt must not lock out a legitimate payment."""
    utr, txid = extracted.get("utr"), extracted.get("transaction_id")
    if utr:
        if await db.receipt_verifications.find_one({"extracted_utr": utr, "verification_status": "verified", "transaction_id": {"$ne": tid}}):
            return "utr"
        if await db.manual_transactions.find_one({"utr_full": utr, "merchant_verification_status": {"$in": ["verified", "admin_reviewed"]}, "id": {"$ne": tid}}):
            return "utr"
    if txid:
        if await db.receipt_verifications.find_one({"extracted_transaction_id": txid, "verification_status": "verified", "transaction_id": {"$ne": tid}}):
            return "transaction_id"
    return None


async def verify_receipt(*, user, txn, image_bytes: bytes, mime: str, proof_file: str) -> dict:
    """Full pipeline: extract → cross-check bill amount / receiver / status /
    duplicates → persist a receipt_verifications record. Never raises on OCR
    ambiguity — unverifiable receipts land in review_required instead."""
    tid = txn["id"]
    try:
        extracted, raw = await extract_receipt(image_bytes, mime)
    except ValueError:
        raise
    except Exception:
        logger.exception("[receipt_verify] extraction failed txn=%s", tid)
        extracted, raw = {}, {}

    status_ok = extracted.get("status") == "success"
    bill_paise = int(txn.get("merchant_amount_paise") or 0)
    amt_paise = extracted.get("amount_paise")
    amount_matched = amt_paise is not None and amt_paise == bill_paise
    receiver_matched = upi_match(txn.get("payee_upi_snapshot"), extracted.get("payee_upi"))
    reference = extracted.get("utr") or extracted.get("transaction_id")
    dup_field = await _duplicate_field(extracted, tid) if reference else None
    duplicate = dup_field is not None
    dup_reason = DUP_MSG if not dup_field else (
        f"This UTR has already been used for another verified payment" if dup_field == "utr"
        else "This transaction ID has already been used for another verified payment"
    )

    reasons = []
    if extracted.get("status") in ("failed", "pending"):
        reasons.append(f"Receipt shows a {extracted['status']} transaction")
    elif not status_ok:
        reasons.append("Payment success status not readable")
    if amt_paise is None:
        reasons.append("Payment amount not readable")
    elif not amount_matched:
        reasons.append(f"Amount mismatch: receipt ₹{amt_paise / 100:.2f} vs bill ₹{bill_paise / 100:.2f}")
    if receiver_matched is False:
        reasons.append("Payment was made to a different UPI ID than the bill payee")
    if not reference:
        reasons.append("UTR / transaction reference not readable")
    if duplicate:
        reasons.append(dup_reason)

    if status_ok and amount_matched and receiver_matched is not False and reference and not duplicate:
        verification_status = "verified"
    elif (
        extracted.get("status") in ("failed", "pending")
        or duplicate
        or (amt_paise is not None and not amount_matched)
        or receiver_matched is False
    ):
        verification_status = "rejected"
    else:
        verification_status = "review_required"

    rec = {
        "id": str(uuid.uuid4()),
        "transaction_id": tid,
        "bill_id": txn.get("bill_id"),
        "user_id": user["id"],
        "receipt_file": proof_file,
        "extracted_amount": round(amt_paise / 100, 2) if amt_paise is not None else None,
        "currency": "INR",
        "extracted_utr": extracted.get("utr"),
        "extracted_transaction_id": extracted.get("transaction_id"),
        "transaction_date": extracted.get("transaction_date"),
        "transaction_time": extracted.get("transaction_time"),
        "payment_provider": extracted.get("provider"),
        "payer_name": extracted.get("payer_name"),
        "payer_upi": extracted.get("payer_upi"),
        "payee_name": extracted.get("payee_name"),
        "payee_upi": extracted.get("payee_upi"),
        "bank_name": extracted.get("bank_name"),
        "bank_account_masked": extracted.get("bank_account_masked"),
        "extra_reference": extracted.get("extra_reference"),
        "payment_status": extracted.get("status"),
        "bill_amount_paise": bill_paise,
        "amount_matched": amount_matched,
        "receiver_matched": receiver_matched,
        "duplicate_check": "duplicate" if duplicate else "new",
        "verification_status": verification_status,
        "failure_reasons": reasons,
        "ocr_raw_data": raw,
        "created_at": now_iso(),
        "verified_at": now_iso() if verification_status == "verified" else None,
    }
    # Re-uploads for the same bill replace its earlier verification attempts.
    await db.receipt_verifications.delete_many({"transaction_id": tid})
    try:
        await db.receipt_verifications.insert_one(rec)
    except DuplicateKeyError:
        rec["duplicate_check"] = "duplicate"
        rec["verification_status"] = "rejected"
        if DUP_MSG not in rec["failure_reasons"]:
            rec["failure_reasons"].append(DUP_MSG)
        logger.warning("[receipt_verify] duplicate UTR/txn blocked txn=%s utr=%s", tid, rec.get("extracted_utr"))
    logger.info(
        "[receipt_verify] txn=%s status=%s amount_match=%s receiver_match=%s dup=%s -> %s",
        tid, rec["payment_status"], amount_matched, receiver_matched, duplicate, rec["verification_status"],
    )
    return rec
