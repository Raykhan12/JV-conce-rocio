from django.shortcuts import render, redirect
from django.core.mail import EmailMessage
from django.conf import settings
from django.utils.timezone import now

from .models import Noticia
from .forms import CertificadoForm, DenunciaForm


def inicio(request):
    noticias_recientes = Noticia.objects.filter(publicada=True)[:3]
    return render(request, 'publico/inicio.html', {'noticias': noticias_recientes})


def noticias(request):
    todas = Noticia.objects.filter(publicada=True)
    return render(request, 'publico/noticias.html', {'noticias': todas})


def formularios(request):
    return render(request, 'publico/formularios.html')


# ─── Certificado de Residencia ───────────────────────────────────────────────

def certificado(request):
    if request.method == 'POST':
        form = CertificadoForm(request.POST, request.FILES)
        if form.is_valid():
            solicitud = form.save()
            _notificar_junta(
                asunto=f'[Certificado] Nueva solicitud de {solicitud.nombre}',
                cuerpo=(
                    f'Se recibió una nueva solicitud de Certificado de Residencia.\n'
                    f'{'─'*50}\n'
                    f'Nombre:    {solicitud.nombre}\n'
                    f'RUT:       {solicitud.rut}\n'
                    f'Dirección: {solicitud.direccion}\n'
                    f'Teléfono:  {solicitud.telefono}\n'
                    f'Email:     {solicitud.email}\n'
                    f'Canal:     {solicitud.get_canal_display()}\n'
                    f'Motivo:    {solicitud.get_motivo_display()}'
                    + (f' ({solicitud.motivo_otro})' if solicitud.motivo_otro else '') + '\n'
                    f'Socio:     {"Sí" if solicitud.es_socio else "No"}\n'
                    f'{'─'*50}\n'
                    f'Ver en el panel: {settings.SITE_URL}/panel/certificado/{solicitud.pk}/\n'
                ),
            )
            return redirect('cert_exito')
    else:
        form = CertificadoForm()
    return render(request, 'publico/cert_residencia.html', {'form': form})


def cert_exito(request):
    return render(request, 'publico/cert_exito.html')


# ─── Denuncia Vecinal ────────────────────────────────────────────────────────

def denuncia(request):
    if request.method == 'POST':
        form = DenunciaForm(request.POST)
        if form.is_valid():
            reporte = form.save()
            _notificar_junta(
                asunto=f'[Denuncia {reporte.get_urgencia_display()}] {reporte.get_categoria_display()} — {reporte.nombre}',
                cuerpo=(
                    f'Se recibió una nueva denuncia vecinal.\n'
                    f'{'─'*50}\n'
                    f'Nombre:    {reporte.nombre}\n'
                    f'Dirección: {reporte.direccion}\n'
                    f'Teléfono:  {reporte.telefono}\n'
                    + (f'Email:     {reporte.email}\n' if reporte.email else '')
                    + f'Categoría: {reporte.get_categoria_display()}\n'
                    f'Urgencia:  {reporte.get_urgencia_display()}\n'
                    f'Ubicación: {reporte.ubicacion}\n'
                    f'{'─'*50}\n'
                    f'Descripción:\n{reporte.descripcion}\n'
                    f'{'─'*50}\n'
                    f'Ver en el panel: {settings.SITE_URL}/panel/denuncia/{reporte.pk}/\n'
                ),
            )
            return redirect('denuncia_exito')
    else:
        form = DenunciaForm()
    return render(request, 'publico/denuncia.html', {'form': form})


def denuncia_exito(request):
    return render(request, 'publico/denuncia_exito.html')


# ─── Helper interno ──────────────────────────────────────────────────────────

def _notificar_junta(asunto, cuerpo):
    destino = settings.JUNTA_EMAIL
    if not destino:
        return
    try:
        EmailMessage(
            subject=asunto,
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destino],
        ).send(fail_silently=True)
    except Exception:
        pass
