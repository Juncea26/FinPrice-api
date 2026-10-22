"""
Conector específico para Tottus Perú (storeId: 'tottus').
"""
import json
from typing import Any, Dict, Optional
import httpx
from bs4 import BeautifulSoup

from app.collectors.base import BaseStoreCollector
from app.collectors.normalizer import clean_pen_price, sanity_check_price
from app.core.logging import get_logger

logger = get_logger("collectors.tottus")


class TottusCollector(BaseStoreCollector):
    def __init__(self):
        super().__init__(
            store_id="tottus",
            store_name="Tottus",
            base_url="https://www.tottus.com.pe",
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
                props = next_data.get("props", {}).get("pageProps", {})
                product = props.get("product", {})
                prices = product.get("prices", {})
                p = clean_pen_price(prices.get("currentPrice") or prices.get("cmrPrice"))
                if p and sanity_check_price(p):
                    orig_p = clean_pen_price(prices.get("regularPrice"))
                    return {
                        "price": p,
                        "original_price": orig_p or p,
                        "offer_url": offer_url,
                    }
            except Exception:
                pass

        # 3. Selectores HTML Tottus
        price_elem = soup.select_one(".primary-price, [data-price], .cmr-price, .tottus-price")
        if price_elem:
            p = clean_pen_price(price_elem.get_text())
            if p and sanity_check_price(p):
                list_elem = soup.select_one(".regular-price, .crossed-out-price")
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
