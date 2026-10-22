# FinPrice Cloud API 🇵🇪

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.9-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.13-E92063.svg)](https://docs.pydantic.dev/)
[![SQLAlchemy Async](https://img.shields.io/badge/SQLAlchemy-Async%202.0-D71F00.svg)](https://www.sqlalchemy.org/)
[![Docker](https://img.shields.io/badge/Docker-Multi--stage%20Non--root-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Pytest-13%20passed%20(100%25)-brightgreen.svg)]()
[![Zero-Mock](https://img.shields.io/badge/Policy-Zero--Mock%20100%25%20Real-success.svg)]()

**FinPrice Cloud API** es un microservicio en la nube 100% autónomo y resiliente encargado de recolectar en vivo, normalizar, almacenar en caché y servir precios de retail e-commerce del Perú en moneda local (**Soles - `PEN`**) directamente desde las plataformas oficiales.

---

## 🚫 Política Estricta Zero-Mock (Cero Simulación)

1. **Cero Datos Falsos ni Precios Inventados**:
   - Prohibido el uso de URLs dummy (`https://ejemplo.com/...`), imágenes genéricas de bancos de fotos o generadores de números aleatorios para el historial.
   - Cada precio, imagen oficial, descuento y especificación técnica proviene de la extracción en vivo de la tienda.
2. **Tiendas Reales Verificadas por Producto**:
   - Si un producto solo se vende en 4 tiendas (por ejemplo: Falabella, Tiendas Efe, La Curacao e Hiraoka) y no se comercializa en otras, la lista `storePrices` contiene **únicamente las 4 tiendas reales** (`availableStoresCount = 4`). No se inyectan tiendas vacías ni enlaces rotos.
3. **Historial de Precios Acumulativo Real**:
   - La serie `priceHistory30Days` y el `historicalMinPrice` se construyen **exclusivamente con los snapshots reales guardados en la base de datos** (`finprice_real.db` / PostgreSQL) cada vez que el recolector observa un precio real, iniciando con `"Hoy"` y acumulando el historial de mercado día a día.
4. **Ofertas Comunitarias Reales**:
   - La tabla `community_offers` inicia limpia (0 registros falsos) y solo persiste reportes de usuarios enviados a través de `POST /api/v1/community-offers` con validación de departamentos oficiales del Perú.

---

## 🏛️ Arquitectura Modular del Repositorio

```text
FinPrice-api/
├── main.py                        # Entrypoint FastAPI (lifespan con scraping inicial real, middlewares, routers)
├── requirements.txt               # fastapi, uvicorn, pydantic, pydantic-settings, httpx[http2], beautifulsoup4, lxml, sqlalchemy, aiosqlite, slowapi
├── .env.example                   # Variables de entorno (FINPRICE_ADMIN_API_KEY, ALLOWED_ORIGINS, COLLECTION_INTERVAL_MINUTES)
├── Dockerfile                     # Imagen ligera Python 3.11-slim con usuario non-root
├── pytest.ini                     # Configuración de ejecución de pytest
├── README.md                      # Documentación completa de arquitectura y despliegue
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── config.py              # Configuración centralizada con pydantic-settings
│   │   ├── security.py            # Validación X-API-Key (secrets.compare_digest), Rate Limiting, SSRF allowlist
│   │   └── database.py            # Motor SQLAlchemy Async (SQLite persistente finprice_real.db / PostgreSQL)
│   ├── models/
│   │   ├── entities.py            # Tablas reales: ProductEntity, StoreOfferEntity, PriceHistoryEntity, CommunityOfferEntity
│   │   └── schemas.py             # Esquemas Pydantic v2 en camelCase + retrocompatibilidad GET /products
│   ├── collectors/
│   │   ├── catalog_urls.py        # Registro oficial de URLs reales verificadas por producto y tienda
│   │   ├── http_client.py         # Cliente httpx.AsyncClient con headers reales de navegador, HTTP/2, retries y semáforo
│   │   ├── parsers/
│   │   │   ├── falabella.py       # Extractor real para falabella.com.pe (__NEXT_DATA__ + JSON-LD)
│   │   │   ├── conectaretail.py   # Extractor real para efe.com.pe y lacuracao.pe (Magento 2 JSON-LD + data-price-amount)
│   │   │   ├── ripley.py          # Extractor real para simple.ripley.com.pe (__NEXT_DATA__ detailProps + JSON-LD)
│   │   │   └── hiraoka.py         # Extractor real para hiraoka.com.pe (Magento 2 JSON-LD + meta product:price:amount)
│   │   └── orchestrator.py        # Ejecuta scraping concurrente, persiste en DB y actualiza historial real
│   └── api/
│       └── v1/
│           ├── router.py          # Router central /api/v1 y diagnóstico /health
│           ├── products.py        # GET /api/v1/products y GET /api/v1/products/{product_id}
│           ├── stores.py          # GET /api/v1/stores
│           ├── community.py       # GET y POST /api/v1/community-offers
│           └── sync.py            # POST /api/v1/collectors/sync (disparo manual con X-API-Key)
└── tests/
    └── test_real_collectors.py    # Tests de extracción real, validación de URLs y contrato JSON
```

---

## 🏪 Retailers Peruanos Soportados y Extractores Reales

| Retailer | Dominio Oficial | Extractor Específico | Estrategia de Extracción Real |
| :--- | :--- | :--- | :--- |
| **Falabella CMR** | `falabella.com.pe` | [`app/collectors/parsers/falabella.py`](file:///Users/juniorsampicordova/FinPrice-api/app/collectors/parsers/falabella.py) | `__NEXT_DATA__` (`productData.variants[0].prices`), precios CMR e imágenes en `media.falabella.com`. |
| **Tiendas Efe** | `efe.com.pe` | [`app/collectors/parsers/conectaretail.py`](file:///Users/juniorsampicordova/FinPrice-api/app/collectors/parsers/conectaretail.py) | Magento 2 `[data-price-amount]`, `.price-wrapper .price`, JSON-LD `Product` y `og:image`. |
| **La Curacao** | `lacuracao.pe` | [`app/collectors/parsers/conectaretail.py`](file:///Users/juniorsampicordova/FinPrice-api/app/collectors/parsers/conectaretail.py) | Magento 2 Conecta Retail `[data-price-amount]`, precio de oferta y precio de lista tachado. |
| **Hiraoka** | `hiraoka.com.pe` | [`app/collectors/parsers/hiraoka.py`](file:///Users/juniorsampicordova/FinPrice-api/app/collectors/parsers/hiraoka.py) | Magento 2 JSON-LD `SalePrice` vs `ListPrice`, `meta[property="product:price:amount"]` e imagen oficial. |
| **Ripley** | `simple.ripley.com.pe` | [`app/collectors/parsers/ripley.py`](file:///Users/juniorsampicordova/FinPrice-api/app/collectors/parsers/ripley.py) | `__NEXT_DATA__` (`detailProps.data.product.parentpricestock.price`) extrayendo precio Ripley, internet y lista. |

---

## ⚡ Rendimiento en Lectura (< 50ms) y Recálculo Dinámico

- **Caché en Memoria**: Mantiene en memoria las entidades de catálogo con un TTL de 60 segundos (`CACHE_TTL_SECONDS=60`).
- **Filtrado Directo en CPU**: Búsqueda por texto, categoría, marca, RAM, procesador, almacenamiento y resolución ejecutadas directamente en estructuras en memoria sin llamadas externas.
- **Recálculo por Tiendas Habilitadas (`enabled_stores`)**: Al enviar `enabled_stores=efe,hiraoka`, la API filtra las tiendas y recalcula dinámicamente `bestPrice`, `bestStoreName`, `discountPercentage` y `isBestPrice` en < 2ms.
- **Cabeceras de Control**: Emite `Cache-Control: public, max-age=60` y la latencia calculada en `X-Process-Time`.

---

## 🔐 Seguridad y Blindaje para Producción

- **Protección de Sincronización Manual**: `POST /api/v1/collectors/sync` exige la cabecera `X-API-Key`, validada con `secrets.compare_digest` para evitar ataques de temporización.
- **Rate Limiting Inteligente por IP**: 60 peticiones/minuto en lectura y 5 peticiones/minuto en escritura/sincronización con respuesta HTTP 429 y cabecera `Retry-After`.
- **Prevención de SSRF**: Allowlist de dominios retail peruanos autorizados y bloqueo estricto de esquemas no seguros (`http://`), localhost, IPs privadas (`127.0.0.1`, `10.x.x.x`, `192.168.x.x`) y metadatos de cloud (`169.254.169.254`).
- **Cabeceras OWASP**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
- **Contenedor Seguro**: Ejecución con usuario non-root (`UID 10001: finprice`) sobre imagen base `python:3.11-slim`.

---

## ⚙️ Variables de Entorno

| Variable | Tipo | Valor por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `str` | `development` | Modo de ejecución (`development` o `production`). |
| `HOST` | `str` | `0.0.0.0` | IP de escucha del servidor ASGI. |
| `PORT` | `int` | `8000` | Puerto TCP. |
| `FINPRICE_ADMIN_API_KEY` | `str` | `finprice_secret_admin_key_2026` | Clave secreta para disparar la recolección manual. |
| `ALLOWED_ORIGINS` | `str` | `*` | Orígenes CORS autorizados. |
| `DATABASE_URL` | `str` | `sqlite+aiosqlite:///./finprice_real.db` | Conexión SQLAlchemy Async (SQLite real o PostgreSQL). |
| `CACHE_TTL_SECONDS` | `int` | `60` | Tiempo de vida de la caché en memoria de productos. |
| `COLLECTION_INTERVAL_MINUTES` | `int` | `360` | Intervalo del scraper automático en background (6h). |
| `COLLECTOR_MAX_CONCURRENCY` | `int` | `4` | Semáforo de conexiones salientes simultáneas. |

---

## 🚀 Despliegue en la Nube

### Opción A: Render / Railway / Fly.io

1. Conecta el repositorio en el panel cloud de **Render** o **Railway**.
2. Tipo de servicio: **Web Service (Python o Dockerfile)**.
3. Define las variables de entorno en el panel:
   - `ENVIRONMENT=production`
   - `FINPRICE_ADMIN_API_KEY=tu_clave_secreta_super_segura`
4. Comando de inicio:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

### Opción B: Google Cloud Run

```bash
gcloud builds submit --tag gcr.io/TU-PROYECTO/finprice-api:latest
gcloud run deploy finprice-api \
  --image gcr.io/TU-PROYECTO/finprice-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars ENVIRONMENT=production,FINPRICE_ADMIN_API_KEY=tu_clave_secreta \
  --memory 512Mi --cpu 1
```

### Opción C: Docker Multi-Stage Local

```bash
docker build -t finprice-api:latest .
docker run -d -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e FINPRICE_ADMIN_API_KEY=tu_clave \
  --name finprice-container finprice-api:latest
```

---

## 🧪 Pruebas Automatizadas

La suite incluye pruebas de extractores reales, cumplimiento de la política Zero-Mock, contratos camelCase, filtros de hardware y una prueba de extracción en vivo contra servidores peruanos:

```bash
# Activar entorno virtual
source .venv/bin/activate

# Ejecutar suite de pruebas
pytest tests/test_real_collectors.py -v
```

Salida esperada:
```text
tests/test_real_collectors.py::test_parse_falabella_next_data PASSED     [  7%]
tests/test_real_collectors.py::test_parse_conectaretail_magento2 PASSED  [ 15%]
tests/test_real_collectors.py::test_parse_hiraoka_json_ld PASSED         [ 23%]
tests/test_real_collectors.py::test_parse_ripley_detail_props PASSED     [ 30%]
tests/test_real_collectors.py::test_catalog_urls_strict_zero_mock_policy PASSED [ 38%]
tests/test_real_collectors.py::test_root_and_health PASSED               [ 46%]
tests/test_real_collectors.py::test_products_camel_case_contract PASSED  [ 53%]
tests/test_real_collectors.py::test_hardware_filters_and_sorting PASSED  [ 61%]
tests/test_real_collectors.py::test_enabled_stores_dynamic_recalc PASSED [ 69%]
tests/test_real_collectors.py::test_community_offers_flow PASSED         [ 76%]
tests/test_real_collectors.py::test_admin_sync_security PASSED           [ 84%]
tests/test_real_collectors.py::test_legacy_get_products PASSED           [ 92%]
tests/test_real_collectors.py::test_live_network_extraction_hiraoka PASSED [100%]

============================== 13 passed in 0.43s ==============================
```

---

## 📡 Ejemplos cURL de Verificación

### 1. Diagnóstico de Salud
```bash
curl -X GET "http://localhost:8000/api/v1/health"
```

### 2. Catálogo General (Ordenado de menor a mayor precio)
```bash
curl -X GET "http://localhost:8000/api/v1/products?sort_order=LOW_TO_HIGH"
```

### 3. Filtro por Hardware (RAM y Almacenamiento)
```bash
curl -X GET "http://localhost:8000/api/v1/products?ram=12GB&storage=512GB"
```

### 4. Recálculo Dinámico por Tiendas Habilitadas
```bash
curl -X GET "http://localhost:8000/api/v1/products?enabled_stores=efe,hiraoka"
```

### 5. Detalle de Producto por ID
```bash
curl -X GET "http://localhost:8000/api/v1/products/prod_samsung_s25_ultra"
```

### 6. Listado de Tiendas Oficiales
```bash
curl -X GET "http://localhost:8000/api/v1/stores"
```

### 7. Registro de Oferta Física Comunitaria (con Ubigeo Perú)
```bash
curl -X POST "http://localhost:8000/api/v1/community-offers" \
  -H "Content-Type: application/json" \
  -d '{
    "productId": "prod_samsung_s25_ultra",
    "physicalStoreName": "Tiendas Efe Chiclayo Centro",
    "department": "Lambayeque",
    "province": "Chiclayo",
    "district": "Chiclayo",
    "priceFound": 3699.00,
    "comment": "Precio exclusivo en vitrina con boleta",
    "authorName": "Carlos M."
  }'
```

### 8. Disparo Manual de Sincronización en Vivo (Protegido)
```bash
curl -X POST "http://localhost:8000/api/v1/collectors/sync" \
  -H "X-API-Key: finprice_secret_admin_key_2026"
```

### 9. Endpoint Legado (Retrocompatibilidad /products)
```bash
curl -X GET "http://localhost:8000/products?search=Samsung"
```

---

## 📄 Licencia
Software bajo licencia MIT. Diseñado para scraping ético, seguro y de alta fidelidad para el ecosistema retail de Perú.
