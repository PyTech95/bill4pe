"""PDF generation for individual bills and consolidated expense reports."""
import io
from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

from core.config import calc_bill_fee
from core.security import now_iso


def build_pdf_bytes(expense: dict, user: dict) -> bytes:
    user_name = (user or {}).get("name", "Customer")
    user_gstin = (user or {}).get("gstin")
    user_company = (user or {}).get("company_name") or (user or {}).get("corporate_name")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#0A1128")
    LIME = colors.HexColor("#D4FF00")
    LIGHT = colors.HexColor("#F4F5F7")
    BORDER = colors.HexColor("#E2E8F0")

    title_st = ParagraphStyle("title", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=22, textColor=NAVY, leading=26, spaceAfter=4)
    sub_st = ParagraphStyle("sub", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=9, textColor=colors.HexColor("#64748B"), leading=12)
    h2_st = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                           fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=4)
    body_st = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica",
                             fontSize=10, leading=14, textColor=colors.black)

    story = []
    # Build a QR for bill authenticity verification
    bill_id_str = expense.get('bill_id') or expense['id'][:8].upper()
    verify_url = f"https://www.bill4pe.com/verify/{bill_id_str}"
    qr_widget = QrCodeWidget(verify_url, barLevel='M')
    qr_bounds = qr_widget.getBounds()
    qr_w = qr_bounds[2] - qr_bounds[0]
    qr_h = qr_bounds[3] - qr_bounds[1]
    qr_size = 22 * mm
    qr_drawing = Drawing(qr_size, qr_size, transform=[qr_size / qr_w, 0, 0, qr_size / qr_h, 0, 0])
    qr_drawing.add(qr_widget)

    # Header with QR on the right
    header_tbl = Table([
        [Paragraph("<b>BILL4PE</b>", title_st),
         Paragraph(f"<b>OFFICIAL INVOICE</b><br/>"
                   f"Bill ID: {bill_id_str}<br/>"
                   f"Date: {expense['created_at'][:16].replace('T', ' ')}", sub_st),
         qr_drawing],
    ], colWidths=[70 * mm, 85 * mm, 25 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("An Intelligent Billing — Scan QR to verify authenticity", sub_st))
    story.append(Spacer(1, 14))

    pay = expense.get("payment", {}) or {}
    trip = pay.get("trip") or None
    stay = pay.get("stay") or None
    # Merchant info
    cat_label = (expense.get("category") or "").title() or "—"
    sub_label = expense.get("sub_category") or ""
    # Prefer trip/stay nature_of_business when present
    nature = None
    if trip:
        nature = trip.get("nature_of_business")
    if stay and not nature:
        nature = stay.get("nature_of_business")
    if not nature:
        nature = f"{cat_label}{' / ' + sub_label if sub_label else ''}"
    story.append(Paragraph("MERCHANT DETAILS", h2_st))
    m_tbl = Table([
        ["Merchant Name", pay.get("merchant_name") or "—"],
        ["Mobile", pay.get("merchant_mobile") or "—"],
        ["UPI ID", pay.get("merchant_upi") or "—"],
        ["Nature of Business", nature],
        ["Transaction ID", pay.get("transaction_id") or "—"],
        ["Payment Method", pay.get("payment_method", "UPI")],
        ["Location (Lat, Lng)", f"{pay.get('latitude', '—')}, {pay.get('longitude', '—')}"],
    ], colWidths=[45 * mm, 135 * mm])
    m_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(m_tbl)
    story.append(Spacer(1, 12))

    # Customer
    story.append(Paragraph("BILLED TO", h2_st))
    story.append(Paragraph(f"<b>{user_name}</b>", body_st))
    if user_company:
        story.append(Paragraph(user_company, sub_st))
    if user_gstin:
        story.append(Paragraph(f"<b>GSTIN:</b> {user_gstin}", sub_st))
    story.append(Paragraph(f"Expense Category: {expense.get('category')}"
                           f"{' / ' + expense['sub_category'] if expense.get('sub_category') else ''}", sub_st))
    story.append(Spacer(1, 12))

    # Items
    story.append(Paragraph("ITEMS", h2_st))
    rows = [["#", "Item", "Qty", "Unit Price (₹)", "Amount (₹)"]]
    for idx, it in enumerate(expense.get("items", []), 1):
        amt = float(it["quantity"]) * float(it["unit_price"])
        rows.append([str(idx), it["name"], f"{it['quantity']:g}",
                     f"{it['unit_price']:.2f}", f"{amt:.2f}"])

    subtotal = float(expense.get("total", 0) or 0)
    # Convenience Fee row (charged when bill is generated) — 1% of subtotal, min ₹1
    show_fee = bool(expense.get("bill_generated"))
    fee_amt = float(expense.get("bill_fee") or 0.0) if show_fee else 0.0
    if show_fee and not fee_amt:
        fee_amt = calc_bill_fee(subtotal)
    grand_total = subtotal + fee_amt

    if show_fee:
        rows.append(["", "", "", "Subtotal", f"{subtotal:.2f}"])
        rows.append(["", "Convenience Fee (1% of bill)", "", "", f"{fee_amt:.2f}"])
        rows.append(["", "", "", "GRAND TOTAL", f"₹ {grand_total:.2f}"])
    else:
        rows.append(["", "", "", "TOTAL", f"₹ {subtotal:.2f}"])

    items_tbl = Table(rows, colWidths=[12 * mm, 88 * mm, 18 * mm, 30 * mm, 32 * mm])
    base_style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
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
        # last row = Grand Total; -2 = Convenience Fee; -3 = Subtotal
        base_style += [
            ("INNERGRID", (0, 0), (-1, -4), 0.3, BORDER),
            ("FONTNAME", (3, -3), (-1, -3), "Helvetica-Bold"),
            ("BACKGROUND", (3, -3), (-1, -3), LIGHT),
            ("ALIGN", (1, -2), (1, -2), "LEFT"),
            ("FONTNAME", (1, -2), (1, -2), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, -2), (1, -2), colors.HexColor("#64748B")),
            ("BACKGROUND", (1, -2), (-1, -2), LIGHT),
            ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (3, -1), (-1, -1), LIME),
            ("TEXTCOLOR", (3, -1), (-1, -1), NAVY),
        ]
    else:
        base_style += [
            ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
            ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (3, -1), (-1, -1), LIME),
            ("TEXTCOLOR", (3, -1), (-1, -1), NAVY),
        ]
    items_tbl.setStyle(TableStyle(base_style))
    story.append(items_tbl)
    story.append(Spacer(1, 12))

    # Stay details (only for hotel category)
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
        ], colWidths=[55 * mm, 125 * mm])
        stay_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
            ("BACKGROUND", (0, 0), (0, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("FONTNAME", (1, -1), (1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (1, -1), (1, -1), LIME),
            ("TEXTCOLOR", (1, -1), (1, -1), NAVY),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(stay_tbl)
        story.append(Spacer(1, 12))

    # Trip details (only for travel category)
    if trip and (trip.get("from_text") or trip.get("to_text") or trip.get("pickup_lat") is not None):
        story.append(Paragraph("TRIP DETAILS", h2_st))
        trip_tbl = Table([
            ["From", trip.get("from_text") or "—"],
            ["To", trip.get("to_text") or "—"],
            ["Amount", f"₹ {float(expense.get('total', 0)):.2f}"],
        ], colWidths=[45 * mm, 135 * mm])
        trip_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
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

        pick_lat = trip.get("pickup_lat")
        pick_lng = trip.get("pickup_lng")
        drop_lat = trip.get("drop_lat")
        drop_lng = trip.get("drop_lng")

        def fmt(v):
            return f"{v:.6f}" if isinstance(v, (int, float)) else "—"

        gps_tbl = Table([
            ["", "Latitude", "Longitude"],
            ["Picking Point", fmt(pick_lat), fmt(pick_lng)],
            ["Dropping Point", fmt(drop_lat), fmt(drop_lng)],
        ], colWidths=[50 * mm, 65 * mm, 65 * mm])
        gps_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 1), (0, -1), colors.HexColor("#64748B")),
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

    # Notes (if any)
    note_txt = (expense.get("notes") or "").strip()
    if note_txt:
        story.append(Paragraph("NOTES", h2_st))
        story.append(Paragraph(note_txt.replace("\n", "<br/>"), body_st))
        story.append(Spacer(1, 12))

    # Footer
    story.append(Paragraph(
        "<b>Note:</b> This is a system-generated reimbursement invoice via BILL4PE. "
        "Items, prices and merchant details were captured at point of purchase. "
        "For corporate reimbursement, attach this invoice to your expense report.", sub_st))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Generated: {now_iso()[:19]} UTC | BILL4PE © 2026 | www.bill4pe.com", sub_st))

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

    title_st = ParagraphStyle("title", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=22, textColor=NAVY, leading=26, spaceAfter=4)
    sub_st = ParagraphStyle("sub", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=9, textColor=colors.HexColor("#64748B"), leading=12)
    h2_st = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                           fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=4)

    story = []
    total = sum(float(e.get("total", 0)) for e in expenses)
    by_cat: dict = {}
    for e in expenses:
        c = e.get("category", "other")
        by_cat[c] = by_cat.get(c, 0) + float(e.get("total", 0))

    # Header
    header_tbl = Table([
        [Paragraph("<b>BILL4PE</b>", title_st),
         Paragraph(f"<b>EXPENSE REPORT</b><br/>"
                   f"Report ID: {report['id'][:8].upper()}<br/>"
                   f"Date: {report['created_at'][:16].replace('T', ' ')}<br/>"
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
    story.append(Paragraph(f"Submitted by: <b>{user_name}</b>", sub_st))
    if report.get("notes"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<i>{report.get('notes')}</i>", sub_st))
    story.append(Spacer(1, 14))

    # Summary
    story.append(Paragraph("SUMMARY", h2_st))
    sum_rows = [["Category", "Amount (INR)"]]
    for c, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        sum_rows.append([c.title(), f"{v:.2f}"])
    sum_rows.append(["TOTAL", f"{total:.2f}"])
    sum_tbl = Table(sum_rows, colWidths=[120 * mm, 60 * mm])
    sum_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 16))

    # Line items
    story.append(Paragraph("LINE ITEMS", h2_st))
    rows = [["#", "Date", "Category", "Merchant", "Bill ID", "Amount (₹)"]]
    for idx, e in enumerate(expenses, 1):
        pay = e.get("payment") or {}
        rows.append([
            str(idx),
            (e.get("created_at") or "")[:16].replace("T", " "),
            (e.get("category", "") + ("/" + e["sub_category"] if e.get("sub_category") else "")).title(),
            (pay.get("merchant_name") or "—")[:24],
            (e.get("bill_id") or e["id"][:6].upper()),
            f"{float(e.get('total', 0)):.2f}",
        ])
    rows.append(["", "", "", "", "TOTAL", f"₹ {total:.2f}"])
    items_tbl = Table(rows, colWidths=[10 * mm, 28 * mm, 34 * mm, 48 * mm, 30 * mm, 30 * mm])
    items_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, BORDER),
        ("FONTNAME", (4, -1), (-1, -1), "Helvetica-Bold"),
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
    story.append(Paragraph(f"Generated: {now_iso()[:19]} UTC | BILL4PE © 2026 | www.bill4pe.com", sub_st))

    doc.build(story)
    buf.seek(0)
    return buf.read()
