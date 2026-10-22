"""
Conector específico para Hiraoka Perú (storeId: 'hiraoka').
"""
from typing import Any, Dict, Optional
import httpx
from bs4 import BeautifulSoup

from app.collectors.base import BaseStoreCollector
from app.collectors.normalizer import clean_pen_price, sanity_check_price
from app.core.logging import get_logger

logger = get_logger("collectors.hiraoka")


class HiraokaCollector(BaseStoreCollector):
    def __init__(self):
        super().__init__(
            store_id="hiraoka",
            store_name="Hiraoka",
            base_url="https://hiraoka.com.pe",
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

        # 2. Selectores HTML Magento / Hiraoka
        soup = BeautifulSoup(html, "lxml")
        price_elem = soup.select_one(
            ".special-price .price, [data-price-type='finalPrice'] .price, .product-info-price .price"
        )
        if price_elem:
            p = clean_pen_price(price_elem.get_text())
            if p and sanity_check_price(p):
                old_elem = soup.select_one(".old-price .price, [data-price-type='oldPrice'] .price")
                orig_p = clean_pen_price(old_elem.get_text()) if old_elem else p
                return {
                    "price": p,
                    "original_price": orig_p or p,
                    "offer_url": offer_url,
                }

        # 3. Fallback Open Graph
        og_data = self.extract_open_graph_price(html)
        if og_data:
            og_data["offer_url"] = offer_url
            return og_data

        return None
