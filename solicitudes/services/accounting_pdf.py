from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from django.utils import timezone

from payments.models import Expense, Payment
from solicitudes.models import SolicitudCertificado
from solicitudes.services.accounting_debts import debt_status_by_address


GREEN = colors.HexColor('#173d31')
LIGHT_GREEN = colors.HexColor('#edf5f1')
RED = colors.HexColor('#a61b1b')
MUTED = colors.HexColor('#65766f')
GRID = colors.HexColor('#dbe3df')


def clp(value):
    return f"$ {int(value or 0):,}".replace(',', '.')


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ReportTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=20,
        leading=24, textColor=GREEN, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name='ReportSubtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=9,
        leading=12, textColor=MUTED, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name='SectionTitle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13,
        leading=16, textColor=GREEN, spaceBefore=8, spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name='Tiny', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5,
        leading=9.5, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name='Cell', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5,
        leading=9.5, wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        name='CellRight', parent=styles['Cell'], alignment=TA_RIGHT,
    ))
    return styles


def _table(data, widths, numeric_columns=()):
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), GREEN),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('LEADING', (0, 0), (-1, -1), 9.5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f9f8')]),
        ('GRID', (0, 0), (-1, -1), 0.35, GRID),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    for column in numeric_columns:
        style.append(('ALIGN', (column, 1), (column, -1), 'RIGHT'))
    table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle(style))
    return table


def _page(canvas, doc, report_title):
    canvas.saveState()
    canvas.setStrokeColor(GRID)
    canvas.line(doc.leftMargin, 15 * mm, A4[0] - doc.rightMargin, 15 * mm)
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 10 * mm, report_title)
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f'Página {doc.page}')
    canvas.restoreState()


def _document(title):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=20 * mm,
        title=title,
        author='Junta de Vecinos Villas Concepción-El Rocío',
    )
    return buffer, document


def accounting_report_pdf(request):
    styles = _styles()
    buffer, document = _document('Informe contable JJVV')
    today = timezone.localdate()
    generated_at = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    payments = list(Payment.all_objects.filter(status=Payment.Status.PAID, deleted_at__isnull=True).select_related('address').order_by('paid_at', 'pk'))
    expenses = list(Expense.objects.filter(deleted_at__isnull=True).select_related('registered_by').order_by('expense_date', 'pk'))
    certificates = list(SolicitudCertificado.objects.filter(valor_cobrado__isnull=False).order_by('fecha_pago', 'pk'))
    paid_online = sum(payment.accounted_amount for payment in payments if payment.gateway == 'flow')
    paid_in_person = sum(payment.accounted_amount for payment in payments if payment.gateway != 'flow')
    certificate_income = sum(certificate.valor_cobrado or 0 for certificate in certificates)
    total_income = paid_online + paid_in_person + certificate_income
    total_expenses = sum(expense.amount for expense in expenses)
    balance = total_income - total_expenses

    story = [
        Paragraph('Informe contable', styles['ReportTitle']),
        Paragraph('Junta de Vecinos Villas Concepción-El Rocío', styles['ReportSubtitle']),
        Paragraph(f'Corte al {today:%d/%m/%Y} · Generado el {generated_at} · Responsable: {request.user.get_full_name() or request.user.username}', styles['Tiny']),
        Spacer(1, 5 * mm),
    ]
    summary = [
        ['Concepto', 'Monto'],
        ['Ingresos por cuotas presenciales / transferencias', Paragraph(clp(paid_in_person), styles['CellRight'])],
        ['Ingresos por cuotas Flow', Paragraph(clp(paid_online), styles['CellRight'])],
        ['Ingresos por certificados', Paragraph(clp(certificate_income), styles['CellRight'])],
        ['Total ingresos', Paragraph(clp(total_income), styles['CellRight'])],
        ['Total gastos', Paragraph(clp(total_expenses), styles['CellRight'])],
        ['Saldo contable', Paragraph(clp(balance), styles['CellRight'])],
    ]
    story.extend([Paragraph('Resumen ejecutivo', styles['SectionTitle']), _table(summary, [125 * mm, 45 * mm], (1,))])

    payment_rows = [['Fecha', 'Dirección', 'Pagador', 'Medio', 'Comprobante', 'Monto cuotas']]
    for payment in payments:
        method = 'Flow' if payment.gateway == 'flow' else (payment.metadata.get('payment_method_label') or payment.get_payment_method_display() if hasattr(payment, 'get_payment_method_display') else payment.payment_method or 'Manual')
        payment_rows.append([
            payment.paid_at.strftime('%d/%m/%Y') if payment.paid_at else '—',
            Paragraph(payment.address.label, styles['Cell']),
            Paragraph(payment.payer_name or payment.payer_email, styles['Cell']),
            Paragraph(method, styles['Cell']),
            Paragraph(payment.gateway_payment_id or '—', styles['Cell']),
            Paragraph(clp(payment.accounted_amount), styles['CellRight']),
        ])
    story.extend([Paragraph(f'Ingresos por cuotas · {len(payments)} pagos', styles['SectionTitle']), _table(payment_rows, [17*mm, 40*mm, 35*mm, 25*mm, 27*mm, 26*mm], (5,))])

    certificate_rows = [['Fecha', 'Solicitud / solicitante', 'Dirección', 'Recibo', 'Monto']]
    for certificate in certificates:
        certificate_rows.append([
            certificate.fecha_pago.strftime('%d/%m/%Y') if certificate.fecha_pago else '—',
            Paragraph(f'{certificate.numero} · {certificate.nombre}', styles['Cell']),
            Paragraph(certificate.direccion, styles['Cell']),
            certificate.num_recibo or '—',
            Paragraph(clp(certificate.valor_cobrado), styles['CellRight']),
        ])
    story.extend([Paragraph(f'Ingresos por certificados · {len(certificates)} cobros', styles['SectionTitle']), _table(certificate_rows, [20*mm, 48*mm, 52*mm, 24*mm, 26*mm], (4,))])

    expense_rows = [['Fecha', 'Descripción', 'Categoría', 'Proveedor', 'Documento', 'Monto']]
    for expense in expenses:
        expense_rows.append([
            expense.expense_date.strftime('%d/%m/%Y'),
            Paragraph(expense.description, styles['Cell']),
            Paragraph(expense.get_category_display(), styles['Cell']),
            Paragraph(expense.vendor or '—', styles['Cell']),
            Paragraph(expense.reference or ('Comprobante adjunto' if expense.receipt else '—'), styles['Cell']),
            Paragraph(clp(expense.amount), styles['CellRight']),
        ])
    story.extend([
        Paragraph(f'Gastos registrados · {len(expenses)} movimientos', styles['SectionTitle']),
        _table(expense_rows, [20*mm, 47*mm, 30*mm, 31*mm, 23*mm, 24*mm], (5,)),
        Spacer(1, 5*mm),
        Paragraph('Notas: los montos Flow informan el valor aplicado a cuotas y separan la comisión en la metadata del pago. Los años 2020 y 2021 son períodos condonados. Este documento es un informe interno y debe compararse con cartola bancaria y comprobantes respaldatorios.', styles['Tiny']),
    ])
    document.build(story, onFirstPage=lambda c, d: _page(c, d, 'Informe contable JJVV'), onLaterPages=lambda c, d: _page(c, d, 'Informe contable JJVV'))
    return buffer.getvalue()


def debt_report_pdf(request):
    styles = _styles()
    buffer, document = _document('Informe de deudas por domicilio JJVV')
    addresses = debt_status_by_address()
    indebted = [address for address in addresses if address.debt_amount > 0]
    generated_at = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    total_debt = sum(address.debt_amount for address in indebted)
    total_months = sum(address.debt_count for address in indebted)
    rows = [['Dirección', 'Titular', 'Último mes pagado', 'Estado', 'Meses', 'Monto']]
    for address in sorted(indebted, key=lambda item: (-item.debt_amount, item.label)):
        rows.append([
            Paragraph(address.label, styles['Cell']),
            Paragraph(address.owner_name or 'Sin titular registrado', styles['Cell']),
            Paragraph(address.last_paid_label, styles['Cell']),
            Paragraph(address.payment_state, styles['Cell']),
            str(address.debt_count),
            Paragraph(clp(address.debt_amount), styles['CellRight']),
        ])
    story = [
        Paragraph('Informe de deudas por domicilio', styles['ReportTitle']),
        Paragraph('Junta de Vecinos Villas Concepción-El Rocío', styles['ReportSubtitle']),
        Paragraph(f'Generado el {generated_at} · Responsable: {request.user.get_full_name() or request.user.username}', styles['Tiny']),
        Spacer(1, 5*mm),
        Paragraph(f'{len(indebted)} domicilios con deuda estimada · {total_months} meses pendientes · Total {clp(total_debt)}', styles['SectionTitle']),
        _table(rows, [42*mm, 37*mm, 25*mm, 42*mm, 13*mm, 23*mm], (4, 5)),
        Spacer(1, 5*mm),
        Paragraph('Criterio: el informe considera cargos pendientes registrados y meses faltantes hasta la fecha según la configuración vigente. Excluye 2020 y 2021 por condonación. Los montos estimados deben validarse antes de iniciar cobros o acciones de regularización.', styles['Tiny']),
    ]
    document.build(story, onFirstPage=lambda c, d: _page(c, d, 'Informe de deudas por domicilio'), onLaterPages=lambda c, d: _page(c, d, 'Informe de deudas por domicilio'))
    return buffer.getvalue()
