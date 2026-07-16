# Planificación: Sitio Web Junta de Vecinos — Villa Concepción-Rocío

## 1. Visión General

Sitio web con dos áreas:
- **Pública:** Inicio, Noticias, Formularios (residencia y denuncias)
- **Privada (Admin):** Login para miembros de la junta, gestión y seguimiento de solicitudes

---

## 2. Stack Tecnológico

| Capa | Tecnología | Justificación |
|---|---|---|
| Framework full-stack | **Django 5** | Python nativo; incluye ORM, auth, admin y formularios de fábrica |
| Panel admin | **Django Admin** | Dashboard de solicitudes con ~20 líneas de Python, sin construir desde cero |
| Base de datos | **PostgreSQL 16** | Confiable, relacional, bien soportado en K8s |
| ORM | **Django ORM** | Nativo de Django; migraciones y queries parametrizadas incluidas |
| Autenticación admin | **Django Auth** | Sistema de usuarios y sesiones nativo, sin librerías extra |
| Templates (páginas públicas) | **Django Templates + Tailwind CSS** | Server-side rendering simple, fácil de mantener |
| Contenedores | **Docker** | Imágenes para K8s |
| Ingress | **Nginx Ingress (ya configurado)** | Se reutiliza la infra existente |
| TLS | **Certbot / cert-manager (ya configurado)** | HTTPS automático |

> **Por qué Django full-stack:**
> Bajo tráfico → un solo pod es suficiente. Django maneja templates, formularios,
> autenticación y el panel admin de fábrica, sin librerías adicionales. Al conocer
> Python, el tiempo de desarrollo se reduce considerablemente.

---

## 3. Arquitectura en Kubernetes

```
Internet
    │
    ▼
Nginx Ingress (TLS via Certbot)
    │
    ├── /            → Service: django-app  (puerto 8000)
    │                    └── Pod: Django (Gunicorn + app)
    │                              │
    │                              └── Service: postgres  (puerto 5432)
    │                                       └── Pod: PostgreSQL
    │                                                └── PVC: postgres-data
    └── (solo un dominio, todo pasa por Django)
```

### Recursos K8s a crear:
- `Deployment` → django-app
- `Deployment` → postgres
- `Service` → django-app (ClusterIP)
- `Service` → postgres (ClusterIP)
- `PersistentVolumeClaim` → postgres-data
- `PersistentVolumeClaim` → django-media (boletas de servicio subidas por usuarios)
- `Secret` → postgres-credentials (usuario, contraseña, DATABASE_URL)
- `Secret` → app-secrets (DJANGO_SECRET_KEY)
- `ConfigMap` → app-config (variables no sensibles: DEBUG=False, ALLOWED_HOSTS)
- `Ingress` → con TLS, apunta a django-app

---

## 4. Estructura del Proyecto

```
jv-web/
├── jv_web/                    # Configuración principal de Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── publico/                   # App: páginas públicas
│   ├── models.py              # Modelo Noticia
│   ├── views.py               # Inicio, Noticias, Formularios
│   ├── urls.py
│   └── templates/
│       └── publico/
│           ├── base.html              # Layout base (nav, footer)
│           ├── inicio.html
│           ├── noticias.html
│           ├── formularios.html       # Selector de formulario
│           ├── cert_residencia.html   # Formulario certificado
│           ├── cert_exito.html        # Confirmación certificado
│           ├── denuncia.html          # Formulario denuncia
│           └── denuncia_exito.html    # Confirmación denuncia
├── solicitudes/               # App: modelos y admin de solicitudes
│   ├── models.py              # SolicitudCertificado + DenunciaVecinal
│   ├── admin.py               # Configuración del panel Django Admin
│   ├── forms.py               # Django Forms para ambos formularios
│   └── migrations/
├── media/                     # Archivos subidos (boletas de servicio) — montado como PVC
├── static/                    # CSS, JS, imágenes
│   └── css/
│       └── tailwind.css
├── k8s/
│   ├── namespace.yaml
│   ├── postgres-pvc.yaml
│   ├── postgres-deployment.yaml
│   ├── postgres-service.yaml
│   ├── secrets.yaml           # ⚠ NO versionar con valores reales
│   ├── configmap.yaml
│   ├── django-deployment.yaml
│   ├── django-service.yaml
│   └── ingress.yaml
├── Dockerfile
├── requirements.txt
├── .env.example               # Plantilla de variables (sin secretos)
└── docker-compose.dev.yml     # Para desarrollo local con Postgres
```

---

## 5. Modelos de Base de Datos (Django ORM)

Se usan **dos modelos separados** porque los campos de cada formulario son muy distintos.
Ambos son visibles en el panel Django Admin.

```python
# solicitudes/models.py
from django.db import models
from django.contrib.auth.models import User

ESTADO_CHOICES = [
    ('PENDIENTE',  'Pendiente'),
    ('EN_PROCESO', 'En Proceso'),
    ('COMPLETADO', 'Completado'),
    ('RECHAZADO',  'Rechazado'),
]


class SolicitudCertificado(models.Model):
    """Formulario: Solicitud de Certificado de Residencia"""

    CANAL_CHOICES = [
        ('PRESENCIAL', 'Presencial'),
        ('EMAIL',      'Correo electrónico'),
    ]
    MOTIVO_CHOICES = [
        ('TRAMITE_PERSONAL',  'Trámite personal'),
        ('BENEFICIO',         'Postulación a beneficio'),
        ('MATRICULA',         'Matrícula escolar'),
        ('ACREDITACION',      'Acreditación de domicilio'),
        ('OTRO',              'Otro'),
    ]

    # Datos del solicitante
    nombre      = models.CharField('Nombre completo', max_length=150)
    rut         = models.CharField('RUT', max_length=12)
    direccion   = models.CharField('Dirección', max_length=200)
    telefono    = models.CharField('Teléfono de contacto', max_length=20)
    email       = models.EmailField('Correo electrónico')

    # Detalles de la solicitud
    canal       = models.CharField('Canal de atención', max_length=15, choices=CANAL_CHOICES)
    motivo      = models.CharField('Motivo', max_length=20, choices=MOTIVO_CHOICES)
    motivo_otro = models.CharField('Motivo (otro)', max_length=200, blank=True)
    es_socio    = models.BooleanField('¿Es socio/a de la JJVV?')

    # Solo para no socios: boleta de servicio
    boleta_servicio = models.FileField(
        'Boleta de servicio (luz o agua)',
        upload_to='boletas/%Y/%m/',
        blank=True, null=True
    )

    # Autorización
    autorizado  = models.BooleanField('Autoriza uso de datos personales', default=False)

    # Gestión interna
    estado      = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE')
    asignado_a  = models.ForeignKey(User, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name='certificados_asignados')
    notas_internas = models.TextField('Notas internas', blank=True)
    creado_en   = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Solicitud de Certificado'
        verbose_name_plural = 'Solicitudes de Certificado'
        ordering = ['-creado_en']

    def __str__(self):
        return f"Certificado — {self.nombre} ({self.get_estado_display()})"


class DenunciaVecinal(models.Model):
    """Formulario: Reporte de Problemáticas Vecinales"""

    CATEGORIA_CHOICES = [
        ('SEGURIDAD',    '🚨 Seguridad'),
        ('INFRAESTRUC',  '💡 Infraestructura'),
        ('MEDIOAMBIENTE','🌳 Medio Ambiente'),
        ('TRANSITO',     '🚗 Tránsito y Transporte'),
        ('CONVIVENCIA',  '🏘 Convivencia Vecinal'),
        ('OTRO',         '📋 Otro'),
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
    nombre      = models.CharField('Nombre completo', max_length=150)
    direccion   = models.CharField('Dirección (calle y número)', max_length=200)
    telefono    = models.CharField('Teléfono de contacto', max_length=20)
    email       = models.EmailField('Correo electrónico', blank=True)

    # Tipo de problema
    categoria   = models.CharField('Categoría', max_length=15, choices=CATEGORIA_CHOICES)

    # Detalles
    descripcion       = models.TextField('Descripción detallada')
    ubicacion         = models.CharField('Ubicación específica', max_length=300)
    horario           = models.JSONField('Horario en que ocurre', default=list, blank=True)
    # ^ Lista de valores de HORARIO_CHOICES, ej: ["MANANA", "TARDE"]
    ocurrido_antes    = models.TextField('¿Ha ocurrido antes?', blank=True)

    # Urgencia
    urgencia    = models.CharField('Urgencia', max_length=10, choices=URGENCIA_CHOICES)

    # Evidencia
    desc_evidencia    = models.TextField('Descripción de evidencia disponible', blank=True)
    notas_adicionales = models.TextField('Notas adicionales', blank=True)

    # Gestión interna
    estado      = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE')
    asignado_a  = models.ForeignKey(User, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name='denuncias_asignadas')
    notas_internas = models.TextField('Notas internas', blank=True)
    creado_en   = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Denuncia Vecinal'
        verbose_name_plural = 'Denuncias Vecinales'
        ordering = ['-creado_en']

    def __str__(self):
        return f"Denuncia [{self.get_urgencia_display()}] — {self.nombre} ({self.get_estado_display()})"


# publico/models.py
class Noticia(models.Model):
    titulo    = models.CharField(max_length=200)
    contenido = models.TextField()
    imagen    = models.ImageField(upload_to='noticias/', blank=True)
    publicada = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Noticias'
        ordering = ['-creado_en']

    def __str__(self):
        return self.titulo
```

> Los usuarios admin se gestionan con el modelo `User` nativo de Django.
> No es necesario crear un modelo de usuario propio.

---

## 6. Seguridad (OWASP Top 10 — puntos clave)

| Amenaza | Medida implementada |
|---|---|
| **Inyección SQL** | Django ORM con queries parametrizadas — nunca `raw()` con input del usuario |
| **Autenticación rota** | Django Auth usa PBKDF2 con salt para contraseñas; sesiones firmadas con `SECRET_KEY` |
| **Datos sensibles expuestos** | `SECRET_KEY` y credenciales de BD en K8s Secrets; HTTPS obligatorio; `DEBUG=False` en producción |
| **Control de acceso roto** | Decorador `@login_required` en vistas admin; Django Admin solo accesible a `is_staff=True` |
| **Configuración insegura** | `ALLOWED_HOSTS` configurado; puerto de Postgres no expuesto fuera del cluster |
| **CSRF** | Django incluye protección CSRF automática en todos los formularios POST |
| **Rate limiting** | Anotación en Ingress Nginx para limitar peticiones al login y formularios |
| **Validación de entrada** | Django Forms validan y limpian todos los campos antes de llegar a la BD |

**Settings de seguridad a activar en `settings.py` (producción):**
```python
DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
```

---

## 7. Pasos de Implementación

### Fase 1 — Proyecto base (local)
- [ ] 1.1 Crear virtualenv e instalar Django: `python -m venv venv && pip install django psycopg2-binary gunicorn pillow`
- [ ] 1.2 Crear proyecto: `django-admin startproject jv_web` y apps: `python manage.py startapp publico` / `startapp solicitudes`
- [ ] 1.3 Configurar `docker-compose.dev.yml` con Postgres para desarrollo local
- [ ] 1.4 Definir modelos en `solicitudes/models.py` y `publico/models.py`
- [ ] 1.5 Primera migración: `python manage.py makemigrations && python manage.py migrate`
- [ ] 1.6 Crear superusuario admin inicial: `python manage.py createsuperuser`

### Fase 2 — Páginas públicas
- [ ] 2.1 Página de Inicio (`/`) — Hero, presentación de la junta, acceso rápido a formularios
- [ ] 2.2 Página de Noticias (`/noticias`) — Lista de noticias publicadas desde BD
- [ ] 2.3 Página `/formularios/` — Tarjetas para elegir entre los dos formularios
- [ ] 2.4 Formulario Certificado de Residencia (`/formularios/certificado/`)
      - Campos: nombre, RUT, dirección, teléfono, email, canal, motivo (+otro), ¿es socio?
      - Lógica condicional: si no es socio, mostrar campo de carga de boleta
      - Checkbox de autorización de datos personales (obligatorio)
- [ ] 2.5 Formulario Denuncia Vecinal (`/formularios/denuncia/`)
      - Campos: nombre, dirección, teléfono, email (opcional)
      - Categoría, descripción detallada, ubicación específica
      - Horario multi-selección, ¿ocurrió antes?, urgencia
      - Descripción de evidencia y notas adicionales (opcionales)
- [ ] 2.6 Páginas de confirmación (`/formularios/certificado/exito/` y `/formularios/denuncia/exito/`)
- [ ] 2.7 Agregar Tailwind CSS vía CDN o build estático

### Fase 3 — Panel Admin (Django Admin)
- [ ] 3.1 Registrar `SolicitudCertificado` en admin: columnas nombre, estado, canal, motivo, es_socio, asignado, fecha
- [ ] 3.2 Registrar `DenunciaVecinal` en admin: columnas nombre, categoría, urgencia, estado, asignado, fecha
- [ ] 3.3 Filtros laterales por estado y categoría/motivo en ambos modelos
- [ ] 3.4 Campos `estado` y `asignado_a` editables directamente desde el listado
- [ ] 3.5 Campo `notas_internas` visible solo en la vista de detalle (no en el listado)
- [ ] 3.6 Registrar `Noticia` en admin para gestión de publicaciones
- [ ] 3.7 El login de `/admin/` ya viene incluido en Django — no requiere código extra

### Fase 4 — Containerización
- [ ] 4.1 Escribir `Dockerfile` con imagen `python:3.12-slim` + Gunicorn
- [ ] 4.2 Configurar `collectstatic` en el build para servir archivos estáticos vía WhiteNoise
- [ ] 4.3 Probar imagen local: `docker build -t raykhan007/jv-web:latest .` + `docker run`
- [ ] 4.4 Subir imagen: `docker push raykhan007/jv-web:latest`

### Fase 5 — Kubernetes
- [ ] 5.1 Crear namespace: `kubectl create namespace jv-web`
- [ ] 5.2 Aplicar `postgres-pvc.yaml`, `postgres-deployment.yaml`, `postgres-service.yaml`
- [ ] 5.3 Crear secrets con valores reales: `kubectl create secret generic ...` (NO usando el YAML en git)
- [ ] 5.4 Aplicar `django-deployment.yaml` y `django-service.yaml`
- [ ] 5.5 Configurar `ingress.yaml` con el dominio y la anotación de TLS de certbot/cert-manager
- [ ] 5.6 Correr migraciones desde un Job de K8s: `python manage.py migrate`
- [ ] 5.7 Verificar HTTPS funcionando

### Fase 6 — Mejoras opcionales
- [ ] 6.1 Notificación por email al llegar una solicitud nueva
      - Usar `django.core.mail` con `EmailMessage`
      - Agregar a K8s Secret: `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`
      - Enviar al recibir el POST exitoso en la vista (o con una señal `post_save`)
- [ ] 6.2 Personalizar el tema visual del Django Admin (logo de la junta, colores)
- [ ] 6.3 CronJob de K8s para backups automáticos de la BD (`pg_dump`)

---

## 8. Ejemplos de archivos clave

### Ingress YAML
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: jv-web-ingress
  namespace: jv-web
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    # Si usas cert-manager con Let's Encrypt:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    # Rate limiting (5 req/s por IP)
    nginx.ingress.kubernetes.io/limit-rps: "5"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - villasconcerocio.cl
      secretName: jv-web-tls
  rules:
    - host: villasconcerocio.cl
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: django-app
                port:
                  number: 8000
```

### Dockerfile (Django + Gunicorn)
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Recolectar archivos estáticos en el build (servidos por WhiteNoise)
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "jv_web.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
```

> Imagen publicada en Docker Hub como `raykhan007/jv-web:latest`

### Panel Admin (~30 líneas de Python para ambos formularios)
```python
# solicitudes/admin.py
from django.contrib import admin
from .models import SolicitudCertificado, DenunciaVecinal

@admin.register(SolicitudCertificado)
class CertificadoAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'rut', 'motivo', 'canal', 'es_socio', 'estado', 'asignado_a', 'creado_en')
    list_filter   = ('estado', 'motivo', 'canal', 'es_socio')
    list_editable = ('estado', 'asignado_a')
    search_fields = ('nombre', 'rut', 'email', 'direccion')
    readonly_fields = ('creado_en', 'actualizado')

@admin.register(DenunciaVecinal)
class DenunciaAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'categoria', 'urgencia', 'estado', 'asignado_a', 'creado_en')
    list_filter   = ('estado', 'categoria', 'urgencia')
    list_editable = ('estado', 'asignado_a')
    search_fields = ('nombre', 'direccion', 'descripcion', 'ubicacion')
    readonly_fields = ('creado_en', 'actualizado')
```

---

## 9. Notas Importantes

1. **Nunca versionar secretos en git.** El archivo `k8s/secrets.yaml` debe estar en `.gitignore`. Usar `kubectl create secret` directamente en el cluster.
2. **Primer usuario admin:** `python manage.py createsuperuser` en el pod al primer deploy. El panel `/admin/` de Django solo acepta usuarios con `is_staff=True`.
3. **No hay registro público de usuarios:** Los miembros de la junta solo pueden ser creados por el superusuario desde el panel admin.
4. **Backups de BD:** Configurar un CronJob de K8s que haga `pg_dump` periódico y lo guarde en un volumen o storage externo.
5. **Archivos estáticos:** Usar **WhiteNoise** (`pip install whitenoise`) para que Gunicorn sirva los estáticos sin configuración extra en Nginx. Agregar al `MIDDLEWARE` de Django.
6. **Archivos de media (boletas):** El directorio `media/` debe estar en un **PVC montado** en el pod de Django. Si el pod se recrea, los archivos no se pierden. Configurar `MEDIA_ROOT` apuntando al mountPath del PVC.
7. **Imágenes Docker:** Si no tienes un registry privado, Docker Hub en plan gratuito sirve para bajo tráfico. Alternativa: instalar un registry dentro del mismo cluster.

---

## 10. Pendiente (confirmar antes de implementar)

- [x] ~~Dominio/hostname del sitio~~ ✅ `villasconcerocio.cl`
- [x] ~~Campos del formulario de Certificado de Residencia~~ ✅
- [x] ~~Campos del formulario de Denuncia Vecinal~~ ✅
- [x] ~~¿Se necesita adjuntar archivos?~~ ✅ Solo boleta de servicio en certificado (no socios)
- [x] ~~¿Se quiere notificación por email al llegar una solicitud?~~ ✅ Sí (requiere configurar SMTP)
- [x] ~~¿Quién gestiona las noticias?~~ ✅ Desde el panel `/admin/`
- [x] ~~Registry de imágenes Docker~~ ✅ Docker Hub: `raykhan007`

✅ **Toda la información está completa. Se puede iniciar la implementación.**
