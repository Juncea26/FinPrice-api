"""
Conector específico para La Curacao Perú (storeId: 'curacao').
"""
import json
from typing import Any, Dict, Optional
import httpx
from bs4 import BeautifulSoup

from app.collectors.base import BaseStoreCollector
from app.collectors.normalizer import clean_pen_price, sanity_check_price
from app.core.logging import get_logger

logger = get_logger("collectors.curacao")


class CuracaoCollector(BaseStoreCollector):
    def __init__(self):
        super().__init__(
            store_id="curacao",
            store_name="La Curacao",
            base_url="https://www.lacuracao.pe",
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

        # 2. Estrategia VTEX Estado
        soup = BeautifulSoup(html, "lxml")
        vtex_script = soup.find("template", attrs={"data-varname": "__STATE__"})
        if vtex_script and vtex_script.string:
            try:
                state_data = json.loads(vtex_script.string)
                for key, val in state_data.items():
                    if isinstance(val, dict) and "Price" in val:
                        p = clean_pen_price(val.get("Price"))
                        if p and sanity_check_price(p):
                            orig_p = clean_pen_price(val.get("ListPrice"))
                            return {
                                "price": p,
                                "original_price": orig_p or p,
                                "offer_url": offer_url,
                            }
            except Exception:
                pass

        # 3. Selectores HTML La Curacao
        price_elem = soup.select_one(".vtex-product-price-1-x-sellingPriceValue, .curacao-price-sale, .price-sale")
        if price_elem:
            p = clean_pen_price(price_elem.get_text())
            if p and sanity_check_price(p):
                list_elem = soup.select_one(".vtex-product-price-1-x-listPrice, .curacao-price-list")
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
