"""AI endpoints: image item detection, autocomplete suggestions, receipt OCR, voice expense.

All AI features use Google Gemini via GEMINI_API_KEY (google-genai on the VPS).
Voice notes are transcribed by Gemini's native audio understanding, then parsed
by Gemini text. No Emergent/OpenAI/Whisper dependency is required.
"""
import json
import os
import asyncio
import tempfile
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, ImageOps

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
    VOICE_PARSE_PROMPT,
    PRODUCT_FALLBACK_PROMPT,
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




def _prepare_image(raw: bytes, max_side: int = 1600) -> tuple[bytes, str]:
    """Normalize phone photos before Gemini: fix EXIF rotation and cap size."""
    try:
        im = ImageOps.exif_transpose(Image.open(BytesIO(raw))).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=88, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return raw, "image/jpeg"


def _clean_items(payload) -> list[dict]:
    if isinstance(payload, dict):
        payload = payload.get("items") or []
    if not isinstance(payload, list):
        return []
    cleaned = []
    for it in payload:
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
        if qty <= 0:
            qty = 1.0
        if price < 0:
            price = 0.0
        cleaned.append({"name": name[:120], "quantity": qty, "unit_price": round(price, 2)})
    return cleaned[:20]


def _parse_items_reply(reply: str) -> list[dict]:
    txt = _strip_code_fence(reply)
    candidates = []
    if "[" in txt and "]" in txt:
        candidates.append(_extract_json_block(txt, "[", "]"))
    if "{" in txt and "}" in txt:
        candidates.append(_extract_json_block(txt, "{", "}"))
    candidates.append(txt)
    for c in candidates:
        try:
            items = _clean_items(json.loads(c))
            if items:
                return items
        except Exception:
            pass
    return []


def _normalise_voice_payload(parsed: dict, transcript_hint: str = "") -> dict:
    parsed = parsed if isinstance(parsed, dict) else {}
    transcript = str(parsed.get("transcript") or transcript_hint or "").strip()
    category = str(parsed.get("category", "other")).lower().strip()
    if category not in VALID_CATEGORIES:
        category = "other"
    sub_category = str(parsed.get("sub_category", "Misc")).strip() or "Misc"
    merchant_name = str(parsed.get("merchant_name", "")).strip()
    try:
        total_amount = float(parsed.get("total_amount", 0) or 0)
    except Exception:
        total_amount = 0.0
    items = _clean_items(parsed.get("items") or [])
    if not items and total_amount > 0:
        items = [{"name": sub_category or "Expense", "quantity": 1.0, "unit_price": round(total_amount, 2)}]
    return {
        "transcript": transcript, "category": category, "sub_category": sub_category,
        "merchant_name": merchant_name, "total_amount": round(total_amount, 2), "items": items,
    }


def _basic_voice_fallback(transcript: str) -> dict:
    """Small deterministic fallback so browser speech text is never discarded."""
    import re
    t = (transcript or "").strip()
    low = t.lower()
    category, sub = "other", "Misc"
    rules = [
        (("lunch", "dinner", "breakfast", "food", "khana", "chai", "tea", "coffee"), "food", "Food"),
        (("cab", "uber", "ola", "taxi", "auto", "metro", "train", "flight", "travel"), "travel", "Travel"),
        (("hotel", "room", "stay"), "hotel", "Hotel"),
        (("pen", "paper", "notebook", "stationery"), "stationery", "Stationery"),
        (("grocery", "atta", "dal", "rice", "sabzi"), "grocery", "Grocery"),
    ]
    for words, cat, label in rules:
        if any(w in low for w in words):
            category, sub = cat, label
            break
    nums = re.findall(r"(?<!\w)(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d{1,2})?)(?!\w)", low)
    amount = float(nums[-1]) if nums else 0.0
    return _normalise_voice_payload({
        "transcript": t, "category": category, "sub_category": sub,
        "merchant_name": "", "total_amount": amount,
        "items": ([{"name": sub, "quantity": 1, "unit_price": amount}] if amount > 0 else []),
    }, t)


async def _parse_voice_text(transcript: str) -> dict:
    transcript = (transcript or "").strip()
    if not transcript:
        return _basic_voice_fallback("")
    if has_gemini():
        try:
            reply = await gemini_text(
                system_prompt=VOICE_PARSE_PROMPT,
                user_text=f"Transcript: {transcript}\nReturn strict JSON only.",
            )
            txt = _extract_json_block(_strip_code_fence(reply), "{", "}")
            parsed = json.loads(txt)
            out = _normalise_voice_payload(parsed, transcript)
            if out["transcript"] or out["items"] or out["total_amount"] > 0:
                return out
        except Exception:
            logger.exception("Voice text fallback parsing failed")
    return _basic_voice_fallback(transcript)

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
    if not raw:
        raise HTTPException(400, "Empty image")
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 10MB)")
    raw, mime = _prepare_image(raw, 1600)
    try:
        prompt = category_prompt(category)
        reply = await gemini_vision(
            system_prompt=prompt,
            user_text=(
                f"Identify every visible {category} product/item. Product identification is required even "
                "when price is not visible; use unit_price 0 if necessary. Return strict JSON only."
            ),
            image_bytes=raw, mime=mime,
        )
        cleaned = _parse_items_reply(reply)
        fallback_used = False
        if not cleaned:
            fallback_used = True
            second = await gemini_vision(
                system_prompt=PRODUCT_FALLBACK_PROMPT,
                user_text="Inspect this image again as a general product recognizer. Return strict JSON only.",
                image_bytes=raw, mime=mime,
            )
            cleaned = _parse_items_reply(second)
        return {"items": cleaned, "identified": bool(cleaned), "fallback_used": fallback_used}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("AI detection failed")
        raise _ai_error(e, "Product identification failed. Please try a clearer photo.")


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
    asks the user to upload a clearer receipt) instead of hanging past the gateway limit.
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
        return {"utr": "", "found": False, "error": "AI is busy — please upload the receipt again in a moment."}
    except Exception as e:
        logger.exception("UTR extraction failed")
        return {"utr": "", "found": False, "error": "Couldn't read the payment reference — please upload a clearer full receipt."}
    txt = _extract_json_block(_strip_code_fence(reply), "{", "}")
    try:
        parsed = json.loads(txt)
    except Exception:
        parsed = {}
    digits = "".join(c for c in str(parsed.get("utr", "")) if c.isdigit())
    if len(digits) == 12:
        return {"utr": digits, "found": True}
    return {"utr": "", "found": False}


@router.post("/voice/expense-text")
async def voice_expense_text(payload: dict, user=Depends(get_current_user)):
    """Parse browser speech-to-text into the same structured expense draft."""
    transcript = str((payload or {}).get("transcript", "")).strip()
    if not transcript:
        raise HTTPException(422, "No speech text was captured. Please speak again.")
    out = await _parse_voice_text(transcript)
    if not out["transcript"] and not out["items"] and out["total_amount"] == 0:
        raise HTTPException(422, "Could not understand the speech. Please speak the item and amount clearly.")
    return out


@router.post("/voice/expense")
async def voice_expense(
    file: UploadFile = File(...),
    transcript_hint: str = Form(""),
    user=Depends(get_current_user),
):
    """Audio + browser transcript hint -> resilient structured expense draft.

    The browser transcript is a fallback, not a replacement: Gemini audio remains
    authoritative when it succeeds, but a device/browser transcription is never lost
    if audio transcoding or AI audio processing fails.
    """
    raw = await file.read()
    hint = (transcript_hint or "").strip()
    if not raw:
        if hint:
            return await _parse_voice_text(hint)
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

    try:
        mp3 = to_mp3(raw, suffix)
    except Exception:
        if hint:
            logger.warning("Audio transcode failed; using browser transcript fallback")
            return await _parse_voice_text(hint)
        raise HTTPException(400, "Unsupported or corrupted audio. Please re-record and try again.")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.write(mp3)
    tmp.flush()
    tmp.close()

    reply = ""
    try:
        if has_gemini():
            reply = await gemini_transcribe(tmp.name, VOICE_AUDIO_PROMPT)
    except Exception as e:
        logger.exception("Gemini voice processing failed")
        if hint:
            logger.info("Using browser speech transcript after Gemini audio failure")
            return await _parse_voice_text(hint)
        raise _ai_error(e, "Voice transcription failed. Please try again.")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    parsed = {}
    if reply:
        txt = _extract_json_block(_strip_code_fence(reply), "{", "}")
        try:
            parsed = json.loads(txt)
        except Exception:
            parsed = {}
    out = _normalise_voice_payload(parsed, hint)
    if not out["transcript"] and hint:
        out = await _parse_voice_text(hint)
    elif not out["items"] and out["total_amount"] == 0 and hint:
        fallback = await _parse_voice_text(hint)
        if fallback["items"] or fallback["total_amount"] > 0:
            out = fallback
    if not out["transcript"] and not out["items"] and out["total_amount"] == 0:
        raise HTTPException(422, "Could not understand the audio. Please speak the item and amount clearly.")
    return out

