"""LLM helper layer — Google Gemini for ALL AI features (vision, text, audio).

BILL4PE uses Google Gemini for AI functionality. GEMINI_API_KEY powers:
  - vision (receipt / image understanding)
  - text generation (expense parsing)
  - audio transcription (Hindi / English / Hinglish voice notes)

Provider selection:
  * If GEMINI_API_KEY is set -> use the official `google-genai` SDK directly
    (this is what runs on the VPS — the only key you need).
  * Else if EMERGENT_LLM_KEY is set -> use the Emergent managed proxy
    (emergentintegrations) as an OPTIONAL preview-only fallback. It routes to
    Gemini and introduces NO OpenAI dependency.

No OpenAI / Whisper dependency anywhere. Audio transcription is done by Gemini's
native audio understanding via the Files API.

Transient Gemini errors (429 rate-limit / 503 high-demand) are retried
automatically with exponential backoff so brief spikes don't reach the user.
"""
from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
import tempfile
import uuid

from core.config import (
    EMERGENT_LLM_KEY,
    GEMINI_API_KEY,
    GEMINI_AUDIO_MODEL,
    GEMINI_TEXT_MODEL,
    GEMINI_VISION_MODEL,
    logger,
)

DEFAULT_TRANSCRIBE_PROMPT = """Transcribe this audio accurately.

The speaker may speak Hindi, English, or Hinglish.

Preserve numbers, merchant names, amounts, dates and payment-related information accurately.

Return only the transcription without explanations."""


# ---------------- Retry helper for transient Gemini errors ----------------
# Only retry GENUINELY transient, server-side conditions (503 high-demand /
# overloaded). We do NOT retry 429/quota: the free-tier limit is a DAILY cap, so
# retrying just makes the user wait several seconds for the same failure.
_TRANSIENT_MARKERS = (
    "503", "unavailable", "overloaded", "high demand", "service is currently",
)
_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "3"))
_RETRY_BASE_DELAY = float(os.environ.get("GEMINI_RETRY_BASE_DELAY", "1.5"))


def _is_transient(exc: Exception) -> bool:
    m = str(exc).lower()
    return any(k in m for k in _TRANSIENT_MARKERS)


async def _retry(make_coro, *, label: str = "gemini"):
    """Run an awaitable factory, retrying transient errors with backoff.

    `make_coro` is a zero-arg callable returning a fresh coroutine each time.
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await make_coro()
        except Exception as exc:  # noqa: BLE001 - we re-raise below
            last_exc = exc
            if attempt >= _MAX_RETRIES or not _is_transient(exc):
                raise
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"{label}: transient error (attempt {attempt + 1}/{_MAX_RETRIES}), "
                f"retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    raise last_exc  # pragma: no cover


def has_gemini() -> bool:
    return bool(GEMINI_API_KEY or EMERGENT_LLM_KEY)


def has_key() -> bool:
    return has_gemini()


# ---------------- Gemini: vision (image understanding) ----------------
async def gemini_vision(system_prompt: str, user_text: str, image_bytes: bytes, mime: str, model: str | None = None) -> str:
    _model = model or GEMINI_VISION_MODEL
    if GEMINI_API_KEY:
        def _run():
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            resp = client.models.generate_content(
                model=_model,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime or "image/jpeg"), user_text],
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            )
            return (resp.text or "").strip()
        return await _retry(lambda: asyncio.to_thread(_run), label="gemini_vision")

    async def _emergent():
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        b64 = base64.b64encode(image_bytes).decode()
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"vision-{uuid.uuid4()}",
                       system_message=system_prompt).with_model("gemini", _model)
        reply = await chat.send_message(UserMessage(text=user_text, file_contents=[ImageContent(image_base64=b64)]))
        return (reply or "").strip()
    return await _retry(_emergent, label="gemini_vision")


# ---------------- Gemini: plain text ----------------
async def gemini_text(system_prompt: str, user_text: str) -> str:
    if GEMINI_API_KEY:
        def _run():
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            resp = client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=[user_text],
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            )
            return (resp.text or "").strip()
        return await _retry(lambda: asyncio.to_thread(_run), label="gemini_text")

    async def _emergent():
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"text-{uuid.uuid4()}",
                       system_message=system_prompt).with_model("gemini", GEMINI_TEXT_MODEL)
        reply = await chat.send_message(UserMessage(text=user_text))
        return (reply or "").strip()
    return await _retry(_emergent, label="gemini_text")


# ---------------- Gemini: audio (voice transcription) ----------------
async def gemini_transcribe(file_path: str, prompt: str = "") -> str:
    """Transcribe an audio file (Hindi / English / Hinglish) with Gemini.

    Supports .webm, .m4a, .mp4, .wav, .mp3 (transcode webm/opus to mp3 upstream).
    Uses the Gemini Files API: upload -> generate -> delete. All blocking SDK
    calls run in a worker thread so the FastAPI event loop is not blocked.
    Transient 429/503 errors are retried with backoff. Returns plain text.
    """
    instruction = prompt or DEFAULT_TRANSCRIBE_PROMPT

    if GEMINI_API_KEY:
        def _run():
            from google import genai
            from google.genai import types
            with open(file_path, "rb") as f:
                data = f.read()
            mime = mimetypes.guess_type(file_path)[0] or "audio/mp3"
            client = genai.Client(api_key=GEMINI_API_KEY)
            # Inline audio (Part.from_bytes) — for short voice notes this avoids the
            # extra Files API upload + delete round-trips and is faster.
            resp = client.models.generate_content(
                model=GEMINI_AUDIO_MODEL,
                contents=[types.Part.from_bytes(data=data, mime_type=mime), instruction],
            )
            return (resp.text or "").strip()
        return await _retry(lambda: asyncio.to_thread(_run), label="gemini_transcribe")

    async def _emergent():
        from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
        mime = mimetypes.guess_type(file_path)[0] or "audio/mp3"
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"audio-{uuid.uuid4()}",
                       system_message=instruction).with_model("gemini", GEMINI_AUDIO_MODEL)
        reply = await chat.send_message(
            UserMessage(text=instruction, file_contents=[FileContentWithMimeType(mime_type=mime, file_path=file_path)])
        )
        return (reply or "").strip()
    return await _retry(_emergent, label="gemini_transcribe")


__all__ = [
    "gemini_vision",
    "gemini_text",
    "gemini_transcribe",
    "has_gemini",
    "has_key",
    "logger",
]
