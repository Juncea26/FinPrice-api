"""
Conector específico para Ripley Perú (storeId: 'ripley').
"""
import json
import re
from typing import Any, Dict, Optional
import httpx
from bs4 import BeautifulSoup

from app.collectors.base import BaseStoreCollector
from app.collectors.normalizer import clean_pen_price, sanity_check_price
from app.core.logging import get_logger

logger = get_logger("collectors.ripley")


class RipleyCollector(BaseStoreCollector):
    def __init__(self):
        super().__init__(
            store_id="ripley",
            store_name="Ripley",
            base_url="https://simple.ripley.com.pe",
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

        # 2. Estrategia __PRELOADED_STATE__ o __NEXT_DATA__
        soup = BeautifulSoup(html, "lxml")
        scripts = soup.find_all("script")
        for s in scripts:
            if s.string and "__PRELOADED_STATE__" in s.string:
                try:
                    match = re.search(r"__PRELOADED_STATE__\s*=\s*(\{.*?\});", s.string, re.DOTALL)
                    if match:
                        state_json = json.loads(match.group(1))
                        product = state_json.get("product", {})
                        prices = product.get("prices", {})
                        p = clean_pen_price(prices.get("offerPrice") or prices.get("cardPrice") or prices.get("listPrice"))
                        if p and sanity_check_price(p):
                            orig_p = clean_pen_price(prices.get("listPrice"))
                            return {
                                "price": p,
                                "original_price": orig_p or p,
                                "offer_url": offer_url,
                            }
                except Exception:
                    pass

        # 3. Selectores HTML Ripley
        price_elem = soup.select_one(".catalog-prices__offer-price, .catalog-prices__card-price, .product-price")
        if price_elem:
            p = clean_pen_price(price_elem.get_text())
            if p and sanity_check_price(p):
                list_elem = soup.select_one(".catalog-prices__list-price")
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
