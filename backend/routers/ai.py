"""AI endpoints: image item detection, autocomplete suggestions, receipt OCR, voice expense.

Uses official SDKs (google-generativeai for Gemini, openai for Whisper) via
`services.llm` so the backend can be self-hosted on any Ubuntu VPS without
proprietary Emergent libraries.
"""
import json
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from core.config import logger
from core.security import get_current_user
from services.llm import (
    gemini_text,
    gemini_vision,
    has_gemini,
    has_openai,
    openai_transcribe,
)
from services.prompts import (
    RECEIPT_PROMPT,
    VALID_CATEGORIES,
    VOICE_PARSE_PROMPT,
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
        raise HTTPException(500, f"AI detection failed: {str(e)[:200]}")


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
        raise HTTPException(500, f"Receipt OCR failed: {str(e)[:200]}")


@router.post("/voice/expense")
async def voice_expense(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Accept audio file → Whisper transcript → Gemini parse → structured draft expense."""
    if not has_openai():
        raise HTTPException(500, "AI key not configured (OPENAI_API_KEY)")
    if not has_gemini():
        raise HTTPException(500, "AI key not configured (GEMINI_API_KEY)")
    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(400, "Audio too large (max 25MB)")
    if not raw:
        raise HTTPException(400, "Empty audio file")

    ct = (file.content_type or "").lower()
    if "webm" in ct:
        suffix = ".webm"
    elif "mp4" in ct or "m4a" in ct:
        suffix = ".m4a"
    elif "wav" in ct:
        suffix = ".wav"
    elif "mpeg" in ct or "mp3" in ct:
        suffix = ".mp3"
    else:
        suffix = ".webm"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(raw)
    tmp.flush()
    tmp.close()
    try:
        transcript = await openai_transcribe(
            tmp.name,
            prompt="Indian expense note. Mentions amounts in rupees, food items, cab/flight, merchant names.",
        )
        if not transcript:
            raise HTTPException(422, "Could not hear anything in the audio")

        reply = await gemini_text(
            system_prompt=VOICE_PARSE_PROMPT,
            user_text=f"Transcript: {transcript}",
        )
        txt = _extract_json_block(_strip_code_fence(reply), "{", "}")
        try:
            parsed = json.loads(txt)
        except Exception:
            parsed = {}

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

        return {
            "transcript": transcript,
            "category": category,
            "sub_category": sub_category,
            "merchant_name": merchant_name,
            "total_amount": round(total_amount, 2),
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Voice parse failed")
        raise HTTPException(500, f"Voice processing failed: {str(e)[:200]}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
