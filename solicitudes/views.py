from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, F, Sum
from django.http import HttpResponse
import csv

from .models import SolicitudCertificado, DenunciaVecinal, SolicitudIngreso, ESTADO_CHOICES
from payments.models import Charge, Payment


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
    paid_online = Payment.all_objects.filter(status=Payment.Status.PAID, deleted_at__isnull=True).aggregate(total=Sum('amount'))['total'] or 0
    certificate_income = SolicitudCertificado.objects.filter(valor_cobrado__isnull=False).aggregate(total=Sum('valor_cobrado'))['total'] or 0

    debt_by_address = (
        active_charges.filter(status__in=[Charge.Status.PENDING, Charge.Status.PARTIAL, Charge.Status.OVERDUE])
        .values('address_id', 'address__label', 'address__owner_name')
        .annotate(debt=Sum(F('amount') - F('paid_amount')), count=Count('pk'))
        .filter(debt__gt=0)
        .order_by('-debt', 'address__label')
    )
    recent_payments = Payment.all_objects.filter(status=Payment.Status.PAID, deleted_at__isnull=True).select_related('address').order_by('-paid_at')[:30]
    recent_certificates = SolicitudCertificado.objects.filter(valor_cobrado__isnull=False).order_by('-fecha_pago', '-creado_en')[:20]

    return render(request, 'solicitudes/contabilidad.html', {
        'invoiced': invoiced,
        'paid': paid,
        'pending': pending,
        'paid_online': paid_online,
        'certificate_income': certificate_income,
        'debt_by_address': debt_by_address,
        'recent_payments': recent_payments,
        'recent_certificates': recent_certificates,
        'charge_counts': active_charges.values('status').annotate(total=Sum(1)),
    })


@staff_member_required(login_url='/panel/ingresar/')
def contabilidad_export(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="contabilidad-jjvv.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tipo', 'Referencia', 'Dirección', 'Concepto', 'Fecha', 'Total CLP', 'Pagado CLP', 'Pendiente CLP', 'Estado', 'Correo'])

    for charge in Charge.all_objects.select_related('address').order_by('address__label', 'period_year', 'period_month'):
        writer.writerow([
            'Cuota', charge.pk, charge.address.label, f'{charge.period_month:02d}/{charge.period_year}',
            charge.due_date, charge.amount, charge.paid_amount, charge.remaining_amount, charge.status,
            charge.address.owner_email,
        ])
    for payment in Payment.all_objects.select_related('address').order_by('-created_at'):
        writer.writerow([
            'Pago Flow', payment.pk, payment.address.label, payment.description or 'Pago en línea',
            payment.paid_at or payment.created_at, payment.amount, payment.amount if payment.status == Payment.Status.PAID else 0,
            0, payment.status, payment.payer_email,
        ])
    for certificate in SolicitudCertificado.objects.filter(valor_cobrado__isnull=False).order_by('-fecha_pago'):
        writer.writerow([
            'Certificado', certificate.pk, certificate.direccion, f'Certificado {certificate.numero}',
            certificate.fecha_pago, certificate.valor_cobrado, certificate.valor_cobrado, 0, certificate.estado,
            certificate.email,
        ])
    return response
