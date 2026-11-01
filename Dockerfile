# ==============================================================================
# Dockerfile de Producción para FinPrice API en Render (Límite estricto 512 MB RAM)
# Optimizado para arranque en < 2 segundos, mínimo consumo de memoria y 1 solo worker
# ==============================================================================

FROM python:3.11-slim

WORKDIR /app

# Variables de entorno críticas para optimización de RAM y logging inmediato
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MALLOC_TRIM_THRESHOLD_=65536 \
    ENVIRONMENT=production \
    PORT=8000

# Instalar dependencias esenciales de sistema (curl para healthcheck nativo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Crear usuario sin privilegios para mayor seguridad
RUN addgroup --system --gid 10001 finprice && \
    adduser --system --uid 10001 --ingroup finprice --no-create-home appuser

# Copiar el código de la aplicación
COPY main.py .
COPY app ./app

# Asignar permisos al usuario de ejecución
RUN chown -R appuser:finprice /app
USER appuser

EXPOSE 8000

# Healthcheck interno apuntando al endpoint ultraligero /ping
HEALTHCHECK --interval=20s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/ping || exit 1

# Comando de inicio: 1 solo worker para no duplicar RAM, limitando concurrencia
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --limit-concurrency 40 --timeout-keep-alive 30"]
