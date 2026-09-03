"""Email delivery — portable.

  * If RESEND_API_KEY is set -> send directly via the Resend SDK (your own
    Resend account). This is what runs on your Hostinger VPS.
  * Else if EMERGENT_EMAIL_KEY is set -> use the Emergent managed proxy
    (preview environment only).
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger("bill4pe")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "BILL4PE")

# Emergent managed proxy (preview only)
EMERGENT_EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_BASE_URL = "https://integrations.emergentagent.com"


def has_email() -> bool:
    return bool(RESEND_API_KEY or EMERGENT_EMAIL_KEY)


async def send_email(recipient: str, subject: str, html: str, reply_to: str | None = None) -> str | None:
    # Preferred: your own Resend account (works anywhere)
    if RESEND_API_KEY:
        import resend
        resend.api_key = RESEND_API_KEY
        params = {
            "from": f"{EMAIL_FROM_NAME} <{SENDER_EMAIL}>",
            "to": [recipient],
            "subject": subject,
            "html": html,
        }
        if reply_to:
            params["reply_to"] = reply_to
        result = await asyncio.to_thread(resend.Emails.send, params)
        return result.get("id") if isinstance(result, dict) else getattr(result, "id", None)

    # Fallback: Emergent managed proxy
    if EMERGENT_EMAIL_KEY:
        payload = {"to": [recipient], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
        if reply_to:
            payload["contact_email"] = reply_to
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMERGENT_EMAIL_KEY},
                json=payload,
            )
        resp.raise_for_status()
        try:
            return resp.json().get("id")
        except Exception:
            return None

    raise RuntimeError("No email provider configured (set RESEND_API_KEY)")


def build_invoice_html(expense: dict, user: dict, verify_url: str | None = None, note: str | None = None) -> str:
    pay = expense.get("payment") or {}
    total = float(expense.get("total", 0) or 0)
    fee = float(expense.get("bill_fee") or 0)
    grand = total + fee
    bill_id = expense.get("bill_id") or expense["id"][:8].upper()
    user_name = (user or {}).get("name", "Customer")

    item_rows = ""
    for it in expense.get("items", []):
        amt = float(it.get("quantity", 1)) * float(it.get("unit_price", 0))
        item_rows += (
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#0F172A;font-size:14px;">{it.get("name","")}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#64748B;font-size:13px;text-align:center;">{it.get("quantity",1):g}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#64748B;font-size:13px;text-align:right;">₹{float(it.get("unit_price",0)):.2f}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#0F172A;font-size:14px;text-align:right;font-weight:600;">₹{amt:.2f}</td>'
            f'</tr>'
        )

    fee_rows = ""
    if fee:
        fee_rows = (
            f'<tr><td colspan="3" style="padding:6px 12px;text-align:right;color:#64748B;font-size:13px;">Subtotal</td>'
            f'<td style="padding:6px 12px;text-align:right;color:#0F172A;font-size:14px;">₹{total:.2f}</td></tr>'
            f'<tr><td colspan="3" style="padding:6px 12px;text-align:right;color:#64748B;font-size:13px;">Convenience Fee</td>'
            f'<td style="padding:6px 12px;text-align:right;color:#0F172A;font-size:14px;">₹{fee:.2f}</td></tr>'
        )

    note_block = ""
    if note:
        note_block = (
            f'<tr><td colspan="4" style="padding:12px;background:#F4F6FA;color:#334155;font-size:13px;line-height:1.6;">'
            f'{note}</td></tr>'
        )

    verify_block = ""
    if verify_url:
        verify_block = (
            f'<div style="text-align:center;margin-top:20px;">'
            f'<a href="{verify_url}" style="display:inline-block;background:#1F6FEB;color:#FFFFFF;text-decoration:none;'
            f'font-size:14px;font-weight:600;padding:12px 24px;border-radius:8px;">Verify &amp; View Invoice</a>'
            f'</div>'
        )

    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#F4F6FA;padding:24px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#FFFFFF;border-radius:12px;overflow:hidden;border:1px solid #E5EAF2;">
        <tr><td style="background:#0A1128;padding:22px 24px;">
          <span style="color:#FFFFFF;font-size:20px;font-weight:800;letter-spacing:0.5px;">BILL4PE</span>
          <span style="color:#94A3B8;font-size:12px;float:right;padding-top:6px;">Official Invoice</span>
        </td></tr>
        <tr><td style="padding:24px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="color:#64748B;font-size:12px;">Bill ID<br/><b style="color:#0F172A;font-size:15px;">{bill_id}</b></td>
              <td style="text-align:right;color:#64748B;font-size:12px;">Merchant<br/><b style="color:#0F172A;font-size:15px;">{pay.get("merchant_name") or "—"}</b></td>
            </tr>
          </table>
          <p style="color:#334155;font-size:14px;margin:18px 0 6px;">Hi, please find the invoice from <b>{user_name}</b> below.</p>
          <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:8px;margin-top:10px;">
            <tr style="background:#0A1128;">
              <td style="padding:8px 12px;color:#FFFFFF;font-size:12px;">Item</td>
              <td style="padding:8px 12px;color:#FFFFFF;font-size:12px;text-align:center;">Qty</td>
              <td style="padding:8px 12px;color:#FFFFFF;font-size:12px;text-align:right;">Unit</td>
              <td style="padding:8px 12px;color:#FFFFFF;font-size:12px;text-align:right;">Amount</td>
            </tr>
            {item_rows}
            {fee_rows}
            <tr><td colspan="3" style="padding:12px;text-align:right;color:#0F172A;font-size:15px;font-weight:700;">GRAND TOTAL</td>
                <td style="padding:12px;text-align:right;color:#0A1128;font-size:16px;font-weight:800;background:#D4FF00;">₹{grand:.2f}</td></tr>
            {note_block}
          </table>
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;">
            <tr><td style="color:#64748B;font-size:12px;padding:4px 0;">Transaction ID</td>
                <td style="text-align:right;color:#0F172A;font-size:13px;">{pay.get("transaction_id") or "—"}</td></tr>
            <tr><td style="color:#64748B;font-size:12px;padding:4px 0;">Payment Method</td>
                <td style="text-align:right;color:#0F172A;font-size:13px;">{pay.get("payment_method","UPI")}</td></tr>
          </table>
          {verify_block}
        </td></tr>
        <tr><td style="padding:14px 24px;background:#F4F6FA;color:#94A3B8;font-size:11px;">
          System-generated reimbursement invoice via BILL4PE · www.bill4pe.com
        </td></tr>
      </table>
    </div>
    """
