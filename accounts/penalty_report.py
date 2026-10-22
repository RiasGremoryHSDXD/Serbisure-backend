"""Printable penalty history using the same bundled fonts as worker CVs."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.utils import timezone

from .penalties import PH_TIME


def penalty_pdf(records, *, actor, filters, count):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    assets = Path(__file__).parent / 'assets'
    for name, filename in [('PenaltyRegular', 'Nunito-Regular.ttf'), ('PenaltyBold', 'Nunito-Bold.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(assets / filename)))
    ink, muted, peach = [colors.HexColor(value) for value in ('#0D0D11', '#52525B', '#FFB380')]
    body = ParagraphStyle('body', fontName='PenaltyRegular', fontSize=8.2, leading=11,
        textColor=ink, spaceAfter=3, splitLongWords=True)
    small = ParagraphStyle('small', parent=body, fontSize=7, leading=9.5, textColor=muted)
    title = ParagraphStyle('title', parent=body, fontName='PenaltyBold', fontSize=20, leading=25, spaceAfter=8)
    label = ParagraphStyle('label', parent=body, fontName='PenaltyBold')

    def p(value, style=body):
        # User notes are plain text, never ReportLab markup or external links.
        text = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
        return Paragraph(escape(text).replace('\n', '<br/>'), style)

    def stamp(value):
        return timezone.localtime(value, PH_TIME).strftime('%d %b %Y, %I:%M %p') + ' PHT'

    output = BytesIO()
    page_width, page_height = landscape(A4)
    doc = SimpleDocTemplate(output, pagesize=(page_width, page_height), leftMargin=30, rightMargin=30,
        topMargin=58, bottomMargin=42, title='SerbiSure - Penalty Adjustment Report', author='SerbiSure')
    generated = stamp(timezone.now())
    scope = (' / '.join(value for value in [actor.barangay, actor.city, actor.province] if value)
        if actor.account_type == 'Barangay' else filters.get('barangay') or 'All barangays')
    story = [p('Penalty Adjustment Report', title), p(f'Generated: {generated}', small),
        p(f'Jurisdiction: {scope}', small),
        p(f'Exported by: {actor.get_full_name().strip() or actor.username} | Admin ID: {actor.pk}', small)]
    if filters.get('role'):
        story.append(p(f"Role filter: {filters['role']}", small))
    if filters.get('search'):
        story.append(p(f"Search filter: {filters['search']}", small))
    if filters.get('user_id'):
        story.append(p(f"User filter: {filters['user_id']}", small))
    story.extend([p(f'Records: {count} | Historical score snapshots, not current balances.', small), Spacer(1, 10)])
    columns = ['User', 'Change', 'Score', 'Reason / incident notes', 'Report / cancellation', 'Adjusted by', 'Date / period']
    rows = [[p(column, label) for column in columns]]
    for entry in records:
        report = [p('Verified report' if entry.report_verified else 'Not verified', label)]
        if entry.incident_reference:
            report.append(p(entry.incident_reference))
        if entry.booking_id_snapshot:
            report.append(p(f'Booking ID: {entry.booking_id_snapshot}', small))
        rows.append([
            [p(entry.user_name, label), p(entry.user_role, small),
                p(' / '.join(value for value in [entry.user_barangay, entry.city_key, entry.province_key] if value), small),
                p(f'User ID: {entry.user_id_snapshot}', small)],
            p(f'{entry.points_delta:+d}', label),
            p(f'{entry.points_before}/3 to {entry.points_after}/3', label),
            p(entry.reason), report,
            [p(entry.admin_name, label), p(entry.admin_role, small), p(f'Admin ID: {entry.admin_id_snapshot}', small)],
            [p(stamp(entry.created_at)), p(f'Period: {entry.penalty_month:%Y-%m}', small),
                p(f'Audit record ID: {entry.pk}', small)],
        ])
    if count:
        table = LongTable(rows, colWidths=[(doc.width - 12) * ratio for ratio in (.18, .06, .08, .27, .15, .14, .12)],
            repeatRows=1, splitByRow=0, splitInRow=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FFF1E7')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAFAFA')]),
            ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor('#E4E4E7')),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(table)
    else:
        story.append(p('No adjustments match these filters.'))

    def page_frame(canvas, document):
        canvas.saveState()
        canvas.setFillColor(ink)
        canvas.setFont('PenaltyBold', 12)
        canvas.drawString(30, page_height - 30, 'SerbiSure | Penalty adjustments')
        canvas.setFillColor(peach)
        canvas.rect(30, page_height - 41, doc.width, 3, fill=1, stroke=0)
        canvas.setFillColor(muted)
        canvas.setFont('PenaltyRegular', 8)
        canvas.drawString(30, 24, 'Penalty adjustment history | Confidential administrative record')
        canvas.drawRightString(page_width - 30, 24, f'Page {document.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return output.getvalue()
