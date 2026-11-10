"""
Módulo de seguridad:
1. Rate Limiting por IP (50 peticiones/minuto por IP con ventana deslizante de 60s)
2. WAF + Lista Negra de IPs Maliciosas (IP_BLACKLIST) con autobloqueo dinámico y Anti-SQLi/XSS
3. Autenticación por Token firmada con HMAC-SHA256 (Bearer / X-FinPrice-Token) para la App Android
4. Validación administrativa X-API-Key con secrets.compare_digest
5. Prevención de SSRF (allowlist retail) y sanitización de entradas
"""
import base64
import hashlib
import hmac
import html
import ipaddress
import json
import re
import secrets
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set
from urllib.parse import unquote, urlparse

from fastapi import Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("core.security")

MAX_REQUESTS_PER_MINUTE_PER_IP: int = 50
MAX_VIOLATIONS_BEFORE_BLACKLIST: int = 5

# Conjunto precargado de IPs maliciosas / escáneres conocidos
STATIC_IP_BLACKLIST: Set[str] = {
    "185.220.101.1",
    "45.155.205.233",
    "194.165.16.11",
    "89.248.165.50",
    "91.240.118.172",
}

# Conjunto activo en memoria (incluye autobloqueo dinámico en tiempo real)
IP_BLACKLIST: Set[str] = set(STATIC_IP_BLACKLIST)

# Patrones de ataque WAF (SQL Injection y Cross-Site Scripting)
WAF_MALICIOUS_PATTERNS = re.compile(
    r"(?:"
    r"'\s*or\s+['\"]?1['\"]?\s*=\s*['\"]?1"
    r"|\"\s*or\s+['\"]?1['\"]?\s*=\s*['\"]?1"
    r"|\bor\s+1\s*=\s*1\b"
    r"|\bdrop\s+table\b"
    r"|\bunion\s+(?:all\s+)?select\b"
    r"|;\s*delete\s+from\b"
    r"|;\s*update\s+\w+\s+set\b"
    r"|<script\b"
    r"|javascript\s*:"
    r"|\bsleep\s*\(\s*\d+\s*\)"
    r"|\bbenchmark\s*\("
    r")",
    re.IGNORECASE,
)

# Herramientas de ataque automatizado bloqueadas en capa de API / WAF
BLOCKED_ATTACK_USER_AGENTS = (
    "sqlmap",
    "nikto",
    "masscan",
    "acunetix",
    "nmap",
    "dirbuster",
    "havij",
    "zgrab",
    "nuclei",
)

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
    """Ventana deslizante de 60s por IP con seguimiento de infracciones consecutivas."""

    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._violation_counts: Dict[str, int] = defaultdict(int)

    def is_allowed(
        self, client_ip: str, max_requests: int = MAX_REQUESTS_PER_MINUTE_PER_IP, window_seconds: int = 60, scope: str = "default"
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds
        key = f"{scope}:{client_ip}"

        timestamps = [ts for ts in self._requests[key] if ts > window_start]
        self._requests[key] = timestamps

        if len(timestamps) >= max_requests:
            self._violation_counts[client_ip] += 1
            if self._violation_counts[client_ip] >= MAX_VIOLATIONS_BEFORE_BLACKLIST:
                IP_BLACKLIST.add(client_ip)
                logger.warning(
                    f"IP {client_ip} agregada dinámicamente a IP_BLACKLIST tras {self._violation_counts[client_ip]} infracciones de Rate Limit"
                )
            earliest = timestamps[0]
            retry_after = max(1, int(window_seconds - (now - earliest)))
            return False, retry_after

        self._violation_counts[client_ip] = 0
        self._requests[key].append(now)
        return True, 0

    def reset(self) -> None:
        """Reinicia los contadores y restaura IP_BLACKLIST a su estado base para pruebas automatizadas."""
        self._requests.clear()
        self._violation_counts.clear()
        IP_BLACKLIST.clear()
        IP_BLACKLIST.update(STATIC_IP_BLACKLIST)


rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    """Obtiene la IP real del cliente considerando cabeceras de proxy inverso (X-Forwarded-For / X-Real-IP)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


def inspect_request_for_waf_threats(request: Request) -> Optional[str]:
    """
    Inspecciona URL, query params y cabeceras en busca de payloads SQLi/XSS
    o herramientas de ataque automatizado (sqlmap, nikto, masscan, etc.).
    """
    ua = (request.headers.get("User-Agent") or "").lower()
    for tool in BLOCKED_ATTACK_USER_AGENTS:
        if tool in ua:
            return f"Blocked automated attack scanner User-Agent: {tool}"

    raw_path = unquote(request.url.path or "")
    raw_query = unquote(request.url.query or "")
    combined = f"{raw_path} {raw_query}"
    if WAF_MALICIOUS_PATTERNS.search(combined):
        return "Blocked SQLi/XSS payload in URL/query"

    for hdr_name in ("X-Search", "Referer", "X-Custom-Payload"):
        hdr_val = request.headers.get(hdr_name)
        if hdr_val and WAF_MALICIOUS_PATTERNS.search(unquote(hdr_val)):
            return f"Blocked SQLi/XSS payload in header {hdr_name}"

    return None


class RateLimitAndWAFMiddleware(BaseHTTPMiddleware):
    """
    Middleware de Seguridad Integral (WAF + Blacklist + Rate Limiting de 50 req/min por IP):
    1. Excluye /ping (para UptimeRobot).
    2. Rechaza inmediatamente con HTTP 403 Forbidden cualquier IP en IP_BLACKLIST.
    3. Inspecciona payloads SQLi/XSS y escáneres de ataque: si detecta ataque, agrega la IP
       a IP_BLACKLIST y responde HTTP 403 Forbidden antes de tocar rutas o base de datos.
    4. Controla ventana deslizante de 60s con máximo 50 peticiones por minuto por IP.
       En la petición #51 dentro del mismo minuto devuelve HTTP 429 Too Many Requests con
       Retry-After: 60 y si reincide 5 veces seguidas la agrega a IP_BLACKLIST.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/ping":
            return await call_next(request)

        client_ip = get_client_ip(request)

        # 1. Verificar si la IP ya está en la lista negra (IP_BLACKLIST)
        if client_ip in IP_BLACKLIST:
            logger.warning(f"WAF 403: Petición rechazada para IP en lista negra {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": f"Acceso bloqueado por WAF: La IP {client_ip} se encuentra en IP_BLACKLIST."
                },
            )

        # 2. Inspección WAF Anti-SQLi / Anti-XSS / Anti-Scanner
        threat = inspect_request_for_waf_threats(request)
        if threat:
            IP_BLACKLIST.add(client_ip)
            logger.warning(f"WAF Auto-Blacklist para IP {client_ip}: {threat}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": f"Acceso denegado por WAF ({threat}). IP {client_ip} agregada a IP_BLACKLIST."
                },
            )

        # 3. Rate Limiting por IP: máximo 50 peticiones por minuto por IP
        max_req = min(MAX_REQUESTS_PER_MINUTE_PER_IP, settings.RATE_LIMIT_READ_PER_MINUTE)
        allowed, _ = rate_limiter.is_allowed(
            client_ip, max_requests=max_req, window_seconds=60, scope="read"
        )
        if not allowed:
            if client_ip in IP_BLACKLIST:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": f"IP {client_ip} bloqueada en IP_BLACKLIST por abuso reiterado de Rate Limit."
                    },
                )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": "60"},
                content={
                    "detail": "Rate limit exceeded: máximo 50 consultas por minuto por IP."
                },
            )

        request.state.rate_limit_checked = True
        return await call_next(request)


async def check_read_rate_limit(request: Request) -> None:
    """Limita lecturas a 50 peticiones por minuto por IP (RATE_LIMIT_READ_PER_MINUTE)."""
    if getattr(request.state, "rate_limit_checked", False):
        return
    ip = get_client_ip(request)
    if ip in IP_BLACKLIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso bloqueado: IP {ip} en lista negra.",
        )
    allowed, retry_after = rate_limiter.is_allowed(
        ip, max_requests=min(MAX_REQUESTS_PER_MINUTE_PER_IP, settings.RATE_LIMIT_READ_PER_MINUTE), window_seconds=60, scope="read"
    )
    if not allowed:
        logger.warning("Rate limit de lectura excedido", extra={"client_ip": ip})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: máximo 50 consultas por minuto por IP.",
            headers={"Retry-After": "60"},
        )


async def check_write_rate_limit(request: Request) -> None:
    """Limita escrituras a RATE_LIMIT_WRITE_PER_MINUTE."""
    ip = get_client_ip(request)
    if ip in IP_BLACKLIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso bloqueado: IP {ip} en lista negra.",
        )
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
# 2.5 AUTENTICACIÓN POR TOKEN FIRMADO (HMAC-SHA256 / Bearer / X-FinPrice-Token)
# ==============================================================================

def create_api_access_token(
    client_id: str = "finprice-android-app",
    expires_in_seconds: int = 86400,
) -> Dict[str, Any]:
    """
    Genera un token firmado criptográficamente con HMAC-SHA256 para la App Android
    o clientes autorizados de FinPrice API.
    """
    now_ts = int(time.time())
    exp_ts = now_ts + expires_in_seconds
    payload = {
        "sub": client_id,
        "iat": now_ts,
        "exp": exp_ts,
        "scope": "read:catalog write:community",
        "iss": "FinPrice-api",
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    sig = hmac.new(
        settings.FINPRICE_TOKEN_SECRET.encode("utf-8"),
        b64_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    token = f"fp_tok_{b64_payload}.{sig}"
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": expires_in_seconds,
        "client_id": client_id,
        "scope": payload["scope"],
    }


def verify_signed_token(token: str) -> Dict[str, Any]:
    """Verifica la firma HMAC-SHA256 y vigencia de un token emitido por FinPrice API."""
    raw = token.strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw.startswith("fp_tok_") or "." not in raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso inválido o con formato incorrecto.",
        )
    body_part = raw[len("fp_tok_"):]
    b64_payload, provided_sig = body_part.rsplit(".", 1)
    expected_sig = hmac.new(
        settings.FINPRICE_TOKEN_SECRET.encode("utf-8"),
        b64_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(provided_sig, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma criptográfica del token inválida.",
        )
    pad = "=" * ((4 - len(b64_payload) % 4) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(b64_payload + pad).decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Payload del token corrupto.",
        )
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token de acceso ha expirado.",
        )
    return payload


async def verify_api_token_or_client(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_finprice_token: Optional[str] = Header(None, alias="X-FinPrice-Token"),
) -> Dict[str, Any]:
    """
    Valida el token firmado (Bearer o X-FinPrice-Token) si es enviado por el cliente,
    y bloquea herramientas de ataque automatizado (sqlmap, nikto, masscan, etc.).
    """
    ua = (request.headers.get("User-Agent") or "").lower()
    for blocked in BLOCKED_ATTACK_USER_AGENTS:
        if blocked in ua:
            ip = get_client_ip(request)
            IP_BLACKLIST.add(ip)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cliente bloqueado por seguridad: {blocked}",
            )
    raw_tok = x_finprice_token or authorization
    if raw_tok:
        return verify_signed_token(raw_tok)
    return {"sub": "android-public-client", "scope": "read:catalog"}


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
