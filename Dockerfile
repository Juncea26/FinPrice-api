# ==============================================================================
# Multi-stage Dockerfile para FinPrice API en la Nube
# Optimizado para ligereza, seguridad (non-root) y compatibilidad con Cloud Run/Render
# ==============================================================================

# STAGE 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instalar dependencias del sistema necesarias para compilar paquetes si aplica
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Compilar wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt


# STAGE 2: Runner (Imagen final ligera y endurecida)
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    PORT=8000 \
    HOST=0.0.0.0

# Instalar dependencias de ejecución esenciales (curl para healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Instalar paquetes desde los wheels compilados
COPY --from=builder /build/wheels /wheels
COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

# Crear usuario y grupo de sistema sin privilegios de root (UID/GID 10001)
RUN addgroup --system --gid 10001 finprice && \
    adduser --system --uid 10001 --ingroup finprice --no-create-home appuser

# Copiar el código fuente de la aplicación con la propiedad asignada a appuser
COPY --chown=appuser:finprice main.py .
COPY --chown=appuser:finprice app ./app

# Directorio de trabajo con permisos para SQLite y logs
RUN chown -R appuser:finprice /app

# Cambiar al usuario sin privilegios
USER appuser

EXPOSE 8000

# Healthcheck nativo consultando el endpoint de diagnóstico de FinPrice
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Comando de inicio del servidor ASGI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
