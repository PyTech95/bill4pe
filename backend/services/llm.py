"""LLM helper layer using official standard SDKs.

- OpenAI Whisper STT via `openai` SDK
- Google Gemini (vision + text) via the new official `google-genai` SDK

Replaces the previous `emergentintegrations` wrapper so the backend can
run on any Ubuntu VPS without proprietary Emergent libraries.

Env vars consumed (set in backend/.env):
    OPENAI_API_KEY       – for Whisper STT (and any future GPT calls)
    GEMINI_API_KEY       – for Gemini vision + text
    OPENAI_WHISPER_MODEL – default "whisper-1"
    GEMINI_VISION_MODEL  – default "gemini-1.5-flash"
    GEMINI_TEXT_MODEL    – default "gemini-1.5-flash"
"""
from __future__ import annotations

import asyncio
from typing import Optional

from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI

from core.config import (
    GEMINI_API_KEY,
    GEMINI_TEXT_MODEL,
    GEMINI_VISION_MODEL,
    OPENAI_API_KEY,
    OPENAI_WHISPER_MODEL,
    logger,
)

# ---------------------------------------------------------------------------
# Gemini setup (lazy)
# ---------------------------------------------------------------------------
_gemini_client: Optional[genai.Client] = None


def _gemini() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not configured")
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


async def gemini_vision(system_prompt: str, user_text: str, image_bytes: bytes, mime: str) -> str:
    """Send image + text to Gemini vision; return raw text reply."""
    client = _gemini()

    def _call() -> str:
        resp = client.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type=mime),
                user_text,
            ],
            config=genai_types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return (resp.text or "").strip()

    return await asyncio.to_thread(_call)


async def gemini_text(system_prompt: str, user_text: str) -> str:
    """Send a pure text prompt to Gemini; return raw text reply."""
    client = _gemini()

    def _call() -> str:
        resp = client.models.generate_content(
            model=GEMINI_TEXT_MODEL,
            contents=user_text,
            config=genai_types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return (resp.text or "").strip()

    return await asyncio.to_thread(_call)


# ---------------------------------------------------------------------------
# OpenAI Whisper setup
# ---------------------------------------------------------------------------
_openai_client: Optional[AsyncOpenAI] = None


def _openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


async def openai_transcribe(file_path: str, prompt: str = "") -> str:
    """Transcribe an audio file via Whisper; return text."""
    client = _openai()
    with open(file_path, "rb") as af:
        resp = await client.audio.transcriptions.create(
            model=OPENAI_WHISPER_MODEL,
            file=af,
            response_format="json",
            prompt=prompt or "",
        )
    return (getattr(resp, "text", "") or "").strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def has_gemini() -> bool:
    return bool(GEMINI_API_KEY)


def has_openai() -> bool:
    return bool(OPENAI_API_KEY)


__all__ = [
    "gemini_vision",
    "gemini_text",
    "openai_transcribe",
    "has_gemini",
    "has_openai",
    "logger",
]
