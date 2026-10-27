"""
Suite de Pruebas Automatizadas de FinPrice API Real & Zero-Mock + Triple Candado de Integridad
==============================================================================================
Verifica:
1. Extractores reales por retailer con aislamiento de DOM (.product-info-main) y filtrado de carruseles
2. Sistema de Triple Candado de Integridad (Zero False-Positive Guard):
   - validate_product_identity (bloqueo de accesorios, familia/modelo/sufijos exactos, capacidad storage)
   - validate_cross_store_prices (filtro estadístico anti-outliers < 55% de referencia)
   - Caso real de regresión: Xiaomi Redmi Note 15 Pro 5G 512GB (Hiraoka S/ 1829.00 vs Efe Redmi A7/A3 S/ 399.00)
   - Saneamiento automático de base de datos en arranque y sync
3. Regla Zero-Mock: ausencia de URLs inventadas, dominios falsos o imágenes genéricas
4. Contrato de datos en camelCase estricto (bestPrice, storePrices, priceHistory30Days, techSpecs)
5. Filtros avanzados de hardware (RAM, Almacenamiento, Categoría, enabled_stores)
6. Seguridad: Autenticación X-API-Key en POST /api/v1/collectors/sync (401, 403 vs 202)
7. Diagnóstico y métricas en GET /api/v1/health
8. Ofertas comunitarias persistidas con validación de ubigeo peruano
9. Retrocompatibilidad de GET /products
"""
import json
import os
import shutil
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.collectors.catalog_urls import CATALOG_PRODUCTS, STORES_INFO
from app.collectors.fingerprint_matcher import (
    ProductFingerprint,
    build_compact_search_query,
    build_fingerprint_from_catalog_item,
    discover_product_across_8_stores,
    matches_fingerprint,
)
from app.collectors.orchestrator import get_parser_for_store, orchestrator
from app.collectors.parsers.conectaretail import parse_conectaretail
from app.collectors.parsers.falabella import parse_falabella
from app.collectors.parsers.hiraoka import parse_hiraoka
from app.collectors.parsers.ripley import parse_ripley
from app.collectors.parsers.tottus import parse_tottus
from app.collectors.parsers.vtex_cencosud import parse_vtex_cencosud
from app.collectors.spec_extractor import (
    CANONICAL_SPEC_MAP,
    extract_product_specs,
    extract_specs_from_title_fallback,
    generate_product_features,
    merge_product_specs,
)
from app.collectors.url_utils import canonicalize_store_url
from app.collectors.query_builder import build_search_queries
from app.collectors.universal_matcher import (
    UniversalProductResolver,
    filter_offers_by_price_sanity,
    match_product_universal,
)
from app.collectors.validators import (
    ScrapedOffer,
    select_best_canonical_image,
    validate_cross_store_prices,
    validate_product_identity,
)
from app.models.entities import ProductEntity, StoreOfferEntity
from main import app


def _title_for_url(url: str) -> str:
    for item in CATALOG_PRODUCTS:
        for _, s_url in item["store_urls"].items():
            if s_url == url:
                return item["title"]
    return "Producto Oficial"


@pytest.fixture(scope="session", autouse=True)
def preserve_production_sqlite_db():
    """Preserva la base de datos real (finprice_real.db) intacta tras ejecutar los mocks de pytest."""
    db_path = "finprice_real.db"
    backup_path = "finprice_real.db.bak"
    had_db = os.path.exists(db_path)
    if had_db:
        shutil.copy2(db_path, backup_path)
    yield
    if had_db and os.path.exists(backup_path):
        shutil.move(backup_path, db_path)


@pytest.fixture(scope="module")
def client():
    """Cliente de pruebas con lifespan activo (inicializa tablas y orquestador)."""
    def mock_fetch(url, *args, **kwargs):
        matched_title = _title_for_url(url)
        json_title = matched_title.replace('"', '\\"')
        is_lg_oled = "oled" in url.lower() and "c6" in url.lower()
        is_ipad_a16 = "ipad" in url.lower() and "a16" in url.lower()
        if "falabella" in url:
            if is_ipad_a16:
                return """
                <html><script id="__NEXT_DATA__" type="application/json">
                {"props":{"pageProps":{"productData":{"id":"prod18440041","name":"iPad Apple 11 Chip A16 Wi-Fi","description":"iPad Apple 11 con 128GB de almacenamiento","attributes":{"specifications":[{"name":"Capacidad de almacenamiento","value":"128GB"},{"name":"Tamaño de la pantalla","value":"11"}]},"variants":[{"id":"21014911","name":"IPAD A16 WIFI 128GB SLV","prices":[{"type":"cmrPrice","price":["1,899"],"crossed":false},{"type":"normalPrice","price":["2,599"],"crossed":true}],"medias":[{"url":"https://media.falabella.com/falabellaPE/21014911_1/public"}]}]}}}}
                </script></html>
                """
            f_price = "3,599.00" if is_lg_oled else "3,499.00"
            return """
            <html><script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"productData":{"name":"__TITLE__","variants":[{"prices":[{"type":"cmrPrice","price":["__PRICE__"],"crossed":false},{"type":"normalPrice","price":["4,999.00"],"crossed":true}],"medias":[{"url":"https://media.falabella.com/falabellaPE/prod1/image.jpg"}]}]}}}}
            </script></html>
            """.replace("__TITLE__", json_title).replace("__PRICE__", f_price)
        elif "tottus" in url:
            if is_ipad_a16:
                return """
                <html><script id="__NEXT_DATA__" type="application/json">
                {"props":{"pageProps":{"productData":{"id":"150930380","name":"Ipad A16 Wifi 128GB Azul","attributes":{"specifications":[{"name":"Tamaño de la pantalla","value":"11"},{"name":"Capacidad de almacenamiento","value":"128GB"},{"name":"marca","value":"APPLE"}]},"variants":[{"id":"150930381","name":"Ipad A16 Wifi 128GB Azul","prices":[{"type":"internetPrice","price":["1,899"],"crossed":false},{"type":"normalPrice","price":["2,599"],"crossed":true}],"medias":[{"url":"https://media.falabella.com/tottusPE/43620624_1/public"}]}]}}}}
                </script></html>
                """
            return None
        elif "efe" in url or "curacao" in url:
            e_price = "5139.00" if is_lg_oled else ("1979.00" if is_ipad_a16 else "1899.00")
            return """
            <html><head><meta property="og:image" content="https://www.efe.com.pe/media/catalog/product/prod1.jpg" /></head>
            <body>
              <div class="product-info-main">
                <h1 class="page-title"><span data-ui-id="page-title-wrapper">__TITLE__</span></h1>
                <span class="price-wrapper" data-price-type="finalPrice" data-price-amount="__PRICE__"><span class="price">S/ __PRICE__</span></span>
              </div>
            </body></html>
            """.replace("__TITLE__", matched_title).replace("__PRICE__", e_price)
        elif "hiraoka" in url:
            h_price = "3899.00" if is_lg_oled else ("1949.00" if is_ipad_a16 else "1829.00")
            return """
            <html><body>
              <div class="product-info-main">
                <h1 class="page-title"><span data-ui-id="page-title-wrapper">__TITLE__</span></h1>
              </div>
              <script type="application/ld+json">
              {"@type":"Product","name":"__JSON_TITLE__","image":"https://hiraoka.com.pe/pub/media/catalog/product/img.jpg","offers":[{"@type":"Offer","price":"__PRICE__","priceSpecification":{"priceType":"https://schema.org/SalePrice","price":"__PRICE__"}}]}
              </script>
            </body></html>
            """.replace("__JSON_TITLE__", json_title).replace("__TITLE__", matched_title).replace("__PRICE__", h_price)
        elif "ripley" in url:
            r_price = "3599" if is_lg_oled else "3399"
            return """
            <html><script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"detailProps":{"data":{"product":{"name":"__TITLE__","images":["https://rimage.ripley.com.pe/img.jpg"],"parentpricestock":{"price":{"ripley":{"valueNumber":__PRICE__},"master":{"valueNumber":4999}}}}}}}}}
            </script></html>
            """.replace("__TITLE__", json_title).replace("__PRICE__", r_price)
        return None

    with patch("app.collectors.orchestrator.fetch_page", side_effect=mock_fetch):
        import asyncio
        from app.collectors.orchestrator import CIRCUIT_BREAKERS
        from app.services.catalog_service import catalog_service

        async def _reset_and_sync():
            for cb in CIRCUIT_BREAKERS.values():
                cb.record_success()
            await init_db()
            async with AsyncSessionLocal() as session:
                await orchestrator.sync_all_catalog_products(
                    session=session,
                    on_cache_invalidate=catalog_service.invalidate_cache,
                )

        asyncio.run(_reset_and_sync())
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from app.core.security import rate_limiter
    rate_limiter.reset()


# ==============================================================================
# 1. PRUEBAS DEL TRIPLE CANDADO DE INTEGRIDAD (ZERO FALSE-POSITIVE GUARD)
# ==============================================================================

def test_validate_product_identity_redmi_note_15_pro_vs_intruders():
    """
    Caso real de producción:
    - Producto canónico: 'Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca'
    - Oferta Hiraoka: 'Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM' -> ACEPTADA
    - Oferta intrusa Tiendas Efe: 'Xiaomi Redmi A7 / A3 13MP' -> RECHAZADA
    - Variantes sin 'Pro', otros modelos ('Redmi 14C'), otra capacidad ('256GB') y accesorios -> RECHAZADAS
    """
    canonical = "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca"

    # 1. Oferta legítima de Hiraoka -> ACEPTADA
    assert validate_product_identity(
        canonical_title=canonical,
        scraped_title="Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
        scraped_url="https://hiraoka.com.pe/celular-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-cafe-moca",
        store_id="hiraoka",
    ) is True

    # 2. Oferta intrusa de Tiendas Efe (Redmi A7 / A3 13MP a S/ 399.00) -> RECHAZADA
    assert validate_product_identity(
        canonical_title=canonical,
        scraped_title="Xiaomi Redmi A7 / A3 13MP",
        scraped_url="https://www.efe.com.pe/redmi-a7pro-4gb-128gb-black-a7problack.html",
        store_id="efe",
    ) is False

    # 3. Oferta intrusa Redmi A7 Pro 128GB -> RECHAZADA
    assert validate_product_identity(
        canonical_title=canonical,
        scraped_title="Celular Xiaomi Redmi A7 Pro 128GB 4GB 6.9 Negro",
        scraped_url="https://www.efe.com.pe/redmi-a7pro-4gb-128gb-black-a7problack.html",
        store_id="efe",
    ) is False

    # 4. Oferta Redmi 14C -> RECHAZADA
    assert validate_product_identity(
        canonical_title=canonical,
        scraped_title="Celular Xiaomi Redmi 14C 256GB",
        scraped_url="https://www.efe.com.pe/xiaomi-redmi-14c.html",
        store_id="efe",
    ) is False

    # 5. Oferta Redmi Note 15 (sin sufijo crítico 'Pro' cuando el canónico exige 'Pro') -> RECHAZADA
    assert validate_product_identity(
        canonical_title=canonical,
        scraped_title="Xiaomi Redmi Note 15 5G 512GB 12GB RAM",
        scraped_url="https://www.efe.com.pe/xiaomi-redmi-note-15-5g-512gb.html",
        store_id="efe",
    ) is False

    # 6. Oferta con diferente capacidad de almacenamiento (128GB / 256GB vs 512GB) -> RECHAZADA
    assert validate_product_identity(
        canonical_title=canonical,
        scraped_title="Xiaomi Redmi Note 15 Pro 5G 256GB 8GB RAM",
        scraped_url="https://www.efe.com.pe/redmi-note15pro-8gb-256gb-blue.html",
        store_id="efe",
    ) is False

    # 7. Bloqueo de accesorios ('funda', 'case', 'protector', 'cargador', etc.) -> RECHAZADA
    assert validate_product_identity(
        canonical_title=canonical,
        scraped_title="Funda Case Protector para Xiaomi Redmi Note 15 Pro 5G 512GB",
        scraped_url="https://www.falabella.com.pe/funda-xiaomi-redmi-note-15-pro-512gb",
        store_id="falabella",
    ) is False


def test_validate_cross_store_prices_outlier_rejection():
    """
    Verifica que validate_cross_store_prices rechace cualquier oferta cuyo precio
    sea menor al 55% del precio de referencia (max para 2 tiendas, mediana para >=3 tiendas).
    """
    offers_two_stores = [
        ScrapedOffer(
            store_id="hiraoka",
            store_name="Hiraoka",
            title="Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
            price=1829.00,
            original_price=1999.00,
            offer_url="https://hiraoka.com.pe/celular-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-cafe-moca",
            image_url="https://hiraoka.com.pe/pub/media/catalog/product/redmi_note_15_pro.jpg",
        ),
        ScrapedOffer(
            store_id="efe",
            store_name="Tiendas Efe",
            title="Xiaomi Redmi A7 / A3 13MP",
            price=399.00,
            original_price=599.00,
            offer_url="https://www.efe.com.pe/redmi-a7pro-4gb-128gb-black-a7problack.html",
            image_url="https://www.efe.com.pe/media/catalog/product/redmi_a7.jpg",
        ),
    ]

    filtered = validate_cross_store_prices(offers_two_stores)
    assert len(filtered) == 1
    assert filtered[0].store_id == "hiraoka"
    assert filtered[0].price == 1829.00

    # Verificar también para 3 tiendas usando la mediana
    offers_three_stores = [
        {"store_id": "hiraoka", "store_name": "Hiraoka", "price": 1829.00},
        {"store_id": "curacao", "store_name": "La Curacao", "price": 1899.00},
        {"store_id": "efe", "store_name": "Tiendas Efe", "price": 599.00},  # < 1829 * 0.55 (1005.95)
    ]
    filtered_three = validate_cross_store_prices(offers_three_stores)
    assert len(filtered_three) == 2
    assert [o["price"] for o in filtered_three] == [1829.00, 1899.00]


@pytest.mark.asyncio
async def test_full_regression_xiaomi_redmi_note_15_pro_contamination_guard():
    """
    Prueba integral del caso crítico reportado:
    - Producto canónico: 'Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca'
    - Oferta Hiraoka: 'Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM' a S/ 1829.00 -> ACEPTADA
    - Oferta intrusa Tiendas Efe: 'Xiaomi Redmi A7 / A3 13MP' a S/ 399.00 -> RECHAZADA
    - Resultado final esperado: best_price = 1829.00, best_store = 'Hiraoka', sin rastro de S/ 399.00.
    """
    await init_db()

    def mock_contaminated_network(url: str, *args, **kwargs):
        if "hiraoka.com.pe" in url and "redmi-note-15-pro" in url:
            return """
            <html><body>
              <div class="product-info-main">
                <h1 class="page-title"><span data-ui-id="page-title-wrapper">Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM</span></h1>
              </div>
              <script type="application/ld+json">
              {
                "@type": "Product",
                "name": "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
                "image": "https://hiraoka.com.pe/pub/media/catalog/product/1/_/1_23_12.jpg",
                "offers": [{"@type": "Offer", "price": "1829.00", "priceSpecification": {"priceType": "https://schema.org/SalePrice", "price": "1829.00"}}]
              }
              </script>
            </body></html>
            """
        elif "efe.com.pe" in url or "lacuracao.pe" in url:
            # Simulamos que Tiendas Efe / Curacao intenta inyectar el celular de gama baja de S/ 399.00
            return """
            <html>
            <head><meta property="og:image" content="https://www.efe.com.pe/media/catalog/product/intruso_399.jpg" /></head>
            <body>
              <div class="product-info-main">
                <h1 class="page-title"><span data-ui-id="page-title-wrapper">Xiaomi Redmi A7 / A3 13MP</span></h1>
                <span data-price-type="finalPrice" data-price-amount="399.00"><span class="price">S/ 399.00</span></span>
                <span data-price-type="oldPrice" data-price-amount="599.00"><span class="price">S/ 599.00</span></span>
              </div>
            </body></html>
            """
        elif "hiraoka.com.pe" in url:
            matched_title = _title_for_url(url)
            return """
            <html><body>
              <div class="product-info-main">
                <h1 class="page-title"><span data-ui-id="page-title-wrapper">__TITLE__</span></h1>
              </div>
              <script type="application/ld+json">
              {"@type":"Product","name":"__TITLE__","image":"https://hiraoka.com.pe/pub/media/catalog/product/img.jpg","offers":[{"@type":"Offer","price":"3499.00","priceSpecification":{"priceType":"https://schema.org/SalePrice","price":"3499.00"}}]}
              </script>
            </body></html>
            """.replace("__TITLE__", matched_title)
        return None

    with patch("app.collectors.orchestrator.fetch_page", side_effect=mock_contaminated_network):
        async with AsyncSessionLocal() as session:
            await orchestrator.sync_all_catalog_products(session=session)
            from sqlalchemy import select
            q = await session.execute(
                select(ProductEntity).where(ProductEntity.id == "prod_xiaomi_redmi_note")
            )
            prod = q.scalar_one()

            assert prod.best_price == 1829.00
            assert prod.best_store_name == "Hiraoka"
            assert prod.available_stores_count == 1
            assert "hiraoka.com.pe" in prod.image_url
            assert "intruso_399" not in prod.image_url

            store_prices = [o.price for o in prod.store_offers]
            assert store_prices == [1829.00]
            assert 399.00 not in store_prices


@pytest.mark.asyncio
async def test_database_sanitization_removes_existing_contaminated_offers():
    """
    Verifica que sanitize_database_offers elimine inmediatamente de la BD cualquier
    StoreOfferEntity existente que falle validate_product_identity o validate_cross_store_prices
    y recalcule best_price, best_store_name y available_stores_count.
    """
    await init_db()
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        q = await session.execute(
            select(ProductEntity).where(ProductEntity.id == "prod_xiaomi_redmi_note")
        )
        prod = q.scalar_one()

        # Inyectar manualmente en la BD la oferta contaminada de S/ 399.00 como si ya estuviera guardada
        bad_offer = StoreOfferEntity(
            product_id=prod.id,
            store_id="efe",
            store_name="Tiendas Efe",
            price=399.00,
            original_price=599.00,
            offer_url="https://www.efe.com.pe/redmi-a7pro-4gb-128gb-black-a7problack.html",
            is_best_price=True,
        )
        session.add(bad_offer)
        prod.best_price = 399.00
        prod.best_store_name = "Tiendas Efe"
        prod.available_stores_count = 2
        await session.commit()

        # Ejecutar rutina de saneamiento
        stats = await orchestrator.sanitize_database_offers(session=session)
        assert stats["removed_offers"] >= 1

        await session.refresh(prod)
        assert prod.best_price == 1829.00
        assert prod.best_store_name == "Hiraoka"
        assert prod.available_stores_count == 1
        assert all(o.price != 399.00 for o in prod.store_offers)


# ==============================================================================
# 2. PRUEBAS DE EXTRACTORES REALES Y AISLAMIENTO DE DOM PRINCIPAL
# ==============================================================================

def test_parse_conectaretail_ignores_related_and_upsell_carousels():
    """
    Verifica que parse_conectaretail ignore precios e imágenes dentro de .block.related
    o .block.upsell y extraiga estrictamente desde .product-info-main.
    """
    html_with_carousel_first = """
    <html>
    <head>
      <meta property="og:image" content="https://www.efe.com.pe/media/catalog/product/redmi15pro.jpg" />
    </head>
    <body>
      <div class="page-wrapper">
        <div class="block related">
          <span class="price-wrapper" data-price-type="finalPrice" data-price-amount="49.00">
            <span class="price">S/ 49.00</span>
          </span>
        </div>
        <div class="product-info-main">
          <h1 class="page-title"><span data-ui-id="page-title-wrapper">Celular Xiaomi Redmi Note 15 Pro 5G 512GB</span></h1>
          <div class="price-box">
            <span class="price-wrapper" data-price-type="finalPrice" data-price-amount="1899.00">
              <span class="price">S/ 1,899.00</span>
            </span>
            <span class="old-price">
              <span class="price-wrapper" data-price-type="oldPrice" data-price-amount="2099.00">
                <span class="price">S/ 2,099.00</span>
              </span>
            </span>
          </div>
        </div>
      </div>
    </body>
    </html>
    """
    url = "https://www.efe.com.pe/redmi-note15pro-5g-12gb-512gb-brown.html"
    res = parse_conectaretail(html_with_carousel_first, url)
    assert res is not None
    assert res["price"] == 1899.00
    assert res["original_price"] == 2099.00
    assert "Xiaomi Redmi Note 15 Pro" in res["title"]


def test_parse_search_results_validates_identity_before_selecting():
    """
    Verifica que cuando un parser recibe una lista de búsqueda (/catalogsearch/result/?q=...),
    jamás tome el primer resultado a ciegas, sino únicamente el que apruebe validate_product_identity.
    """
    search_html = """
    <html><body>
      <ol class="products list items product-items">
        <li class="item product product-item">
          <div class="product-item-info">
            <a class="product-item-link" href="https://www.efe.com.pe/redmi-a7-128gb.html">
              Celular Xiaomi Redmi A7 128GB 4GB
            </a>
            <span data-price-type="finalPrice" data-price-amount="399.00"><span class="price">S/ 399.00</span></span>
          </div>
        </li>
        <li class="item product product-item">
          <div class="product-item-info">
            <a class="product-item-link" href="https://www.efe.com.pe/redmi-note15pro-5g-512gb.html">
              Celular Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM
            </a>
            <span data-price-type="finalPrice" data-price-amount="1899.00"><span class="price">S/ 1,899.00</span></span>
          </div>
        </li>
      </ol>
    </body></html>
    """
    search_url = "https://www.efe.com.pe/catalogsearch/result/?q=redmi+note+15+pro"
    canonical = "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca"

    res = parse_conectaretail(search_html, search_url, canonical_title=canonical)
    assert res is not None
    assert res["price"] == 1899.00
    assert res["offer_url"] == "https://www.efe.com.pe/redmi-note15pro-5g-512gb.html"


def test_parse_falabella_next_data():
    """Verifica extracción real desde __NEXT_DATA__ de Falabella."""
    sample_html = """
    <html>
    <script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "productData": {
            "name": "Celular Samsung Galaxy S25 Ultra 512GB",
            "variants": [
              {
                "prices": [
                  {"type": "cmrPrice", "price": ["3,499.00"], "crossed": false},
                  {"type": "internetPrice", "price": ["3,699.00"], "crossed": false},
                  {"type": "normalPrice", "price": ["5,499.00"], "crossed": true}
                ],
                "medias": [
                  {"url": "https://media.falabella.com/falabellaPE/prod1/image.jpg"}
                ]
              }
            ]
          }
        }
      }
    }
    </script>
    </html>
    """
    url = "https://www.falabella.com.pe/falabella-pe/product/prod1/celular"
    res = parse_falabella(sample_html, url)
    assert res is not None
    assert res["price"] == 3499.00
    assert res["original_price"] == 5499.00
    assert "media.falabella.com" in res["image_url"]
    assert res["offer_url"] == url


def test_parse_conectaretail_magento2():
    """Verifica extracción real para Efe y Curacao mediante data-price-amount y meta og:image."""
    sample_html = """
    <html>
    <head>
      <meta property="og:image" content="https://www.efe.com.pe/media/catalog/product/prod1.jpg" />
    </head>
    <body>
      <div class="product-info-main">
        <h1 class="page-title"><span data-ui-id="page-title-wrapper">Samsung Galaxy S25 Ultra 512GB</span></h1>
        <div class="price-box">
          <span class="price-container">
            <span class="price-wrapper" data-price-type="finalPrice" data-price-amount="3799.00">
              <span class="price">S/ 3,799.00</span>
            </span>
          </span>
          <span class="old-price">
            <span class="price-wrapper" data-price-type="oldPrice" data-price-amount="5299.00">
              <span class="price">S/ 5,299.00</span>
            </span>
          </span>
        </div>
      </div>
    </body>
    </html>
    """
    url = "https://www.efe.com.pe/producto-test.html"
    res = parse_conectaretail(sample_html, url)
    assert res is not None
    assert res["price"] == 3799.00
    assert res["original_price"] == 5299.00
    assert res["image_url"] == "https://www.efe.com.pe/media/catalog/product/prod1.jpg"


def test_parse_hiraoka_json_ld():
    """Verifica extracción real en Hiraoka con SalePrice y ListPrice en JSON-LD."""
    sample_html = """
    <html>
    <script type="application/ld+json">
    {
      "@type": "Product",
      "name": "Celular Samsung Galaxy S26",
      "image": "https://hiraoka.com.pe/pub/media/catalog/product/img.jpg",
      "offers": [
        {
          "@type": "Offer",
          "price": "4499.00",
          "priceSpecification": {
            "priceType": "https://schema.org/SalePrice",
            "price": "4499.00"
          }
        },
        {
          "@type": "Offer",
          "price": "5499.00",
          "priceSpecification": {
            "priceType": "https://schema.org/ListPrice",
            "price": "5499.00"
          }
        }
      ]
    }
    </script>
    </html>
    """
    url = "https://hiraoka.com.pe/celular-test"
    res = parse_hiraoka(sample_html, url)
    assert res is not None
    assert res["price"] == 4499.00
    assert res["original_price"] == 5499.00
    assert "hiraoka.com.pe" in res["image_url"]


def test_parse_ripley_detail_props():
    """Verifica extracción real en Ripley mediante parentpricestock."""
    sample_html = """
    <html>
    <script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "detailProps": {
            "data": {
              "product": {
                "name": "IPHONE 16 128GB",
                "images": ["https://rimage.ripley.com.pe/Attachment/img1.jpg"],
                "parentpricestock": {
                  "price": {
                    "master": {"valueNumber": 5399},
                    "sale": {"valueNumber": 3599},
                    "ripley": {"valueNumber": 3399}
                  }
                }
              }
            }
          }
        }
      }
    }
    </script>
    </html>
    """
    url = "https://simple.ripley.com.pe/iphone-16-128gb-p"
    res = parse_ripley(sample_html, url)
    assert res is not None
    assert res["price"] == 3399.00
    assert res["original_price"] == 5399.00
    assert "rimage.ripley.com.pe" in res["image_url"]


# ==============================================================================
# 3. VERIFICACIÓN ZERO-MOCK Y COINCIDENCIA DE IDENTIDAD EN EL CATÁLOGO OFICIAL
# ==============================================================================

def test_catalog_urls_strict_zero_mock_and_identity_policy():
    """
    Verifica que el catálogo oficial cumpla con la regla de oro:
    - 0 URLs falsas o 'ejemplo.com'
    - Solo retailers peruanos reales
    - Todas las URLs del catálogo aprueban validate_product_identity contra su título canónico
    """
    allowed_domains = {
        "falabella.com.pe",
        "tottus.com.pe",
        "efe.com.pe",
        "lacuracao.pe",
        "hiraoka.com.pe",
        "simple.ripley.com.pe",
        "metro.pe",
        "wong.pe",
    }

    assert len(CATALOG_PRODUCTS) >= 5

    for p in CATALOG_PRODUCTS:
        assert p["id"].startswith("prod_")
        assert len(p["title"]) > 5
        assert p["category"] in {"Smartphones", "Laptops", "Tablets", "TVs"}
        assert len(p["store_urls"]) >= 1

        for store_id, url in p["store_urls"].items():
            assert store_id in STORES_INFO, f"Tienda desconocida: {store_id}"
            assert url.startswith("https://")
            assert "ejemplo.com" not in url
            assert "test.com" not in url
            matched = any(domain in url for domain in allowed_domains)
            assert matched, f"URL con dominio no autorizado: {url}"
            assert validate_product_identity(
                canonical_title=p["title"],
                scraped_title="",
                scraped_url=url,
                store_id=store_id,
                tech_specs=p.get("tech_specs"),
            ), f"URL en catálogo no coincide con identidad de '{p['title']}': {url}"


# ==============================================================================
# 4. ENDPOINTS Y CONTRATO DE DATOS (CAMELCASE ESTRICTO)
# ==============================================================================

def test_root_and_health(client: TestClient):
    """Verifica / y /api/v1/health."""
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "healthy"

    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    h_data = res_health.json()
    assert h_data["database"] == "connected"
    assert "totalProducts" in h_data
    assert "storesStatus" in h_data
    assert h_data["totalStores"] >= 5


def test_products_camel_case_contract(client: TestClient):
    """Verifica que /api/v1/products cumpla con el contrato estricto camelCase."""
    res = client.get("/api/v1/products")
    assert res.status_code == 200
    prods = res.json()
    assert len(prods) >= 1

    p = prods[0]
    expected_keys = [
        "id", "title", "category", "bestPrice", "originalPrice", "bestStoreName",
        "discountPercentage", "availableStoresCount", "imageUrl", "description",
        "features", "isFavorite", "storePrices", "techSpecs", "isHistoricalMin",
        "priceHistory30Days",
    ]
    for key in expected_keys:
        assert key in p, f"Falta clave camelCase: {key}"

    assert p["availableStoresCount"] == len(p["storePrices"])
    prices = [sp["price"] for sp in p["storePrices"]]
    assert prices == sorted(prices)
    assert p["storePrices"][0]["isBestPrice"] is True


def test_hardware_filters_and_sorting(client: TestClient):
    """Verifica filtros por categoría, RAM, almacenamiento y ordenamiento."""
    res_cat = client.get("/api/v1/products?category=Smartphones")
    assert res_cat.status_code == 200
    for p in res_cat.json():
        assert p["category"] == "Smartphones"

    res_ram = client.get("/api/v1/products?ram=12GB")
    assert res_ram.status_code == 200
    for p in res_ram.json():
        ram_spec = p["techSpecs"].get("Memoria RAM", "").lower().replace(" ", "")
        title_ram = p["title"].lower().replace(" ", "")
        assert "12gb" in ram_spec or "12gb" in title_ram

    res_sort = client.get("/api/v1/products?sort_order=LOW_TO_HIGH")
    assert res_sort.status_code == 200
    sorted_prices = [p["bestPrice"] for p in res_sort.json()]
    assert sorted_prices == sorted(sorted_prices)


def test_spec_extractor_canonical_mapping_and_stores():
    """
    Verifica extracción y normalización automática de specs desde:
    1. Magento 2 (#product-attribute-specs-table)
    2. Falabella (__NEXT_DATA__ attributes)
    3. Ripley (window.__PRELOADED_STATE__.product.product.attributes)
    """
    assert "Marca" in CANONICAL_SPEC_MAP
    assert "Procesador" in CANONICAL_SPEC_MAP
    assert "Memoria RAM" in CANONICAL_SPEC_MAP
    assert "Almacenamiento" in CANONICAL_SPEC_MAP

    magento_html = """
    <html><body>
      <table id="product-attribute-specs-table">
        <tr><th>Marca</th><td>XIAOMI</td></tr>
        <tr><th>Modelo del procesador</th><td>Snapdragon 7s Gen4</td></tr>
        <tr><th>Capacidad de memoria RAM</th><td>12GB</td></tr>
        <tr><th>Memoria interna</th><td>512GB</td></tr>
        <tr><th>Tamaño de pantalla</th><td>6.8"</td></tr>
        <tr><th>Tipo de pantalla</th><td>AMOLED Display</td></tr>
        <tr><th>Resolución cámara posterior</th><td>200MP+8MP</td></tr>
        <tr><th>Capacidad de batería</th><td>6500 mAh</td></tr>
        <tr><th>Red móvil</th><td>5G</td></tr>
      </table>
    </body></html>
    """
    res_mag = extract_product_specs(
        magento_html,
        title="Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
        store_id="efe",
    )
    assert res_mag["brand"] == "Xiaomi"
    specs = res_mag["tech_specs"]
    assert specs["Marca"] == "Xiaomi"
    assert specs["Procesador"] == "Snapdragon 7s Gen4"
    assert specs["Memoria RAM"] == "12 GB"
    assert specs["Almacenamiento"] == "512 GB"
    assert specs["Pantalla"] == '6.8" AMOLED'
    assert specs["Cámara Principal"] == "200 MP + 8 MP"
    assert specs["Batería"] == "6500 mAh"
    assert specs["Conectividad"] == "5G"
    assert 4 <= len(res_mag["features"]) <= 6

    ripley_html = """
    <html><script>
    window.__PRELOADED_STATE__ = {"product":{"product":{"brand":"SAMSUNG","attributes":[{"name":"Procesador","value":"Exynos 1580"},{"name":"Memoria RAM","value":"8GB"},{"name":"Almacenamiento","value":"256GB"}]}}};
    </script></html>
    """
    res_rip = extract_product_specs(ripley_html, title="Samsung Galaxy A56", store_id="ripley")
    assert res_rip["brand"] == "Samsung"
    assert res_rip["tech_specs"]["Procesador"] == "Exynos 1580"
    assert res_rip["tech_specs"]["Memoria RAM"] == "8 GB"
    assert res_rip["tech_specs"]["Almacenamiento"] == "256 GB"


def test_extract_specs_from_title_fallback_and_merge():
    """
    Verifica extract_specs_from_title_fallback en smartphones y laptops,
    así como merge_product_specs entre múltiples tiendas.
    """
    s1 = extract_specs_from_title_fallback("Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM")
    assert s1["Marca"] == "Xiaomi"
    assert s1["Memoria RAM"] == "12 GB"
    assert s1["Almacenamiento"] == "512 GB"
    assert s1["Conectividad"] == "5G"

    s2 = extract_specs_from_title_fallback("Laptop Asus TUF Intel Core 5 16GB RAM 512GB SSD RTX 3050")
    assert s2["Marca"] == "Asus"
    assert s2["Procesador"] == "Intel Core 5"
    assert s2["Memoria RAM"] == "16 GB"
    assert s2["Almacenamiento"] == "512 GB"

    s3 = extract_specs_from_title_fallback("Celular Honor Magic 8+256GB 5G")
    assert s3["Marca"] == "Honor"
    assert s3["Memoria RAM"] == "8 GB"
    assert s3["Almacenamiento"] == "256 GB"
    assert s3["Conectividad"] == "5G"

    merged = merge_product_specs(
        specs_list=[
            {"Marca": "Xiaomi", "Memoria RAM": "12GB", "Pantalla": '6.8"'},
            {"Memoria interna": "512GB", "Pantalla": '6.8" AMOLED 120Hz', "Batería": "6500 mAh"},
        ],
        title="Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
    )
    assert merged["Memoria RAM"] == "12 GB"
    assert merged["Almacenamiento"] == "512 GB"
    assert merged["Pantalla"] == '6.8" AMOLED 120Hz'
    assert merged["Batería"] == "6500 mAh"
    feats = generate_product_features(None, merged, title="Xiaomi Redmi Note 15 Pro 5G")
    assert 4 <= len(feats) <= 6


def test_dynamic_filters_endpoint_and_dynamic_product_queries(client: TestClient):
    """
    Verifica que GET /api/v1/filters devuelva categories, brands_by_category y specs_by_category
    calculados dinámicamente desde la base de datos y que GET /api/v1/products filtre con ellos.
    """
    res_f = client.get("/api/v1/filters")
    assert res_f.status_code == 200
    f_data = res_f.json()

    assert "categories" in f_data
    assert f_data["categories"][0] == "Todos"
    assert "Smartphones" in f_data["categories"]

    assert "brands_by_category" in f_data
    assert f_data["brands_by_category"]["Todos"][0] == "Todas"
    assert "Xiaomi" in f_data["brands_by_category"]["Smartphones"]

    assert "specs_by_category" in f_data
    smart_specs = f_data["specs_by_category"]["Smartphones"]
    assert "Memoria RAM" in smart_specs
    assert smart_specs["Memoria RAM"][0] == "Todas"
    assert "12 GB" in smart_specs["Memoria RAM"]

    assert "Almacenamiento" in smart_specs
    assert smart_specs["Almacenamiento"][0] == "Todos"
    assert "512 GB" in smart_specs["Almacenamiento"]

    # Probar filtrado dinámico en GET /api/v1/products usando el formato '12 GB' y '512 GB'
    res_p = client.get("/api/v1/products?category=Smartphones&ram=12%20GB&storage=512%20GB")
    assert res_p.status_code == 200
    items = res_p.json()
    assert len(items) >= 1
    for item in items:
        assert item["techSpecs"]["Memoria RAM"] == "12 GB"
        assert item["techSpecs"]["Almacenamiento"] == "512 GB"


def test_enabled_stores_dynamic_recalc(client: TestClient):
    """Verifica que al enviar enabled_stores se recalculen los precios con solo esas tiendas."""
    res = client.get("/api/v1/products?enabled_stores=efe,hiraoka")
    assert res.status_code == 200
    prods = res.json()
    for p in prods:
        for sp in p["storePrices"]:
            assert sp["storeId"] in {"efe", "hiraoka"}
        assert p["bestStoreName"] in {"Tiendas Efe", "Hiraoka"}


def test_community_offers_flow(client: TestClient):
    """Verifica creación y consulta de ofertas físicas comunitarias con validación de ubigeo."""
    prods_res = client.get("/api/v1/products")
    first_prod_id = prods_res.json()[0]["id"]

    offer_payload = {
        "productId": first_prod_id,
        "physicalStoreName": "Tiendas Efe Chiclayo Centro",
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "priceFound": 3699.00,
        "comment": "Precio en liquidación de vitrina",
        "authorName": "Usuario Real",
    }
    res_create = client.post("/api/v1/community-offers", json=offer_payload)
    assert res_create.status_code == 201
    created = res_create.json()
    assert created["department"] == "Lambayeque"
    assert created["priceFound"] == 3699.00

    invalid_payload = offer_payload.copy()
    invalid_payload["department"] = "ProvinciaInventada"
    res_err = client.post("/api/v1/community-offers", json=invalid_payload)
    assert res_err.status_code == 422


def test_admin_sync_security(client: TestClient):
    """Verifica protección estricta con X-API-Key en POST /api/v1/collectors/sync."""
    res_no_key = client.post("/api/v1/collectors/sync")
    assert res_no_key.status_code == 401

    res_bad_key = client.post(
        "/api/v1/collectors/sync", headers={"X-API-Key": "bad_key_attempt"}
    )
    assert res_bad_key.status_code == 403

    with patch("app.collectors.orchestrator.orchestrator.sync_all_catalog_products", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = {"status": "success", "updated_offers": 1}
        res_ok = client.post(
            "/api/v1/collectors/sync",
            headers={"X-API-Key": settings.FINPRICE_ADMIN_API_KEY},
        )
        assert res_ok.status_code == 202
        data = res_ok.json()
        assert data["status"] == "accepted"


def test_legacy_get_products(client: TestClient):
    """Verifica compatibilidad de GET /products para clientes previos."""
    res = client.get("/products")
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    item = items[0]
    assert "id" in item and isinstance(item["id"], int)
    assert "name" in item
    assert "category" in item
    assert "lowest_price" in item
    assert "best_store" in item
    assert "offers" in item
    assert len(item["offers"]) > 0


# ==============================================================================
# 5. PRUEBA EN VIVO CONTRA RETAILER REAL PERUANO (XIAOMI REDMI NOTE 15 PRO 5G)
# ==============================================================================

@pytest.mark.asyncio
async def test_live_network_extraction_hiraoka():
    """
    Realiza una extracción en vivo directamente contra hiraoka.com.pe para el
    Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca, verificando precio real e identidad.
    """
    from app.collectors.http_client import fetch_page
    canonical = "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca"
    url = "https://hiraoka.com.pe/celular-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-cafe-moca"
    html = await fetch_page(url)
    assert html is not None, "El servidor de Hiraoka no respondió o hubo timeout de red"
    data = parse_hiraoka(html, url, canonical_title=canonical)
    assert data is not None, "No se pudo extraer la información real de Hiraoka"
    assert data["price"] > 1000.0, f"Precio extraído no razonable: {data['price']}"
    assert data["offer_url"] == url
    assert "hiraoka.com.pe" in data["image_url"]
    assert validate_product_identity(canonical, data["title"], url, store_id="hiraoka") is True


# ==============================================================================
# 6. SOPORTE DE LAS 8 TIENDAS DEL RETAIL PERUANO Y HUELLA TÉCNICA (FINGERPRINT)
# ==============================================================================

def test_canonicalize_store_url_all_8_stores_and_ad_params():
    """
    Verifica que canonicalize_store_url identifique cada una de las 8 tiendas
    (falabella, tottus, ripley, metro, wong, efe, curacao, hiraoka) y limpie todos
    los parámetros basura de publicidad (kid, gclsrc, gad_source, gad_campaignid,
    gbraid, gsImpressionId, s, pos, catPos, p, ps, orig, searchTerm, color_80, utm_*).
    """
    cases = [
        (
            "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493?kid=bnnext288707&gad_source=1&utm_campaign=cyber",
            "falabella",
            "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493",
        ),
        (
            "https://www.tottus.com.pe/tottus-pe/articulo/153301442/televisor-jvc-40-qled-fhd-roku-tv/153301443?utm_source=google&gclsrc=aw.ds",
            "tottus",
            "https://www.tottus.com.pe/tottus-pe/articulo/153301442/televisor-jvc-40-qled-fhd-roku-tv/153301443",
        ),
        (
            "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p?color_80=negro&s=mdco",
            "ripley",
            "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p",
        ),
        (
            "https://www.metro.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p?utm_medium=cpc&gad_source=1",
            "metro",
            "https://www.metro.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p",
        ),
        (
            "https://www.wong.pe/televisor-samsung-65-uhd-u8000h-vision-ai-smart-tv-2026-1067739/p?gbraid=0AAAAADl2B2Z",
            "wong",
            "https://www.wong.pe/televisor-samsung-65-uhd-u8000h-vision-ai-smart-tv-2026-1067739/p",
        ),
        (
            "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html?kid=bnnext288707&gclsrc=aw.ds&gad_source=1&gad_campaignid=20434711906&gbraid=0AAAAADl2B2Z_1t2gP5iB7-tO5c9l5jW5u",
            "efe",
            "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        ),
        (
            "https://www.lacuracao.pe/celular-honor-magic-8-lite-8-256gb-5g-negro-magic8lite-b.html?pos=1&catPos=1&p=1&ps=12&orig=search&searchTerm=celular",
            "curacao",
            "https://www.lacuracao.pe/celular-honor-magic-8-lite-8-256gb-5g-negro-magic8lite-b.html",
        ),
        (
            "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026?gsImpressionId=236c0f76-0d99-4d3b-a3e8-ab56d72b11db",
            "hiraoka",
            "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026",
        ),
    ]

    for dirty_url, expected_store, expected_clean_url in cases:
        store_id, clean_url = canonicalize_store_url(dirty_url)
        assert store_id == expected_store
        assert clean_url == expected_clean_url
        assert "?" not in clean_url
        assert get_parser_for_store(store_id) is not None


def test_product_fingerprint_matcher_lg_oled_55_c6_zero_false_positives_and_negatives():
    """
    Verifica que matches_fingerprint:
    1. Acepte las variantes reales de redacción comercial del LG 55" OLED evo AI C6 4K Smart TV 2026
       en Falabella, Ripley, Hiraoka, Efe y La Curacao (Cero Falsos Negativos).
    2. Rechace tamaños distintos (42", 48", 65", 77") aunque sean OLED C6 y modelos distintos
       como OLED B6 (OLED55B6PSA), OLED G6, C5 o QNED (Cero Falsos Positivos).
    """
    fp = ProductFingerprint(
        brand="lg",
        family_tokens=["oled", "c6"],
        screen_inches=55,
        forbidden_tokens=["b6", "b5", "b4", "c5", "c4", "g6", "g5", "qned", "nanocell"],
    )

    assert build_compact_search_query(fp) == "LG OLED 55 C6"

    # 1. Coincidencias reales exactas en las tiendas donde sí existe
    assert matches_fingerprint(
        fp,
        candidate_title='Televisor LG 55" OLED evo AI C6 4K Smart TV 2026',
        candidate_specs={"Marca": "LG", "Pantalla": '55" OLED'},
        candidate_url="https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493",
    ) is True

    assert matches_fingerprint(
        fp,
        candidate_title='Televisor Smart TV LG 55" OLED evo AI C6 4K 2026',
        candidate_specs={"Marca": "LG", "Pantalla": '55"'},
        candidate_url="https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p",
    ) is True

    assert matches_fingerprint(
        fp,
        candidate_title='Televisor LG 55" OLED evo AI C6 4K Smart TV 2026',
        candidate_specs={"Marca": "LG"},
        candidate_url="https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026",
    ) is True

    assert matches_fingerprint(
        fp,
        candidate_title='55" LG OLED evo AI C6 4K Smart TV 2026 OLED55C6PSA',
        candidate_specs={"Marca": "LG"},
        candidate_url="https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
    ) is True

    # 2. Rechazo de otros tamaños del mismo modelo C6 (42", 48", 65", 77")
    for wrong_inches in (42, 48, 65, 77):
        assert matches_fingerprint(
            fp,
            candidate_title=f'Televisor LG {wrong_inches}" OLED evo AI C6 4K Smart TV 2026',
            candidate_specs={"Marca": "LG"},
            candidate_url=f"https://www.falabella.com.pe/falabella-pe/product/80046490/{wrong_inches}-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046490",
        ) is False

    # 3. Rechazo de otros modelos en 55" (ej. LG OLED B6 en Metro/Wong o LG OLED G6)
    assert matches_fingerprint(
        fp,
        candidate_title="Televisor LG OLED 55 OLED55B6PSA 4K Smart TV",
        candidate_specs={"Marca": "LG"},
        candidate_url="https://www.wong.pe/televisor-lg-oled-55-oled55b6psa/p",
    ) is False

    assert matches_fingerprint(
        fp,
        candidate_title='Televisor LG 55" OLED evo AI G6 4K Smart TV 2026',
        candidate_specs={"Marca": "LG"},
        candidate_url="https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-g6-4k-smart-tv-2026",
    ) is False


@pytest.mark.asyncio
async def test_discover_product_across_8_stores_includes_matches_and_omits_non_existing_stores():
    """
    Verifica que discover_product_across_8_stores evalúe las 8 tiendas concurrentemente:
    - Incluye Falabella (S/ 3599), Ripley (S/ 3599), Hiraoka (S/ 3899), Efe y Curacao (S/ 5139)
      con sus URLs canonicalizadas.
    - Omite limpiamente Tottus, Metro y Wong cuando sus búsquedas devuelven otros televisores
      (ej. JVC 40" QLED en Tottus, LG OLED 55 B6 en Metro y Samsung 65" U8000H en Wong).
    """
    fp = ProductFingerprint(
        brand="lg",
        family_tokens=["oled", "c6"],
        screen_inches=55,
        forbidden_tokens=["b6", "b5", "g6", "qned"],
    )
    direct_urls = {
        "falabella": "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493?kid=bnnext288707",
        "ripley": "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p?color_80=negro&s=mdco",
        "hiraoka": "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026?gsImpressionId=236c0f76",
        "efe": "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html?gad_source=1",
        "curacao": "https://www.lacuracao.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html?pos=1",
    }

    async def fake_8_store_scraper(store_id: str, url: str, **kwargs):
        if store_id == "falabella":
            return {
                "title": '55" LG OLED evo AI C6 4K Smart TV 2026',
                "price": 3599.00,
                "original_price": 4999.00,
                "offer_url": url,
            }
        if store_id == "ripley":
            return {
                "title": 'Televisor Smart TV LG 55" OLED evo AI C6 4K 2026',
                "price": 3599.00,
                "original_price": 4999.00,
                "offer_url": url,
            }
        if store_id == "hiraoka":
            return {
                "title": 'Televisor LG 55" OLED evo AI C6 4K Smart TV 2026',
                "price": 3899.00,
                "original_price": 4999.00,
                "offer_url": url,
            }
        if store_id in {"efe", "curacao"}:
            return {
                "title": '55" LG OLED evo AI C6 4K Smart TV 2026 OLED55C6PSA',
                "price": 5139.00,
                "original_price": 6769.00,
                "offer_url": url,
            }
        # En Tottus, Metro y Wong no existe el LG OLED 55 C6; sus buscadores devuelven otros TVs:
        if store_id == "tottus":
            return {
                "title": 'Televisor JVC 40" QLED FHD Roku TV',
                "price": 489.00,
                "original_price": 899.00,
                "offer_url": "https://www.tottus.com.pe/tottus-pe/articulo/153301442/televisor-jvc-40-qled-fhd-roku-tv/153301443",
            }
        if store_id == "metro":
            return {
                "title": "Televisor LG OLED 55 OLED55B6PSA",
                "price": 3499.00,
                "original_price": 4599.00,
                "offer_url": "https://www.metro.pe/televisor-lg-oled-55-oled55b6psa/p",
            }
        if store_id == "wong":
            return {
                "title": 'Televisor Samsung 65" UHD U8000H Vision AI Smart TV 2026',
                "price": 1799.00,
                "original_price": 2499.00,
                "offer_url": "https://www.wong.pe/televisor-samsung-65-uhd-u8000h-vision-ai-smart-tv-2026-1067739/p",
            }
        return None

    verified = await discover_product_across_8_stores(
        fingerprint=fp,
        direct_store_urls=direct_urls,
        canonical_title='LG 55" OLED evo AI C6 4K Smart TV 2026',
        scrape_fn=fake_8_store_scraper,
        enable_live_search_discovery=True,
    )

    store_ids = [o["store_id"] for o in verified]
    assert len(verified) == 5
    assert "falabella" in store_ids
    assert "ripley" in store_ids
    assert "hiraoka" in store_ids
    assert "efe" in store_ids
    assert "curacao" in store_ids
    # Tottus, Metro y Wong deben haber sido omitidos limpiamente
    assert "tottus" not in store_ids
    assert "metro" not in store_ids
    assert "wong" not in store_ids
    assert verified[0]["price"] == 3599.00
    assert all("?" not in o["offer_url"] for o in verified)


def test_parse_vtex_cencosud_metro_wong_and_parse_tottus():
    """
    Verifica los extractores dedicados para:
    - Metro (metro.pe) y Wong (wong.pe) mediante VTEX API JSON y HTML /p con JSON-LD/Apollo
    - Tottus (tottus.com.pe) mediante #__NEXT_DATA__ y JSON-LD
    """
    wong_vtex_json = json.dumps([
        {
            "productName": 'Televisor Samsung 65" UHD U8000H Vision AI Smart TV 2026',
            "brand": "Samsung",
            "link": "https://www.wong.pe/televisor-samsung-65-uhd-u8000h-vision-ai-smart-tv-2026-1067739/p?utm_source=vtex",
            "allSpecifications": ["Tamaño de Pantalla", "Resolución de video"],
            "Tamaño de Pantalla": ["65 Pulgadas"],
            "Resolución de video": ["4K UHD"],
            "items": [
                {
                    "images": [{"imageUrl": "https://wongfood.vtexassets.com/arquivos/ids/750000/tv.jpg"}],
                    "sellers": [
                        {
                            "commertialOffer": {
                                "Price": 1899.0,
                                "ListPrice": 2599.0,
                                "AvailableQuantity": 8,
                                "IsAvailable": True,
                            }
                        }
                    ],
                }
            ],
        }
    ])
    res_wong = parse_vtex_cencosud(
        wong_vtex_json,
        "https://www.wong.pe/televisor-samsung-65-uhd-u8000h-vision-ai-smart-tv-2026-1067739/p",
    )
    assert res_wong is not None
    assert res_wong["price"] == 1899.0
    assert res_wong["original_price"] == 2599.0
    assert res_wong["brand"] == "Samsung"
    assert res_wong["offer_url"] == "https://www.wong.pe/televisor-samsung-65-uhd-u8000h-vision-ai-smart-tv-2026-1067739/p"

    # Producto sin stock (AvailableQuantity = 0) en Metro debe descartarse
    metro_out_of_stock_json = json.dumps([
        {
            "productName": "Impresora Multifuncional Epson L3350 WiFi",
            "brand": "Epson",
            "link": "https://www.metro.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p",
            "items": [
                {
                    "sellers": [
                        {
                            "commertialOffer": {
                                "Price": 699.0,
                                "ListPrice": 899.0,
                                "AvailableQuantity": 0,
                                "IsAvailable": False,
                            }
                        }
                    ]
                }
            ],
        }
    ])
    assert parse_vtex_cencosud(
        metro_out_of_stock_json,
        "https://www.metro.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p",
    ) is None

    # Tottus Next.js + JSON-LD
    tottus_html = """
    <html>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"productData":{"name":"Televisor JVC 40\\" QLED FHD Roku TV","variants":[{"prices":[{"type":"cmrPrice","price":["489.00"],"crossed":false},{"type":"normalPrice","price":["899.00"],"crossed":true}],"medias":[{"url":"https://media.tottus.com.pe/tottusPE/153301443/public"}]}]}}}}
    </script>
    <script type="application/ld+json">
    {"@type":"Product","name":"Televisor JVC 40\\" QLED FHD Roku TV","brand":{"@type":"Brand","name":"JVC"},"offers":{"@type":"Offer","price":"489.00"}}
    </script>
    </html>
    """
    res_tottus = parse_tottus(
        tottus_html,
        "https://www.tottus.com.pe/tottus-pe/articulo/153301442/televisor-jvc-40-qled-fhd-roku-tv/153301443?kid=test",
    )
    assert res_tottus is not None
    assert res_tottus["price"] == 489.0
    assert res_tottus["original_price"] == 899.0
    assert res_tottus["brand"] == "JVC"
    assert res_tottus["offer_url"] == "https://www.tottus.com.pe/tottus-pe/articulo/153301442/televisor-jvc-40-qled-fhd-roku-tv/153301443"


def test_lg_oled_55_c6_has_falabella_ripley_and_hiraoka_with_best_price_3599(client: TestClient):
    """
    Verifica que el televisor LG 55" OLED evo AI C6 4K Smart TV 2026 (prod_lg_oled_tv)
    incluya las ofertas reales de Falabella (S/ 3,599.00), Ripley (S/ 3,599.00) e Hiraoka (S/ 3,899.00),
    con bestPrice = 3599.0 y URLs canónicas limpias.
    """
    res = client.get("/api/v1/products/prod_lg_oled_tv")
    assert res.status_code == 200
    tv = res.json()

    assert tv["id"] == "prod_lg_oled_tv"
    assert tv["bestPrice"] == 3599.0

    by_store = {sp["storeId"]: sp for sp in tv["storePrices"]}
    assert "falabella" in by_store
    assert "ripley" in by_store
    assert "hiraoka" in by_store

    assert by_store["falabella"]["price"] == 3599.0
    assert by_store["falabella"]["offerUrl"] == (
        "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493"
    )
    assert by_store["ripley"]["price"] == 3599.0
    assert by_store["ripley"]["offerUrl"] == (
        "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p"
    )
    assert by_store["hiraoka"]["price"] == 3899.0
    assert by_store["hiraoka"]["offerUrl"] == (
        "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026"
    )


# ==============================================================================
# 7. PRUEBAS DE QUERY BUILDER EN CASCADA, MULTI-SKU Y UNIVERSAL PRODUCT RESOLVER
# ==============================================================================

def test_build_search_queries_cascade_specific_and_broad():
    """
    Verifica que build_search_queries elimine colores y unidades verbosas, generando:
    1. specific_query: "{marca_o_linea} {modelo_y_chip} {almacenamiento_o_pulgadas}"
    2. broad_model_query: "{marca_o_linea} {modelo_y_chip}"
    """
    q_ipad = build_search_queries(
        "Apple iPad 11 Pulgadas A16 Wi-Fi 128GB Azul",
        {"Almacenamiento": "128GB", "Pantalla": "11 Pulgadas"},
    )
    assert q_ipad == ["iPad A16 128GB", "iPad A16"]

    q_tv = build_search_queries(
        'LG 55" OLED evo AI C6 4K Smart TV con Dolby Atmos 2026',
        {"Pantalla": "OLED evo 55 Pulgadas"},
    )
    assert q_tv == ["LG OLED 55 C6", "LG OLED C6"]

    q_redmi = build_search_queries(
        "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca",
        {"Almacenamiento": "512GB"},
    )
    assert q_redmi == ["Redmi Note 15 Pro 512GB", "Redmi Note 15 Pro"]

    q_tab = build_search_queries(
        "Tablet Samsung Galaxy Tab S10 FE 128GB Gris",
        {"Almacenamiento": "128GB"},
    )
    assert q_tab == ["Galaxy Tab S10 FE 128GB", "Galaxy Tab S10 FE"]


def test_multi_sku_variant_resolution_falabella_and_tottus_ipad_a16():
    """
    Verifica que parse_falabella y parse_tottus resuelvan variantes Multi-SKU
    e inspeccionen attributes.specifications y description cuando:
    - En Falabella el título principal es 'iPad Apple 11 Chip A16 Wi-Fi' (sin '128GB'),
      y '128GB' está en la variante SKU 21014911, en tech_specs y en description.
    - En Tottus el título principal es 'Ipad A16 Wifi 128GB Azul' (sin '11'),
      y '11' está en tech_specs ('Tamaño de la pantalla': '11').
    """
    canonical_ipad = "Apple iPad 11 Pulgadas A16 Wi-Fi 128GB Azul"

    falabella_multi_sku_html = """
    <html><script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "productData": {
            "id": "prod18440041",
            "name": "iPad Apple 11 Chip A16 Wi-Fi",
            "description": "Con 128GB de almacenamiento y pantalla de 11 pulgadas.",
            "attributes": {
              "specifications": [
                {"name": "Capacidad de almacenamiento", "value": "128GB"},
                {"name": "Tamaño de la pantalla", "value": "11"},
                {"name": "Conectividad/conexión", "value": "Wifi"}
              ]
            },
            "variants": [
              {
                "id": "21014999",
                "name": "IPAD A16 WIFI 256GB SLV",
                "prices": [{"type": "cmrPrice", "price": ["2,499"], "crossed": false}],
                "medias": [{"url": "https://media.falabella.com/falabellaPE/21014999_1/public"}]
              },
              {
                "id": "21014911",
                "name": "IPAD A16 WIFI 128GB SLV",
                "prices": [
                  {"type": "cmrPrice", "price": ["1,899"], "crossed": false},
                  {"type": "internetPrice", "price": ["1,999"], "crossed": false},
                  {"type": "normalPrice", "price": ["2,599"], "crossed": true}
                ],
                "medias": [{"url": "https://media.falabella.com/falabellaPE/21014911_1/public"}]
              }
            ]
          }
        }
      }
    }
    </script></html>
    """
    f_url = "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911"
    f_parsed = parse_falabella(falabella_multi_sku_html, f_url, canonical_title=canonical_ipad)
    assert f_parsed is not None
    assert f_parsed["price"] == 1899.0
    assert f_parsed["original_price"] == 2599.0
    assert f_parsed["variant_sku_id"] == "21014911"
    assert f_parsed["offer_url"] == f_url
    assert f_parsed["tech_specs"]["Almacenamiento"] == "128 GB"
    assert f_parsed["tech_specs"]["Pantalla"] == '11"'
    assert match_product_universal(canonical_ipad, f_parsed) is True

    tottus_html = """
    <html><script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "productData": {
            "id": "150930380",
            "name": "Ipad A16 Wifi 128GB Azul",
            "attributes": {
              "specifications": [
                {"name": "Tamaño de la pantalla", "value": "11"},
                {"name": "Capacidad de almacenamiento", "value": "128GB"},
                {"name": "Procesador específico txt", "value": "A16"},
                {"name": "marca", "value": "APPLE"}
              ]
            },
            "variants": [
              {
                "id": "150930381",
                "name": "Ipad A16 Wifi 128GB Azul",
                "prices": [
                  {"type": "internetPrice", "price": ["1,899"], "crossed": false},
                  {"type": "normalPrice", "price": ["2,599"], "crossed": true}
                ],
                "medias": [{"url": "https://media.falabella.com/tottusPE/43620624_1/public"}]
              }
            ]
          }
        }
      }
    }
    </script></html>
    """
    t_url = "https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381"
    t_parsed = parse_tottus(tottus_html, t_url, canonical_title=canonical_ipad)
    assert t_parsed is not None
    assert t_parsed["price"] == 1899.0
    assert t_parsed["original_price"] == 2599.0
    assert t_parsed["tech_specs"]["Pantalla"] == '11"'
    assert t_parsed["tech_specs"]["Almacenamiento"] == "128 GB"
    assert match_product_universal(canonical_ipad, t_parsed) is True


def test_match_product_universal_6_rules_full_corpus():
    """
    Verifica las 6 reglas universales de match_product_universal sobre el corpus completo:
    1. Ignora colores (Plata, Azul, Rosa, Amarillo compiten en la misma ficha).
    2. Coincidencia estricta de modelo/chip y bloqueo de sub-modelos intrusos (iPad Air / iPad Pro / iPad Mini).
    3. Almacenamiento validado en el corpus completo (title, tech_specs o description) y rechazo si declara 256GB/64GB.
    4. Tamaño de pantalla con tolerancia comercial en Tablets (10.9" == 11") y exactitud en TVs (55" != 65").
    5. Conectividad: bloquea iPad Wi-Fi + Cellular / 5G cuando el objetivo es solo Wi-Fi.
    6. Filtro estadístico de cordura de precios (0.55 <= price / median <= 1.65).
    """
    target_ipad = {
        "title": "Apple iPad 11 Pulgadas A16 Wi-Fi 128GB Azul",
        "category": "Tablets",
        "brand": "Apple",
        "tech_specs": {"Almacenamiento": "128GB", "Pantalla": "11 Pulgadas"},
    }

    # Regla 1 + 4: distinto color ('Plata') y redondeo comercial ('10.9"') -> ACEPTADO
    assert match_product_universal(
        target_ipad,
        {
            "title": 'iPad 10.9" (11ma Gen) A16 WiFi 128GB Plata',
            "offer_url": "https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wifi-128gb-plata",
            "tech_specs": {"Marca": "Apple", "Almacenamiento": "128 GB", "Pantalla": '10.9"'},
            "description": "",
        },
    ) is True

    # Regla 2: Bloqueo de sub-modelos intrusos ('iPad Air', 'iPad Pro', 'iPad Mini') -> RECHAZADO
    for intruder_submodel in ("iPad Air 11 A16 128GB Wi-Fi", "iPad Pro 11 A16 128GB Wi-Fi", "iPad Mini A16 128GB Wi-Fi"):
        assert match_product_universal(
            target_ipad,
            {
                "title": intruder_submodel,
                "offer_url": "https://www.falabella.com.pe/falabella-pe/product/123/ipad/123",
                "tech_specs": {"Almacenamiento": "128 GB", "Pantalla": '11"'},
                "description": "",
            },
        ) is False

    # Regla 3: Rechazo cuando el candidato es de 256GB en título o en tech_specs -> RECHAZADO
    assert match_product_universal(
        target_ipad,
        {
            "title": "iPad Apple 11 Chip A16 Wi-Fi",
            "offer_url": "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014999",
            "tech_specs": {"Capacidad de almacenamiento": "256GB", "Tamaño de la pantalla": "11"},
            "description": "Versión de 256GB",
        },
    ) is False

    # Regla 5: Rechazo de versión Wi-Fi + Cellular / 5G cuando el objetivo es solo Wi-Fi -> RECHAZADO
    assert match_product_universal(
        target_ipad,
        {
            "title": 'iPad 11" Chip A16 Wi-Fi + Cellular 5G 128GB Azul',
            "offer_url": "https://hiraoka.com.pe/ipad-11-a16-wifi-cellular-128gb",
            "tech_specs": {"Almacenamiento": "128 GB", "Pantalla": '11"', "Conectividad": "5G"},
            "description": "",
        },
    ) is False

    # Regla 6: Filtro estadístico de cordura de precios (0.55 <= price / median <= 1.65)
    raw_offers = [
        {"store_id": "falabella", "price": 1899.0},
        {"store_id": "tottus", "price": 1899.0},
        {"store_id": "hiraoka", "price": 1949.0},
        {"store_id": "efe", "price": 1979.0},
        {"store_id": "curacao", "price": 129.0},   # Accesorio/funda < 0.55 * mediana
        {"store_id": "ripley", "price": 4599.0},   # Otro modelo caro > 1.65 * mediana
    ]
    sane = filter_offers_by_price_sanity(raw_offers)
    assert [o["store_id"] for o in sane] == ["falabella", "tottus", "hiraoka", "efe"]


@pytest.mark.asyncio
async def test_universal_product_resolver_cascade_fallback_to_broad_query():
    """
    Verifica la regla de oro del buscador en cascada en UniversalProductResolver:
    Si specific_query ('iPad A16 128GB') no devuelve resultados en Falabella (porque el título
    en Falabella es 'iPad Apple 11 Chip A16 Wi-Fi' sin '128GB'), ejecuta inmediatamente
    broad_model_query ('iPad A16') y valida el producto mediante su corpus completo.
    """
    target_ipad = {
        "id": "prod_ipad_11",
        "title": "Apple iPad 11 Pulgadas A16 Wi-Fi 128GB Azul",
        "category": "Tablets",
        "brand": "Apple",
        "tech_specs": {"Almacenamiento": "128GB", "Pantalla": "11 Pulgadas"},
        "store_urls": {},
    }
    queried_urls = []

    async def fake_cascade_scraper(store_id: str, url: str, **kwargs):
        queried_urls.append((store_id, url))
        if store_id == "falabella":
            # specific_query ('iPad+A16+128GB') no devuelve nada porque el título no tiene '128GB'
            if "128GB" in url:
                return None
            # broad_model_query ('iPad+A16') sí encuentra el producto y su ficha tiene 128GB en tech_specs/description
            return {
                "title": "iPad Apple 11 Chip A16 Wi-Fi",
                "price": 1899.0,
                "original_price": 2599.0,
                "offer_url": "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911",
                "tech_specs": {"Marca": "Apple", "Almacenamiento": "128 GB", "Pantalla": '11"'},
                "description": "IPAD A16 WIFI 128GB SLV",
            }
        return None

    resolver = UniversalProductResolver(scrape_fn=fake_cascade_scraper)
    offer = await resolver.resolve_store_offer(
        store_id="falabella",
        target_product=target_ipad,
        direct_url=None,
        enable_cascade_search=True,
    )
    assert offer is not None
    assert offer["store_id"] == "falabella"
    assert offer["price"] == 1899.0
    assert offer["offer_url"] == "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911"
    # Debe haber intentado primero specific_query y luego broad_model_query
    assert len(queried_urls) == 2
    assert "128GB" in queried_urls[0][1]
    assert "128GB" not in queried_urls[1][1]


def test_ipad_11_a16_synchronizes_falabella_tottus_hiraoka_and_efe(client: TestClient):
    """
    Verifica que el Apple iPad 11 Pulgadas A16 Wi-Fi 128GB (prod_ipad_11) sincronice:
    - Falabella: S/ 1,899.00 (https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911)
    - Tottus: S/ 1,899.00 (https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381)
    - Hiraoka: S/ 1,949.00 (https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wifi-128gb-plata)
    - Tiendas Efe: S/ 1,979.00 (https://www.efe.com.pe/ipad-a16-wi-fi-md4e4ll-a-11-128gb-6gb-p26513743.html)
    con bestPrice = 1899.0.
    """
    res = client.get("/api/v1/products/prod_ipad_11")
    assert res.status_code == 200
    ipad = res.json()

    assert ipad["id"] == "prod_ipad_11"
    assert ipad["bestPrice"] == 1899.0
    assert ipad["availableStoresCount"] == 4

    by_store = {sp["storeId"]: sp for sp in ipad["storePrices"]}
    assert set(by_store.keys()) == {"falabella", "tottus", "hiraoka", "efe"}

    assert by_store["falabella"]["price"] == 1899.0
    assert by_store["falabella"]["offerUrl"] == (
        "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911"
    )
    assert by_store["tottus"]["price"] == 1899.0
    assert by_store["tottus"]["offerUrl"] == (
        "https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381"
    )
    assert by_store["hiraoka"]["price"] == 1949.0
    assert by_store["hiraoka"]["offerUrl"] == (
        "https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wifi-128gb-plata"
    )
    assert by_store["efe"]["price"] == 1979.0
    assert by_store["efe"]["offerUrl"] == (
        "https://www.efe.com.pe/ipad-a16-wi-fi-md4e4ll-a-11-128gb-6gb-p26513743.html"
    )


