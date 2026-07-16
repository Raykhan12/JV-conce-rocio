FROM python:3.12-slim

# Variables de build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema necesarias para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código fuente
COPY . .

# Recolectar estáticos (WhiteNoise los sirve en producción)
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "jv_web.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]
