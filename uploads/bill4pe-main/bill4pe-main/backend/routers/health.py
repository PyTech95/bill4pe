"""Post-deploy diagnostics: which providers are configured."""
import os

from fastapi import APIRouter

from services.llm import has_gemini
from services.email import has_email

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/providers")
async def providers():
    """Reports which integrations are ready. Use right after deploying to a VPS."""
    return {
        "ai": {
            "gemini_vision_text": has_gemini(),
            "gemini_audio_voice": has_gemini(),
            "using_own_keys": {
                "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            },
            "fallback_emergent_llm": bool(os.environ.get("EMERGENT_LLM_KEY")),
        },
        "email": {
            "enabled": has_email(),
            "using_own_resend": bool(os.environ.get("RESEND_API_KEY")),
            "sender": os.environ.get("SENDER_EMAIL"),
            "fallback_emergent_email": bool(os.environ.get("EMERGENT_EMAIL_KEY")),
        },
        "payments": {
            "razorpay_configured": bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET")),
            "webhook_secret_set": bool(os.environ.get("RAZORPAY_WEBHOOK_SECRET")),
        },
        "database": {
            "db_name": os.environ.get("DB_NAME"),
        },
    }
