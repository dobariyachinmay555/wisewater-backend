import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_water_bill_pdf(
    bill_number: str,
    society_name: str,
    society_code: str,
    society_address: str,
    resident_name: str,
    flat_number: str,
    mobile_number: str,
    reading_date: str,
    due_date: str,
    previous_unit: int,
    current_unit: int,
    consumed_units: int,
    unit_price: float,
    total_amount: float,
    payment_status: str = "UNPAID",
    output_dir: str = "uploads/bills"
) -> str:
    """
    Generate an official, professional PDF invoice for a water bill.
    Returns the relative path to the generated PDF file.
    """
    os.makedirs(output_dir, exist_ok=True)
    clean_bill_no = bill_number.replace("/", "_").replace(" ", "_")
    filename = f"WaterBill_{clean_bill_no}.pdf"
    file_path = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom colors & styles
    primary_color = colors.HexColor("#0284C7")  # Ocean Blue
    text_dark = colors.HexColor("#0F172A")      # Slate 900
    text_muted = colors.HexColor("#64748B")     # Slate 500
    bg_light = colors.HexColor("#F8FAFC")       # Slate 50
    border_color = colors.HexColor("#E2E8F0")   # Slate 200
    accent_green = colors.HexColor("#10B981")   # Emerald

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=primary_color
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=text_muted
    )
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=text_dark
    )
    body_bold = ParagraphStyle(
        'BodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=text_dark
    )
    body_regular = ParagraphStyle(
        'BodyReg',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=text_dark
    )
    body_muted = ParagraphStyle(
        'BodyMuted',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=text_muted
    )

    story = []

    # 1. Header: WiseWater & Invoice Details
    header_data = [
        [
            Paragraph("<b>WiseWater</b>", title_style),
            Paragraph(f"<b>WATER UTILITY BILL</b><br/><font color='{text_muted}'>Invoice: {bill_number}</font>", ParagraphStyle('HeadRight', parent=body_regular, alignment=2, leading=14))
        ],
        [
            Paragraph("Smart Sub-metering & Water Management", subtitle_style),
            Paragraph(f"Date: <b>{reading_date}</b> | Due: <font color='#EF4444'><b>{due_date}</b></font>", ParagraphStyle('DateRight', parent=body_regular, alignment=2, leading=14))
        ]
    ]
    header_table = Table(header_data, colWidths=[280, 240])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 14))

    # Divider line
    story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceBefore=4, spaceAfter=14))

    # 2. Society & Resident Info Cards (2 Columns)
    soc_info = (
        f"<b>{society_name}</b><br/>"
        f"Society Code: {society_code}<br/>"
        f"Address: {society_address or 'N/A'}"
    )
    resident_info = (
        f"<b>{resident_name}</b><br/>"
        f"Flat / Unit: <b>{flat_number}</b><br/>"
        f"Mobile: {mobile_number or 'N/A'}"
    )

    info_data = [
        [
            Paragraph("<b>ISSUED BY (SOCIETY):</b>", body_muted),
            Paragraph("<b>BILLED TO (RESIDENT):</b>", body_muted)
        ],
        [
            Paragraph(soc_info, body_regular),
            Paragraph(resident_info, body_regular)
        ]
    ]
    info_table = Table(info_data, colWidths=[260, 260])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_light),
        ('BOX', (0, 0), (-1, -1), 1, border_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 16))

    # 3. Meter Consumption Details Table
    story.append(Paragraph("<b>Meter Reading & Consumption Breakdown</b>", section_title))
    story.append(Spacer(1, 8))

    breakdown_data = [
        [
            Paragraph("<b>Description</b>", body_bold),
            Paragraph("<b>Previous</b>", ParagraphStyle('H1', parent=body_bold, alignment=1)),
            Paragraph("<b>Current</b>", ParagraphStyle('H2', parent=body_bold, alignment=1)),
            Paragraph("<b>Consumed Units</b>", ParagraphStyle('H3', parent=body_bold, alignment=1)),
            Paragraph("<b>Rate (₹/Unit)</b>", ParagraphStyle('H4', parent=body_bold, alignment=1)),
            Paragraph("<b>Amount (₹)</b>", ParagraphStyle('H5', parent=body_bold, alignment=2)),
        ],
        [
            Paragraph("Water Consumption (Sub-meter)", body_regular),
            Paragraph(f"{previous_unit}", ParagraphStyle('V1', parent=body_regular, alignment=1)),
            Paragraph(f"{current_unit}", ParagraphStyle('V2', parent=body_regular, alignment=1)),
            Paragraph(f"<b>{consumed_units} units</b>", ParagraphStyle('V3', parent=body_bold, alignment=1, textColor=primary_color)),
            Paragraph(f"₹{unit_price:.2f}", ParagraphStyle('V4', parent=body_regular, alignment=1)),
            Paragraph(f"<b>₹{total_amount:.2f}</b>", ParagraphStyle('V5', parent=body_bold, alignment=2)),
        ]
    ]

    breakdown_table = Table(breakdown_data, colWidths=[160, 65, 65, 85, 75, 70])
    breakdown_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E0F2FE")),
        ('BOX', (0, 0), (-1, -1), 1, border_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(breakdown_table)
    story.append(Spacer(1, 14))

    # 4. Total Summary & Payment Status Box
    status_fg = "#10B981" if payment_status.upper() == "PAID" else "#D97706"

    total_data = [
        [
            Paragraph(f"Payment Status: <font color='{status_fg}'><b>{payment_status.upper()}</b></font>", body_bold),
            Paragraph(f"<b>TOTAL AMOUNT DUE:</b>", ParagraphStyle('TB', parent=body_bold, alignment=2)),
            Paragraph(f"<b>₹{total_amount:.2f}</b>", ParagraphStyle('TA', parent=title_style, alignment=2, textColor=accent_green, fontSize=16, leading=18))
        ]
    ]
    total_table = Table(total_data, colWidths=[200, 160, 160])
    total_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_light),
        ('BOX', (0, 0), (-1, -1), 1.5, primary_color),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(total_table)
    story.append(Spacer(1, 24))

    # 5. Footer & Instructions
    footer_text = (
        "<b>Payment Instructions:</b><br/>"
        "1. Please settle the water bill payment before the due date to avoid service disruption.<br/>"
        "2. Payments can be submitted directly to society administration or online via society payment channels.<br/>"
        "3. For any billing or reading discrepancies, please contact your Society Chairman / Administrator."
    )
    story.append(Paragraph(footer_text, subtitle_style))
    story.append(Spacer(1, 16))

    system_note = (
        f"<font color='{text_muted}'>This is a computer-generated invoice from WiseWater Smart Sub-metering System. "
        f"Generated on {datetime.now().strftime('%d %b %Y, %I:%M %p')}.</font>"
    )
    story.append(Paragraph(system_note, ParagraphStyle('SysNote', parent=subtitle_style, alignment=1, fontSize=8)))

    doc.build(story)
    return f"/uploads/bills/{filename}"
