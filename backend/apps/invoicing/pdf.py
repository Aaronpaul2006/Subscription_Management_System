"""Invoice PDF, drawn with ReportLab (pure Python, no system libraries)."""

from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Invoice

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
BRAND = colors.HexColor("#4f46e5")
LINE = colors.HexColor("#e2e8f0")


def _m(value) -> str:
    # The built-in PDF fonts have no rupee glyph, so amounts carry the ISO code.
    return f"{value:,.2f}"


def invoice_pdf(invoice: Invoice) -> bytes:
    company = settings.COMPANY
    currency = company["currency"]
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {invoice.display_number}",
        author=company["name"],
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=12, textColor=INK)
    muted = ParagraphStyle("muted", parent=body, textColor=MUTED)
    h1 = ParagraphStyle(
        "h1", parent=body, fontSize=20, leading=24, fontName="Helvetica-Bold", textColor=BRAND
    )
    right = ParagraphStyle("right", parent=body, alignment=2)

    status = invoice.get_status_display().upper()
    if invoice.is_overdue:
        status = f"OVERDUE · {invoice.days_overdue} DAYS"
    header = Table(
        [
            [
                Paragraph(
                    f"<b>{company['name']}</b><br/>{company['address']}<br/>"
                    f"{company['email']}<br/>Tax ID: {company['tax_id']}",
                    body,
                ),
                Paragraph(
                    f"<font size=20 color='#4f46e5'><b>INVOICE</b></font><br/><br/>"
                    f"<b>{invoice.display_number}</b><br/>"
                    f"<font color='#64748b'>{status}</font>",
                    right,
                ),
            ]
        ],
        colWidths=[100 * mm, 74 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    b = invoice.bill_to or {}
    bill_lines = [f"<b>{b.get('company') or b.get('name', '')}</b>"]
    if b.get("company"):
        bill_lines.append(b.get("name", ""))
    for key in ("address", "city", "state", "country", "email"):
        if b.get(key):
            bill_lines.append(b[key])
    if b.get("tax_id"):
        bill_lines.append(f"Tax ID: {b['tax_id']}")
    meta = [
        ["Invoice date", invoice.invoice_date.strftime("%d %b %Y")],
        ["Due date", invoice.due_date.strftime("%d %b %Y")],
        ["Payment terms", invoice.payment_term or "Immediate"],
    ]
    if invoice.period_start:
        meta.append(
            ["Service period", f"{invoice.period_start:%d %b %Y} – {invoice.period_end:%d %b %Y}"]
        )
    if invoice.subscription_id:
        meta.append(["Subscription", invoice.subscription.number])
    meta_table = Table(
        [[Paragraph(k, muted), Paragraph(v, body)] for k, v in meta], colWidths=[28 * mm, 46 * mm]
    )
    meta_table.setStyle(
        TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2)])
    )
    parties = Table(
        [
            [
                Paragraph(
                    "<font color='#64748b'>BILL TO</font><br/>" + "<br/>".join(bill_lines), body
                ),
                meta_table,
            ]
        ],
        colWidths=[100 * mm, 74 * mm],
    )
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    rows = [["Description", "Qty", "Unit price", "Discount", "Tax", "Amount"]]
    for line in invoice.lines.all():
        tax_names = ", ".join(f"{t['name']}" for t in line.taxes) or "—"
        rows.append(
            [
                Paragraph(line.description, body),
                f"{line.quantity:g}",
                _m(line.unit_price),
                _m(line.discount_amount) if line.discount_amount else "—",
                Paragraph(
                    f"{_m(line.tax_amount)}<br/><font size=7 color='#64748b'>{tax_names}</font>",
                    right,
                ),
                _m(line.total),
            ]
        )
    lines = Table(
        rows, colWidths=[70 * mm, 14 * mm, 24 * mm, 20 * mm, 24 * mm, 22 * mm], repeatRows=1
    )
    lines.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("FONT", (1, 1), (-1, -1), "Helvetica", 9),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    totals = [["Subtotal", _m(invoice.untaxed_amount)]]
    for applied in invoice.applied_discounts.all():
        totals.append([f"Discount: {applied.name}", f"-{_m(applied.amount)}"])
    totals += [
        ["Tax", _m(invoice.tax_amount)],
        [f"Total ({currency})", _m(invoice.total)],
        ["Paid", _m(invoice.amount_paid)],
        [f"Amount due ({currency})", _m(invoice.amount_due)],
    ]
    totals_table = Table(totals, colWidths=[50 * mm, 30 * mm], hAlign="RIGHT")
    total_row = len(totals) - 3
    totals_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONT", (0, total_row), (-1, total_row), "Helvetica-Bold", 10),
                ("LINEABOVE", (0, total_row), (-1, total_row), 0.8, INK),
                ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11),
                ("TEXTCOLOR", (0, -1), (-1, -1), BRAND),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK),
            ]
        )
    )

    story = [
        header,
        Spacer(1, 8 * mm),
        parties,
        Spacer(1, 8 * mm),
        lines,
        Spacer(1, 4 * mm),
        totals_table,
    ]
    payments = list(invoice.payments.all())
    if payments:
        story += [Spacer(1, 6 * mm), Paragraph("<b>Payments received</b>", body)]
        for p in payments:
            story.append(
                Paragraph(
                    f"{p.payment_date:%d %b %Y} · {p.get_method_display()} · "
                    f"{currency} {_m(p.amount)}" + (f" · {p.reference}" if p.reference else ""),
                    muted,
                )
            )
    story += [
        Spacer(1, 10 * mm),
        Paragraph(f"Thank you for your business. Questions? Write to {company['email']}.", muted),
    ]
    if invoice.status == Invoice.Status.DRAFT:
        story.insert(0, Paragraph("DRAFT — not a valid tax invoice until confirmed", h1))
    doc.build(story)
    return buf.getvalue()
