from django.db import models
from django.contrib.auth.models import User

ESTADO_CHOICES = [
    ('PENDIENTE',  'Pendiente'),
    ('EN_PROCESO', 'En Proceso'),
    ('COMPLETADO', 'Completado'),
    ('RECHAZADO',  'Rechazado'),
]


class SolicitudCertificado(models.Model):
    CANAL_CHOICES = [
        ('PRESENCIAL', 'Presencial'),
        ('EMAIL',      'Correo electrónico'),
    ]
    MOTIVO_CHOICES = [
        ('TRAMITE_PERSONAL', 'Trámite personal'),
        ('BENEFICIO',        'Postulación a beneficio'),
        ('MATRICULA',        'Matrícula escolar'),
        ('ACREDITACION',     'Acreditación de domicilio'),
        ('OTRO',             'Otro'),
    ]

    # Datos del solicitante
    nombre    = models.CharField('Nombre completo', max_length=150)
    rut       = models.CharField('RUT', max_length=12)
    direccion = models.CharField('Dirección', max_length=200)
    telefono  = models.CharField('Teléfono de contacto', max_length=20)
    email     = models.EmailField('Correo electrónico')

    # Detalles de la solicitud
    canal        = models.CharField('Canal de atención', max_length=15, choices=CANAL_CHOICES)
    motivo       = models.CharField('Motivo', max_length=20, choices=MOTIVO_CHOICES)
    motivo_otro  = models.CharField('Motivo (especificar)', max_length=200, blank=True)
    es_socio     = models.BooleanField('¿Es socio/a de la JJVV?')

    # Solo para no socios
    boleta_servicio = models.FileField(
        'Boleta de servicio (luz o agua)',
        upload_to='boletas/%Y/%m/',
        blank=True,
        null=True,
    )

    # Autorización de datos personales
    autorizado = models.BooleanField('Autoriza uso de datos personales', default=False)

    # Gestión interna
    estado         = models.CharField('Estado', max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE')
    asignado_a     = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='certificados_asignados', verbose_name='Asignado a',
    )
    notas_internas = models.TextField('Notas internas', blank=True)
    creado_en      = models.DateTimeField(auto_now_add=True)
    actualizado    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Solicitud de Certificado'
        verbose_name_plural = 'Solicitudes de Certificado'
        ordering            = ['-creado_en']

    def __str__(self):
        return f'Certificado — {self.nombre} [{self.get_estado_display()}]'


class DenunciaVecinal(models.Model):
    CATEGORIA_CHOICES = [
        ('SEGURIDAD',     '🚨 Seguridad'),
        ('INFRAESTRUC',   '💡 Infraestructura'),
        ('MEDIOAMBIENTE', '🌳 Medio Ambiente'),
        ('TRANSITO',      '🚗 Tránsito y Transporte'),
        ('CONVIVENCIA',   '🏘 Convivencia Vecinal'),
        ('OTRO',          '📋 Otro'),
    ]
    URGENCIA_CHOICES = [
        ('URGENTE', '🔴 Urgente — acción inmediata'),
        ('ALTA',    '🟡 Alta — dentro de esta semana'),
        ('MEDIA',   '🟢 Media — dentro del mes'),
        ('BAJA',    '⚪ Baja — sin urgencia inmediata'),
    ]
    HORARIO_CHOICES = [
        ('MANANA',    '🌅 Mañana (06:00–12:00)'),
        ('TARDE',     '☀️ Tarde (12:00–18:00)'),
        ('NOCHE',     '🌙 Noche (18:00–00:00)'),
        ('MADRUGADA', '🕐 Madrugada (00:00–06:00)'),
        ('TODO_DIA',  '⏰ Todo el día'),
        ('NO_APLICA', '❓ No aplica / No sé'),
    ]

    # Datos del solicitante
    nombre    = models.CharField('Nombre completo', max_length=150)
    direccion = models.CharField('Dirección (calle y número)', max_length=200)
    telefono  = models.CharField('Teléfono de contacto', max_length=20)
    email     = models.EmailField('Correo electrónico', blank=True)

    # Tipo de problema
    categoria = models.CharField('Categoría', max_length=15, choices=CATEGORIA_CHOICES)

    # Detalles
    descripcion    = models.TextField('Descripción detallada')
    ubicacion      = models.CharField('Ubicación específica', max_length=300)
    # Lista de claves de HORARIO_CHOICES, ej: ["MANANA", "NOCHE"]
    horario        = models.JSONField('Horario en que ocurre', default=list, blank=True)
    ocurrido_antes = models.TextField('¿Ha ocurrido antes? ¿Cuándo?', blank=True)

    # Urgencia
    urgencia = models.CharField('Urgencia', max_length=10, choices=URGENCIA_CHOICES)

    # Evidencia (descripción textual, sin adjunto)
    desc_evidencia    = models.TextField('Descripción de evidencia disponible', blank=True)
    notas_adicionales = models.TextField('Notas adicionales', blank=True)

    # Gestión interna
    estado         = models.CharField('Estado', max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE')
    asignado_a     = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='denuncias_asignadas', verbose_name='Asignado a',
    )
    notas_internas = models.TextField('Notas internas', blank=True)
    creado_en      = models.DateTimeField(auto_now_add=True)
    actualizado    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Denuncia Vecinal'
        verbose_name_plural = 'Denuncias Vecinales'
        ordering            = ['-creado_en']

    def __str__(self):
        return f'Denuncia [{self.get_urgencia_display()}] — {self.nombre} [{self.get_estado_display()}]'

    def horario_display(self):
        mapping = dict(self.HORARIO_CHOICES)
        return ', '.join(mapping.get(h, h) for h in self.horario)
    horario_display.short_description = 'Horario'
