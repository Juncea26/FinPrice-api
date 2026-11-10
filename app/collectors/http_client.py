"""
Cliente HTTP asíncrono optimizado con headers de navegador real,
reintentos con backoff exponencial, jitter, HTTP/2 y control de concurrencia mediante semáforo.
Reutiliza una única instancia compartida de httpx.AsyncClient para no agotar la RAM (< 300 MB).
"""
import asyncio
import gc
import random
import time
from typing import Dict, Optional

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

# User-Agents realistas de navegadores comunes en Perú
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
]

# Semáforo global limitado a 2 tiendas concurrentes para estricto control de memoria
_loop_semaphores: Dict[int, asyncio.Semaphore] = {}
_shared_clients: Dict[int, httpx.AsyncClient] = {}
LAST_FETCH_STATUS: Dict[str, str] = {}


def is_transient_fetch_failure(url: str) -> bool:
    """
    Indica si la última petición a `url` falló por un error temporal de red o WAF
    (TimeoutException, NetworkError, HTTP 403, 429, 500, 502, 503, 504),
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
        # Límite estricto a 2 concurrentes
        sem = asyncio.Semaphore(min(2, settings.COLLECTOR_MAX_CONCURRENCY))
        _loop_semaphores[loop_id] = sem
    return sem


def get_shared_client() -> httpx.AsyncClient:
    """Retorna la instancia única compartida de httpx.AsyncClient para el event loop actual."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    client = _shared_clients.get(loop_id)
    if client is None or client.is_closed:
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        timeout = httpx.Timeout(
            timeout=15.0,
            connect=settings.COLLECTOR_TIMEOUT_CONNECT,
            read=settings.COLLECTOR_TIMEOUT_READ,
        )
        client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            http2=HAS_HTTP2,
            follow_redirects=True,
        )
        _shared_clients[loop_id] = client
    return client


async def close_shared_client() -> None:
    """Cierra limpiamente el cliente compartido del event loop actual."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    client = _shared_clients.pop(loop_id, None)
    if client and not client.is_closed:
        await client.aclose()


def get_browser_headers() -> Dict[str, str]:
    """Genera cabeceras HTTP que simulan una solicitud legítima de navegador."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "DNT": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


async def fetch_page(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    max_retries: int = 2,
) -> Optional[str]:
    """
    Ejecuta una petición GET asíncrona segura con semáforo limitado a 2 tiendas,
    reutilizando una única instancia de AsyncClient y liberando memoria de inmediato.
    """
    async with _get_collector_semaphore():
        headers = get_browser_headers()
        effective_client = client if client is not None else get_shared_client()

        for attempt in range(max_retries + 1):
            try:
                response = await effective_client.get(url, headers=headers)
                status_code = response.status_code

                if status_code in {429, 500, 502, 503, 504}:
                    LAST_FETCH_STATUS[url] = "transient_error"
                    del response
                    if attempt < max_retries:
                        backoff = (2 ** attempt) + random.uniform(0.2, 0.7)
                        logger.warning(
                            f"HTTP {status_code} al solicitar {url}. Reintentando en {backoff:.2f}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue
                    logger.warning(
                        f"HTTP {status_code} persistente en {url}. Se retendrá la última oferta válida."
                    )
                    return None

                if status_code in {200, 206}:
                    LAST_FETCH_STATUS[url] = "ok"
                    text = response.text
                    del response
                    return text

                if status_code == 403:
                    LAST_FETCH_STATUS[url] = "transient_error"
                    del response
                    logger.warning(
                        f"Respuesta temporal WAF (403) para {url}. Se retendrá la última oferta válida."
                    )
                    return None

                LAST_FETCH_STATUS[url] = "not_found" if status_code in {404, 410} else f"http_{status_code}"
                del response
                logger.warning(
                    f"Respuesta no exitosa ({status_code}) para {url}"
                )
                return None

            except (httpx.TimeoutException, httpx.NetworkError) as err:
                LAST_FETCH_STATUS[url] = "transient_error"
                if attempt < max_retries:
                    backoff = (2 ** attempt) + random.uniform(0.2, 0.7)
                    logger.warning(
                        f"Fallo de conexión para {url}: {err}. Reintentando en {backoff:.2f}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.warning(
                        f"Error temporal de red tras {max_retries} reintentos en {url}: {err}. Se retendrá la última oferta válida."
                    )
                    return None
            finally:
                # Recolección rápida si es necesario
                pass

    return None
