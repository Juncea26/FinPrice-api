"""
Cliente HTTP asíncrono resiliente con huella TLS/JA3 real de Chrome (`curl_cffi`),
fallback automático a HTTP/1.1 ante HTTP 426 / 403 / errores de protocolo,
respaldo secundario con `httpx`, headers de navegador real y control de concurrencia.
Reutiliza sesiones compartidas por event loop para mantener la RAM bajo control (< 300 MB).
"""
import asyncio
import random
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.collectors.url_utils import canonicalize_store_url

logger = get_logger("collectors.http_client")

try:
    import h2  # noqa: F401
    HAS_HTTP2 = True
except ImportError:
    HAS_HTTP2 = False

try:
    from curl_cffi import CurlError, CurlHttpVersion  # type: ignore[attr-defined]
    from curl_cffi.requests import AsyncSession as CurlAsyncSession

    HAS_CURL_CFFI = True
    CURL_HTTP_V1_1 = getattr(CurlHttpVersion, "V1_1", 2)
except ImportError:
    try:
        from curl_cffi.requests import AsyncSession as CurlAsyncSession  # type: ignore[no-redef]
        from curl_cffi.curl import CurlError  # type: ignore[no-redef]

        HAS_CURL_CFFI = True
        CURL_HTTP_V1_1 = 2
    except ImportError:
        CurlAsyncSession = None  # type: ignore[assignment,misc]
        CurlError = Exception  # type: ignore[assignment,misc]
        HAS_CURL_CFFI = False
        CURL_HTTP_V1_1 = 2

# Perfiles Chrome recientes para rotación de huella TLS/JA3 en curl_cffi
CHROME_IMPERSONATE_PROFILES: Tuple[str, ...] = ("chrome124", "chrome120")

PROFILE_USER_AGENTS: Dict[str, str] = {
    "chrome124": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "chrome120": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

PROFILE_SEC_CH_UA: Dict[str, str] = {
    "chrome124": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "chrome120": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
}

# User-Agents realistas de navegadores comunes en Perú (compatibilidad retroactiva)
USER_AGENTS = [
    PROFILE_USER_AGENTS["chrome124"],
    PROFILE_USER_AGENTS["chrome120"],
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Tiendas donde curl_cffi con TLS/JA3 de Chrome es el transporte principal
_CURL_PRIMARY_STORES = {"ripley", "efe", "curacao"}
# Tiendas propensas a HTTP 426 / errores de negociación HTTP/2 que requieren fallback estricto a HTTP/1.1
_HTTP1_FALLBACK_STORES = {"efe", "curacao"}

# Semáforo global limitado a 2 tiendas concurrentes para estricto control de memoria
_loop_semaphores: Dict[int, asyncio.Semaphore] = {}
_shared_clients: Dict[int, httpx.AsyncClient] = {}
_shared_http1_clients: Dict[int, httpx.AsyncClient] = {}
_shared_curl_sessions: Dict[int, Any] = {}
_profile_counter: int = 0
LAST_FETCH_STATUS: Dict[str, str] = {}


def _mark_fetch_status(url: str, status: str) -> None:
    """Registra el estado de la última petición tanto para la URL original como para su forma canónica."""
    LAST_FETCH_STATUS[url] = status
    _, clean_u = canonicalize_store_url(url)
    if clean_u and clean_u != url:
        LAST_FETCH_STATUS[clean_u] = status


def is_transient_fetch_failure(url: str) -> bool:
    """
    Indica si la última petición a `url` falló por un error temporal de red, protocolo o WAF
    (TimeoutException, NetworkError, HTTP 403, 426, 429, 500, 502, 503, 504),
    en cuyo caso la Regla de Retención Tolerante a Fallos (Módulo 3) exige conservar
    la oferta previa en store_offers con su último precio válido.
    """
    _, clean_u = canonicalize_store_url(url)
    st = LAST_FETCH_STATUS.get(url) or LAST_FETCH_STATUS.get(clean_u or "")
    return st == "transient_error"


def _get_collector_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    sem = _loop_semaphores.get(loop_id)
    if sem is None:
        sem = asyncio.Semaphore(min(2, settings.COLLECTOR_MAX_CONCURRENCY))
        _loop_semaphores[loop_id] = sem
    return sem


def _build_httpx_client(http2: bool) -> httpx.AsyncClient:
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    timeout = httpx.Timeout(
        timeout=15.0,
        connect=settings.COLLECTOR_TIMEOUT_CONNECT,
        read=settings.COLLECTOR_TIMEOUT_READ,
    )
    return httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        http2=http2,
        follow_redirects=True,
    )


def get_shared_client() -> httpx.AsyncClient:
    """Retorna la instancia única compartida de httpx.AsyncClient para el event loop actual."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    client = _shared_clients.get(loop_id)
    if client is None or client.is_closed:
        client = _build_httpx_client(http2=HAS_HTTP2)
        _shared_clients[loop_id] = client
    return client


def get_shared_http1_client() -> httpx.AsyncClient:
    """Retorna el cliente httpx.AsyncClient compartido forzado a HTTP/1.1 (http2=False)."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    client = _shared_http1_clients.get(loop_id)
    if client is None or client.is_closed:
        client = _build_httpx_client(http2=False)
        _shared_http1_clients[loop_id] = client
    return client


def get_shared_curl_session() -> Any:
    """Retorna la sesión compartida de curl_cffi.requests.AsyncSession para el event loop actual."""
    if not HAS_CURL_CFFI or CurlAsyncSession is None:
        raise RuntimeError("curl_cffi no está disponible en el entorno actual.")
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    session = _shared_curl_sessions.get(loop_id)
    if session is None or getattr(session, "_closed", False):
        session = CurlAsyncSession(
            max_clients=10,
            timeout=(settings.COLLECTOR_TIMEOUT_CONNECT, settings.COLLECTOR_TIMEOUT_READ),
            allow_redirects=True,
        )
        _shared_curl_sessions[loop_id] = session
    return session


async def close_shared_client() -> None:
    """Cierra limpiamente todos los clientes HTTP compartidos del event loop actual."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    for pool in (_shared_clients, _shared_http1_clients):
        client = pool.pop(loop_id, None)
        if client and not client.is_closed:
            await client.aclose()
    curl_session = _shared_curl_sessions.pop(loop_id, None)
    if curl_session and not getattr(curl_session, "_closed", False):
        await curl_session.close()


def get_browser_headers(profile: Optional[str] = None) -> Dict[str, str]:
    """Genera cabeceras HTTP completas coherentes con un navegador Chrome real en Perú."""
    chosen_profile = (
        profile
        if profile in PROFILE_USER_AGENTS
        else random.choice(CHROME_IMPERSONATE_PROFILES)
    )
    return {
        "User-Agent": PROFILE_USER_AGENTS[chosen_profile],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "DNT": "1",
        "Sec-Ch-Ua": PROFILE_SEC_CH_UA[chosen_profile],
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


def _next_profile_index() -> int:
    global _profile_counter
    idx = _profile_counter
    _profile_counter = (_profile_counter + 1) % len(CHROME_IMPERSONATE_PROFILES)
    return idx


async def _request_via_curl_cffi(
    url: str,
    profile: str,
    force_http1: bool = False,
) -> Tuple[Optional[int], Optional[str], Optional[Exception]]:
    """Ejecuta un GET con curl_cffi imitando huella TLS/JA3 de Chrome."""
    if not HAS_CURL_CFFI:
        return (None, None, RuntimeError("curl_cffi no disponible"))
    try:
        session = get_shared_curl_session()
        kwargs: Dict[str, Any] = {
            "impersonate": profile,
            "headers": get_browser_headers(profile),
        }
        if force_http1:
            kwargs["http_version"] = CURL_HTTP_V1_1
        response = await session.get(url, **kwargs)
        status_code = int(response.status_code)
        text = response.text if status_code in {200, 206} else None
        del response
        return (status_code, text, None)
    except Exception as err:
        return (None, None, err)


async def _request_via_httpx(
    url: str,
    headers: Dict[str, str],
    client: Optional[httpx.AsyncClient] = None,
    force_http1: bool = False,
) -> Tuple[Optional[int], Optional[str], Optional[Exception]]:
    """Ejecuta un GET usando httpx (HTTP/2 compartido, HTTP/1.1 compartido o cliente inyectado)."""
    try:
        effective_client = (
            client
            if client is not None
            else (get_shared_http1_client() if force_http1 else get_shared_client())
        )
        response = await effective_client.get(url, headers=headers)
        status_code = int(response.status_code)
        text = response.text if status_code in {200, 206} else None
        del response
        return (status_code, text, None)
    except Exception as err:
        return (None, None, err)


async def _execute_resilient_attempt(
    url: str,
    store_id: str,
    attempt: int,
    base_idx: int,
    client: Optional[httpx.AsyncClient],
) -> Tuple[Optional[int], Optional[str], Optional[Exception]]:
    """
    Ejecuta un intento de descarga aplicando la estrategia óptima por tienda:
    - ripley / efe / curacao: curl_cffi principal con rotación chrome124/chrome120,
      fallback inmediato a HTTP/1.1 (CurlHttpVersion.V1_1) ante 426/403/error de protocolo,
      y respaldo secundario con httpx HTTP/1.1 si curl_cffi falla.
    - Otras tiendas: httpx principal con fallback automático a curl_cffi y HTTP/1.1 ante 403/426/error.
    """
    profile = CHROME_IMPERSONATE_PROFILES[(base_idx + attempt) % len(CHROME_IMPERSONATE_PROFILES)]
    alt_profile = CHROME_IMPERSONATE_PROFILES[(base_idx + attempt + 1) % len(CHROME_IMPERSONATE_PROFILES)]

    if client is None and store_id in _CURL_PRIMARY_STORES and HAS_CURL_CFFI:
        status, text, err = await _request_via_curl_cffi(url, profile=profile, force_http1=False)
        if status in {200, 206} and text is not None:
            return (status, text, None)
        if status in {404, 410}:
            return (status, None, None)

        needs_http1_fallback = (
            status in {426, 403}
            or err is not None
            or (store_id in _HTTP1_FALLBACK_STORES and (status is None or status >= 400))
        )
        if needs_http1_fallback:
            if err is None or isinstance(err, CurlError):
                logger.info(
                    f"Fallback HTTP/1.1 con curl_cffi ({alt_profile}) para {url} "
                    f"(previo: status={status}, err={err})"
                )
                s2, t2, e2 = await _request_via_curl_cffi(
                    url, profile=alt_profile, force_http1=True
                )
                if s2 in {200, 206} and t2 is not None:
                    return (s2, t2, None)
                if s2 in {404, 410}:
                    return (s2, None, None)
                if s2 is not None:
                    status = s2
                if e2 is not None:
                    err = e2

            # Respaldo secundario con httpx forzando HTTP/1.1 si curl_cffi falló o devolvió 426/403
            if status in {426, 403} or err is not None:
                logger.info(
                    f"Respaldo secundario httpx HTTP/1.1 para {url} (previo: status={status}, err={err})"
                )
                s3, t3, e3 = await _request_via_httpx(
                    url,
                    headers=get_browser_headers(alt_profile),
                    force_http1=True,
                )
                if s3 in {200, 206} and t3 is not None:
                    return (s3, t3, None)
                if s3 in {404, 410}:
                    return (s3, None, None)
                if s3 is not None and status is None:
                    status = s3
                if e3 is not None and err is None:
                    err = e3

        return (status, None, err)

    # Transporte principal httpx para el resto de tiendas (o cuando se inyectó client)
    status, text, err = await _request_via_httpx(
        url,
        headers=get_browser_headers(profile),
        client=client,
        force_http1=False,
    )
    if status in {200, 206} and text is not None:
        return (status, text, None)
    if status in {404, 410}:
        return (status, None, None)

    if client is None and (status in {403, 426} or err is not None):
        if HAS_CURL_CFFI:
            force_v1_first = status == 426 and store_id in _HTTP1_FALLBACK_STORES
            s2, t2, e2 = await _request_via_curl_cffi(
                url, profile=profile, force_http1=force_v1_first
            )
            if s2 in {200, 206} and t2 is not None:
                return (s2, t2, None)
            if s2 in {404, 410}:
                return (s2, None, None)
            if not force_v1_first and (s2 in {403, 426} or e2 is not None):
                s2b, t2b, e2b = await _request_via_curl_cffi(
                    url, profile=alt_profile, force_http1=True
                )
                if s2b in {200, 206} and t2b is not None:
                    return (s2b, t2b, None)
                if s2b in {404, 410}:
                    return (s2b, None, None)
                if s2b is not None:
                    s2 = s2b
                if e2b is not None:
                    e2 = e2b
            if s2 is not None:
                status = s2
            if e2 is not None:
                err = e2

        if status in {426, 403} or err is not None:
            s3, t3, e3 = await _request_via_httpx(
                url,
                headers=get_browser_headers(alt_profile),
                force_http1=True,
            )
            if s3 in {200, 206} and t3 is not None:
                return (s3, t3, None)
            if s3 in {404, 410}:
                return (s3, None, None)
            if s3 is not None and status is None:
                status = s3
            if e3 is not None and err is None:
                err = e3

    return (status, None, err)


async def fetch_page(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    max_retries: int = 2,
) -> Optional[str]:
    """
    Ejecuta una petición GET asíncrona segura con semáforo limitado a 2 tiendas,
    usando curl_cffi (Chrome TLS/JA3) para Ripley/Efe/Curacao y fallback HTTP/1.1 + httpx.
    """
    store_id, _ = canonicalize_store_url(url)
    base_idx = _next_profile_index()

    async with _get_collector_semaphore():
        for attempt in range(max_retries + 1):
            status_code, text, err = await _execute_resilient_attempt(
                url=url,
                store_id=store_id,
                attempt=attempt,
                base_idx=base_idx,
                client=client,
            )

            if status_code in {200, 206} and text is not None:
                _mark_fetch_status(url, "ok")
                return text

            if status_code in {403, 426}:
                _mark_fetch_status(url, "transient_error")
                if attempt < min(1, max_retries):
                    backoff = 0.4 + random.uniform(0.1, 0.4)
                    logger.warning(
                        f"HTTP {status_code} en {url} tras fallback inicial. "
                        f"Rotando perfil Chrome en {backoff:.2f}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue
                logger.warning(
                    f"Respuesta temporal WAF/Protocolo ({status_code}) persistente para {url}. "
                    "Se retendrá la última oferta válida."
                )
                return None

            if status_code in {429, 500, 502, 503, 504} or (err is not None and status_code is None):
                _mark_fetch_status(url, "transient_error")
                if attempt < max_retries:
                    backoff = (2 ** attempt) + random.uniform(0.2, 0.7)
                    detail = f"HTTP {status_code}" if status_code else f"Fallo de conexión: {err}"
                    logger.warning(
                        f"{detail} al solicitar {url}. Reintentando en {backoff:.2f}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue
                logger.warning(
                    f"Error temporal tras {max_retries} reintentos en {url} "
                    f"(status={status_code}, err={err}). Se retendrá la última oferta válida."
                )
                return None

            _mark_fetch_status(
                url,
                "not_found" if status_code in {404, 410} else f"http_{status_code}",
            )
            logger.warning(f"Respuesta no exitosa ({status_code}) para {url}")
            return None

    return None
