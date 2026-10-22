"""
Suite de Pruebas Automatizadas de FinPrice API Real & Zero-Mock
===============================================================
Verifica:
1. Extractores reales por retailer (Falabella, Conecta Retail / Efe / Curacao, Hiraoka, Ripley)
2. Regla Zero-Mock: ausencia de URLs inventadas, dominios falsos o imágenes genéricas
3. Contrato de datos en camelCase estricto (bestPrice, storePrices, priceHistory30Days, techSpecs)
4. Filtros avanzados de hardware (RAM, Almacenamiento, Categoría, enabled_stores)
5. Seguridad: Autenticación X-API-Key en POST /api/v1/collectors/sync (401, 403 vs 202)
6. Diagnóstico y métricas en GET /api/v1/health
7. Ofertas comunitarias persistidas con validación de ubigeo peruano
8. Retrocompatibilidad de GET /products
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.collectors.catalog_urls import CATALOG_PRODUCTS, PERU_DEPARTMENTS, STORES_INFO
from app.collectors.parsers.conectaretail import parse_conectaretail
from app.collectors.parsers.falabella import parse_falabella
from app.collectors.parsers.hiraoka import parse_hiraoka
from app.collectors.parsers.ripley import parse_ripley
from main import app


@pytest.fixture(scope="module")
def client():
    """Cliente de pruebas con lifespan activo (inicializa tablas y orquestador)."""
    def mock_fetch(url, *args, **kwargs):
        if "falabella" in url:
            return """
            <html><script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"productData":{"variants":[{"prices":[{"type":"cmrPrice","price":["3,499.00"],"crossed":false},{"type":"normalPrice","price":["5,499.00"],"crossed":true}],"medias":[{"url":"https://media.falabella.com/falabellaPE/prod1/image.jpg"}]}]}}}}
            </script></html>
            """
        elif "efe" in url or "curacao" in url:
            return """
            <html><head><meta property="og:image" content="https://www.efe.com.pe/media/catalog/product/prod1.jpg" /></head>
            <body><span class="price-wrapper" data-price-amount="3799.00"><span class="price">S/ 3,799.00</span></span></body></html>
            """
        elif "hiraoka" in url:
            return """
            <html><script type="application/ld+json">
            {"@type":"Product","name":"Celular Hiraoka","image":"https://hiraoka.com.pe/pub/media/catalog/product/img.jpg","offers":[{"@type":"Offer","price":"4499.00","priceSpecification":{"priceType":"https://schema.org/SalePrice","price":"4499.00"}}]}
            </script></html>
            """
        elif "ripley" in url:
            return """
            <html><script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"detailProps":{"data":{"product":{"name":"IPHONE 16","images":["https://rimage.ripley.com.pe/img.jpg"],"parentpricestock":{"price":{"ripley":{"valueNumber":3399},"master":{"valueNumber":5399}}}}}}}}}
            </script></html>
            """
        return None

    with patch("app.collectors.orchestrator.fetch_page", side_effect=mock_fetch):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from app.core.security import rate_limiter
    rate_limiter.reset()


# ==============================================================================
# 1. PRUEBAS DE EXTRACTORES REALES (PARSERS)
# ==============================================================================

def test_parse_falabella_next_data():
    """Verifica extracción real desde __NEXT_DATA__ de Falabella."""
    sample_html = """
    <html>
    <script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "productData": {
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
      <div class="price-box">
        <span class="price-container">
          <span class="price-wrapper" data-price-amount="3799.00">
            <span class="price">S/ 3,799.00</span>
          </span>
        </span>
        <span class="old-price">
          <span class="price-wrapper" data-price-amount="5299.00">
            <span class="price">S/ 5,299.00</span>
          </span>
        </span>
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
    assert res["price"] == 3399.00  # Mejor precio con Tarjeta Ripley
    assert res["original_price"] == 5399.00
    assert "rimage.ripley.com.pe" in res["image_url"]


# ==============================================================================
# 2. VERIFICACIÓN ZERO-MOCK EN EL CATÁLOGO OFICIAL
# ==============================================================================

def test_catalog_urls_strict_zero_mock_policy():
    """
    Verifica que el catálogo oficial cumpla con la regla de oro:
    - 0 URLs falsas o 'ejemplo.com'
    - Solo retailers peruanos reales
    - Cada producto tiene solo tiendas verificadas reales (no links vacíos)
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
            # Dominio válido
            matched = any(domain in url for domain in allowed_domains)
            assert matched, f"URL con dominio no autorizado: {url}"


# ==============================================================================
# 3. ENDPOINTS Y CONTRATO DE DATOS (CAMELCASE ESTRICTO)
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

    # availableStoresCount debe ser igual al len(storePrices) real
    assert p["availableStoresCount"] == len(p["storePrices"])

    # storePrices ordenados por precio ascendente
    prices = [sp["price"] for sp in p["storePrices"]]
    assert prices == sorted(prices)
    assert p["storePrices"][0]["isBestPrice"] is True


def test_hardware_filters_and_sorting(client: TestClient):
    """Verifica filtros por categoría, RAM, almacenamiento y ordenamiento."""
    # Filtro por categoría
    res_cat = client.get("/api/v1/products?category=Smartphones")
    assert res_cat.status_code == 200
    for p in res_cat.json():
        assert p["category"] == "Smartphones"

    # Filtro por RAM
    res_ram = client.get("/api/v1/products?ram=12GB")
    assert res_ram.status_code == 200
    for p in res_ram.json():
        ram_spec = p["techSpecs"].get("Memoria RAM", "").lower()
        title_ram = p["title"].lower()
        assert "12gb" in ram_spec or "12gb" in title_ram

    # Ordenamiento LOW_TO_HIGH
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
    # Obtener el primer producto disponible
    prods_res = client.get("/api/v1/products")
    first_prod_id = prods_res.json()[0]["id"]

    # Crear oferta comunitaria
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

    # Rechazo ante departamento inválido
    invalid_payload = offer_payload.copy()
    invalid_payload["department"] = "ProvinciaInventada"
    res_err = client.post("/api/v1/community-offers", json=invalid_payload)
    assert res_err.status_code == 422


def test_admin_sync_security(client: TestClient):
    """Verifica protección estricta con X-API-Key en POST /api/v1/collectors/sync."""
    # Sin clave -> 401
    res_no_key = client.post("/api/v1/collectors/sync")
    assert res_no_key.status_code == 401

    # Clave incorrecta -> 403
    res_bad_key = client.post(
        "/api/v1/collectors/sync", headers={"X-API-Key": "bad_key_attempt"}
    )
    assert res_bad_key.status_code == 403

    # Clave correcta con mock de background para prueba rápida
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
# 4. PRUEBA EN VIVO CONTRA RETAILER REAL PERUANO
# ==============================================================================

@pytest.mark.asyncio
async def test_live_network_extraction_hiraoka():
    """
    Realiza una extracción en vivo directamente contra hiraoka.com.pe,
    comprobando que el parser extraiga el precio real y la imagen oficial sin simulación.
    """
    from app.collectors.http_client import fetch_page
    url = "https://hiraoka.com.pe/celular-samsung-galaxy-s26-6-3-512gb-12gb-ram-black"
    html = await fetch_page(url)
    assert html is not None, "El servidor de Hiraoka no respondió o hubo timeout de red"
    data = parse_hiraoka(html, url)
    assert data is not None, "No se pudo extraer la información real de Hiraoka"
    assert data["price"] > 1000.0, f"Precio extraído no razonable: {data['price']}"
    assert data["offer_url"] == url
    assert "hiraoka.com.pe" in data["image_url"]
