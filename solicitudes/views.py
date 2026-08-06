from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect

from .models import SolicitudCertificado, DenunciaVecinal, SolicitudIngreso, ESTADO_CHOICES


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


@login_required
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


@login_required
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


@login_required
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


@login_required
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
