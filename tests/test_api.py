"""
Suite de Pruebas Automatizadas de FinPrice API
======================================================
Verifica:
1. Endpoints /api/v1/products con contrato camelCase estricto
2. Filtros por categoría, RAM, almacenamiento, procesador y ordenamiento de precios
3. Recálculo dinámico con enabled_stores
4. Retrocompatibilidad de GET /products
5. Seguridad: Autenticación X-API-Key en POST /api/v1/collectors/sync (401/403 vs 202)
6. Diagnóstico y métricas en GET /api/v1/health y GET /
7. Ofertas comunitarias con validación de ubigeo peruano
8. Normalizador de precios y filtros de cordura (sanity check)
9. Resiliencia de Circuit Breaker
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.collectors.base import CircuitBreaker, CircuitState
from app.collectors.normalizer import (
    calculate_discount_percentage,
    clean_pen_price,
    evaluate_historical_min,
    sanity_check_price,
)
from main import app


@pytest.fixture(scope="module")
def client():
    """Cliente de pruebas FastAPI con ciclo de vida (lifespan) activo."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_rate_limit_counters():
    """Reinicia contadores de rate limiting para garantizar aislamiento entre pruebas."""
    from app.core.security import rate_limiter
    rate_limiter.reset()


# ==============================================================================
# 1. PRUEBAS DE ENDPOINTS GENERALES Y SALUD
# ==============================================================================

def test_root_endpoint(client: TestClient):
    """Verifica que GET / responda confirmando que la API está activa."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "FinPrice API está activa en la nube"
    assert data["version"] == "2.0.0"
    assert data["status"] == "healthy"


def test_health_diagnostic_endpoint(client: TestClient):
    """Verifica diagnóstico detallado /api/v1/health."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["totalProducts"] >= 8
    assert data["totalStores"] == 8
    assert data["activeStores"] >= 1
    assert "storesStatus" in data
    # Verificar que las 8 tiendas estén reportadas
    stores = data["storesStatus"]
    for s_id in ["efe", "falabella", "ripley", "curacao", "hiraoka", "tottus", "metro", "wong"]:
        assert s_id in stores


def test_security_headers_present(client: TestClient):
    """Verifica que los middlewares inyecten cabeceras seguras en las respuestas."""
    response = client.get("/")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "max-age=31536000" in response.headers.get("Strict-Transport-Security", "")
    assert "X-Process-Time" in response.headers


# ==============================================================================
# 2. PRUEBAS DEL CONTRATO DE PRODUCTOS (CAMELCASE ESTRICTO)
# ==============================================================================

def test_get_products_camel_case_schema(client: TestClient):
    """
    Verifica que GET /api/v1/products devuelva productos con todos los campos en camelCase
    según el contrato del dominio móvil: bestPrice, storePrices, priceHistory30Days, techSpecs, etc.
    """
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    products = response.json()
    assert len(products) >= 8

    p1 = products[0]
    # Comprobar claves de primer nivel en camelCase
    required_camel_keys = [
        "id",
        "title",
        "category",
        "bestPrice",
        "originalPrice",
        "bestStoreName",
        "discountPercentage",
        "availableStoresCount",
        "imageUrl",
        "description",
        "features",
        "isFavorite",
        "storePrices",
        "techSpecs",
        "isHistoricalMin",
        "priceHistory30Days",
    ]
    for key in required_camel_keys:
        assert key in p1, f"La clave camelCase '{key}' falta en ProductSchema"

    # Verificar StorePriceSchema
    assert len(p1["storePrices"]) > 0
    sp1 = p1["storePrices"][0]
    required_sp_keys = ["storeId", "storeName", "price", "offerUrl", "isBestPrice"]
    for sp_key in required_sp_keys:
        assert sp_key in sp1, f"La clave '{sp_key}' falta en StorePriceSchema"
    assert sp1["offerUrl"].startswith("https://")
    assert sp1["isBestPrice"] is True

    # Verificar PricePointSchema
    assert len(p1["priceHistory30Days"]) > 0
    hp1 = p1["priceHistory30Days"][0]
    assert "dayOffset" in hp1
    assert "dateLabel" in hp1
    assert "price" in hp1


def test_get_product_by_id(client: TestClient):
    """Verifica detalle de un producto específico."""
    response = client.get("/api/v1/products/prod_1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "prod_1"
    assert "Samsung" in data["title"]
    assert len(data["storePrices"]) >= 3
    assert len(data["priceHistory30Days"]) >= 10

    # Producto inexistente debe retornar 404
    not_found_resp = client.get("/api/v1/products/prod_non_existent_999")
    assert not_found_resp.status_code == 404


# ==============================================================================
# 3. PRUEBAS DE FILTROS AVANZADOS Y ORDENAMIENTO
# ==============================================================================

def test_filter_by_category(client: TestClient):
    """Verifica filtro por categoría (Smartphones, Laptops, Tablets, TVs)."""
    response = client.get("/api/v1/products?category=Smartphones")
    assert response.status_code == 200
    products = response.json()
    assert len(products) > 0
    for p in products:
        assert p["category"] == "Smartphones"


def test_filter_by_brand(client: TestClient):
    """Verifica filtro por marca (Apple, Samsung, etc.)."""
    response = client.get("/api/v1/products?brand=Apple")
    assert response.status_code == 200
    products = response.json()
    assert len(products) > 0
    for p in products:
        assert "apple" in p["title"].lower()


def test_filter_by_ram(client: TestClient):
    """Verifica filtro por memoria RAM (ej. 16GB)."""
    response = client.get("/api/v1/products?ram=16GB")
    assert response.status_code == 200
    products = response.json()
    assert len(products) > 0
    for p in products:
        specs_ram = p["techSpecs"].get("Memoria RAM", "").lower()
        title_ram = p["title"].lower()
        assert "16gb" in specs_ram or "16gb" in title_ram


def test_filter_by_storage(client: TestClient):
    """Verifica filtro por almacenamiento (ej. 512GB)."""
    response = client.get("/api/v1/products?storage=512GB")
    assert response.status_code == 200
    products = response.json()
    assert len(products) > 0
    for p in products:
        specs_storage = p["techSpecs"].get("Almacenamiento", "").lower()
        title_storage = p["title"].lower()
        assert "512gb" in specs_storage or "512gb" in title_storage


def test_filter_by_sort_order(client: TestClient):
    """Verifica ordenamiento por precio LOW_TO_HIGH y HIGH_TO_LOW."""
    # Ascendente
    res_asc = client.get("/api/v1/products?sort_order=LOW_TO_HIGH")
    assert res_asc.status_code == 200
    prods_asc = res_asc.json()
    prices_asc = [p["bestPrice"] for p in prods_asc]
    assert prices_asc == sorted(prices_asc)

    # Descendente
    res_desc = client.get("/api/v1/products?sort_order=HIGH_TO_LOW")
    assert res_desc.status_code == 200
    prods_desc = res_desc.json()
    prices_desc = [p["bestPrice"] for p in prods_desc]
    assert prices_desc == sorted(prices_desc, reverse=True)


def test_filter_by_enabled_stores_dynamic_recalc(client: TestClient):
    """
    Verifica que al enviar enabled_stores, se filtren las ofertas por tienda
    y se recalculen dinámicamente bestPrice y bestStoreName considerando solo esas tiendas.
    """
    response = client.get("/api/v1/products?enabled_stores=efe,hiraoka")
    assert response.status_code == 200
    products = response.json()
    assert len(products) > 0
    for p in products:
        # Cada tienda ofrecida debe ser 'efe' o 'hiraoka'
        for sp in p["storePrices"]:
            assert sp["storeId"] in {"efe", "hiraoka"}
        # bestStoreName debe coincidir con alguna de ellas
        assert p["bestStoreName"] in {"Tiendas Efe", "Hiraoka"}


# ==============================================================================
# 4. PRUEBAS DE TIENDAS Y OFERTAS COMUNITARIAS
# ==============================================================================

def test_get_stores_endpoint(client: TestClient):
    """Verifica GET /api/v1/stores con las 8 tiendas oficiales."""
    response = client.get("/api/v1/stores")
    assert response.status_code == 200
    stores = response.json()
    assert len(stores) == 8
    store_ids = [s["id"] for s in stores]
    assert "efe" in store_ids
    assert "falabella" in store_ids
    assert "ripley" in store_ids
    assert "curacao" in store_ids
    assert "hiraoka" in store_ids
    assert "tottus" in store_ids
    assert "metro" in store_ids
    assert "wong" in store_ids


def test_community_offers_flow(client: TestClient):
    """Verifica listado y creación de ofertas físicas con ubigeo peruano."""
    # Listar ofertas
    res_get = client.get("/api/v1/community-offers")
    assert res_get.status_code == 200
    offers = res_get.json()
    assert len(offers) >= 3

    # Crear nueva oferta con departamento válido (Lambayeque)
    new_offer_payload = {
        "productId": "prod_1",
        "physicalStoreName": "Hiraoka Independencia",
        "department": "Lima",
        "province": "Lima",
        "district": "Independencia",
        "priceFound": 4350.00,
        "photoUri": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600",
        "comment": "Precio en vitrina de entrada con boleta",
        "authorName": "Tester Antigravity",
    }
    res_post = client.post("/api/v1/community-offers", json=new_offer_payload)
    assert res_post.status_code == 201
    created = res_post.json()
    assert created["department"] == "Lima"
    assert created["priceFound"] == 4350.00
    assert created["productId"] == "prod_1"

    # Intentar crear con departamento inválido debe ser rechazado (422)
    invalid_payload = {
        "productId": "prod_1",
        "physicalStoreName": "Tienda X",
        "department": "DepartamentoInexistente",
        "province": "X",
        "district": "Y",
        "priceFound": 1000.0,
    }
    res_invalid = client.post("/api/v1/community-offers", json=invalid_payload)
    assert res_invalid.status_code == 422


# ==============================================================================
# 5. RETROCOMPATIBILIDAD ESTRICTA (GET /products)
# ==============================================================================

def test_legacy_get_products(client: TestClient):
    """Verifica que el endpoint legado GET /products mantenga el formato original."""
    response = client.get("/products")
    assert response.status_code == 200
    products = response.json()
    assert len(products) >= 8

    p1 = products[0]
    assert "id" in p1 and isinstance(p1["id"], int)
    assert "name" in p1
    assert "category" in p1
    assert "lowest_price" in p1
    assert "best_store" in p1
    assert "offers" in p1
    assert len(p1["offers"]) > 0

    first_offer = p1["offers"][0]
    assert "store_name" in first_offer
    assert "price" in first_offer
    assert "currency" in first_offer
    assert first_offer["currency"] == "PEN"
    assert "product_url" in first_offer


# ==============================================================================
# 6. SEGURIDAD Y SINCRONIZACIÓN ADMINISTRATIVA (X-API-Key)
# ==============================================================================

def test_admin_sync_authentication(client: TestClient):
    """
    Verifica que POST /api/v1/collectors/sync:
    - Rechace llamadas sin X-API-Key (HTTP 401)
    - Rechace llamadas con X-API-Key inválida (HTTP 403)
    - Acepte llamadas con la clave correcta (HTTP 202 Accepted)
    """
    from unittest.mock import AsyncMock, patch

    # 1. Sin cabecera
    res_missing = client.post("/api/v1/collectors/sync")
    assert res_missing.status_code == 401

    # 2. Con clave errónea
    res_invalid = client.post(
        "/api/v1/collectors/sync", headers={"X-API-Key": "clave_incorrecta_hack"}
    )
    assert res_invalid.status_code == 403

    # 3. Con clave correcta (mockeamos sync_all_stores para ejecución rápida e independiente de red)
    with patch("app.collectors.registry.collector_registry.sync_all_stores", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = {"status": "success", "updated_offers": 0}
        res_valid = client.post(
            "/api/v1/collectors/sync",
            headers={"X-API-Key": settings.FINPRICE_ADMIN_API_KEY},
        )
        assert res_valid.status_code == 202
        data = res_valid.json()
        assert data["status"] == "accepted"
        assert "triggeredAt" in data


# ==============================================================================
# 7. PRUEBAS UNITARIAS: NORMALIZADOR Y SANITY CHECK
# ==============================================================================

def test_clean_pen_price():
    """Verifica normalización de precios en formatos peruanos comunes."""
    assert clean_pen_price("S/ 1,450.00") == 1450.00
    assert clean_pen_price("S/. 1,450.50") == 1450.50
    assert clean_pen_price("1450.99") == 1450.99
    assert clean_pen_price("S/ 3.899,00") == 3899.00
    assert clean_pen_price(2999) == 2999.00
    assert clean_pen_price(None) is None
    assert clean_pen_price("") is None
    assert clean_pen_price("Gratis") is None


def test_sanity_check_price():
    """Verifica detección de anomalías y caídas irreales > 90%."""
    # Precios normales
    assert sanity_check_price(1500.0, original_price=2000.0) is True

    # Precios <= 0 o menores al umbral de accesorios (< S/ 20)
    assert sanity_check_price(0.0) is False
    assert sanity_check_price(15.0) is False

    # Caída > 90% (accesorio parseado por error como laptop)
    assert sanity_check_price(150.0, original_price=5000.0) is False

    # Subida absurda > 3x
    assert sanity_check_price(18000.0, original_price=4000.0) is False


def test_calculate_discount_percentage():
    assert calculate_discount_percentage(5000.0, 4000.0) == 20
    assert calculate_discount_percentage(1000.0, 1000.0) == 0
    assert calculate_discount_percentage(1000.0, 1200.0) == 0


def test_evaluate_historical_min():
    is_min, eff_price = evaluate_historical_min(3800.0, 4000.0)
    assert is_min is True
    assert eff_price == 3800.0

    is_min2, eff_price2 = evaluate_historical_min(4200.0, 4000.0)
    assert is_min2 is False
    assert eff_price2 == 4000.0


# ==============================================================================
# 8. PRUEBAS UNITARIAS: CIRCUIT BREAKER
# ==============================================================================

def test_circuit_breaker_lifecycle():
    """Verifica transición de estados: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    cb = CircuitBreaker(store_id="test_store", failure_threshold=2, recovery_timeout=1)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # Fallo 1
    cb.record_failure(Exception("Timeout 1"))
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    # Fallo 2 -> debe abrirse el circuito
    cb.record_failure(Exception("Timeout 2"))
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # Simular paso del tiempo para recovery timeout
    import time
    cb.last_failure_time = time.time() - 2.0
    # Ahora debe permitir una ejecución y transicionar a HALF_OPEN
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Si la prueba tiene éxito, se restaura a CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
