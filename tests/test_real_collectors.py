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
from app.collectors.orchestrator import orchestrator
from app.collectors.parsers.conectaretail import parse_conectaretail
from app.collectors.parsers.falabella import parse_falabella
from app.collectors.parsers.hiraoka import parse_hiraoka
from app.collectors.parsers.ripley import parse_ripley
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
        if "falabella" in url:
            return """
            <html><script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"productData":{"name":"__TITLE__","variants":[{"prices":[{"type":"cmrPrice","price":["3,499.00"],"crossed":false},{"type":"normalPrice","price":["5,499.00"],"crossed":true}],"medias":[{"url":"https://media.falabella.com/falabellaPE/prod1/image.jpg"}]}]}}}}
            </script></html>
            """.replace("__TITLE__", matched_title)
        elif "efe" in url or "curacao" in url:
            return """
            <html><head><meta property="og:image" content="https://www.efe.com.pe/media/catalog/product/prod1.jpg" /></head>
            <body>
              <div class="product-info-main">
                <h1 class="page-title"><span data-ui-id="page-title-wrapper">__TITLE__</span></h1>
                <span class="price-wrapper" data-price-type="finalPrice" data-price-amount="1899.00"><span class="price">S/ 1,899.00</span></span>
              </div>
            </body></html>
            """.replace("__TITLE__", matched_title)
        elif "hiraoka" in url:
            return """
            <html><body>
              <div class="product-info-main">
                <h1 class="page-title"><span data-ui-id="page-title-wrapper">__TITLE__</span></h1>
              </div>
              <script type="application/ld+json">
              {"@type":"Product","name":"__TITLE__","image":"https://hiraoka.com.pe/pub/media/catalog/product/img.jpg","offers":[{"@type":"Offer","price":"1829.00","priceSpecification":{"priceType":"https://schema.org/SalePrice","price":"1829.00"}}]}
              </script>
            </body></html>
            """.replace("__TITLE__", matched_title)
        elif "ripley" in url:
            return """
            <html><script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"detailProps":{"data":{"product":{"name":"__TITLE__","images":["https://rimage.ripley.com.pe/img.jpg"],"parentpricestock":{"price":{"ripley":{"valueNumber":3399},"master":{"valueNumber":5399}}}}}}}}}
            </script></html>
            """.replace("__TITLE__", matched_title)
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

    with patch("app.collectors.orchestrator.fetch_page", side_effect=mock_fetch):
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
        "efe.com.pe",
        "lacuracao.pe",
        "hiraoka.com.pe",
        "simple.ripley.com.pe",
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
        ram_spec = p["techSpecs"].get("Memoria RAM", "").lower()
        title_ram = p["title"].lower()
        assert "12gb" in ram_spec or "12gb" in title_ram

    res_sort = client.get("/api/v1/products?sort_order=LOW_TO_HIGH")
    assert res_sort.status_code == 200
    sorted_prices = [p["bestPrice"] for p in res_sort.json()]
    assert sorted_prices == sorted(sorted_prices)


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
