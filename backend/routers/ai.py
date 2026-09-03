"""AI endpoints: image item detection, autocomplete suggestions, receipt OCR, voice expense.

All AI features use Google Gemini via GEMINI_API_KEY (google-genai on the VPS, or
the Emergent proxy as a preview-only fallback). Voice notes are transcribed by
Gemini's native audio understanding, then parsed by Gemini text. No OpenAI /
Whisper dependency.
"""
import json
import os
import asyncio
import tempfile
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image

from core.config import logger
from core.config import GEMINI_UTR_MODEL
from core.security import get_current_user
from services.llm import (
    gemini_text,
    gemini_transcribe,
    gemini_vision,
    has_gemini,
)
from services.audio import to_mp3
from services.prompts import (
    RECEIPT_PROMPT,
    UTR_EXTRACT_PROMPT,
    VALID_CATEGORIES,
    VOICE_AUDIO_PROMPT,
    category_prompt,
)

router = APIRouter(tags=["ai"])


def _strip_code_fence(txt: str) -> str:
    txt = (txt or "").strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()
    return txt


def _extract_json_block(txt: str, open_char: str, close_char: str) -> str:
    s, e = txt.find(open_char), txt.rfind(close_char)
    if s >= 0 and e > s:
        return txt[s:e + 1]
    return txt


def _normalise_mime(file: UploadFile) -> tuple[str, str]:
    mime = file.content_type or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        mime = "image/jpeg"
    suffix = ".jpg" if "jpeg" in mime else (".png" if "png" in mime else ".webp")
    return mime, suffix


def _ai_error(exc: Exception, fallback_msg: str) -> HTTPException:
    """Map a Gemini exception to a clean, non-leaky HTTPException."""
    msg = str(exc).lower()
    if any(k in msg for k in ("quota", "resource_exhausted", "exceeded", "billing")):
        return HTTPException(429, "Daily AI limit reached on your Gemini key. Enable billing on your Google AI key or try again tomorrow.")
    if any(k in msg for k in ("rate", "429")):
        return HTTPException(429, "AI is busy (rate limit). Please try again in a moment.")
    if any(k in msg for k in ("timeout", "deadline")):
        return HTTPException(504, "AI timed out. Please try again.")
    return HTTPException(500, fallback_msg)


@router.post("/ai/detect-items")
async def detect_items(category: str = "food", file: UploadFile = File(...), user=Depends(get_current_user)):
    if not has_gemini():
        raise HTTPException(500, "AI key not configured (GEMINI_API_KEY)")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 8MB)")
    mime, _suffix = _normalise_mime(file)
    try:
        prompt = category_prompt(category)
        reply = await gemini_vision(
            system_prompt=prompt,
            user_text=f"Detect all {category} items in this image. Return strict JSON array only.",
            image_bytes=raw,
            mime=mime,
        )
        txt = _extract_json_block(_strip_code_fence(reply), "[", "]")
        try:
            items = json.loads(txt)
        except Exception:
            items = []
        cleaned = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            if not name:
                continue
            try:
                qty = float(it.get("quantity", 1) or 1)
                price = float(it.get("unit_price", 0) or 0)
            except Exception:
                qty, price = 1.0, 0.0
            cleaned.append({"name": name, "quantity": qty, "unit_price": round(price, 2)})
        return {"items": cleaned}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("AI detection failed")
        raise _ai_error(e, "AI detection failed")


@router.post("/ai/suggest-items")
async def suggest_items(payload: dict, user=Depends(get_current_user)):
    """Suggest item names for manual entry autocomplete."""
    if not has_gemini():
        return {"suggestions": []}
    category = payload.get("category", "food")
    query = payload.get("query", "")
    if len(query) < 2:
        return {"suggestions": []}
    try:
        system_msg = (
            f"You suggest short Indian {category} item names for autocomplete. "
            f"Return ONLY a JSON array of 5 short strings, no prose. "
            f"Example: [\"Roti\",\"Rumali Roti\",\"Romali\",\"Roomali Roti\",\"Tandoori Roti\"]"
        )
        reply = await gemini_text(
            system_prompt=system_msg,
            user_text=f"Suggest items starting with '{query}'",
        )
        txt = _extract_json_block(_strip_code_fence(reply), "[", "]")
        arr = json.loads(txt)
        return {"suggestions": [str(x) for x in arr if isinstance(x, (str, int, float))][:5]}
    except Exception:
        return {"suggestions": []}


@router.post("/ai/scan-receipt")
async def scan_receipt(file: UploadFile = File(...), user=Depends(get_current_user)):
    """OCR a printed receipt photo into structured expense data."""
    if not has_gemini():
        raise HTTPException(500, "AI key not configured (GEMINI_API_KEY)")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 8MB)")
    mime, _suffix = _normalise_mime(file)
    try:
        reply = await gemini_vision(
            system_prompt=RECEIPT_PROMPT,
            user_text="Parse this Indian printed receipt. Return strict JSON object only.",
            image_bytes=raw,
            mime=mime,
        )
        txt = _extract_json_block(_strip_code_fence(reply), "{", "}")
        try:
            parsed = json.loads(txt)
        except Exception:
            parsed = {}

        category = str(parsed.get("category", "other")).lower().strip()
        if category not in VALID_CATEGORIES:
            category = "other"

        items = []
        for it in (parsed.get("items") or []):
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            if not name:
                continue
            try:
                qty = float(it.get("quantity", 1) or 1)
                price = float(it.get("unit_price", 0) or 0)
            except Exception:
                qty, price = 1.0, 0.0
            items.append({"name": name, "quantity": qty, "unit_price": round(price, 2)})

        def num(v):
            try:
                return round(float(v or 0), 2)
            except Exception:
                return 0.0

        return {
            "merchant_name": str(parsed.get("merchant_name", "")).strip(),
            "date": str(parsed.get("date", "")).strip(),
            "items": items,
            "subtotal": num(parsed.get("subtotal")),
            "tax": num(parsed.get("tax")),
            "total": num(parsed.get("total")),
            "category": category,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Receipt OCR failed")
        raise _ai_error(e, "Receipt OCR failed")


@router.post("/ai/extract-utr")
async def extract_utr(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Read a UPI payment screenshot and auto-extract the 12-digit UTR.

    Degrades gracefully: on AI timeout/overload it returns found=false (the client
    then asks the user to type the UTR) instead of hanging past the gateway limit.
    """
    if not has_gemini():
        raise HTTPException(500, "AI key not configured (GEMINI_API_KEY)")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 8MB)")
    mime, _suffix = _normalise_mime(file)
    # Downscale large phone screenshots so the vision call stays well under the
    # gateway timeout (fewer image tiles = a noticeably faster Gemini response).
    try:
        im = Image.open(BytesIO(raw)).convert("RGB")
        im.thumbnail((1024, 1024))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=85)
        raw = buf.getvalue()
        mime = "image/jpeg"
    except Exception:
        pass
    try:
        reply = await asyncio.wait_for(
            gemini_vision(
                system_prompt=UTR_EXTRACT_PROMPT,
                user_text="Extract the 12-digit UTR / UPI transaction reference number from this payment screenshot. Return strict JSON only.",
                image_bytes=raw,
                mime=mime,
                model=GEMINI_UTR_MODEL,
            ),
            timeout=40,
        )
    except asyncio.TimeoutError:
        logger.warning("UTR extraction timed out")
        return {"utr": "", "found": False, "error": "AI is busy — please type the 12-digit UTR."}
    except Exception as e:
        logger.exception("UTR extraction failed")
        return {"utr": "", "found": False, "error": "Couldn't read the UTR — please type it."}
    txt = _extract_json_block(_strip_code_fence(reply), "{", "}")
    try:
        parsed = json.loads(txt)
    except Exception:
        parsed = {}
    digits = "".join(c for c in str(parsed.get("utr", "")) if c.isdigit())
    if len(digits) == 12:
        return {"utr": digits, "found": True}
    return {"utr": "", "found": False}


@router.post("/voice/expense")
async def voice_expense(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Audio → Gemini transcribe → Gemini text parse → structured draft expense.

    Flow:
        Audio Recording -> FastAPI Upload -> Gemini Audio Transcription
        -> Gemini Text Parsing -> Structured Expense Draft

    Same request/response contract as before so the existing UI auto-fill keeps working.
    """
    if not has_gemini():
        raise HTTPException(500, "AI key not configured (GEMINI_API_KEY)")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty audio file")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio too large (max 25MB)")

    ct = (file.content_type or "").lower()
    if "webm" in ct:
        suffix = ".webm"
    elif "mp4" in ct or "m4a" in ct:
        suffix = ".m4a"
    elif "wav" in ct:
        suffix = ".wav"
    elif "ogg" in ct:
        suffix = ".ogg"
    elif "mpeg" in ct or "mp3" in ct:
        suffix = ".mp3"
    else:
        suffix = ".webm"

    # Transcode to Gemini-friendly MP3 (handles browser webm/opus).
    try:
        mp3 = to_mp3(raw, suffix)
    except Exception:
        raise HTTPException(400, "Unsupported or corrupted audio. Please re-record and try again.")

    # Write MP3 to a temp file for the Gemini Files API; endpoint cleans it up.
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.write(mp3)
    tmp.flush()
    tmp.close()

    # Single Gemini audio call: transcribe + extract expense fields (JSON) in one
    # request. Doing it in one call (instead of transcribe + separate parse)
    # halves how much of your Gemini quota each voice note consumes.
    try:
        reply = await gemini_transcribe(tmp.name, VOICE_AUDIO_PROMPT)
    except Exception as e:
        msg = str(e).lower()
        logger.exception("Gemini voice processing failed")
        if any(k in msg for k in ("quota", "resource_exhausted", "exceeded", "billing")):
            raise HTTPException(429, "Daily AI limit reached on your Gemini key. Enable billing on your Google AI key or try again tomorrow.")
        if any(k in msg for k in ("rate", "429")):
            raise HTTPException(429, "AI is busy (rate limit). Please try again in a moment.")
        if any(k in msg for k in ("timeout", "deadline")):
            raise HTTPException(504, "AI timed out. Please try again.")
        raise HTTPException(502, "Voice transcription failed")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    txt = _extract_json_block(_strip_code_fence(reply), "{", "}")
    try:
        parsed = json.loads(txt)
    except Exception:
        parsed = {}

    transcript = str(parsed.get("transcript", "")).strip()
    category = str(parsed.get("category", "other")).lower().strip()
    if category not in VALID_CATEGORIES:
        category = "other"
    sub_category = str(parsed.get("sub_category", "Misc")).strip() or "Misc"
    merchant_name = str(parsed.get("merchant_name", "")).strip()
    try:
        total_amount = float(parsed.get("total_amount", 0) or 0)
    except Exception:
        total_amount = 0.0

    items = []
    for it in (parsed.get("items") or []):
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()
        if not name:
            continue
        try:
            qty = float(it.get("quantity", 1) or 1)
            price = float(it.get("unit_price", 0) or 0)
        except Exception:
            qty, price = 1.0, 0.0
        items.append({"name": name, "quantity": qty, "unit_price": round(price, 2)})

    if not items and total_amount > 0:
        items = [{"name": sub_category or "Expense", "quantity": 1.0, "unit_price": round(total_amount, 2)}]

    if not transcript and not items and total_amount == 0:
        raise HTTPException(422, "Could not understand the audio. Please speak the amount and item clearly.")

    return {
        "transcript": transcript,
        "category": category,
        "sub_category": sub_category,
        "merchant_name": merchant_name,
        "total_amount": round(total_amount, 2),
        "items": items,
    }
