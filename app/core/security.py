"""
Módulo de seguridad: Validación X-API-Key, Rate Limiting, SSRF allowlist y sanitización.
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

logger = get_logger("core.security")

# Dominios retail verificados permitidos
ALLOWED_RETAIL_DOMAINS = {
    "falabella.com.pe",
    "www.falabella.com.pe",
    "simple.ripley.com.pe",
    "ripley.com.pe",
    "www.ripley.com.pe",
    "hiraoka.com.pe",
    "www.hiraoka.com.pe",
    "efe.com.pe",
    "www.efe.com.pe",
    "lacuracao.pe",
    "www.lacuracao.pe",
    "tottus.com.pe",
    "www.tottus.com.pe",
    "metro.pe",
    "www.metro.pe",
    "wong.pe",
    "www.wong.pe",
    "images.samsung.com",
    "store.storeimages.cdn-apple.com",
    "media.falabella.com",
    "rimage.ripley.com.pe",
    "dlcdnwebimgs.asus.com",
    "i02.appmifile.com",
    "www.lg.com",
}

CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x1f\x7f]")
HTML_TAG_REGEX = re.compile(r"<[^>]+>")


# ==============================================================================
# 1. AUTENTICACIÓN ADMINISTRATIVA (X-API-Key con secrets.compare_digest)
# ==============================================================================

async def verify_admin_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """Valida la cabecera X-API-Key usando secrets.compare_digest contra ataques de timing."""
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
# 2. RATE LIMITER POR IP CON VENTANA DESLIZANTE Y SCOPES
# ==============================================================================

class InMemoryRateLimiter:
    """Ventana deslizante que divide cuotas de lectura de cuotas de escritura."""

    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(
        self, client_ip: str, max_requests: int, window_seconds: int = 60, scope: str = "default"
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds
        key = f"{scope}:{client_ip}"

        timestamps = [ts for ts in self._requests[key] if ts > window_start]
        self._requests[key] = timestamps

        if len(timestamps) >= max_requests:
            earliest = timestamps[0]
            retry_after = max(1, int(window_seconds - (now - earliest)))
            return False, retry_after

        self._requests[key].append(now)
        return True, 0

    def reset(self) -> None:
        """Reinicia los contadores para pruebas automatizadas."""
        self._requests.clear()


rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    """Obtiene la IP del cliente considerando cabeceras de proxy inverso."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


async def check_read_rate_limit(request: Request) -> None:
    """Limita lecturas a RATE_LIMIT_READ_PER_MINUTE."""
    ip = get_client_ip(request)
    allowed, retry_after = rate_limiter.is_allowed(
        ip, max_requests=settings.RATE_LIMIT_READ_PER_MINUTE, window_seconds=60, scope="read"
    )
    if not allowed:
        logger.warning("Rate limit de lectura excedido", extra={"client_ip": ip})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Límite de peticiones de lectura excedido. Intenta más tarde.",
            headers={"Retry-After": str(retry_after)},
        )


async def check_write_rate_limit(request: Request) -> None:
    """Limita escrituras a RATE_LIMIT_WRITE_PER_MINUTE."""
    ip = get_client_ip(request)
    allowed, retry_after = rate_limiter.is_allowed(
        ip, max_requests=settings.RATE_LIMIT_WRITE_PER_MINUTE, window_seconds=60, scope="write"
    )
    if not allowed:
        logger.warning("Rate limit de escritura excedido", extra={"client_ip": ip})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Límite de peticiones de escritura excedido. Intenta más tarde.",
            headers={"Retry-After": str(retry_after)},
        )


# ==============================================================================
# 3. PREVENCIÓN DE SSRF, XSS Y CARACTERES DE CONTROL
# ==============================================================================

def sanitize_input_text(text: Optional[str], max_length: int = 80) -> Optional[str]:
    """Sanitiza parámetros de consulta rechazando caracteres de control e inyecciones."""
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

    cleaned = HTML_TAG_REGEX.sub("", cleaned)
    return html.escape(cleaned)


def validate_safe_url(url: str, check_allowlist: bool = False) -> str:
    """
    Valida estrictamente que una URL:
    - Utilice el esquema seguro 'https://'
    - No apunte a rangos de IP privados, loopback o metadata de cloud
    - Opcionalmente pertenezca a la allowlist de retailers peruanos
    """
    if not url.startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La URL debe utilizar obligatoriamente el protocolo seguro 'https://'.",
        )

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URL inválida: no contiene un nombre de host válido.",
        )

    if hostname.lower() in {"localhost", "127.0.0.1", "0.0.0.0"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Destino host no permitido por políticas de seguridad.",
        )

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No se permiten destinos en redes privadas o reservadas.",
            )
    except ValueError:
        pass

    if check_allowlist and hostname.lower() not in ALLOWED_RETAIL_DOMAINS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dominio no autorizado en la lista blanca de retail: {hostname}",
        )

    return url
