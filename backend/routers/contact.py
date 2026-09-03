"""Landing-page contact form submissions."""
import os
import uuid
import asyncio
import logging
from fastapi import APIRouter

import resend

from core.db import db
from core.models import ContactMsg
from core.security import now_iso

router = APIRouter(tags=["contact"])
logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
CONTACT_INBOX = "connect@bill4pe.com"

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def _build_html(body: ContactMsg) -> str:
    phone_row = (
        f'<tr><td style="padding:8px 0;color:#64748B;font-size:12px;text-transform:uppercase;letter-spacing:1px;">Phone</td>'
        f'<td style="padding:8px 0;color:#0F172A;font-size:14px;">{body.phone}</td></tr>'
        if body.phone else ""
    )
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#F4F6FA;padding:24px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;background:#FFFFFF;border-radius:12px;overflow:hidden;border:1px solid #E5EAF2;">
        <tr><td style="background:#002970;padding:20px 24px;color:#FFFFFF;font-size:18px;font-weight:700;">New BILL4PE contact request</td></tr>
        <tr><td style="padding:24px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="padding:8px 0;color:#64748B;font-size:12px;text-transform:uppercase;letter-spacing:1px;width:90px;">Name</td>
                <td style="padding:8px 0;color:#0F172A;font-size:14px;">{body.name}</td></tr>
            <tr><td style="padding:8px 0;color:#64748B;font-size:12px;text-transform:uppercase;letter-spacing:1px;">Email</td>
                <td style="padding:8px 0;color:#0F172A;font-size:14px;"><a href="mailto:{body.email}" style="color:#1F6FEB;text-decoration:none;">{body.email}</a></td></tr>
            {phone_row}
          </table>
          <div style="margin-top:18px;padding:14px 16px;background:#F4F6FA;border-radius:8px;color:#0F172A;font-size:14px;line-height:1.6;white-space:pre-wrap;">{body.message}</div>
        </td></tr>
        <tr><td style="padding:14px 24px;background:#F4F6FA;color:#94A3B8;font-size:11px;">Sent from bill4pe.com contact form</td></tr>
      </table>
    </div>
    """


@router.post("/contact")
async def contact(body: ContactMsg):
    record = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "email": body.email,
        "phone": body.phone,
        "message": body.message,
        "created_at": now_iso(),
        "email_sent": False,
        "email_id": None,
    }

    if RESEND_API_KEY:
        try:
            params = {
                "from": SENDER_EMAIL,
                "to": [CONTACT_INBOX],
                "reply_to": body.email,
                "subject": f"New contact: {body.name}",
                "html": _build_html(body),
            }
            email = await asyncio.to_thread(resend.Emails.send, params)
            record["email_sent"] = True
            record["email_id"] = email.get("id") if isinstance(email, dict) else None
        except Exception as exc:  # noqa: BLE001
            logger.error("Resend email failed: %s", exc)
    else:
        logger.warning("RESEND_API_KEY not set — contact message stored but email not sent.")

    await db.contact_messages.insert_one(record)
    return {"ok": True, "emailed": record["email_sent"]}
