"""PDF generation for individual bills and consolidated expense reports.

Fonts and logo are bundled under backend/assets/ so PDFs render identically on
any host (including a self-managed VPS). FreeSans carries the ₹ (U+20B9) glyph.
"""
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from core.config import calc_bill_fee

# ---- Bundled assets: fonts (₹ capable) + transparent logo ----
ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT, FONT_B = "Helvetica", "Helvetica-Bold"
try:
    _reg = ASSETS / "FreeSans.ttf"
    _regb = ASSETS / "FreeSansBold.ttf"
    if _reg.exists():
        pdfmetrics.registerFont(TTFont("B4P", str(_reg)))
        pdfmetrics.registerFont(TTFont("B4P-Bold", str(_regb if _regb.exists() else _reg)))
        FONT, FONT_B = "B4P", "B4P-Bold"
except Exception:
    pass
LOGO_PATH = ASSETS / "logo_transparent.png"

# ---- IST (Indian Standard Time) ----
try:
    from zoneinfo import ZoneInfo
    _IST = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover
    _IST = timezone(timedelta(hours=5, minutes=30))


def _fmt_ist(iso_str: Optional[str] = None) -> str:
    """Format an ISO timestamp (or now) as '10 Aug 2026, 03:45 PM IST'."""
    dt = None
    if iso_str:
        try:
            dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        except Exception:
            dt = None
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_IST).strftime("%d %b %Y, %I:%M %p IST")


def _esc(v) -> str:
    s = "" if v is None else str(v)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf_bytes(expense: dict, user: dict) -> bytes:
    user = user or {}
    user_name = user.get("name", "Customer")
    user_gstin = user.get("gstin")
    user_company = user.get("company_name") or user.get("corporate_name")
    user_phone = user.get("phone")
    user_email = user.get("email")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, title="BILL4PE Invoice")
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#0A1128")
    LIME = colors.HexColor("#D4FF00")
    LIGHT = colors.HexColor("#F4F5F7")
    BORDER = colors.HexColor("#E2E8F0")
    MUTED = colors.HexColor("#64748B")

    meta_st = ParagraphStyle("meta", parent=styles["Normal"], fontName=FONT,
                             fontSize=9, textColor=MUTED, leading=13, alignment=2)
    sub_st = ParagraphStyle("sub", parent=styles["Normal"], fontName=FONT,
                            fontSize=9, textColor=MUTED, leading=12)
    h2_st = ParagraphStyle("h2", parent=styles["Heading2"], fontName=FONT_B,
                           fontSize=10.5, textColor=NAVY, spaceBefore=8, spaceAfter=4)
    body_st = ParagraphStyle("body", parent=styles["Normal"], fontName=FONT,
                             fontSize=10, leading=14, textColor=colors.black)
    party_st = ParagraphStyle("party", parent=styles["Normal"], fontName=FONT,
                              fontSize=9, textColor=NAVY, leading=14)

    story = []

    # ---- QR for authenticity ----
    bill_id_str = expense.get("bill_id") or expense["id"][:8].upper()
    verify_url = f"https://www.bill4pe.com/verify/{bill_id_str}"
    qr_widget = QrCodeWidget(verify_url, barLevel="M")
    b = qr_widget.getBounds()
    qr_size = 22 * mm
    qr_drawing = Drawing(qr_size, qr_size,
                         transform=[qr_size / (b[2] - b[0]), 0, 0, qr_size / (b[3] - b[1]), 0, 0])
    qr_drawing.add(qr_widget)

    # ---- Header: logo (transparent) | invoice meta | QR ----
    if LOGO_PATH.exists():
        logo_flow = Image(str(LOGO_PATH), width=44 * mm, height=44 * mm * 724 / 2172)
        logo_flow.hAlign = "LEFT"
    else:
        logo_flow = Paragraph("<b>BILL4PE</b>", ParagraphStyle(
            "lt", fontName=FONT_B, fontSize=22, textColor=NAVY))

    date_ist = _fmt_ist(expense.get("created_at"))
    _snap = expense.get("bill_snapshot") or {}
    _doc_title = _snap.get("document_title") or "TAX INVOICE"
    meta = Paragraph(
        f"<b><font size=13 color='#0A1128'>{_esc(_doc_title)}</font></b><br/>"
        f"Bill ID: <b>{_esc(bill_id_str)}</b><br/>"
        f"Date: {date_ist}", meta_st)

    header_tbl = Table([[logo_flow, meta, qr_drawing]], colWidths=[62 * mm, 88 * mm, 24 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2.2, NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 3))
    story.append(Paragraph("Intelligent UPI billing — scan the QR to verify authenticity", sub_st))
    story.append(Spacer(1, 12))

    pay = expense.get("payment", {}) or {}
    trip = pay.get("trip") or None
    stay = pay.get("stay") or None
    cat_label = (expense.get("category") or "").title() or "—"
    sub_label = expense.get("sub_category") or ""
    nature = (trip or {}).get("nature_of_business") or (stay or {}).get("nature_of_business")
    if not nature:
        nature = f"{cat_label}{' / ' + sub_label if sub_label else ''}"

    # ---- Parties: Billed To (customer) | Paid To (merchant) side by side ----
    billed_lines = [f"<b>BILLED TO</b>", f"<font size=11 color='#0A1128'><b>{_esc(user_name)}</b></font>"]
    if user_company:
        billed_lines.append(_esc(user_company))
    if user_gstin:
        billed_lines.append(f"GSTIN: <b>{_esc(user_gstin)}</b>")
    if user_phone:
        billed_lines.append(f"Phone: {_esc(user_phone)}")
    if user_email:
        billed_lines.append(_esc(user_email))
    billed_para = Paragraph("<br/>".join(billed_lines), party_st)

    merch_lines = [
        "<b>PAID TO (MERCHANT)</b>",
        f"<font size=11 color='#0A1128'><b>{_esc(pay.get('merchant_name') or '—')}</b></font>",
    ]
    if pay.get("merchant_upi"):
        merch_lines.append(f"UPI: {_esc(pay.get('merchant_upi'))}")
    if pay.get("merchant_mobile"):
        merch_lines.append(f"Mobile: {_esc(pay.get('merchant_mobile'))}")
    merch_lines.append(f"Nature: {_esc(nature)}")
    merch_para = Paragraph("<br/>".join(merch_lines), party_st)

    parties = Table([[billed_para, merch_para]], colWidths=[87 * mm, 87 * mm])
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.append(parties)
    story.append(Spacer(1, 10))

    # ---- Transaction details ----
    lat, lng = pay.get("latitude"), pay.get("longitude")
    loc = f"{lat:.5f}, {lng:.5f}" if isinstance(lat, (int, float)) and isinstance(lng, (int, float)) else "—"
    txn_tbl = Table([
        ["Transaction ID", pay.get("transaction_id") or "—", "Payment Method", pay.get("payment_method", "UPI")],
        ["Status", _snap.get("merchant_payment_status_label") or (pay.get("payment_status") or "paid").title(), "Location", loc],
    ], colWidths=[32 * mm, 58 * mm, 32 * mm, 52 * mm])
    txn_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
        ("FONTNAME", (0, 0), (0, -1), FONT_B),
        ("FONTNAME", (2, 0), (2, -1), FONT_B),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(txn_tbl)
    story.append(Spacer(1, 12))

    # ---- Items ----
    story.append(Paragraph("ITEMS", h2_st))
    rows = [["#", "Item", "Qty", "Unit Price (₹)", "Amount (₹)"]]
    for idx, it in enumerate(expense.get("items", []), 1):
        amt = float(it["quantity"]) * float(it["unit_price"])
        rows.append([str(idx), it["name"], f"{it['quantity']:g}",
                     f"{it['unit_price']:.2f}", f"{amt:.2f}"])

    subtotal = float(expense.get("total", 0) or 0)
    show_fee = bool(expense.get("bill_generated"))
    raw_fee = expense.get("bill_fee")
    if raw_fee is not None:
        fee_amt = float(raw_fee)
    elif show_fee:
        fee_amt = calc_bill_fee(subtotal)
    else:
        fee_amt = 0.0
    grand_total = subtotal + fee_amt
    fee_pct = expense.get("bill_fee_percent")
    fee_label = (
        f"Convenience Fee ({float(fee_pct):g}% of bill)"
        if fee_pct is not None else "Convenience Fee"
    )

    if show_fee and fee_amt > 0:
        rows.append(["", "", "", "Subtotal", f"{subtotal:.2f}"])
        rows.append(["", fee_label, "", "", f"{fee_amt:.2f}"])
        rows.append(["", "", "", "GRAND TOTAL", f"₹ {grand_total:.2f}"])
    else:
        rows.append(["", "", "", "TOTAL", f"₹ {subtotal:.2f}"])

    items_tbl = Table(rows, colWidths=[12 * mm, 86 * mm, 18 * mm, 30 * mm, 32 * mm])
    base_style = [
        ("FONTNAME", (0, 0), (-1, 0), FONT_B),
        ("FONTNAME", (0, 1), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if show_fee:
        base_style += [
            ("INNERGRID", (0, 0), (-1, -4), 0.3, BORDER),
            ("FONTNAME", (3, -3), (-1, -3), FONT_B),
            ("BACKGROUND", (3, -3), (-1, -3), LIGHT),
            ("ALIGN", (1, -2), (1, -2), "LEFT"),
            ("FONTNAME", (1, -2), (1, -2), FONT_B),
            ("TEXTCOLOR", (1, -2), (1, -2), MUTED),
            ("BACKGROUND", (1, -2), (-1, -2), LIGHT),
            ("FONTNAME", (3, -1), (-1, -1), FONT_B),
            ("BACKGROUND", (3, -1), (-1, -1), LIME),
            ("TEXTCOLOR", (3, -1), (-1, -1), NAVY),
        ]
    else:
        base_style += [
            ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
            ("FONTNAME", (3, -1), (-1, -1), FONT_B),
            ("BACKGROUND", (3, -1), (-1, -1), LIME),
            ("TEXTCOLOR", (3, -1), (-1, -1), NAVY),
        ]
    items_tbl.setStyle(TableStyle(base_style))
    story.append(items_tbl)
    story.append(Spacer(1, 12))

    # ---- Stay details (hotel) ----
    if stay and (stay.get("hotel_name") or stay.get("check_in") or stay.get("nights")):
        story.append(Paragraph("STAY DETAILS", h2_st))
        try:
            rate = float(stay.get("per_night_rate") or 0)
        except Exception:
            rate = 0.0
        nights = stay.get("nights") or 0
        stay_tbl = Table([
            ["Hotel Name", stay.get("hotel_name") or "—"],
            ["Room Type", stay.get("room_type") or "—"],
            ["Check-in", stay.get("check_in") or "—"],
            ["Check-out", stay.get("check_out") or "—"],
            ["Number of Nights", f"{nights} night{'s' if nights != 1 else ''}"],
            ["Per-night Rate", f"₹ {rate:.2f}" if rate else "—"],
            ["Total Amount", f"₹ {float(expense.get('total', 0)):.2f}"],
        ], colWidths=[55 * mm, 123 * mm])
        stay_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
            ("FONTNAME", (0, 0), (0, -1), FONT_B),
            ("BACKGROUND", (0, 0), (0, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("FONTNAME", (1, -1), (1, -1), FONT_B),
            ("BACKGROUND", (1, -1), (1, -1), LIME),
            ("TEXTCOLOR", (1, -1), (1, -1), NAVY),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(stay_tbl)
        story.append(Spacer(1, 12))

    # ---- Trip details (travel) ----
    if trip and (trip.get("from_text") or trip.get("to_text") or trip.get("pickup_lat") is not None):
        story.append(Paragraph("TRIP DETAILS", h2_st))
        trip_tbl = Table([
            ["From", trip.get("from_text") or "—"],
            ["To", trip.get("to_text") or "—"],
            ["Amount", f"₹ {float(expense.get('total', 0)):.2f}"],
        ], colWidths=[45 * mm, 133 * mm])
        trip_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
            ("FONTNAME", (0, 0), (0, -1), FONT_B),
            ("BACKGROUND", (0, 0), (0, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(trip_tbl)
        story.append(Spacer(1, 10))

        def fmt(v):
            return f"{v:.6f}" if isinstance(v, (int, float)) else "—"

        gps_tbl = Table([
            ["", "Latitude", "Longitude"],
            ["Picking Point", fmt(trip.get("pickup_lat")), fmt(trip.get("pickup_lng"))],
            ["Dropping Point", fmt(trip.get("drop_lat")), fmt(trip.get("drop_lng"))],
        ], colWidths=[50 * mm, 64 * mm, 64 * mm])
        gps_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), FONT_B),
            ("FONTNAME", (0, 1), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 1), (0, -1), FONT_B),
            ("TEXTCOLOR", (0, 1), (0, -1), MUTED),
            ("BACKGROUND", (0, 1), (0, -1), LIGHT),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(gps_tbl)
        story.append(Spacer(1, 12))

    # ---- Notes ----
    note_txt = (expense.get("notes") or "").strip()
    if note_txt:
        story.append(Paragraph("NOTES", h2_st))
        story.append(Paragraph(_esc(note_txt).replace("\n", "<br/>"), body_st))
        story.append(Spacer(1, 12))

    # ---- Footer ----
    story.append(Paragraph(
        "<b>Note:</b> This is a system-generated reimbursement invoice via BILL4PE. "
        "Items, prices and merchant details were captured at point of purchase. "
        "For corporate reimbursement, attach this invoice to your expense report.", sub_st))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Generated: {_fmt_ist()} | BILL4PE © 2026 | www.bill4pe.com", sub_st))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def build_report_pdf(report: dict, expenses: List[dict], user_name: str) -> bytes:
    """Build a multi-bill expense report PDF — a single sheet per company submission."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#050816")
    BRAND = colors.HexColor("#1F6FEB")
    BORDER = colors.HexColor("#E2E8F0")

    title_st = ParagraphStyle("title", parent=styles["Heading1"], fontName=FONT_B,
                              fontSize=22, textColor=NAVY, leading=26, spaceAfter=4)
    sub_st = ParagraphStyle("sub", parent=styles["Normal"], fontName=FONT,
                            fontSize=9, textColor=colors.HexColor("#64748B"), leading=12)
    h2_st = ParagraphStyle("h2", parent=styles["Heading2"], fontName=FONT_B,
                           fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=4)

    story = []
    total = sum(float(e.get("total", 0)) for e in expenses)
    by_cat: dict = {}
    for e in expenses:
        c = e.get("category", "other")
        by_cat[c] = by_cat.get(c, 0) + float(e.get("total", 0))

    header_tbl = Table([
        [Paragraph("<b>BILL4PE</b>", title_st),
         Paragraph(f"<b>EXPENSE REPORT</b><br/>"
                   f"Report ID: {report['id'][:8].upper()}<br/>"
                   f"Date: {_fmt_ist(report.get('created_at'))}<br/>"
                   f"Items: {len(expenses)}", sub_st)],
    ], colWidths=[90 * mm, 90 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, BRAND),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 4))
    story.append(Paragraph(report.get("title", "Expense Report"), title_st))
    story.append(Paragraph(f"Submitted by: <b>{_esc(user_name)}</b>", sub_st))
    if report.get("notes"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<i>{_esc(report.get('notes'))}</i>", sub_st))
    story.append(Spacer(1, 14))

    story.append(Paragraph("SUMMARY", h2_st))
    sum_rows = [["Category", "Amount (INR)"]]
    for c, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        sum_rows.append([c.title(), f"{v:.2f}"])
    sum_rows.append(["TOTAL", f"{total:.2f}"])
    sum_tbl = Table(sum_rows, colWidths=[120 * mm, 60 * mm])
    sum_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), FONT_B),
        ("FONTNAME", (0, 1), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
        ("FONTNAME", (0, -1), (-1, -1), FONT_B),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 16))

    story.append(Paragraph("LINE ITEMS", h2_st))
    rows = [["#", "Date", "Category", "Merchant", "Bill ID", "Amount (₹)"]]
    for idx, e in enumerate(expenses, 1):
        pay = e.get("payment") or {}
        rows.append([
            str(idx),
            _fmt_ist(e.get("created_at")).replace(" IST", ""),
            (e.get("category", "") + ("/" + e["sub_category"] if e.get("sub_category") else "")).title(),
            (pay.get("merchant_name") or "—")[:24],
            (e.get("bill_id") or e["id"][:6].upper()),
            f"{float(e.get('total', 0)):.2f}",
        ])
    rows.append(["", "", "", "", "TOTAL", f"₹ {total:.2f}"])
    items_tbl = Table(rows, colWidths=[9 * mm, 40 * mm, 32 * mm, 42 * mm, 27 * mm, 28 * mm])
    items_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), FONT_B),
        ("FONTNAME", (0, 1), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
        ("FONTNAME", (4, -1), (-1, -1), FONT_B),
        ("BACKGROUND", (4, -1), (-1, -1), BRAND),
        ("TEXTCOLOR", (4, -1), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 20))

    story.append(Paragraph(
        "<b>Note:</b> This consolidated expense report is generated by BILL4PE based on "
        "individual UPI transactions captured at the point of purchase. Each line item links "
        "to its own audit-trail bill (merchant, UPI ID, transaction ID, geo and timestamp). "
        "Attach this report to your reimbursement claim.", sub_st))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Generated: {_fmt_ist()} | BILL4PE © 2026 | www.bill4pe.com", sub_st))

    doc.build(story)
    buf.seek(0)
    return buf.read()
