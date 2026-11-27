from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.db.models import Count, F, OuterRef, Subquery, Sum
from django.http import FileResponse, HttpResponse
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import datetime
from uuid import uuid4
import csv

from .models import SolicitudCertificado, DenunciaVecinal, SolicitudIngreso, ESTADO_CHOICES
from payments.models import Address, Charge, Expense, Payment, PaymentEvent

PAYMENT_METHOD_LABELS = {
    'cash': 'Efectivo',
    'bank_transfer': 'Transferencia bancaria',
    'deposit': 'Depósito',
    'check': 'Cheque',
    'other': 'Otro',
    'flow': 'Flow',
    'manual': 'Histórico presencial',
}


def _stats():
    def cnt(model, estado):
        return model.objects.filter(estado=estado).count()
    return {
        'total':      SolicitudCertificado.objects.count() + DenunciaVecinal.objects.count() + SolicitudIngreso.objects.count(),
        'PENDIENTE':  cnt(SolicitudCertificado, 'PENDIENTE')  + cnt(DenunciaVecinal, 'PENDIENTE')  + cnt(SolicitudIngreso, 'PENDIENTE'),
        'EN_PROCESO': cnt(SolicitudCertificado, 'EN_PROCESO') + cnt(DenunciaVecinal, 'EN_PROCESO') + cnt(SolicitudIngreso, 'EN_PROCESO'),
        'COMPLETADO': cnt(SolicitudCertificado, 'COMPLETADO') + cnt(DenunciaVecinal, 'COMPLETADO') + cnt(SolicitudIngreso, 'COMPLETADO'),
        'RECHAZADO':  cnt(SolicitudCertificado, 'RECHAZADO')  + cnt(DenunciaVecinal, 'RECHAZADO')  + cnt(SolicitudIngreso, 'RECHAZADO'),
    }


def panel_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(request.GET.get('next', 'dashboard'))

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            login(request, user)
            next_url = request.POST.get('next', '').strip() or 'dashboard'
            return redirect(next_url)
        error = 'Usuario o contraseña incorrectos.'

    return render(request, 'solicitudes/login.html', {
        'error': error,
        'next':  request.GET.get('next', ''),
    })


def panel_logout(request):
    if request.method == 'POST':
        logout(request)
    return redirect('inicio')


@staff_member_required(login_url='/panel/ingresar/')
def dashboard(request):
    estado_filter = request.GET.get('estado', '')

    certs     = SolicitudCertificado.objects.select_related('asignado_a').order_by('-creado_en')
    denuncias = DenunciaVecinal.objects.select_related('asignado_a').order_by('-creado_en')
    ingresos  = SolicitudIngreso.objects.select_related('asignado_a').order_by('-creado_en')

    if estado_filter:
        certs     = certs.filter(estado=estado_filter)
        denuncias = denuncias.filter(estado=estado_filter)
        ingresos  = ingresos.filter(estado=estado_filter)

    return render(request, 'solicitudes/dashboard.html', {
        'certs':         certs,
        'denuncias':     denuncias,
        'ingresos':      ingresos,
        'estado_filter': estado_filter,
        'stats':         _stats(),
        'estados':       ESTADO_CHOICES,
    })


@staff_member_required(login_url='/panel/ingresar/')
def detalle_certificado(request, pk):
    cert     = get_object_or_404(SolicitudCertificado, pk=pk)
    usuarios = User.objects.filter(is_staff=True).order_by('first_name', 'username')

    if request.method == 'POST':
        cert.estado          = request.POST.get('estado', cert.estado)
        cert.notas_internas  = request.POST.get('notas_internas', '')
        asignado_id          = request.POST.get('asignado_a', '')
        cert.asignado_a_id   = int(asignado_id) if asignado_id else None
        valor = request.POST.get('valor_cobrado', '').strip()
        cert.valor_cobrado   = int(valor) if valor else None
        cert.num_recibo      = request.POST.get('num_recibo', '').strip()
        fp = request.POST.get('fecha_pago', '').strip()
        cert.fecha_pago      = fp if fp else None
        fe = request.POST.get('fecha_entrega', '').strip()
        cert.fecha_entrega   = fe if fe else None
        cert.save()
        messages.success(request, 'Solicitud actualizada correctamente.')
        return redirect('detalle_certificado', pk=pk)

    return render(request, 'solicitudes/detalle_certificado.html', {
        'cert':     cert,
        'usuarios': usuarios,
        'estados':  ESTADO_CHOICES,
    })


@staff_member_required(login_url='/panel/ingresar/')
def detalle_denuncia(request, pk):
    denuncia = get_object_or_404(DenunciaVecinal, pk=pk)
    usuarios = User.objects.filter(is_staff=True).order_by('first_name', 'username')

    if request.method == 'POST':
        denuncia.estado         = request.POST.get('estado', denuncia.estado)
        denuncia.notas_internas = request.POST.get('notas_internas', '')
        asignado_id             = request.POST.get('asignado_a', '')
        denuncia.asignado_a_id  = int(asignado_id) if asignado_id else None
        denuncia.save()
        messages.success(request, 'Denuncia actualizada correctamente.')
        return redirect('detalle_denuncia', pk=pk)

    return render(request, 'solicitudes/detalle_denuncia.html', {
        'denuncia': denuncia,
        'usuarios': usuarios,
        'estados':  ESTADO_CHOICES,
    })


@staff_member_required(login_url='/panel/ingresar/')
def detalle_ingreso(request, pk):
    ingreso  = get_object_or_404(SolicitudIngreso, pk=pk)
    usuarios = User.objects.filter(is_staff=True).order_by('first_name', 'username')

    if request.method == 'POST':
        ingreso.estado         = request.POST.get('estado', ingreso.estado)
        ingreso.notas_internas = request.POST.get('notas_internas', '')
        asignado_id            = request.POST.get('asignado_a', '')
        ingreso.asignado_a_id  = int(asignado_id) if asignado_id else None
        ingreso.save()
        messages.success(request, 'Solicitud actualizada correctamente.')
        return redirect('detalle_ingreso', pk=pk)

    return render(request, 'solicitudes/detalle_ingreso.html', {
        'ingreso':  ingreso,
        'usuarios': usuarios,
        'estados':  ESTADO_CHOICES,
    })


@staff_member_required(login_url='/panel/ingresar/')
def contabilidad(request):
    charges = Charge.all_objects.filter(deleted_at__isnull=True)
    active_charges = charges.exclude(status__in=[Charge.Status.WAIVED, Charge.Status.CANCELLED])
    charge_totals = active_charges.aggregate(invoiced=Sum('amount'), paid=Sum('paid_amount'))
    invoiced = charge_totals['invoiced'] or 0
    paid = charge_totals['paid'] or 0
    pending = max(0, invoiced - paid)
    paid_online = Payment.all_objects.filter(status=Payment.Status.PAID, gateway='flow', deleted_at__isnull=True).aggregate(total=Sum('amount'))['total'] or 0
    paid_in_person = Payment.all_objects.filter(status=Payment.Status.PAID, deleted_at__isnull=True).exclude(gateway='flow').aggregate(total=Sum('amount'))['total'] or 0
    certificate_income = SolicitudCertificado.objects.filter(valor_cobrado__isnull=False).aggregate(total=Sum('valor_cobrado'))['total'] or 0

    debt_by_address = (
        active_charges.filter(status__in=[Charge.Status.PENDING, Charge.Status.PARTIAL, Charge.Status.OVERDUE])
        .values('address_id', 'address__label', 'address__owner_name')
        .annotate(debt=Sum(F('amount') - F('paid_amount')), count=Count('pk'))
        .filter(debt__gt=0)
        .order_by('-debt', 'address__label')
    )
    debt_lookup = {row['address_id']: row for row in debt_by_address}
    last_paid_charges = Charge.all_objects.filter(
        address_id=OuterRef('pk'),
        deleted_at__isnull=True,
        status=Charge.Status.PAID,
    ).order_by('-period_year', '-period_month')
    current_date = timezone.localdate()
    month_names = (
        'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
    )
    address_payment_status = list(
        Address.objects.filter(active=True)
        .annotate(
            last_paid_year=Subquery(last_paid_charges.values('period_year')[:1]),
            last_paid_month=Subquery(last_paid_charges.values('period_month')[:1]),
        )
        .order_by('label')
    )
    for address in address_payment_status:
        debt = debt_lookup.get(address.pk, {})
        address.debt_count = debt.get('count', 0)
        address.debt_amount = debt.get('debt', 0)
        if address.last_paid_year and address.last_paid_month:
            address.last_paid_label = f'{month_names[address.last_paid_month - 1]} {address.last_paid_year}'
            paid_period = (address.last_paid_year, address.last_paid_month)
            current_period = (current_date.year, current_date.month)
            if paid_period < current_period:
                next_month = address.last_paid_month + 1
                next_year = address.last_paid_year + (1 if next_month == 13 else 0)
                next_month = 1 if next_month == 13 else next_month
                address.payment_state = f'Pendiente desde {month_names[next_month - 1]} {next_year}'
                address.payment_state_class = 'is-red'
            elif paid_period == current_period:
                address.payment_state = 'Al día'
                address.payment_state_class = 'is-green'
            else:
                address.payment_state = 'Pago adelantado registrado'
                address.payment_state_class = 'is-amber'
        else:
            address.last_paid_label = 'Sin cuota pagada'
            address.payment_state = 'Revisar domicilio'
            address.payment_state_class = 'is-red'

    recent_payments = Payment.all_objects.filter(status=Payment.Status.PAID, deleted_at__isnull=True).select_related('address').order_by('-paid_at')[:30]
    recent_certificates = SolicitudCertificado.objects.filter(valor_cobrado__isnull=False).order_by('-fecha_pago', '-creado_en')[:20]
    payment_addresses = Address.objects.filter(active=True).order_by('label')
    expenses = Expense.objects.filter(deleted_at__isnull=True)
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_income = paid_online + paid_in_person + certificate_income
    balance = total_income - total_expenses
    recent_expenses = expenses.select_related('registered_by').order_by('-expense_date', '-pk')[:30]

    return render(request, 'solicitudes/accounting.html', {
        'invoiced': invoiced,
        'paid': paid,
        'pending': pending,
        'paid_online': paid_online,
        'paid_in_person': paid_in_person,
        'certificate_income': certificate_income,
        'debt_by_address': debt_by_address,
        'address_payment_status': address_payment_status,
        'recent_payments': recent_payments,
        'recent_certificates': recent_certificates,
        'payment_addresses': payment_addresses,
        'payment_methods': list(PAYMENT_METHOD_LABELS.items())[:5],
        'expense_categories': Expense.Category.choices,
        'recent_expenses': recent_expenses,
        'total_expenses': total_expenses,
        'total_income': total_income,
        'balance': balance,
        'payment_counts': [
            {'label': Payment.Status(row['status']).label, 'total': row['total']}
            for row in Payment.all_objects.filter(deleted_at__isnull=True).exclude(status=Payment.Status.PENDING).values('status').annotate(total=Count('pk'))
        ],
        'charge_counts': active_charges.values('status').annotate(total=Count('pk')),
    })


@staff_member_required(login_url='/panel/ingresar/')
def contabilidad_export(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="contabilidad-jjvv.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tipo', 'Referencia', 'Dirección', 'Concepto', 'Fecha', 'Medio de pago', 'Comprobante', 'Total CLP', 'Pagado CLP', 'Pendiente CLP', 'Estado', 'Correo'])

    for charge in Charge.all_objects.select_related('address').order_by('address__label', 'period_year', 'period_month'):
        writer.writerow([
            'Cuota', charge.pk, charge.address.label, f'{charge.period_month:02d}/{charge.period_year}',
            charge.due_date, '—', '—', charge.amount, charge.paid_amount, charge.remaining_amount, charge.status,
            charge.address.owner_email,
        ])
    for payment in Payment.all_objects.select_related('address').order_by('-created_at'):
        writer.writerow([
            'Pago cuotas', payment.pk, payment.address.label, payment.description or 'Pago cuotas',
            payment.paid_at or payment.created_at,
            payment.metadata.get('payment_method_label') or PAYMENT_METHOD_LABELS.get(payment.payment_method, payment.payment_method or 'No informado'),
            payment.gateway_payment_id or '—', payment.amount,
            payment.amount if payment.status == Payment.Status.PAID else 0, 0, payment.status, payment.payer_email,
        ])
    for certificate in SolicitudCertificado.objects.filter(valor_cobrado__isnull=False).order_by('-fecha_pago'):
        writer.writerow([
            'Certificado', certificate.pk, certificate.direccion, f'Certificado {certificate.numero}',
            certificate.fecha_pago, 'Certificado', certificate.num_recibo or '—', certificate.valor_cobrado,
            certificate.valor_cobrado, 0, certificate.estado, certificate.email,
        ])
    for expense in Expense.objects.filter(deleted_at__isnull=True).select_related('registered_by').order_by('-expense_date'):
        writer.writerow([
            'Gasto', expense.pk, '—', expense.description,
            expense.expense_date, expense.get_payment_method_display(), expense.reference or '—',
            expense.amount, 0, 0, expense.get_category_display(), expense.registered_by.get_username(),
        ])
    return response


@staff_member_required(login_url='/panel/ingresar/')
@require_POST
def registrar_gasto(request):
    category = request.POST.get('category', '')
    method = request.POST.get('payment_method', '')
    if category not in Expense.Category.values:
        messages.error(request, 'Selecciona una categoría de gasto válida.')
        return redirect('contabilidad')
    if method not in Expense.PaymentMethod.values:
        messages.error(request, 'Selecciona un medio de pago válido.')
        return redirect('contabilidad')

    try:
        amount = int(request.POST.get('amount', ''))
        expense_date = datetime.strptime(request.POST.get('expense_date', ''), '%Y-%m-%d').date()
        description = request.POST.get('description', '').strip()
        if amount <= 0 or not description:
            raise ValueError('Ingresa una descripción y un monto mayor que cero.')
    except (TypeError, ValueError) as exc:
        messages.error(request, str(exc) if str(exc) else 'Ingresa fecha y monto válidos.')
        return redirect('contabilidad')

    receipt = request.FILES.get('receipt')
    if receipt and receipt.size > 10 * 1024 * 1024:
        messages.error(request, 'El comprobante no puede superar 10 MB.')
        return redirect('contabilidad')

    expense = Expense(
        expense_date=expense_date,
        category=category,
        description=description,
        amount=amount,
        vendor=request.POST.get('vendor', '').strip(),
        payment_method=method,
        reference=request.POST.get('reference', '').strip(),
        notes=request.POST.get('notes', '').strip(),
        receipt=receipt,
        registered_by=request.user,
    )
    try:
        expense.full_clean()
        expense.save()
    except ValidationError as exc:
        messages.error(request, '; '.join(str(item) for values in exc.message_dict.values() for item in values))
        return redirect('contabilidad')

    messages.success(request, f'Gasto de ${amount:,} registrado correctamente.'.replace(',', '.'))
    return redirect('contabilidad')


@staff_member_required(login_url='/panel/ingresar/')
def expense_receipt(request, pk):
    expense = get_object_or_404(Expense, pk=pk, deleted_at__isnull=True)
    if not expense.receipt:
        return redirect('contabilidad')
    response = FileResponse(expense.receipt.open('rb'), as_attachment=True, filename=expense.receipt.name.rsplit('/', 1)[-1])
    return response


@staff_member_required(login_url='/panel/ingresar/')
@require_POST
def registrar_pago_cuota(request):
    address_id = request.POST.get('address_id')
    method = request.POST.get('payment_method', 'cash')
    allowed_methods = {'cash', 'bank_transfer', 'deposit', 'check', 'other'}
    if method not in allowed_methods:
        messages.error(request, 'Selecciona un medio de pago válido.')
        return redirect('contabilidad')

    try:
        amount = int(request.POST.get('amount', ''))
        payment_date = datetime.strptime(request.POST.get('payment_date', ''), '%Y-%m-%d').date()
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        messages.error(request, 'Ingresa un monto y una fecha de pago válidos.')
        return redirect('contabilidad')

    payer_name = request.POST.get('payer_name', '').strip()
    reference = request.POST.get('reference', '').strip()
    note = request.POST.get('note', '').strip()

    try:
        with transaction.atomic():
            address = Address.objects.select_for_update().get(pk=address_id, active=True)
            charges = list(
                Charge.objects.select_for_update()
                .filter(address=address, status__in=[Charge.Status.PENDING, Charge.Status.PARTIAL, Charge.Status.OVERDUE])
                .order_by('due_date', 'pk')
            )
            debt = sum(charge.remaining_amount for charge in charges)
            if not charges or debt <= 0:
                raise ValueError('La dirección no tiene cuotas pendientes.')
            if amount > debt:
                raise ValueError(f'El monto no puede superar la deuda pendiente de ${debt:,}.'.replace(',', '.'))

            paid_at = timezone.make_aware(
                datetime.combine(payment_date, datetime.min.time()),
                timezone.get_current_timezone(),
            )
            payment = Payment.objects.create(
                address=address,
                user=request.user,
                amount=amount,
                currency='CLP',
                status=Payment.Status.PENDING,
                source='manual_panel',
                payment_method=method,
                gateway='manual',
                gateway_payment_id=reference[:120] or None,
                payer_email=address.owner_email or '',
                payer_name=payer_name or address.owner_name,
                description=f'Pago manual de cuotas registrado desde el panel ({method})',
                metadata={
                    'charge_ids': [charge.pk for charge in charges],
                    'payment_method_label': dict([
                        ('cash', 'Efectivo'), ('bank_transfer', 'Transferencia bancaria'),
                        ('deposit', 'Depósito'), ('check', 'Cheque'), ('other', 'Otro'),
                    ])[method],
                    'reference': reference,
                    'note': note,
                    'registered_by': request.user.get_username(),
                    'payment_date': payment_date.isoformat(),
                },
                paid_at=paid_at,
            )
            payment.apply_to_charges([charge.pk for charge in charges])
            payment.refresh_from_db()
            payment.paid_at = paid_at
            payment.save(update_fields=['paid_at', 'updated_at'])
            PaymentEvent.objects.create(
                payment=payment,
                gateway='manual',
                event_type='manual.panel_payment',
                external_id=f'manual-panel-{uuid4().hex}',
                payload={
                    'method': method,
                    'reference': reference,
                    'note': note,
                    'registered_by': request.user.get_username(),
                },
                processed=True,
                processed_at=timezone.now(),
            )
    except Address.DoesNotExist:
        messages.error(request, 'La dirección seleccionada no existe o no está activa.')
        return redirect('contabilidad')
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('contabilidad')

    messages.success(request, f'Pago de ${amount:,} registrado para {address.label}.'.replace(',', '.'))
    return redirect('contabilidad')
