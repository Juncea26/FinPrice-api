"""
Semilla de respaldo de inicio rápido (< 50 ms) para Neon PostgreSQL / SQLite.
Garantiza que la base de datos cuente inmediatamente con el catálogo oficial
de 6 productos verificados, 22 ofertas multitienda, historial y comunidad
sin bloquear el arranque ni superar los 512 MB de RAM de Render.
"""
import json
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.entities import (
    ProductEntity,
    StoreOfferEntity,
    PriceHistoryEntity,
    CommunityOfferEntity,
    CommunityPostEntity,
)

logger = get_logger("core.seed_data")

SEED_PRODUCTS = [
    {
        "id": "prod_samsung_s25_ultra",
        "title": "Samsung Galaxy S25 Ultra 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 3799.0,
        "original_price": 7079.0,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 46,
        "available_stores_count": 2,
        "image_url": "https://www.efe.com.pe/media/catalog/product/4/5/459270-800-800.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=700&width=700&canvas=700:700",
        "description": "El estandarte de Samsung con Galaxy AI integrada, procesador Snapdragon 8 Gen 3 for Galaxy, chasis de titanio de grado aeroespacial con S-Pen y cámara cuádruple de 200MP.",
        "features_json": "[\"Procesador: Snapdragon 8 Elite\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.9\\\" Dynamic AMOLED 2X\", \"Resolución: 3120 x 1440\", \"Cámara Principal: 200 MP + 50 MP + 12 MP + 10 MP\"]",
        "tech_specs_json": "{\"Procesador\": \"Snapdragon 8 Elite\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"6.9\\\" Dynamic AMOLED 2X\", \"Sistema Operativo\": \"Android\", \"Conectividad\": \"5G\", \"Marca\": \"Samsung\", \"Cámara Principal\": \"200 MP + 50 MP + 12 MP + 10 MP\", \"Resolución\": \"3120 x 1440\"}",
        "is_favorite": 0,
        "historical_min_price": 3799.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:43:43.619058",
        "updated_at": "2026-10-27 19:42:40.377071"
    },
    {
        "id": "prod_iphone_16",
        "title": "Apple iPhone 16 128GB",
        "category": "Smartphones",
        "brand": "Apple",
        "best_price": 3299.0,
        "original_price": 4499.0,
        "best_store_name": "Falabella",
        "discount_percentage": 27,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/pub/media/catalog/product/i/p/iphone_16_no-ai_white_pdp_image_position_1__gens.jpg",
        "description": "Diseñado con Apple Intelligence, el revolucionario botón de Control de Cámara, chip A18 de segunda generación y cámara Fusion de 48 MP.",
        "features_json": "[\"Procesador: 6 núcleos\", \"Memoria RAM: 8 GB\", \"Almacenamiento: 128 GB\", \"Pantalla: 6.1\\\"\", \"Resolución: 2556 x 1179 píxeles\", \"Cámara Principal: 48 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Procesador\": \"6 núcleos\", \"Sistema Operativo\": \"iOS\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"128 GB\", \"Cámara Principal\": \"48 MP\", \"Conectividad\": \"5G\", \"Pantalla\": \"6.1\\\"\", \"Resolución\": \"2556 x 1179 píxeles\"}",
        "is_favorite": 0,
        "historical_min_price": 3299.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:43:43.619059",
        "updated_at": "2026-10-27 19:42:40.398031"
    },
    {
        "id": "prod_macbook_air_m5",
        "title": "Apple MacBook Air 13.6 Pulgadas M5 16GB RAM 512GB SSD",
        "category": "Laptops",
        "brand": "Apple",
        "best_price": 5899.0,
        "original_price": 6499.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 9,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/pub/media/catalog/product/m/a/macbook_air_13-in_m5_sky_blue_pdp_image_position_1__gens.jpg",
        "description": "Portátil ultradelgada y silenciosa con pantalla Liquid Retina de 13.6 pulgadas, 16GB de memoria unificada, almacenamiento SSD de 512GB y autonomía de hasta 18 horas.",
        "features_json": "[\"Procesador: 10 núcleos\", \"Memoria RAM: 16 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 13.6\\\" Liquid Retina\", \"Resolución: 2560 x 1664\", \"Batería: Litio - Hasta 18 horas\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Procesador\": \"10 núcleos\", \"Sistema Operativo\": \"Mac OS\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"13.6\\\" Liquid Retina\", \"Batería\": \"Litio - Hasta 18 horas\", \"Resolución\": \"2560 x 1664\"}",
        "is_favorite": 0,
        "historical_min_price": 5899.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:43:43.619060",
        "updated_at": "2026-10-27 19:42:40.377071"
    },
    {
        "id": "prod_lg_oled_tv",
        "title": "LG 55\" OLED evo AI C6 4K Smart TV 2026",
        "category": "TVs",
        "brand": "LG",
        "best_price": 3599.0,
        "original_price": 4999.0,
        "best_store_name": "Falabella CMR",
        "discount_percentage": 28,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/pub/media/catalog/product/1/3/139008_2_1.jpg",
        "description": "Televisor inteligente con píxeles OLED autoemisivos, procesador inteligente α9 AI 4K con mapeo dinámico de tonos, soporte Dolby Vision/Atmos y puertos HDMI 2.1 para gaming a 120Hz.",
        "features_json": "[\"Procesador: Procesador de IA α11 4K Generacion 3\", \"Pantalla: 55\\\" OLED evo\", \"Resolución: 4K Ultra HD\", \"Conectividad: Wi-Fi 6\", \"Sistema Operativo: webOs 26\", \"Procesador: α11 AI Processor 4K Gen3\"]",
        "tech_specs_json": "{\"Marca\": \"LG\", \"Conectividad\": \"Wi-Fi 6\", \"Sistema Operativo\": \"webOs 26\", \"Procesador\": \"Procesador de IA α11 4K Generacion 3\", \"Pantalla\": \"55\\\" OLED evo\", \"Resolución\": \"4K Ultra HD\"}",
        "is_favorite": 0,
        "historical_min_price": 3599.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:43:43.619061",
        "updated_at": "2026-10-27 02:51:45.516977"
    },
    {
        "id": "prod_ipad_11",
        "title": "Apple iPad 11\" Chip A16 Wi-Fi 128GB",
        "category": "Tablets",
        "brand": "Apple",
        "best_price": 1899.0,
        "original_price": 2599.0,
        "best_store_name": "Falabella CMR",
        "discount_percentage": 27,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/pub/media/catalog/product/i/p/ipad_a16_wifi_silver_pdp_image_position_1__laes_1.jpg",
        "description": "Tablet potente y versátil con pantalla Liquid Retina de 11 pulgadas, procesador Apple Bionic, cámara frontal horizontal de 12MP y compatibilidad con Apple Pencil.",
        "features_json": "[\"Procesador: Apple Chip A16\", \"Memoria RAM: 6 GB\", \"Almacenamiento: 128 GB\", \"Pantalla: 11\\\" Liquid Retina IPS LCD\", \"Resolución: 2360 × 1640 píxeles\", \"Cámara Principal: 12 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Conectividad\": \"Wi-Fi\", \"Cámara Principal\": \"12 MP\", \"Procesador\": \"Apple Chip A16\", \"Almacenamiento\": \"128 GB\", \"Sistema Operativo\": \"iPadOS 18 P\", \"Pantalla\": \"11\\\" Liquid Retina IPS LCD\", \"Memoria RAM\": \"6 GB\", \"Resolución\": \"2360 × 1640 píxeles\"}",
        "is_favorite": 0,
        "historical_min_price": 1899.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:43:43.619061",
        "updated_at": "2026-10-27 19:42:40.376293"
    },
    {
        "id": "prod_xiaomi_redmi_note",
        "title": "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Xiaomi",
        "best_price": 1829.0,
        "original_price": 1999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 9,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/pub/media/catalog/product/1/_/1_23_12.jpg",
        "description": "Smartphone con pantalla AMOLED curva de 120Hz a resolución 1.5K, cámara de 200MP con OIS, resistencia al agua y polvo IP68 y carga hiperrápida.",
        "features_json": "[\"Procesador: Snapdragon 7s Gen4\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.8\\\" AMOLED\", \"Resolución: 2772 x 1280\", \"Cámara Principal: 200 MP + 8 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Xiaomi\", \"Procesador\": \"Snapdragon 7s Gen4\", \"Sistema Operativo\": \"Android 15\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Cámara Principal\": \"200 MP + 8 MP\", \"Conectividad\": \"5G\", \"Batería\": \"6500 mAh\", \"Pantalla\": \"6.8\\\" AMOLED\", \"Resolución\": \"2772 x 1280\"}",
        "is_favorite": 0,
        "historical_min_price": 1829.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:43:43.619062",
        "updated_at": "2026-10-27 19:42:40.377214"
    }
]
SEED_STORE_OFFERS = [
    {
        "id": 1,
        "product_id": "prod_samsung_s25_ultra",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3799.0,
        "original_price": 7079.0,
        "offer_url": "https://www.efe.com.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-27 02:51:42.153251"
    },
    {
        "id": 2,
        "product_id": "prod_samsung_s25_ultra",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 3799.0,
        "original_price": 7079.0,
        "offer_url": "https://www.lacuracao.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:42.153288"
    },
    {
        "id": 3,
        "product_id": "prod_iphone_16",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3399.0,
        "original_price": 4299.0,
        "offer_url": "https://hiraoka.com.pe/iphone-16-6-1-128gb-negro",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:42.970805"
    },
    {
        "id": 4,
        "product_id": "prod_iphone_16",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3399.0,
        "original_price": 4299.0,
        "offer_url": "https://simple.ripley.com.pe/iphone-16-128gb-2065365819351",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:42.970848"
    },
    {
        "id": 5,
        "product_id": "prod_iphone_16",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3499.0,
        "original_price": 4299.0,
        "offer_url": "https://www.efe.com.pe/iphone-16-blk-128gb-bes-mye73be-a.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:42.970868"
    },
    {
        "id": 6,
        "product_id": "prod_macbook_air_m5",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5899.0,
        "original_price": 6499.0,
        "offer_url": "https://hiraoka.com.pe/macbook-air-de-13-chip-m5-16gb-ram-disco-solido-de-512gb-azul-cielo",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-27 02:51:44.126231"
    },
    {
        "id": 7,
        "product_id": "prod_macbook_air_m5",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5899.0,
        "original_price": 6499.0,
        "offer_url": "https://www.efe.com.pe/macbook-air-13-6-m5-16gb-512gb-silver-mdh74e-a.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:44.126267"
    },
    {
        "id": 8,
        "product_id": "prod_macbook_air_m5",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5899.0,
        "original_price": 6499.0,
        "offer_url": "https://www.lacuracao.pe/macbook-air-13-6-m5-16gb-512gb-silver-mdh74e-a.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:44.126282"
    },
    {
        "id": 9,
        "product_id": "prod_lg_oled_tv",
        "store_id": "falabella",
        "store_name": "Falabella CMR",
        "price": 3599.0,
        "original_price": 4999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-27 02:51:45.517241"
    },
    {
        "id": 10,
        "product_id": "prod_lg_oled_tv",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3599.0,
        "original_price": 4999.0,
        "offer_url": "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:45.517272"
    },
    {
        "id": 11,
        "product_id": "prod_lg_oled_tv",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3899.0,
        "original_price": 4999.0,
        "offer_url": "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:45.517286"
    },
    {
        "id": 12,
        "product_id": "prod_lg_oled_tv",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5139.0,
        "original_price": 6769.0,
        "offer_url": "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:45.517298"
    },
    {
        "id": 13,
        "product_id": "prod_lg_oled_tv",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5139.0,
        "original_price": 6769.0,
        "offer_url": "https://www.lacuracao.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:45.517308"
    },
    {
        "id": 14,
        "product_id": "prod_ipad_11",
        "store_id": "falabella",
        "store_name": "Falabella CMR",
        "price": 1899.0,
        "original_price": 2599.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-27 02:51:46.522471"
    },
    {
        "id": 15,
        "product_id": "prod_ipad_11",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 1899.0,
        "original_price": 2599.0,
        "offer_url": "https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:46.522505"
    },
    {
        "id": 16,
        "product_id": "prod_ipad_11",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1949.0,
        "original_price": 2299.0,
        "offer_url": "https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wifi-128gb-plata",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:46.522519"
    },
    {
        "id": 17,
        "product_id": "prod_ipad_11",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1979.0,
        "original_price": 2989.0,
        "offer_url": "https://www.efe.com.pe/ipad-a16-wi-fi-md4e4ll-a-11-128gb-6gb-p26513743.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:46.522531"
    },
    {
        "id": 18,
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1829.0,
        "original_price": 1999.0,
        "offer_url": "https://hiraoka.com.pe/celular-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-cafe-moca",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-27 02:51:47.655546"
    },
    {
        "id": 19,
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1899.0,
        "original_price": 2099.0,
        "offer_url": "https://www.efe.com.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:47.655579"
    },
    {
        "id": 20,
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 1899.0,
        "original_price": 2099.0,
        "offer_url": "https://www.lacuracao.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 02:51:47.655593"
    },
    {
        "id": 21,
        "product_id": "prod_iphone_16",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3299.0,
        "original_price": 4499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/prod18120095/iPhone-16-128GB/20687062",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-27 19:42:40.381955"
    },
    {
        "id": 22,
        "product_id": "prod_iphone_16",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 3399.0,
        "original_price": 4499.0,
        "offer_url": "https://www.tottus.com.pe/tottus-pe/articulo/149214502/iphone-16-128gb-negro/149214504",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-27 19:42:40.381956"
    }
]
SEED_PRICE_HISTORY = [
    {
        "id": 1,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3799.0,
        "recorded_at": "2026-10-27 02:51:42.153808"
    },
    {
        "id": 2,
        "product_id": "prod_iphone_16",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3299.0,
        "recorded_at": "2026-10-27 02:51:42.971238"
    },
    {
        "id": 3,
        "product_id": "prod_macbook_air_m5",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5899.0,
        "recorded_at": "2026-10-27 02:51:44.126611"
    },
    {
        "id": 4,
        "product_id": "prod_lg_oled_tv",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3599.0,
        "recorded_at": "2026-10-27 02:51:45.517605"
    },
    {
        "id": 5,
        "product_id": "prod_ipad_11",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1899.0,
        "recorded_at": "2026-10-27 02:51:46.522828"
    },
    {
        "id": 6,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1829.0,
        "recorded_at": "2026-10-27 02:51:47.655872"
    }
]
SEED_COMMUNITY_OFFERS = [
    {
        "id": "comm_off_8ff27c97",
        "product_id": "prod_iphone_16",
        "product_name": "Apple iPhone 16 128GB Negro",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "price_found": 3699.0,
        "photo_uri": "",
        "comment": "Precio en liquidación de vitrina",
        "timestamp_millis": 1792683823640,
        "formatted_date": "22 Oct 2026, 15:43",
        "author_name": "Usuario Real",
        "created_at": "2026-10-22 15:43:43.640518"
    },
    {
        "id": "comm_off_bbecdb39",
        "product_id": "prod_iphone_16",
        "product_name": "Apple iPhone 16 128GB Negro",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "price_found": 3699.0,
        "photo_uri": "",
        "comment": "Precio en liquidación de vitrina",
        "timestamp_millis": 1792683843501,
        "formatted_date": "22 Oct 2026, 15:44",
        "author_name": "Usuario Real",
        "created_at": "2026-10-22 15:44:03.502396"
    },
    {
        "id": "comm_off_4e12aabe",
        "product_id": "prod_iphone_16",
        "product_name": "Apple iPhone 16 128GB Negro",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "price_found": 3699.0,
        "photo_uri": "",
        "comment": "Precio en liquidación de vitrina",
        "timestamp_millis": 1792683926696,
        "formatted_date": "22 Oct 2026, 15:45",
        "author_name": "Usuario Real",
        "created_at": "2026-10-22 15:45:26.696658"
    },
    {
        "id": "comm_off_0c12f939",
        "product_id": "prod_iphone_16",
        "product_name": "Apple iPhone 16 128GB Negro",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "price_found": 3699.0,
        "photo_uri": "",
        "comment": "Precio en liquidación de vitrina",
        "timestamp_millis": 1793037625754,
        "formatted_date": "26 Oct 2026, 18:00",
        "author_name": "Usuario Real",
        "created_at": "2026-10-26 18:00:25.754477"
    },
    {
        "id": "comm_off_d333f92d",
        "product_id": "prod_xiaomi_redmi_note",
        "product_name": "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "price_found": 3699.0,
        "photo_uri": "",
        "comment": "Precio en liquidación de vitrina",
        "timestamp_millis": 1793037658589,
        "formatted_date": "26 Oct 2026, 18:00",
        "author_name": "Usuario Real",
        "created_at": "2026-10-26 18:00:58.589818"
    }
]
SEED_COMMUNITY_POSTS = [
    {
        "id": "post_comm_off_8ff27c97",
        "product_id": "prod_iphone_16",
        "title": "Oferta en Tiendas Efe Chiclayo Centro: Apple iPhone 16 128GB Negro",
        "content": "Precio en liquidación de vitrina",
        "product_name": "Apple iPhone 16 128GB Negro",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "price": 3699.0,
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "photo_uri": "",
        "author_name": "Usuario Real",
        "likes_count": 0,
        "status": "active",
        "timestamp_millis": 1792683823640,
        "formatted_date": "22 Oct 2026, 15:43",
        "created_at": "2026-10-22 15:43:43.640518"
    },
    {
        "id": "post_comm_off_bbecdb39",
        "product_id": "prod_iphone_16",
        "title": "Oferta en Tiendas Efe Chiclayo Centro: Apple iPhone 16 128GB Negro",
        "content": "Precio en liquidación de vitrina",
        "product_name": "Apple iPhone 16 128GB Negro",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "price": 3699.0,
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "photo_uri": "",
        "author_name": "Usuario Real",
        "likes_count": 0,
        "status": "active",
        "timestamp_millis": 1792683843501,
        "formatted_date": "22 Oct 2026, 15:44",
        "created_at": "2026-10-22 15:44:03.502396"
    },
    {
        "id": "post_comm_off_4e12aabe",
        "product_id": "prod_iphone_16",
        "title": "Oferta en Tiendas Efe Chiclayo Centro: Apple iPhone 16 128GB Negro",
        "content": "Precio en liquidación de vitrina",
        "product_name": "Apple iPhone 16 128GB Negro",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "price": 3699.0,
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "photo_uri": "",
        "author_name": "Usuario Real",
        "likes_count": 0,
        "status": "active",
        "timestamp_millis": 1792683926696,
        "formatted_date": "22 Oct 2026, 15:45",
        "created_at": "2026-10-22 15:45:26.696658"
    },
    {
        "id": "post_comm_off_0c12f939",
        "product_id": "prod_iphone_16",
        "title": "Oferta en Tiendas Efe Chiclayo Centro: Apple iPhone 16 128GB Negro",
        "content": "Precio en liquidación de vitrina",
        "product_name": "Apple iPhone 16 128GB Negro",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "price": 3699.0,
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "photo_uri": "",
        "author_name": "Usuario Real",
        "likes_count": 0,
        "status": "active",
        "timestamp_millis": 1793037625754,
        "formatted_date": "26 Oct 2026, 18:00",
        "created_at": "2026-10-26 18:00:25.754477"
    },
    {
        "id": "post_comm_off_d333f92d",
        "product_id": "prod_xiaomi_redmi_note",
        "title": "Oferta en Tiendas Efe Chiclayo Centro: Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca",
        "content": "Precio en liquidación de vitrina",
        "product_name": "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca",
        "physical_store_name": "Tiendas Efe Chiclayo Centro",
        "price": 3699.0,
        "department": "Lambayeque",
        "province": "Chiclayo",
        "district": "Chiclayo",
        "photo_uri": "",
        "author_name": "Usuario Real",
        "likes_count": 0,
        "status": "active",
        "timestamp_millis": 1793037658589,
        "formatted_date": "26 Oct 2026, 18:00",
        "created_at": "2026-10-26 18:00:58.589818"
    }
]


def _parse_dt(dt_str):
    if not dt_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return datetime.now(timezone.utc)


async def seed_database_fast(session: AsyncSession) -> int:
    """Inserta la semilla de respaldo en milisegundos si la base de datos está vacía."""
    count_q = await session.execute(select(func.count(ProductEntity.id)))
    count = count_q.scalar() or 0
    if count > 0:
        logger.info(f"Base de datos ya cuenta con {count} productos. Omitiendo semilla inicial.")
        return count

    logger.info("Poblando base de datos con semilla de respaldo oficial...")

    for p in SEED_PRODUCTS:
        prod_entity = ProductEntity(
            id=p["id"],
            title=p["title"],
            category=p["category"],
            brand=p["brand"],
            best_price=p["best_price"],
            original_price=p["original_price"],
            best_store_name=p["best_store_name"],
            discount_percentage=p["discount_percentage"],
            available_stores_count=p["available_stores_count"],
            image_url=p["image_url"],
            description=p["description"],
            features_json=p["features_json"],
            tech_specs_json=p["tech_specs_json"],
            is_favorite=bool(p.get("is_favorite", False)),
            historical_min_price=p.get("historical_min_price"),
            is_historical_min=bool(p.get("is_historical_min", False)),
            created_at=_parse_dt(p.get("created_at")),
            updated_at=_parse_dt(p.get("updated_at")),
        )
        session.add(prod_entity)

    for o in SEED_STORE_OFFERS:
        off_entity = StoreOfferEntity(
            product_id=o["product_id"],
            store_id=o["store_id"],
            store_name=o["store_name"],
            price=o["price"],
            original_price=o.get("original_price"),
            offer_url=o["offer_url"],
            is_best_price=bool(o.get("is_best_price", False)),
            last_scraped_at=_parse_dt(o.get("last_scraped_at")),
        )
        session.add(off_entity)

    for h in SEED_PRICE_HISTORY:
        hist_entity = PriceHistoryEntity(
            product_id=h["product_id"],
            day_offset=h["day_offset"],
            date_label=h["date_label"],
            price=h["price"],
            recorded_at=_parse_dt(h.get("recorded_at")),
        )
        session.add(hist_entity)

    for c in SEED_COMMUNITY_OFFERS:
        comm_entity = CommunityOfferEntity(
            id=c["id"],
            product_id=c["product_id"],
            product_name=c["product_name"],
            physical_store_name=c["physical_store_name"],
            department=c["department"],
            province=c["province"],
            district=c["district"],
            price_found=c["price_found"],
            photo_uri=c.get("photo_uri") or "",
            comment=c.get("comment") or "",
            timestamp_millis=c["timestamp_millis"],
            formatted_date=c["formatted_date"],
            author_name=c.get("author_name") or "Usuario FinPrice",
            created_at=_parse_dt(c.get("created_at")),
        )
        session.add(comm_entity)

    for cp in SEED_COMMUNITY_POSTS:
        post_entity = CommunityPostEntity(
            id=cp["id"],
            product_id=cp.get("product_id"),
            title=cp["title"],
            content=cp.get("content") or "",
            product_name=cp.get("product_name"),
            physical_store_name=cp.get("physical_store_name"),
            price=cp.get("price"),
            department=cp.get("department"),
            province=cp.get("province"),
            district=cp.get("district"),
            photo_uri=cp.get("photo_uri") or "",
            author_name=cp.get("author_name") or "Usuario FinPrice",
            likes_count=cp.get("likes_count", 0),
            status=cp.get("status", "active"),
            timestamp_millis=cp.get("timestamp_millis"),
            formatted_date=cp.get("formatted_date"),
            created_at=_parse_dt(cp.get("created_at")),
            updated_at=_parse_dt(cp.get("created_at")),
        )
        session.add(post_entity)

    await session.commit()
    logger.info(f"Semilla de respaldo insertada exitosamente ({len(SEED_PRODUCTS)} productos en Neon).")
    return len(SEED_PRODUCTS)
