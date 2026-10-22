"""
Cliente HTTP asíncrono optimizado con headers de navegador real,
reintentos con backoff exponencial, jitter, HTTP/2 y control de concurrencia mediante semáforo.
"""
import asyncio
import random
import time
from typing import Dict, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

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

# Semáforo global de concurrencia
collector_semaphore = asyncio.Semaphore(settings.COLLECTOR_MAX_CONCURRENCY)


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
    Ejecuta una petición GET asíncrona segura con semáforo, timeouts estrictos
    y reintentos exponenciales con jitter ante errores 429, 502, 503, 504.
    """
    timeout = httpx.Timeout(
        connect=settings.COLLECTOR_TIMEOUT_CONNECT,
        read=settings.COLLECTOR_TIMEOUT_READ,
        write=10.0,
        pool=10.0,
    )

    async with collector_semaphore:
        headers = get_browser_headers()
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=timeout, http2=HAS_HTTP2, follow_redirects=True)
            should_close = True

        try:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.get(url, headers=headers)
                    if response.status_code in {429, 502, 503, 504}:
                        if attempt < max_retries:
                            backoff = (2 ** attempt) + random.uniform(0.2, 0.7)
                            logger.warning(
                                f"HTTP {response.status_code} al solicitar {url}. Reintentando en {backoff:.2f}s..."
                            )
                            await asyncio.sleep(backoff)
                            continue
                    if response.status_code == 200:
                        return response.text
                    else:
                        logger.warning(
                            f"Respuesta no exitosa ({response.status_code}) para {url}"
                        )
                        return None
                except (httpx.TimeoutException, httpx.NetworkError) as err:
                    if attempt < max_retries:
                        backoff = (2 ** attempt) + random.uniform(0.2, 0.7)
                        logger.warning(
                            f"Fallo de conexión para {url}: {err}. Reintentando en {backoff:.2f}s..."
                        )
                        await asyncio.sleep(backoff)
                    else:
                        logger.warning(f"Error definitivo tras {max_retries} reintentos en {url}: {err}")
                        return None
        finally:
            if should_close:
                await client.aclose()

    return None
