from django.contrib import admin
from .models import SolicitudCertificado, DenunciaVecinal


@admin.register(SolicitudCertificado)
class CertificadoAdmin(admin.ModelAdmin):
    list_display   = ('nombre', 'rut', 'motivo', 'canal', 'es_socio', 'estado', 'asignado_a', 'creado_en')
    list_filter    = ('estado', 'motivo', 'canal', 'es_socio')
    list_editable  = ('estado', 'asignado_a')
    search_fields  = ('nombre', 'rut', 'email', 'direccion')
    readonly_fields = ('creado_en', 'actualizado')
    fieldsets = (
        ('Datos del Solicitante', {
            'fields': ('nombre', 'rut', 'direccion', 'telefono', 'email'),
        }),
        ('Detalles de la Solicitud', {
            'fields': ('canal', 'motivo', 'motivo_otro', 'es_socio', 'boleta_servicio', 'autorizado'),
        }),
        ('Gestión Interna', {
            'fields': ('estado', 'asignado_a', 'notas_internas'),
        }),
        ('Fechas', {
            'fields': ('creado_en', 'actualizado'),
            'classes': ('collapse',),
        }),
    )


@admin.register(DenunciaVecinal)
class DenunciaAdmin(admin.ModelAdmin):
    list_display   = ('nombre', 'categoria', 'urgencia', 'ubicacion', 'estado', 'asignado_a', 'creado_en')
    list_filter    = ('estado', 'categoria', 'urgencia')
    list_editable  = ('estado', 'asignado_a')
    search_fields  = ('nombre', 'direccion', 'descripcion', 'ubicacion')
    readonly_fields = ('creado_en', 'actualizado', 'horario_display')
    fieldsets = (
        ('Datos del Solicitante', {
            'fields': ('nombre', 'direccion', 'telefono', 'email'),
        }),
        ('Problema Reportado', {
            'fields': ('categoria', 'descripcion', 'ubicacion', 'horario_display', 'ocurrido_antes', 'urgencia'),
        }),
        ('Evidencia', {
            'fields': ('desc_evidencia', 'notas_adicionales'),
        }),
        ('Gestión Interna', {
            'fields': ('estado', 'asignado_a', 'notas_internas'),
        }),
        ('Fechas', {
            'fields': ('creado_en', 'actualizado'),
            'classes': ('collapse',),
        }),
    )
