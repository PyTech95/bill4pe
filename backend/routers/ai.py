"""AI endpoints: image item detection, autocomplete suggestions, receipt OCR, voice expense."""
import json
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText

from core.config import EMERGENT_LLM_KEY, logger
from core.security import get_current_user
from services.prompts import (
    category_prompt, RECEIPT_PROMPT, VOICE_PARSE_PROMPT, VALID_CATEGORIES,
)

router = APIRouter(tags=["ai"])


@router.post("/ai/detect-items")
async def detect_items(category: str = "food", file: UploadFile = File(...), user=Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 8MB)")
    mime = file.content_type or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        mime = "image/jpeg"
    suffix = ".jpg" if "jpeg" in mime else (".png" if "png" in mime else ".webp")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(raw)
    tmp.flush()
    tmp.close()
    try:
        prompt = category_prompt(category)
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"detect-{uuid.uuid4()}",
            system_message=prompt,
        ).with_model("gemini", "gemini-3-flash-preview")
        msg = UserMessage(
            text=f"Detect all {category} items in this image. Return strict JSON array only.",
            file_contents=[FileContentWithMimeType(file_path=tmp.name, mime_type=mime)],
        )
        reply = await chat.send_message(msg)
        txt = (reply or "").strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        start, end = txt.find("["), txt.rfind("]")
        if start >= 0 and end > start:
            txt = txt[start:end + 1]
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
    except Exception as e:
        logger.exception("AI detection failed")
        raise HTTPException(500, f"AI detection failed: {str(e)[:200]}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@router.post("/ai/suggest-items")
async def suggest_items(payload: dict, user=Depends(get_current_user)):
    """Suggest item names for manual entry autocomplete."""
    if not EMERGENT_LLM_KEY:
        return {"suggestions": []}
    category = payload.get("category", "food")
    query = payload.get("query", "")
    if len(query) < 2:
        return {"suggestions": []}
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"suggest-{uuid.uuid4()}",
            system_message=(
                f"You suggest short Indian {category} item names for autocomplete. "
                f"Return ONLY a JSON array of 5 short strings, no prose. Example: [\"Roti\",\"Rumali Roti\",\"Romali\",\"Roomali Roti\",\"Tandoori Roti\"]"
            ),
        ).with_model("gemini", "gemini-3-flash-preview")
        reply = await chat.send_message(UserMessage(text=f"Suggest items starting with '{query}'"))
        txt = (reply or "").strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        s, e = txt.find("["), txt.rfind("]")
        if s >= 0 and e > s:
            txt = txt[s:e + 1]
        arr = json.loads(txt)
        return {"suggestions": [str(x) for x in arr if isinstance(x, (str, int, float))][:5]}
    except Exception:
        return {"suggestions": []}


@router.post("/ai/scan-receipt")
async def scan_receipt(file: UploadFile = File(...), user=Depends(get_current_user)):
    """OCR a printed receipt photo into structured expense data."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 8MB)")
    mime = file.content_type or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        mime = "image/jpeg"
    suffix = ".jpg" if "jpeg" in mime else (".png" if "png" in mime else ".webp")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(raw)
    tmp.flush()
    tmp.close()
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"receipt-{uuid.uuid4()}",
            system_message=RECEIPT_PROMPT,
        ).with_model("gemini", "gemini-3-flash-preview")
        msg = UserMessage(
            text="Parse this Indian printed receipt. Return strict JSON object only.",
            file_contents=[FileContentWithMimeType(file_path=tmp.name, mime_type=mime)],
        )
        reply = await chat.send_message(msg)
        txt = (reply or "").strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        start, end = txt.find("{"), txt.rfind("}")
        if start >= 0 and end > start:
            txt = txt[start:end + 1]
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
    except Exception as e:
        logger.exception("Receipt OCR failed")
        raise HTTPException(500, f"Receipt OCR failed: {str(e)[:200]}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@router.post("/voice/expense")
async def voice_expense(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Accept audio file → Whisper transcript → Gemini parse → structured draft expense."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
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
    transcript = ""
    try:
        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        with open(tmp.name, "rb") as af:
            stt_resp = await stt.transcribe(
                file=af,
                model="whisper-1",
                response_format="json",
                prompt="Indian expense note. Mentions amounts in rupees, food items, cab/flight, merchant names.",
            )
        transcript = (getattr(stt_resp, "text", "") or "").strip()
        if not transcript:
            raise HTTPException(422, "Could not hear anything in the audio")

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"voice-parse-{uuid.uuid4()}",
            system_message=VOICE_PARSE_PROMPT,
        ).with_model("gemini", "gemini-3-flash-preview")
        reply = await chat.send_message(UserMessage(text=f"Transcript: {transcript}"))
        txt = (reply or "").strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        start, end = txt.find("{"), txt.rfind("}")
        if start >= 0 and end > start:
            txt = txt[start:end + 1]
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
