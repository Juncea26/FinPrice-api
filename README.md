# FinPrice Cloud API 🇵🇪

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.9-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.13-E92063.svg)](https://docs.pydantic.dev/)
[![Docker](https://img.shields.io/badge/Docker-Multi--stage%20Non--root-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Pytest-20%20passed%20(100%25)-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

**FinPrice Cloud API** es un microservicio autónomo y resiliente de alto rendimiento diseñado para recolectar, normalizar, almacenar en caché y servir precios de tecnología y retail en el Perú en moneda local (**Soles - `PEN`**).

---

## 🛡️ Principio de Aislamiento Estricto (Standalone Cloud Constraint)

1. **Aislamiento 100% Autónomo**: La API opera como un backend cloud independiente. No depende de Android Studio, ni contiene código acoplado a la aplicación móvil.
2. **Resiliencia Anti-Caídas con Circuit Breaker**: Si un conector de tienda externa (Falabella, Ripley, etc.) sufre bloqueo anti-bot, timeout o cambios de maquetación HTML, la API **nunca** devuelve HTTP 500 ni interrumpe su servicio; el recolector registra el incidente en logs JSON estructurados, activa un **Circuit Breaker** por tienda y sirve la última instantánea válida en base de datos.
3. **Arranque Inmediato con Catálogo Semilla**: Al iniciar en frío, si la base de datos está vacía, se inicializa automáticamente con el catálogo semilla oficial compuesto por 8 productos líderes, 8 retailers peruanos, historial a 30 días, especificaciones técnicas y ofertas comunitarias.

---

## 🏛️ Arquitectura Modular del Repositorio

```text
FinPrice-api/
├── main.py                      # Entrypoint FastAPI (lifespan, middlewares, routers)
├── requirements.txt             # Dependencias fijas y seguras (FastAPI, HTTPX, SQLAlchemy, etc.)
├── .env.example                 # Plantilla de variables de entorno (sin secretos reales)
├── Dockerfile                   # Contenedor optimizado multi-stage con usuario non-root
├── pytest.ini                   # Configuración del motor de pruebas
├── README.md                    # Documentación exhaustiva de arquitectura y despliegue
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── config.py            # Configuración pydantic-settings (CORS, Keys, TTL, DB)
│   │   ├── security.py          # Validación X-API-Key, Rate Limiter por IP y sanitización
│   │   └── logging.py           # Logs estructurados JSON con tiempos de ejecución
│   ├── models/
│   │   ├── domain.py            # Modelos ORM SQLAlchemy 2.0 (Products, StorePrices, History)
│   │   └── schemas.py           # Esquemas Pydantic v2 (camelCase + retrocompatibilidad)
│   ├── collectors/
│   │   ├── base.py              # Interfaz BaseStoreCollector, CircuitBreaker y rotación UA
│   │   ├── registry.py          # Orquestador concurrente (asyncio.gather con semáforo)
│   │   ├── stores/              # Conectores específicos para las 8 tiendas de Perú
│   │   │   ├── efe.py           # Tiendas Efe (storeId: "efe")
│   │   │   ├── falabella.py     # Falabella CMR (storeId: "falabella")
│   │   │   ├── ripley.py        # Ripley (storeId: "ripley")
│   │   │   ├── curacao.py       # La Curacao (storeId: "curacao")
│   │   │   ├── hiraoka.py       # Hiraoka (storeId: "hiraoka")
│   │   │   ├── tottus.py        # Tottus (storeId: "tottus")
│   │   │   ├── metro.py         # Metro (storeId: "metro")
│   │   │   └── wong.py          # Wong (storeId: "wong")
│   │   └── normalizer.py        # Limpieza de precios PEN, sanity checks y mínimo histórico
│   ├── services/
│   │   ├── catalog_service.py   # Filtrado dinámico, recálculo por tiendas y caché TTL
│   │   └── scheduler.py         # Job asíncrono en segundo plano (recolección periódica)
│   ├── data/
│   │   └── seed_catalog.py      # Catálogo semilla oficial y lista de ubigeo (25 departamentos)
│   └── api/
│       └── v1/
│           ├── router.py        # Router central /api/v1 y diagnóstico /health
│           ├── products.py      # GET /api/v1/products, GET /api/v1/products/{id}
│           ├── stores.py        # GET /api/v1/stores
│           ├── community.py     # GET y POST /api/v1/community-offers
│           └── admin_sync.py    # POST /api/v1/collectors/sync (Protegido X-API-Key)
└── tests/
    └── test_api.py              # Suite de 20 pruebas automatizadas
```

---

## 🏪 Retailers Peruanos Soportados Oficialmente

| ID | Tienda Comercial | Código | Estrategia de Recolección |
| :--- | :--- | :--- | :--- |
| `efe` | **Tiendas Efe** | `EFE` | JSON-LD + VTEX Estado + Selectores CSS |
| `falabella` | **Falabella CMR** | `FALABELLA` | JSON-LD + `__NEXT_DATA__` Prices + Precios CMR |
| `ripley` | **Ripley** | `RIPLEY` | JSON-LD + `__PRELOADED_STATE__` + Tarjeta Ripley |
| `curacao` | **La Curacao** | `CURACAO` | JSON-LD + VTEX Estado + Selectores CSS |
| `hiraoka` | **Hiraoka** | `HIRAOKA` | JSON-LD + Magento Special Price + Open Graph |
| `tottus` | **Tottus** | `TOTTUS` | JSON-LD + `__NEXT_DATA__` + Precios CMR |
| `metro` | **Metro** | `METRO` | JSON-LD + VTEX IO Selling Price |
| `wong` | **Wong** | `WONG` | JSON-LD + VTEX IO Selling Price |

---

## ⚡ Rendimiento y Caché TTL (< 50ms)

El endpoint `GET /api/v1/products` está optimizado para responder en **menos de 50 milisegundos**:
- **Caché en Memoria**: Mantiene en memoria las entidades de catálogo con un TTL configurable (`CACHE_TTL_SECONDS=60`).
- **Filtrado en CPU sin consultas de red**: Búsqueda por texto, marca, RAM, procesador, almacenamiento y resolución ejecutadas directamente en estructuras de datos indexadas en memoria.
- **Recálculo Dinámico**: Al enviar `enabled_stores`, la API filtra las tiendas activas para el usuario y recalcula sobre la marcha `bestPrice`, `bestStoreName`, `discountPercentage` y `isBestPrice` en < 2ms.
- **Cabeceras HTTP**: Inyecta `Cache-Control: public, max-age=60` y métrica de latencia `X-Process-Time`.

---

## 🔐 Seguridad y Hardening de Nivel Producción

- **Protección Administrativa**: `POST /api/v1/collectors/sync` requiere la cabecera `X-API-Key`, comparada mediante `secrets.compare_digest` para neutralizar ataques de tiempo (*timing attacks*).
- **Rate Limiting Inteligente por IP**:
  - Lecturas: `60 req/min`.
  - Escrituras y sincronización: `5 req/min`.
  - Respuestas HTTP 429 con cabecera estándar `Retry-After`.
- **Prevención SSRF / XSS**:
  - Validación de esquemas estrictos exclusivamente `https://`.
  - Bloqueo de rangos de red privados (`127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`, `169.254.169.254`, etc.).
  - Rechazo de caracteres de control ASCII (`\x00-\x1f\x7f`) y límites estrictos de longitud (`max_length=80`).
- **Cabeceras OWASP**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
- **Contenedor Seguro**: Ejecución con usuario non-root (`UID 10001: finprice`) sobre imagen reducida `python:3.11-slim`.

---

## ⚙️ Variables de Entorno

| Variable | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `string` | `development` | Modo de ejecución (`development` o `production`). |
| `HOST` | `string` | `0.0.0.0` | Dirección IP de escucha del servidor. |
| `PORT` | `int` | `8000` | Puerto TCP de servicio. |
| `FINPRICE_ADMIN_API_KEY` | `string` | `finprice_secret_admin_key_2026` | Clave secreta requerida para sincronización manual. |
| `ALLOWED_ORIGINS` | `string` | `*` | Orígenes permitidos para CORS (en prod restringir). |
| `DATABASE_URL` | `string` | `sqlite:///./finprice_cloud.db` | Cadena de conexión SQLAlchemy (SQLite o PostgreSQL). |
| `CACHE_TTL_SECONDS` | `int` | `60` | Tiempo de vida de la caché en memoria de productos. |
| `COLLECTION_INTERVAL_MINUTES` | `int` | `360` | Frecuencia de sincronización periódica en background (6h). |
| `RATE_LIMIT_READ_PER_MINUTE` | `int` | `60` | Límite de peticiones de lectura por IP. |
| `RATE_LIMIT_WRITE_PER_MINUTE` | `int` | `5` | Límite de peticiones de escritura/sync por IP. |
| `COLLECTOR_MAX_CONCURRENCY` | `int` | `4` | Semáforo de conexiones simultáneas salientes. |

---

## 🚀 Despliegue en la Nube

### Opción A: Render / Railway / Fly.io

1. Conecta este repositorio en tu panel de **Render** o **Railway**.
2. Tipo de servicio: **Web Service (Python o Dockerfile)**.
3. Define las variables de entorno en el panel:
   - `ENVIRONMENT=production`
   - `FINPRICE_ADMIN_API_KEY=tu_clave_secreta_super_segura`
4. Comando de inicio (si no usas Dockerfile):
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

### Opción B: Google Cloud Run (Containerless Serverless)

```bash
# 1. Construir la imagen con Google Cloud Build
gcloud builds submit --tag gcr.io/TU-PROYECTO/finprice-api:latest

# 2. Desplegar en Cloud Run con usuario non-root
gcloud run deploy finprice-api \
  --image gcr.io/TU-PROYECTO/finprice-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars ENVIRONMENT=production,FINPRICE_ADMIN_API_KEY=clave_secreta_2026 \
  --memory 512Mi \
  --cpu 1
```

### Opción C: Docker Local / VPS

```bash
# Construir la imagen multi-stage
docker build -t finprice-api:2.0.0 .

# Ejecutar el contenedor
docker run -d -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e FINPRICE_ADMIN_API_KEY=mi_clave_secreta \
  --name finprice-container finprice-api:2.0.0

# Verificar logs estructurados
docker logs -f finprice-container
```

---

## 🧪 Pruebas Automatizadas (Pytest)

El proyecto incluye 20 pruebas que verifican exhaustivamente contratos, serialización camelCase, filtros de hardware, seguridad, ubigeo y Circuit Breaker:

```bash
# Activar entorno virtual
source .venv/bin/activate

# Ejecutar la suite completa
pytest tests/test_api.py -v
```

Salida esperada:
```text
tests/test_api.py::test_root_endpoint PASSED                             [  5%]
tests/test_api.py::test_health_diagnostic_endpoint PASSED                [ 10%]
tests/test_api.py::test_security_headers_present PASSED                  [ 15%]
tests/test_api.py::test_get_products_camel_case_schema PASSED            [ 20%]
tests/test_api.py::test_get_product_by_id PASSED                         [ 25%]
tests/test_api.py::test_filter_by_category PASSED                        [ 30%]
tests/test_api.py::test_filter_by_brand PASSED                           [ 35%]
tests/test_api.py::test_filter_by_ram PASSED                             [ 40%]
tests/test_api.py::test_filter_by_storage PASSED                         [ 45%]
tests/test_api.py::test_filter_by_sort_order PASSED                      [ 50%]
tests/test_api.py::test_filter_by_enabled_stores_dynamic_recalc PASSED   [ 55%]
tests/test_api.py::test_get_stores_endpoint PASSED                       [ 60%]
tests/test_api.py::test_community_offers_flow PASSED                     [ 65%]
tests/test_api.py::test_legacy_get_products PASSED                       [ 70%]
tests/test_api.py::test_admin_sync_authentication PASSED                 [ 75%]
tests/test_api.py::test_clean_pen_price PASSED                           [ 80%]
tests/test_api.py::test_sanity_check_price PASSED                        [ 85%]
tests/test_api.py::test_calculate_discount_percentage PASSED             [ 90%]
tests/test_api.py::test_evaluate_historical_min PASSED                   [ 95%]
tests/test_api.py::test_circuit_breaker_lifecycle PASSED                 [100%]

============================== 20 passed in 0.26s ==============================
```

---

## 📡 Guía de Endpoints y Ejemplos cURL

### 1. Diagnóstico de Salud
```bash
curl -X GET "http://localhost:8000/api/v1/health" -H "Accept: application/json"
```

### 2. Catálogo General (Ordenado de menor a mayor precio)
```bash
curl -X GET "http://localhost:8000/api/v1/products?sort_order=LOW_TO_HIGH"
```

### 3. Filtro por Hardware (RAM y Almacenamiento)
```bash
curl -X GET "http://localhost:8000/api/v1/products?ram=16GB&storage=512GB"
```

### 4. Recálculo Dinámico por Tiendas Habilitadas
```bash
curl -X GET "http://localhost:8000/api/v1/products?enabled_stores=efe,falabella,hiraoka"
```

### 5. Detalle de Producto por ID (con historial de 30 días)
```bash
curl -X GET "http://localhost:8000/api/v1/products/prod_1"
```

### 6. Listado de Tiendas y Estado de Circuit Breaker
```bash
curl -X GET "http://localhost:8000/api/v1/stores"
```

### 7. Ofertas Físicas Comunitarias (Filtradas por Ubigeo)
```bash
curl -X GET "http://localhost:8000/api/v1/community-offers?department=Lambayeque&province=Chiclayo"
```

### 8. Registro de Oferta Física Comunitaria
```bash
curl -X POST "http://localhost:8000/api/v1/community-offers" \
  -H "Content-Type: application/json" \
  -d '{
    "productId": "prod_1",
    "physicalStoreName": "Falabella Mall Aventura Chiclayo",
    "department": "Lambayeque",
    "province": "Chiclayo",
    "district": "Chiclayo",
    "priceFound": 4299.00,
    "photoUri": "https://ejemplo.com/foto.jpg",
    "comment": "Precio con tarjeta CMR en vitrina",
    "authorName": "Carlos M."
  }'
```

### 9. Sincronización Asíncrona Manual (Protegida con X-API-Key)
```bash
curl -X POST "http://localhost:8000/api/v1/collectors/sync" \
  -H "X-API-Key: finprice_secret_admin_key_2026"
```

### 10. Endpoint Legado (Retrocompatibilidad /products)
```bash
curl -X GET "http://localhost:8000/products?search=MacBook"
```

---

## 📄 Licencia
Este proyecto es software privado de arquitectura empresarial retail bajo licencia MIT. Desarrollado con los más altos estándares de ingeniería de software backend.
