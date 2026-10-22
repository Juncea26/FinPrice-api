"""
Conector específico para Falabella CMR Perú (storeId: 'falabella').
"""
import json
from typing import Any, Dict, Optional
import httpx
from bs4 import BeautifulSoup

from app.collectors.base import BaseStoreCollector
from app.collectors.normalizer import clean_pen_price, sanity_check_price
from app.core.logging import get_logger

logger = get_logger("collectors.falabella")


class FalabellaCollector(BaseStoreCollector):
    def __init__(self):
        super().__init__(
            store_id="falabella",
            store_name="Falabella CMR",
            base_url="https://www.falabella.com.pe",
        )

    async def scrape_store(
        self, client: httpx.AsyncClient, product_id: str, product_title: str, offer_url: str
    ) -> Optional[Dict[str, Any]]:
        response = await self.fetch_with_retry(client, offer_url)
        html = response.text

        # 1. Estrategia JSON-LD
        price_data = self.extract_json_ld_price(html)
        if price_data:
            price_data["offer_url"] = offer_url
            return price_data

        # 2. Estrategia Next.js __NEXT_DATA__
        soup = BeautifulSoup(html, "lxml")
        next_script = soup.find("script", id="__NEXT_DATA__")
        if next_script and next_script.string:
            try:
                next_data = json.loads(next_script.string)
                # Navegar por props.pageProps.product.prices
                page_props = next_data.get("props", {}).get("pageProps", {})
                product = page_props.get("product", {})
                prices = product.get("prices", [])
                if prices:
                    # Buscar precio CMR o precio oferta más bajo
                    extracted_prices = []
                    for pr in prices:
                        val = clean_pen_price(pr.get("price") or pr.get("originalPrice"))
                        if val:
                            extracted_prices.append(val)
                    if extracted_prices:
                        best = min(extracted_prices)
                        orig = max(extracted_prices)
                        if sanity_check_price(best):
                            return {
                                "price": best,
                                "original_price": orig,
                                "offer_url": offer_url,
                            }
            except Exception as e:
                logger.debug(f"Error parseando __NEXT_DATA__ Falabella: {e}")

        # 3. Selectores HTML Falabella
        # Falabella suele usar data-testid o clases copy10, cmr-icon-container, etc.
        price_elem = soup.select_one("[data-variant-price], .copy10, .cmr-price, .prices-0")
        if price_elem:
            p = clean_pen_price(price_elem.get_text())
            if p and sanity_check_price(p):
                list_elem = soup.select_one(".original-price, .crossed-price, .prices-1")
                orig_p = clean_pen_price(list_elem.get_text()) if list_elem else p
                return {
                    "price": p,
                    "original_price": orig_p or p,
                    "offer_url": offer_url,
                }

        # 4. Fallback Open Graph
        og_data = self.extract_open_graph_price(html)
        if og_data:
            og_data["offer_url"] = offer_url
            return og_data

        return None
