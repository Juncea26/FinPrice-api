"""
Interfaz abstracta BaseStoreCollector, Circuit Breaker por tienda retail,
rotación de User-Agents y cliente HTTP asíncrono con reintentos exponenciales y jitter.
"""
import abc
import asyncio
import json
import random
import time
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.logging import get_logger
from app.collectors.normalizer import clean_pen_price, sanity_check_price

logger = get_logger("collectors.base")


# ==============================================================================
# 1. ROTACIÓN DE USER-AGENTS REALISTAS
# ==============================================================================

REALISTIC_USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Safari Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
]


def get_random_user_agent() -> str:
    """Retorna un User-Agent de navegador moderno seleccionado al azar."""
    return random.choice(REALISTIC_USER_AGENTS)


# ==============================================================================
# 2. PATRÓN CIRCUIT BREAKER
# ==============================================================================

class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Operación normal
    OPEN = "OPEN"          # Fallos consecutivos alcanzados, bloquea peticiones salientes
    HALF_OPEN = "HALF_OPEN"# Probando recuperación con una petición


class CircuitBreaker:
    """
    Circuit Breaker para proteger la API de bloqueos, cuelgues o tiendas caídas.
    Si una tienda falla N veces consecutivas, el circuito se abre y se sirve
    inmediatamente la última instantánea de la base de datos sin retardos.
    """

    def __init__(
        self,
        store_id: str,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: int = settings.CIRCUIT_BREAKER_RECOVERY_SECONDS,
    ):
        self.store_id = store_id
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_success_time: Optional[float] = None

    def can_execute(self) -> bool:
        """Determina si se debe permitir una llamada a la red para esta tienda."""
        if self.state == CircuitState.CLOSED:
            return True

        now = time.time()
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (now - self.last_failure_time >= self.recovery_timeout):
                logger.info(
                    f"Circuit Breaker para '{self.store_id}': Transicionando a HALF_OPEN para prueba de recuperación."
                )
                self.state = CircuitState.HALF_OPEN
                return True
            return False

        # Si está HALF_OPEN permite una sola llamada de prueba
        return True

    def record_success(self) -> None:
        """Registra un scrapeo exitoso y restaura el estado a CLOSED."""
        self.failure_count = 0
        self.last_success_time = time.time()
        if self.state != CircuitState.CLOSED:
            logger.info(
                f"Circuit Breaker para '{self.store_id}': Recuperación exitosa. Circuito restablecido a CLOSED."
            )
            self.state = CircuitState.CLOSED

    def record_failure(self, error: Exception) -> None:
        """Registra una falla de red, bloqueo o timeout."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            logger.warning(
                f"Circuit Breaker para '{self.store_id}': Falló prueba en HALF_OPEN. Regresando a OPEN.",
                extra={"error": str(error)},
            )
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            logger.error(
                f"Circuit Breaker para '{self.store_id}': Umbral de fallos alcanzado ({self.failure_count}). ACTIVANDO OPEN.",
                extra={"error": str(error)},
            )
            self.state = CircuitState.OPEN
        else:
            logger.warning(
                f"Circuit Breaker para '{self.store_id}': Fallo registrado ({self.failure_count}/{self.failure_threshold}).",
                extra={"error": str(error)},
            )


# ==============================================================================
# 3. INTERFAZ ABSTRACTA BASE STORE COLLECTOR
# ==============================================================================

class BaseStoreCollector(abc.ABC):
    """
    Clase base para conectores de tiendas retail del Perú.
    Gestiona Circuit Breaker, reintentos con backoff exponencial y parsing seguro.
    """

    def __init__(self, store_id: str, store_name: str, base_url: str):
        self.store_id = store_id
        self.store_name = store_name
        self.base_url = base_url
        self.circuit_breaker = CircuitBreaker(store_id=store_id)

    def get_default_headers(self) -> Dict[str, str]:
        """Cabeceras HTTP simulando un navegador real con aceptación de contenido."""
        return {
            "User-Agent": get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-PE,es-419;q=0.9,es;q=0.8,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    async def fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        custom_headers: Optional[Dict[str, str]] = None,
        max_retries: int = 2,
    ) -> httpx.Response:
        """
        Ejecuta una petición GET asíncrona con Exponential Backoff y Jitter
        ante errores temporales (429, 502, 503, 504 o Timeouts).
        """
        headers = self.get_default_headers()
        if custom_headers:
            headers.update(custom_headers)

        last_exception: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                response = await client.get(url, headers=headers, follow_redirects=True)
                if response.status_code in {429, 502, 503, 504}:
                    if attempt < max_retries:
                        # Backoff exponencial con jitter: 2^(attempt) + random(0.1, 0.5)
                        backoff = (2 ** attempt) + random.uniform(0.1, 0.6)
                        logger.warning(
                            f"HTTP {response.status_code} en '{self.store_id}'. Reintento {attempt+1}/{max_retries} en {backoff:.2f}s",
                            extra={"url": url},
                        )
                        await asyncio.sleep(backoff)
                        continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_exception = exc
                if attempt < max_retries:
                    backoff = (2 ** attempt) + random.uniform(0.1, 0.6)
                    logger.warning(
                        f"Fallo de conexión en '{self.store_id}'. Reintento {attempt+1}/{max_retries} en {backoff:.2f}s: {exc}",
                        extra={"url": url},
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise last_exception

        raise last_exception or httpx.HTTPError(f"Error desconocido en fetch_with_retry para {url}")

    # --------------------------------------------------------------------------
    # MÉTODOS DE EXTRACCIÓN COMUNES
    # --------------------------------------------------------------------------

    def extract_json_ld_price(self, html_text: str) -> Optional[Dict[str, float]]:
        """
        Extrae datos de precios desde etiquetas estructuradas JSON-LD
        (<script type="application/ld+json">).
        """
        try:
            soup = BeautifulSoup(html_text, "lxml")
            scripts = soup.find_all("script", type="application/ld+json")
            for script in scripts:
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string.strip())
                except Exception:
                    continue

                # Puede ser un solo dict o una lista
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("@type")
                    if item_type in {"Product", "IndividualProduct"}:
                        offers = item.get("offers")
                        if isinstance(offers, dict):
                            raw_price = offers.get("price") or offers.get("lowPrice")
                            price = clean_pen_price(raw_price)
                            orig_price = clean_pen_price(offers.get("highPrice"))
                            if price and sanity_check_price(price):
                                return {"price": price, "original_price": orig_price or price}
                        elif isinstance(offers, list) and offers:
                            first = offers[0]
                            if isinstance(first, dict):
                                price = clean_pen_price(first.get("price") or first.get("lowPrice"))
                                if price and sanity_check_price(price):
                                    return {"price": price, "original_price": price}
        except Exception as e:
            logger.debug(f"Error parseando JSON-LD en {self.store_id}: {e}")
        return None

    def extract_open_graph_price(self, html_text: str) -> Optional[Dict[str, float]]:
        """Extrae precio de meta tags Open Graph (og:price:amount, product:price:amount)."""
        try:
            soup = BeautifulSoup(html_text, "lxml")
            for tag_name in ["product:price:amount", "og:price:amount"]:
                meta = soup.find("meta", property=tag_name) or soup.find("meta", attrs={"name": tag_name})
                if meta and meta.get("content"):
                    price = clean_pen_price(meta["content"])
                    if price and sanity_check_price(price):
                        return {"price": price, "original_price": price}
        except Exception as e:
            logger.debug(f"Error en Open Graph en {self.store_id}: {e}")
        return None

    # --------------------------------------------------------------------------
    # MÉTODO PRINCIPAL BLINDADO
    # --------------------------------------------------------------------------

    async def collect(
        self,
        client: httpx.AsyncClient,
        product_id: str,
        product_title: str,
        offer_url: str,
        fallback_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Ejecuta la recolección protegida por el Circuit Breaker.
        Si la tienda externa está caída o el circuito está OPEN, devuelve None de inmediato
        para que el orquestador sirva la última instantánea válida en base de datos.
        """
        if not self.circuit_breaker.can_execute():
            logger.warning(
                f"Circuit Breaker ACTIVO (OPEN) para '{self.store_id}'. Omitiendo scraping en vivo para '{product_id}'."
            )
            return None

        try:
            start_time = time.time()
            result = await self.scrape_store(client, product_id, product_title, offer_url)
            duration_ms = (time.time() - start_time) * 1000

            if result and result.get("price"):
                self.circuit_breaker.record_success()
                logger.info(
                    f"Scraping exitoso en '{self.store_id}' para '{product_id}': S/. {result['price']} ({duration_ms:.1f}ms)"
                )
                return result
            else:
                # Si no se pudo extraer precio válido, registrar como fallo
                self.circuit_breaker.record_failure(ValueError("No se pudo extraer precio válido de la respuesta"))
                return None
        except Exception as e:
            self.circuit_breaker.record_failure(e)
            logger.warning(
                f"Fallo durante la recolección en '{self.store_id}' para '{product_id}': {e}"
            )
            return None

    @abc.abstractmethod
    async def scrape_store(
        self, client: httpx.AsyncClient, product_id: str, product_title: str, offer_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Lógica concreta de scraping por tienda retail.
        Debe retornar dict con {"price": float, "original_price": Optional[float], "offer_url": str}
        o None si no se pudo extraer.
        """
        pass
