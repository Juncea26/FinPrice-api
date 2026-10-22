"""
Módulo de seguridad, validación X-API-Key, prevención de SSRF/XSS y Rate Limiter en memoria.
"""
import html
import ipaddress
import re
import secrets
import time
from collections import defaultdict
from typing import Dict, List, Optional
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("security")


# ==============================================================================
# 1. AUTENTICACIÓN ADMINISTRATIVA (X-API-Key)
# ==============================================================================

async def verify_admin_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    Valida la cabecera X-API-Key contra FINPRICE_ADMIN_API_KEY usando secrets.compare_digest
    para mitigar ataques de temporización (timing attacks).
    """
    if not x_api_key:
        logger.warning("Intento de acceso administrativo sin cabecera X-API-Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida: Cabecera 'X-API-Key' ausente.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    expected_key = settings.FINPRICE_ADMIN_API_KEY
    if not secrets.compare_digest(x_api_key, expected_key):
        logger.warning("Intento de acceso administrativo con X-API-Key inválida")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: 'X-API-Key' inválida.",
        )

    return x_api_key


# ==============================================================================
# 2. RATE LIMITER EN MEMORIA (Sliding Window per IP)
# ==============================================================================

class InMemoryRateLimiter:
    """
    Implementación de rate limiting basada en ventana deslizante en memoria por IP y ámbito (scope).
    Separa las cuotas de lectura de las cuotas de escritura/sincronización.
    """

    def __init__(self):
        # key: f"{scope}:{ip}" -> list of timestamps
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(
        self, client_ip: str, max_requests: int, window_seconds: int = 60, scope: str = "default"
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds
        key = f"{scope}:{client_ip}"

        # Limpiar marcas de tiempo expiradas
        timestamps = [ts for ts in self._requests[key] if ts > window_start]
        self._requests[key] = timestamps

        if len(timestamps) >= max_requests:
            earliest = timestamps[0]
            retry_after = max(1, int(window_seconds - (now - earliest)))
            return False, retry_after

        self._requests[key].append(now)
        return True, 0

    def reset(self) -> None:
        """Reinicia los contadores (útil en pruebas)."""
        self._requests.clear()


rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extrae la IP real del cliente considerando proxies reversos comunes."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Tomar la primera IP de la cadena (la del cliente original)
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


async def check_read_rate_limit(request: Request) -> None:
    """Dependencia para limitar peticiones de lectura (p. ej. 60 req/min)."""
    ip = get_client_ip(request)
    allowed, retry_after = rate_limiter.is_allowed(
        ip, max_requests=settings.RATE_LIMIT_READ_PER_MINUTE, window_seconds=60, scope="read"
    )
    if not allowed:
        logger.warning("Rate limit excedido para IP en lectura", extra={"client_ip": ip})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Límite de peticiones de lectura excedido. Intenta de nuevo más tarde.",
            headers={"Retry-After": str(retry_after)},
        )


async def check_write_rate_limit(request: Request) -> None:
    """Dependencia para limitar peticiones de escritura/sincronización (p. ej. 5 req/min)."""
    ip = get_client_ip(request)
    allowed, retry_after = rate_limiter.is_allowed(
        ip, max_requests=settings.RATE_LIMIT_WRITE_PER_MINUTE, window_seconds=60, scope="write"
    )
    if not allowed:
        logger.warning("Rate limit excedido para IP en escritura", extra={"client_ip": ip})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Límite de peticiones de escritura excedido. Intenta de nuevo más tarde.",
            headers={"Retry-After": str(retry_after)},
        )


# ==============================================================================
# 3. PREVENCIÓN DE SSRF, CONTROL CHARACTERS Y XSS
# ==============================================================================

# Caracteres de control no permitidos (0x00 - 0x1F, 0x7F)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x1f\x7f]")
HTML_TAG_REGEX = re.compile(r"<[^>]+>")


def sanitize_input_text(text: Optional[str], max_length: int = 80) -> Optional[str]:
    """
    Sanitiza strings de consulta:
    - Limita longitud
    - Rechaza o remueve caracteres de control
    - Remueve etiquetas HTML y escapa entidades
    """
    if text is None:
        return None

    cleaned = text.strip()
    if len(cleaned) > max_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El parámetro excede la longitud máxima permitida de {max_length} caracteres.",
        )

    if CONTROL_CHAR_REGEX.search(cleaned):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El parámetro contiene caracteres de control no permitidos.",
        )

    # Limpiar posibles inyecciones de etiquetas HTML
    cleaned = HTML_TAG_REGEX.sub("", cleaned)
    return html.escape(cleaned)


def validate_safe_url(url: str) -> str:
    """
    Valida estrictamente que una URL:
    - Utilice el esquema seguro 'https://'
    - No apunte a rangos de IP privados, loopback (127.0.0.1) o metadata de cloud (169.254.169.254).
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La URL debe utilizar obligatoriamente el protocolo seguro 'https://'.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URL inválida: no contiene un nombre de host válido.",
        )

    # Prohibir localhost explícito
    if hostname.lower() in {"localhost", "127.0.0.1", "0.0.0.0"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dirección host no permitida por políticas de seguridad.",
        )

    # Verificar si es una IP privada o reservada
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No se permiten destinos en redes privadas o reservadas.",
            )
    except ValueError:
        # Es un nombre de dominio regular (FQDN), lo cual es lo esperado
        pass

    return url
