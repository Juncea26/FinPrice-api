"""
Semilla de respaldo de inicio rápido y sincronización UPSERT en Neon PostgreSQL / SQLite.
Garantiza que la base de datos cuente inmediatamente con el catálogo oficial
de 19 productos verificados en 8 retailers peruanos sin bloquear el arranque.
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

def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _parse_dt(dt_str):
    if not dt_str:
        return utc_now_naive()
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return utc_now_naive()

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
        "available_stores_count": 3,
        "image_url": "https://www.efe.com.pe/media/catalog/product/4/5/459270-800-800.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=700&width=700&canvas=700:700",
        "description": "El estandarte de Samsung con Galaxy AI integrada, procesador Snapdragon 8 Elite for Galaxy, chasis de titanio con S-Pen y c\u00e1mara cu\u00e1druple de 200MP.",
        "features_json": "[\"Procesador: Snapdragon 8 Elite\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.9\\\" Dynamic AMOLED 2X\", \"Resoluci\u00f3n: 3120 x 1440\", \"C\u00e1mara Principal: 200 MP + 50 MP + 12 MP + 10 MP\"]",
        "tech_specs_json": "{\"Procesador\": \"Snapdragon 8 Elite\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"6.9\\\" Dynamic AMOLED 2X\", \"Sistema Operativo\": \"Android\", \"Conectividad\": \"5G\", \"Marca\": \"Samsung\", \"C\u00e1mara Principal\": \"200 MP + 50 MP + 12 MP + 10 MP\", \"Resoluci\u00f3n\": \"3120 x 1440\"}",
        "is_favorite": 0,
        "historical_min_price": 3799.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_iphone_16",
        "title": "Apple iPhone 16 128GB",
        "category": "Smartphones",
        "brand": "Apple",
        "best_price": 3399.0,
        "original_price": 3999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 15,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/pub/media/catalog/product/i/p/iphone_16_no-ai_white_pdp_image_position_1__gens.jpg",
        "description": "Dise\u00f1ado con Apple Intelligence, bot\u00f3n Control de C\u00e1mara t\u00e1ctil, chip A18 de segunda generaci\u00f3n y sistema de c\u00e1mara Fusion de 48 MP.",
        "features_json": "[\"Procesador: Apple A18\", \"Memoria RAM: 8 GB\", \"Almacenamiento: 128 GB\", \"Pantalla: 6.1\\\" Super Retina XDR OLED\", \"Resoluci\u00f3n: 2556 x 1179 p\u00edxeles\", \"C\u00e1mara Principal: 48 MP + 12 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Procesador\": \"Apple A18\", \"Sistema Operativo\": \"iOS 18\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"128 GB\", \"C\u00e1mara Principal\": \"48 MP + 12 MP\", \"Conectividad\": \"5G\", \"Pantalla\": \"6.1\\\" OLED\", \"Resoluci\u00f3n\": \"2556 x 1179\"}",
        "is_favorite": 0,
        "historical_min_price": 3399.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
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
        "description": "Smartphone con pantalla AMOLED curva de 120Hz a resoluci\u00f3n 1.5K, c\u00e1mara de 200MP con OIS, resistencia IP68 y carga hiperr\u00e1pida.",
        "features_json": "[\"Procesador: Snapdragon 7s Gen4\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.8\\\" AMOLED 1.5K 120Hz\", \"Resoluci\u00f3n: 2772 x 1280\", \"C\u00e1mara Principal: 200 MP + 8 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Xiaomi\", \"Procesador\": \"Snapdragon 7s Gen4\", \"Sistema Operativo\": \"HyperOS Android 15\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"C\u00e1mara Principal\": \"200 MP + 8 MP\", \"Conectividad\": \"5G\", \"Bater\u00eda\": \"6500 mAh\", \"Pantalla\": \"6.8\\\" AMOLED\", \"Resoluci\u00f3n\": \"2772 x 1280\"}",
        "is_favorite": 0,
        "historical_min_price": 1829.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_motorola_edge_50",
        "title": "Motorola Edge 50 Pro 5G 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Motorola",
        "best_price": 1899.0,
        "original_price": 2499.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 24,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/_/1_491.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Dise\u00f1o premium con acabado en cuero vegano, pantalla pOLED Super HD de 144Hz validada por Pantone y carga TurboPower de 125W.",
        "features_json": "[\"Procesador: Snapdragon 7 Gen 3\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.7\\\" pOLED 144Hz Super HD\", \"C\u00e1mara: 50MP + 13MP + 10MP Telefoto con OIS\", \"Carga r\u00e1pida: 125W TurboPower\"]",
        "tech_specs_json": "{\"Marca\": \"Motorola\", \"Procesador\": \"Snapdragon 7 Gen 3\", \"Sistema Operativo\": \"Android 14\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"C\u00e1mara Principal\": \"50 MP + 13 MP + 10 MP\", \"Conectividad\": \"5G\", \"Bater\u00eda\": \"4500 mAh\", \"Pantalla\": \"6.7\\\" pOLED\", \"Resoluci\u00f3n\": \"2712 x 1220\"}",
        "is_favorite": 0,
        "historical_min_price": 1899.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
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
        "description": "Port\u00e1til ultradelgada y silenciosa con pantalla Liquid Retina de 13.6 pulgadas, 16GB de memoria unificada, SSD de 512GB y autonom\u00eda de hasta 18 horas.",
        "features_json": "[\"Procesador: Apple Silicon 10 n\u00facleos\", \"Memoria RAM: 16 GB unificada\", \"Almacenamiento: 512 GB SSD\", \"Pantalla: 13.6\\\" Liquid Retina True Tone\", \"Resoluci\u00f3n: 2560 x 1664\", \"Bater\u00eda: Litio - Hasta 18 horas\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Procesador\": \"Apple Silicon M-Series\", \"Sistema Operativo\": \"macOS\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"13.6\\\" Liquid Retina\", \"Bater\u00eda\": \"Litio - Hasta 18 horas\", \"Resoluci\u00f3n\": \"2560 x 1664\"}",
        "is_favorite": 0,
        "historical_min_price": 5899.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_asus_zenbook_14",
        "title": "Asus Zenbook 14 OLED Intel Core Ultra 7 16GB RAM 1TB SSD",
        "category": "Laptops",
        "brand": "Asus",
        "best_price": 4699.0,
        "original_price": 5499.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 15,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/4/140239_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop ultraport\u00e1til premium con pantalla Lumina OLED de 120Hz 3K, procesador Intel Core Ultra 7 con NPU para IA y chasis met\u00e1lico ultraligero.",
        "features_json": "[\"Procesador: Intel Core Ultra 7 155H\", \"Memoria RAM: 16 GB LPDDR5X\", \"Almacenamiento: 1 TB SSD NVMe PCIe 4.0\", \"Pantalla: 14\\\" OLED 3K 120Hz 16:10\", \"Resoluci\u00f3n: 2880 x 1800\", \"Bater\u00eda: 75 Wh - Hasta 15 horas\"]",
        "tech_specs_json": "{\"Marca\": \"Asus\", \"Procesador\": \"Intel Core Ultra 7\", \"Sistema Operativo\": \"Windows 11 Home\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"1 TB SSD\", \"Pantalla\": \"14\\\" 3K OLED 120Hz\", \"Resoluci\u00f3n\": \"2880 x 1800\", \"Peso\": \"1.2 kg\"}",
        "is_favorite": 0,
        "historical_min_price": 4699.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_lenovo_ideapad_slim",
        "title": "Lenovo IdeaPad Slim 3 15.6\" AMD Ryzen 7 16GB RAM 512GB SSD",
        "category": "Laptops",
        "brand": "Lenovo",
        "best_price": 2499.0,
        "original_price": 3199.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 22,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135438_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop de productividad vers\u00e1til con procesador AMD Ryzen 7 serie 7000 de 8 n\u00facleos, pantalla FHD antirreflejo y certificaci\u00f3n militar de resistencia.",
        "features_json": "[\"Procesador: AMD Ryzen 7 7730U 8 n\u00facleos\", \"Memoria RAM: 16 GB DDR4\", \"Almacenamiento: 512 GB SSD NVMe\", \"Pantalla: 15.6\\\" Full HD IPS antirreflejo\", \"Resoluci\u00f3n: 1920 x 1080\", \"Audio: Altavoces Dolby Audio\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Procesador\": \"AMD Ryzen 7 7730U\", \"Sistema Operativo\": \"Windows 11 Home\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"512 GB SSD\", \"Pantalla\": \"15.6\\\" Full HD\", \"Resoluci\u00f3n\": \"1920 x 1080\"}",
        "is_favorite": 0,
        "historical_min_price": 2499.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_lg_oled_tv",
        "title": "LG 55\" OLED evo AI C6 4K Smart TV 2026",
        "category": "TVs",
        "brand": "LG",
        "best_price": 3799.0,
        "original_price": 4999.0,
        "best_store_name": "Falabella",
        "discount_percentage": 24,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/pub/media/catalog/product/1/3/139008_2_1.jpg",
        "description": "Televisor inteligente con p\u00edxeles OLED autoemisivos, procesador inteligente \u03b111 AI 4K Gen3, soporte Dolby Vision/Atmos y HDMI 2.1 a 144Hz para gaming.",
        "features_json": "[\"Procesador: Procesador de IA \u03b111 4K Generaci\u00f3n 3\", \"Pantalla: 55\\\" OLED evo 4K 144Hz\", \"Resoluci\u00f3n: 3840 x 2160 Ultra HD\", \"Conectividad: Wi-Fi 6 y HDMI 2.1 VRR\", \"Sistema Operativo: webOS 26 con actualizaciones garantizadas\", \"Sonido: Dolby Atmos 40W 2.2 canales\"]",
        "tech_specs_json": "{\"Marca\": \"LG\", \"Conectividad\": \"Wi-Fi 6, Bluetooth 5.2, HDMI 2.1 x4\", \"Sistema Operativo\": \"webOS 26\", \"Procesador\": \"\u03b111 AI Processor 4K Gen3\", \"Pantalla\": \"55\\\" OLED evo\", \"Resoluci\u00f3n\": \"4K Ultra HD (3840 x 2160)\", \"Tasa de refresco\": \"144Hz\"}",
        "is_favorite": 0,
        "historical_min_price": 3799.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_samsung_neo_qled_65",
        "title": "Samsung 65\" Neo QLED 4K QN85D Smart TV",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 4499.0,
        "original_price": 6499.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 31,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/136646_2_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Neo QLED impulsado por Mini LED Quantum Matrix y procesador NQ4 AI Gen2 con escalado 4K por redes neuronales.",
        "features_json": "[\"Tecnolog\u00eda de panel: Quantum Mini LED Neo QLED\", \"Pantalla: 65\\\" 4K 120Hz\", \"Procesador: NQ4 AI Gen2\", \"Audio: Dolby Atmos con OTS (Object Tracking Sound)\", \"Gaming Hub: HDMI 2.1 FreeSync Premium Pro\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Pantalla\": \"65\\\" Neo QLED\", \"Resoluci\u00f3n\": \"4K Ultra HD (3840 x 2160)\", \"Tasa de refresco\": \"120Hz\", \"Sistema Operativo\": \"Tizen OS\", \"Conectividad\": \"Wi-Fi 5, Bluetooth 5.2, HDMI x4\"}",
        "is_favorite": 0,
        "historical_min_price": 4499.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_tcl_miniled_55",
        "title": "TCL 55\" Mini-LED 4K 144Hz Google TV C755",
        "category": "TVs",
        "brand": "TCL",
        "best_price": 2299.0,
        "original_price": 3299.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 30,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/t/c/tcl_tv_qdminiled_c6k_55_front_full_specs_2_.png?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300&format=jpeg",
        "description": "Pantalla QD-Mini LED con m\u00e1s de 500 zonas de atenuaci\u00f3n local, tasa de refresco nativa de 144Hz VRR y sistema Google TV.",
        "features_json": "[\"Tecnolog\u00eda: QD-Mini LED con Quantum Dot\", \"Pantalla: 55\\\" 4K 144Hz VRR\", \"Brillo pico: 1300 nits HDR\", \"Sonido: Sistema Onkyo 2.1 con subwoofer integrado\", \"Sistema Operativo: Google TV con control por voz manos libres\"]",
        "tech_specs_json": "{\"Marca\": \"TCL\", \"Pantalla\": \"55\\\" QD-Mini LED\", \"Resoluci\u00f3n\": \"3840 x 2160 4K\", \"Tasa de refresco\": \"144Hz\", \"Sistema Operativo\": \"Google TV\", \"HDR\": \"Dolby Vision IQ, HDR10+\"}",
        "is_favorite": 0,
        "historical_min_price": 2299.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_ipad_11",
        "title": "Apple iPad 11\" Chip A16 Wi-Fi 128GB",
        "category": "Tablets",
        "brand": "Apple",
        "best_price": 1899.0,
        "original_price": 2599.0,
        "best_store_name": "Falabella",
        "discount_percentage": 27,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/pub/media/catalog/product/i/p/ipad_a16_wifi_silver_pdp_image_position_1__laes_1.jpg",
        "description": "Tablet potente y vers\u00e1til con pantalla Liquid Retina de 11 pulgadas, chip A16 Bionic, c\u00e1mara frontal horizontal de 12MP y soporte para Apple Pencil.",
        "features_json": "[\"Procesador: Apple Chip A16 Bionic\", \"Memoria RAM: 6 GB\", \"Almacenamiento: 128 GB\", \"Pantalla: 11\\\" Liquid Retina IPS\", \"Resoluci\u00f3n: 2360 \u00d7 1640 p\u00edxeles\", \"C\u00e1mara Principal: 12 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Conectividad\": \"Wi-Fi 6\", \"C\u00e1mara Principal\": \"12 MP\", \"Procesador\": \"Apple Chip A16\", \"Almacenamiento\": \"128 GB\", \"Sistema Operativo\": \"iPadOS 18\", \"Pantalla\": \"11\\\" Liquid Retina IPS\", \"Memoria RAM\": \"6 GB\", \"Resoluci\u00f3n\": \"2360 \u00d7 1640\"}",
        "is_favorite": 0,
        "historical_min_price": 1899.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_samsung_tab_s10",
        "title": "Samsung Galaxy Tab S10+ 12.4\" 256GB 12GB RAM con S-Pen",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 3699.0,
        "original_price": 4599.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 20,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135784_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Galaxy AI con pantalla Dynamic AMOLED 2X antirreflejo de 12.4 pulgadas, procesador MediaTek Dimensity 9300+ y S-Pen incluido.",
        "features_json": "[\"Procesador: MediaTek Dimensity 9300+\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 256 GB UFS\", \"Pantalla: 12.4\\\" Dynamic AMOLED 2X 120Hz\", \"S-Pen: Incluido con latencia de 2.8ms\", \"Resistencia: IP68 contra agua y polvo\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Procesador\": \"Dimensity 9300+\", \"Sistema Operativo\": \"Android 14 One UI 6\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"256 GB\", \"Pantalla\": \"12.4\\\" AMOLED 120Hz\", \"Resoluci\u00f3n\": \"2800 x 1752\"}",
        "is_favorite": 0,
        "historical_min_price": 3699.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_xiaomi_pad_6",
        "title": "Xiaomi Pad 6 11\" 256GB 8GB RAM Wi-Fi",
        "category": "Tablets",
        "brand": "Xiaomi",
        "best_price": 1299.0,
        "original_price": 1699.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 24,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138008_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet con pantalla WQHD+ de 144Hz con 7 niveles de tasa de refresco variable, procesador Snapdragon 870 y cuerpo met\u00e1lico de una sola pieza.",
        "features_json": "[\"Procesador: Snapdragon 870 7nm\", \"Memoria RAM: 8 GB LPDDR5\", \"Almacenamiento: 256 GB UFS 3.1\", \"Pantalla: 11\\\" 2.8K 144Hz Dolby Vision\", \"Bater\u00eda: 8840 mAh con carga de 33W\"]",
        "tech_specs_json": "{\"Marca\": \"Xiaomi\", \"Procesador\": \"Snapdragon 870\", \"Sistema Operativo\": \"MIUI Pad 14\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"256 GB\", \"Pantalla\": \"11\\\" 2.8K IPS 144Hz\", \"Resoluci\u00f3n\": \"2880 x 1800\"}",
        "is_favorite": 0,
        "historical_min_price": 1299.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_sony_wh1000xm5",
        "title": "Sony WH-1000XM5 Aud\u00edfonos Inal\u00e1mbricos Noise Cancelling",
        "category": "Audio",
        "brand": "Sony",
        "best_price": 1299.0,
        "original_price": 1699.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 24,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/w/h/wh-1000xm5_black.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "L\u00edderes en cancelaci\u00f3n de ruido activa con procesador integrado V1 + procesador QN1 HD, 8 micr\u00f3fonos y soporte para audio Hi-Res LDAC.",
        "features_json": "[\"Cancelaci\u00f3n de ruido l\u00edder en la industria con Auto NC Optimizer\", \"Procesador: Dual V1 + QN1 HD\", \"Autonom\u00eda: Hasta 30 horas con NC activado\", \"Carga r\u00e1pida: 3 minutos equivalen a 3 horas de m\u00fasica\", \"Llamadas ultran\u00edtidas con 4 micr\u00f3fonos beamforming y reducci\u00f3n por IA\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Conectividad\": \"Bluetooth 5.2, Jack 3.5mm\", \"C\u00f3decs\": \"LDAC, AAC, SBC\", \"Bater\u00eda\": \"Hasta 30 horas\", \"Peso\": \"250 gramos\", \"Cancelaci\u00f3n activa\": \"S\u00ed, adaptativa\"}",
        "is_favorite": 0,
        "historical_min_price": 1299.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_airpods_pro_2",
        "title": "Apple AirPods Pro (2da Generaci\u00f3n) con Estuche MagSafe USB-C",
        "category": "Audio",
        "brand": "Apple",
        "best_price": 899.0,
        "original_price": 1199.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 25,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/a/i/airpods_4__pdp_image_position_0__gens.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Aud\u00edfonos con chip H2 que ofrece cancelaci\u00f3n activa de ruido el doble de potente, Audio Espacial personalizado y estuche MagSafe USB-C con altavoz.",
        "features_json": "[\"Chip Apple H2 de alto rendimiento\", \"Cancelaci\u00f3n Activa de Ruido 2x superior\", \"Modo Ambiente Adaptativo y Audio Espacial\", \"Estuche con puerto USB-C y chip U1 para b\u00fasqueda precisa\", \"Autonom\u00eda: Hasta 6 horas con NC (30 horas con estuche)\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Chip\": \"Apple H2\", \"Conectividad\": \"Bluetooth 5.3\", \"Resistencia\": \"IP54 al polvo, sudor y agua\", \"Puerto de carga\": \"USB-C y MagSafe inal\u00e1mbrico\"}",
        "is_favorite": 0,
        "historical_min_price": 899.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_ps5_slim",
        "title": "Consola PlayStation 5 Slim 1TB Edici\u00f3n Est\u00e1ndar con Lector",
        "category": "Gaming",
        "brand": "Sony",
        "best_price": 2499.0,
        "original_price": 2999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 17,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/p/s/ps5-pro_1000x1000_01.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Nueva PlayStation 5 con chasis 30% m\u00e1s reducido, SSD ultrarr\u00e1pido de 1TB integrado, lector de discos Ultra HD Blu-ray y mando DualSense con respuesta h\u00e1ptica.",
        "features_json": "[\"SSD personalizado de 1 TB a 5.5 GB/s\", \"Trazado de rayos acelerado por hardware y soporte 4K a 120Hz\", \"Mando inal\u00e1mbrico DualSense con gatillos adaptativos\", \"Audio 3D Tempest\", \"Lector de discos Ultra HD Blu-ray extra\u00edble\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Capacidad\": \"1 TB SSD NVMe\", \"Procesador\": \"AMD Zen 2 de 8 n\u00facleos a 3.5 GHz\", \"Gr\u00e1ficos\": \"AMD RDNA 2 con 10.3 TFLOPs\", \"Salida de video\": \"HDMI 2.1 con VRR y ALLM\"}",
        "is_favorite": 0,
        "historical_min_price": 2499.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_nintendo_switch_oled",
        "title": "Consola Nintendo Switch OLED 64GB Joy-Con Blanco",
        "category": "Gaming",
        "brand": "Nintendo",
        "best_price": 1399.0,
        "original_price": 1799.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 22,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/134746_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Consola h\u00edbrida con vibrante pantalla OLED de 7 pulgadas, soporte ajustable ancho, base con puerto LAN Ethernet con cable y 64GB de almacenamiento interno.",
        "features_json": "[\"Pantalla: 7.0\\\" OLED con colores vivos y contraste infinito\", \"Soporte ajustable amplio para modo sobremesa\", \"Base con puerto LAN Ethernet por cable integrado\", \"Almacenamiento interno de 64 GB expandible con microSD\", \"Audio mejorado en modo port\u00e1til y sobremesa\"]",
        "tech_specs_json": "{\"Marca\": \"Nintendo\", \"Pantalla\": \"7.0\\\" OLED t\u00e1ctil capacitiva\", \"Resoluci\u00f3n port\u00e1til\": \"1280 x 720 (hasta 1080p en TV)\", \"Almacenamiento\": \"64 GB\", \"Bater\u00eda\": \"Hasta 9 horas de juego\"}",
        "is_favorite": 0,
        "historical_min_price": 1399.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_epson_l3250",
        "title": "Impresora Multifuncional Epson EcoTank L3250 Wi-Fi Tanque de Tinta",
        "category": "Impresoras",
        "brand": "Epson",
        "best_price": 749.0,
        "original_price": 999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 25,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/m/impresora_multifuncional_l5590_epson_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Multifuncional 3 en 1 con sistema de tanque de tinta EcoTank de costo ultrabajo, conectividad Wi-Fi y Wi-Fi Direct y aplicaci\u00f3n Smart Panel.",
        "features_json": "[\"Costo de impresi\u00f3n ultra bajo con botellas de tinta de alto rendimiento\", \"Imprime hasta 4500 p\u00e1ginas en negro o 7500 p\u00e1ginas a color con un kit\", \"Conectividad Wi-Fi, Wi-Fi Direct y USB de alta velocidad\", \"Tecnolog\u00eda Heat-Free de Epson sin calor para mayor durabilidad\", \"Esc\u00e1ner plano de cama de 1200 x 2400 dpi\"]",
        "tech_specs_json": "{\"Marca\": \"Epson\", \"Tipo de impresi\u00f3n\": \"Inyecci\u00f3n de tinta continua EcoTank\", \"Funciones\": \"Imprime, copia, escanea\", \"Velocidad\": \"Hasta 33 ppm en negro y 15 ppm a color\", \"Conectividad\": \"Wi-Fi, Wi-Fi Direct, USB\"}",
        "is_favorite": 0,
        "historical_min_price": 749.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
    {
        "id": "prod_sony_alpha_7_iv",
        "title": "C\u00e1mara Mirrorless Sony Alpha 7 IV Full-Frame (Cuerpo)",
        "category": "C\u00e1maras",
        "brand": "Sony",
        "best_price": 9499.0,
        "original_price": 10999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 14,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/1/117167_1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "C\u00e1mara h\u00edbrida todoterreno con sensor CMOS Exmor R retroiluminado de 33MP, procesador BIONZ XR y grabaci\u00f3n de video 4K a 60p en 10 bits 4:2:2.",
        "features_json": "[\"Sensor Full-Frame Exmor R de 33 MP retroiluminado\", \"Procesador de imagen BIONZ XR 8 veces m\u00e1s r\u00e1pido\", \"Enfoque autom\u00e1tico h\u00edbrido r\u00e1pido con 759 puntos AF y Real-time Eye AF para humanos, animales y aves\", \"Grabaci\u00f3n de video 4K 60p en 10-bit 4:2:2 con perfil S-Cinetone\", \"Estabilizaci\u00f3n de imagen \u00f3ptica en el cuerpo (IBIS) de 5.5 pasos\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Sensor\": \"Full-Frame (35.9 x 23.9 mm) 33 MP\", \"Montura\": \"Sony E-Mount\", \"Estabilizador\": \"IBIS de 5 ejes 5.5 pasos\", \"Video\": \"4K 60p 10-bit 4:2:2\", \"Visor\": \"OLED electr\u00f3nico de 3.68 millones de puntos\"}",
        "is_favorite": 0,
        "historical_min_price": 9499.0,
        "is_historical_min": 1,
        "created_at": "2026-10-22 15:00:00",
        "updated_at": "2026-10-31 12:00:00"
    },
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
        "last_scraped_at": "2026-10-31 12:00:00"
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
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 3,
        "product_id": "prod_samsung_s25_ultra",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4199.0,
        "original_price": 6899.0,
        "offer_url": "https://hiraoka.com.pe/samsung-galaxy-s25-ultra-512gb-titanium-gray",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 4,
        "product_id": "prod_iphone_16",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3399.0,
        "original_price": 3999.0,
        "offer_url": "https://hiraoka.com.pe/iphone-16-6-1-128gb-negro",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 5,
        "product_id": "prod_iphone_16",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3399.0,
        "original_price": 4499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/prod18120095/iPhone-16-128GB/20687062",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 6,
        "product_id": "prod_iphone_16",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3399.0,
        "original_price": 4299.0,
        "offer_url": "https://simple.ripley.com.pe/iphone-16-128gb-2065365819351",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 7,
        "product_id": "prod_iphone_16",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3499.0,
        "original_price": 4299.0,
        "offer_url": "https://www.efe.com.pe/iphone-16-blk-128gb-bes-mye73be-a.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 8,
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1829.0,
        "original_price": 1999.0,
        "offer_url": "https://hiraoka.com.pe/celular-libre-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-blue",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 9,
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1899.0,
        "original_price": 2099.0,
        "offer_url": "https://www.efe.com.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 10,
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 1899.0,
        "original_price": 2099.0,
        "offer_url": "https://www.lacuracao.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 11,
        "product_id": "prod_motorola_edge_50",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1899.0,
        "original_price": 2499.0,
        "offer_url": "https://hiraoka.com.pe/celular-libre-motorola-edge-50-pro-5g-6-7-512gb-12gb-ram-negro",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 12,
        "product_id": "prod_motorola_edge_50",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1949.0,
        "original_price": 2599.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/132483842/Motorola-Edge-50-Pro-5G-512GB/132483843",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 13,
        "product_id": "prod_motorola_edge_50",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1999.0,
        "original_price": 2699.0,
        "offer_url": "https://simple.ripley.com.pe/motorola-edge-50-pro-5g-512gb-12gb-ram-negro-2065324901",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 14,
        "product_id": "prod_macbook_air_m5",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5899.0,
        "original_price": 6499.0,
        "offer_url": "https://hiraoka.com.pe/macbook-air-de-13-chip-m5-16gb-ram-disco-solido-de-512gb-azul-cielo",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 15,
        "product_id": "prod_macbook_air_m5",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5899.0,
        "original_price": 6499.0,
        "offer_url": "https://www.efe.com.pe/macbook-air-13-6-m5-16gb-512gb-silver-mdh74e-a.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 16,
        "product_id": "prod_macbook_air_m5",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5899.0,
        "original_price": 6499.0,
        "offer_url": "https://www.lacuracao.pe/macbook-air-13-6-m5-16gb-512gb-silver-mdh74e-a.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 17,
        "product_id": "prod_asus_zenbook_14",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4699.0,
        "original_price": 5499.0,
        "offer_url": "https://hiraoka.com.pe/laptop-asus-zenbook-14-oled-intel-core-ultra-7-16gb-ram-1tb-ssd-14-ux3405ma-pp288w",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 18,
        "product_id": "prod_asus_zenbook_14",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4799.0,
        "original_price": 5699.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/129849201/Laptop-Asus-Zenbook-14-OLED-Ultra-7/129849202",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 19,
        "product_id": "prod_asus_zenbook_14",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4899.0,
        "original_price": 5799.0,
        "offer_url": "https://simple.ripley.com.pe/laptop-asus-zenbook-14-oled-intel-ultra-7-1tb-ssd-2004319201",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 20,
        "product_id": "prod_lenovo_ideapad_slim",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2499.0,
        "original_price": 3199.0,
        "offer_url": "https://hiraoka.com.pe/laptop-lenovo-ideapad-slim-3-15abr8-15-6-amd-ryzen-7-16gb-ram-disco-solido-512gb-abys-blue",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 21,
        "product_id": "prod_lenovo_ideapad_slim",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2549.0,
        "original_price": 3299.0,
        "offer_url": "https://www.efe.com.pe/laptop-lenovo-ideapad-slim-3-15-6-ryzen-7-16gb-512gb.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 22,
        "product_id": "prod_lenovo_ideapad_slim",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2599.0,
        "original_price": 3399.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/128394812/Lenovo-IdeaPad-Slim-3-15.6-Ryzen-7/128394813",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 23,
        "product_id": "prod_lg_oled_tv",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3799.0,
        "original_price": 4999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 24,
        "product_id": "prod_lg_oled_tv",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3799.0,
        "original_price": 4999.0,
        "offer_url": "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 25,
        "product_id": "prod_lg_oled_tv",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3899.0,
        "original_price": 4999.0,
        "offer_url": "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 26,
        "product_id": "prod_lg_oled_tv",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5139.0,
        "original_price": 6769.0,
        "offer_url": "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 27,
        "product_id": "prod_lg_oled_tv",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5139.0,
        "original_price": 6769.0,
        "offer_url": "https://www.lacuracao.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 28,
        "product_id": "prod_samsung_neo_qled_65",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4499.0,
        "original_price": 6499.0,
        "offer_url": "https://hiraoka.com.pe/televisor-samsung-65-neo-qled-4k-qn85d-smart-tv-qn65qn85dlagxpe",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 29,
        "product_id": "prod_samsung_neo_qled_65",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4599.0,
        "original_price": 6799.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/131984210/Samsung-65-Neo-QLED-4K-QN85D/131984211",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 30,
        "product_id": "prod_samsung_neo_qled_65",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4699.0,
        "original_price": 6999.0,
        "offer_url": "https://simple.ripley.com.pe/smart-tv-samsung-65-neo-qled-qn85d-4k-2018318291",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 31,
        "product_id": "prod_tcl_miniled_55",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2299.0,
        "original_price": 3299.0,
        "offer_url": "https://hiraoka.com.pe/televisor-tcl-55-qd-mini-led-4k-google-tv-55c755",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 32,
        "product_id": "prod_tcl_miniled_55",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2399.0,
        "original_price": 3499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/128392180/TCL-55-Mini-LED-4K-C755/128392181",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 33,
        "product_id": "prod_tcl_miniled_55",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2449.0,
        "original_price": 3599.0,
        "offer_url": "https://simple.ripley.com.pe/smart-tv-tcl-55-mini-led-google-tv-55c755-2018329181",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 34,
        "product_id": "prod_ipad_11",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1899.0,
        "original_price": 2599.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 35,
        "product_id": "prod_ipad_11",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 1899.0,
        "original_price": 2599.0,
        "offer_url": "https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 36,
        "product_id": "prod_ipad_11",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1949.0,
        "original_price": 2299.0,
        "offer_url": "https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wifi-128gb-plata",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 37,
        "product_id": "prod_ipad_11",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1979.0,
        "original_price": 2989.0,
        "offer_url": "https://www.efe.com.pe/ipad-a16-wi-fi-md4e4ll-a-11-128gb-6gb-p26513743.html",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 38,
        "product_id": "prod_samsung_tab_s10",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3699.0,
        "original_price": 4599.0,
        "offer_url": "https://hiraoka.com.pe/tablet-samsung-galaxy-tab-s10-plus-12-4-256gb-12gb-ram-silver",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 39,
        "product_id": "prod_samsung_tab_s10",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3799.0,
        "original_price": 4699.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/132891021/Samsung-Galaxy-Tab-S10-Plus-256GB/132891022",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 40,
        "product_id": "prod_samsung_tab_s10",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3899.0,
        "original_price": 4799.0,
        "offer_url": "https://simple.ripley.com.pe/tablet-samsung-galaxy-tab-s10-plus-256gb-silver-2065319801",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 41,
        "product_id": "prod_xiaomi_pad_6",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1299.0,
        "original_price": 1699.0,
        "offer_url": "https://hiraoka.com.pe/tablet-xiaomi-pad-6-11-256gb-8gb-ram-gravity-gray",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 42,
        "product_id": "prod_xiaomi_pad_6",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1349.0,
        "original_price": 1799.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/123984102/Xiaomi-Pad-6-256GB-8GB/123984103",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 43,
        "product_id": "prod_xiaomi_pad_6",
        "store_id": "coolbox",
        "store_name": "Coolbox",
        "price": 1399.0,
        "original_price": 1849.0,
        "offer_url": "https://www.coolbox.pe/tablet-xiaomi-pad-6-256gb-gray/p",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 44,
        "product_id": "prod_sony_wh1000xm5",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1299.0,
        "original_price": 1699.0,
        "offer_url": "https://hiraoka.com.pe/audifonos-sony-wh-1000xm5-noise-cancelling-negro",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 45,
        "product_id": "prod_sony_wh1000xm5",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1349.0,
        "original_price": 1749.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18491201/Audifonos-Sony-WH-1000XM5-Negro/18491202",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 46,
        "product_id": "prod_sony_wh1000xm5",
        "store_id": "coolbox",
        "store_name": "Coolbox",
        "price": 1399.0,
        "original_price": 1799.0,
        "offer_url": "https://www.coolbox.pe/audifonos-sony-wh-1000xm5-negro/p",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 47,
        "product_id": "prod_sony_wh1000xm5",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1399.0,
        "original_price": 1899.0,
        "offer_url": "https://simple.ripley.com.pe/audifonos-sony-wh-1000xm5-bluetooth-negro-2023281928",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 48,
        "product_id": "prod_airpods_pro_2",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 899.0,
        "original_price": 1199.0,
        "offer_url": "https://hiraoka.com.pe/audifonos-apple-airpods-pro-2-generacion-con-estuche-magsafe-usb-c",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 49,
        "product_id": "prod_airpods_pro_2",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 949.0,
        "original_price": 1249.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18129012/AirPods-Pro-2da-Gen-USB-C/18129013",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 50,
        "product_id": "prod_airpods_pro_2",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 999.0,
        "original_price": 1299.0,
        "offer_url": "https://simple.ripley.com.pe/audifonos-apple-airpods-pro-2-generacion-usb-c-206530182",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 51,
        "product_id": "prod_airpods_pro_2",
        "store_id": "coolbox",
        "store_name": "Coolbox",
        "price": 999.0,
        "original_price": 1299.0,
        "offer_url": "https://www.coolbox.pe/audifonos-apple-airpods-pro-2da-gen-usb-c/p",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 52,
        "product_id": "prod_ps5_slim",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2499.0,
        "original_price": 2999.0,
        "offer_url": "https://hiraoka.com.pe/consola-playstation-5-slim-con-lector-1tb-blanco",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 53,
        "product_id": "prod_ps5_slim",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2549.0,
        "original_price": 3099.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/129840129/Consola-PlayStation-5-Slim-1TB/129840130",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 54,
        "product_id": "prod_ps5_slim",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2599.0,
        "original_price": 3199.0,
        "offer_url": "https://simple.ripley.com.pe/consola-playstation-5-slim-1tb-con-lector-208431920",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 55,
        "product_id": "prod_ps5_slim",
        "store_id": "coolbox",
        "store_name": "Coolbox",
        "price": 2599.0,
        "original_price": 3199.0,
        "offer_url": "https://www.coolbox.pe/consola-ps5-slim-1tb-con-lector/p",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 56,
        "product_id": "prod_nintendo_switch_oled",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1399.0,
        "original_price": 1799.0,
        "offer_url": "https://hiraoka.com.pe/consola-nintendo-switch-oled-joy-con-blanco",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 57,
        "product_id": "prod_nintendo_switch_oled",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1449.0,
        "original_price": 1849.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18239012/Nintendo-Switch-OLED-Blanco/18239013",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 58,
        "product_id": "prod_nintendo_switch_oled",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1499.0,
        "original_price": 1899.0,
        "offer_url": "https://simple.ripley.com.pe/consola-nintendo-switch-oled-blanco-206528192",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 59,
        "product_id": "prod_nintendo_switch_oled",
        "store_id": "coolbox",
        "store_name": "Coolbox",
        "price": 1499.0,
        "original_price": 1899.0,
        "offer_url": "https://www.coolbox.pe/consola-nintendo-switch-oled-blanco/p",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 60,
        "product_id": "prod_epson_l3250",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 749.0,
        "original_price": 999.0,
        "offer_url": "https://hiraoka.com.pe/impresora-multifuncional-epson-ecotank-l3250-wi-fi",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 61,
        "product_id": "prod_epson_l3250",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 779.0,
        "original_price": 1049.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18192031/Impresora-Epson-EcoTank-L3250/18192032",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 62,
        "product_id": "prod_epson_l3250",
        "store_id": "coolbox",
        "store_name": "Coolbox",
        "price": 799.0,
        "original_price": 1099.0,
        "offer_url": "https://www.coolbox.pe/impresora-epson-ecotank-l3250-wifi/p",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 63,
        "product_id": "prod_epson_l3250",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 799.0,
        "original_price": 1099.0,
        "offer_url": "https://simple.ripley.com.pe/impresora-multifuncional-epson-ecotank-l3250-202328192",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 64,
        "product_id": "prod_sony_alpha_7_iv",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 9499.0,
        "original_price": 10999.0,
        "offer_url": "https://hiraoka.com.pe/camara-mirrorless-sony-alpha-7-iv-ilce-7m4-cuerpo",
        "is_best_price": 1,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 65,
        "product_id": "prod_sony_alpha_7_iv",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 9699.0,
        "original_price": 11499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18293012/Camara-Sony-Alpha-7-IV-Cuerpo/18293013",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
    {
        "id": 66,
        "product_id": "prod_sony_alpha_7_iv",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 9899.0,
        "original_price": 11899.0,
        "offer_url": "https://simple.ripley.com.pe/camara-sony-alpha-7-iv-mirrorless-cuerpo-20653198",
        "is_best_price": 0,
        "last_scraped_at": "2026-10-31 12:00:00"
    },
]

SEED_PRICE_HISTORY = [
    {
        "id": 1,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3799.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 2,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 3799.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 3,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 3916.35,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 4,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 3975.02,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 5,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 4033.7,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 6,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 4092.37,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 7,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 4151.05,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 8,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 4209.72,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 9,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 4254.88,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 10,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 4254.88,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 11,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 4254.88,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 12,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 4254.88,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 13,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 4254.88,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 14,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 4254.88,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 15,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 4254.88,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 16,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 4254.88,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 17,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 4254.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 18,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 4254.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 19,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 4254.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 20,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 4254.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 21,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 4254.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 22,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 4254.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 23,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 4254.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 24,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 4254.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 25,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 4254.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 26,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 4254.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 27,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 4254.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 28,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 4254.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 29,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 4254.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 30,
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 4254.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 31,
        "product_id": "prod_iphone_16",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3399.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 32,
        "product_id": "prod_iphone_16",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 3399.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 33,
        "product_id": "prod_iphone_16",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 3433.0,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 34,
        "product_id": "prod_iphone_16",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 3450.0,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 35,
        "product_id": "prod_iphone_16",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 3467.0,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 36,
        "product_id": "prod_iphone_16",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 3484.0,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 37,
        "product_id": "prod_iphone_16",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 3501.0,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 38,
        "product_id": "prod_iphone_16",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 3517.99,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 39,
        "product_id": "prod_iphone_16",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 3534.99,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 40,
        "product_id": "prod_iphone_16",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 3551.99,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 41,
        "product_id": "prod_iphone_16",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 3568.99,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 42,
        "product_id": "prod_iphone_16",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 3585.99,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 43,
        "product_id": "prod_iphone_16",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 3602.99,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 44,
        "product_id": "prod_iphone_16",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 3619.99,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 45,
        "product_id": "prod_iphone_16",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 3636.99,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 46,
        "product_id": "prod_iphone_16",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 3653.99,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 47,
        "product_id": "prod_iphone_16",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 3670.99,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 48,
        "product_id": "prod_iphone_16",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 3687.99,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 49,
        "product_id": "prod_iphone_16",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 3704.99,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 50,
        "product_id": "prod_iphone_16",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 3721.99,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 51,
        "product_id": "prod_iphone_16",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 3738.98,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 52,
        "product_id": "prod_iphone_16",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 3755.98,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 53,
        "product_id": "prod_iphone_16",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 3772.98,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 54,
        "product_id": "prod_iphone_16",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 3789.98,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 55,
        "product_id": "prod_iphone_16",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 3806.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 56,
        "product_id": "prod_iphone_16",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 3806.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 57,
        "product_id": "prod_iphone_16",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 3806.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 58,
        "product_id": "prod_iphone_16",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 3806.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 59,
        "product_id": "prod_iphone_16",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 3806.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 60,
        "product_id": "prod_iphone_16",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 3806.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 61,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1829.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 62,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 1829.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 63,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 1839.37,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 64,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 1844.55,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 65,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 1849.74,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 66,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 1854.92,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 67,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 1860.11,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 68,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 1865.29,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 69,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 1870.48,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 70,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 1875.66,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 71,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 1880.85,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 72,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 1886.03,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 73,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 1891.22,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 74,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 1896.4,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 75,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 1901.59,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 76,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 1906.77,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 77,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 1911.96,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 78,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 1917.14,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 79,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 1922.33,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 80,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 1927.51,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 81,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 1932.7,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 82,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 1937.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 83,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 1943.06,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 84,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 1948.25,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 85,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 1953.43,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 86,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 1958.62,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 87,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 1963.8,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 88,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 1968.99,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 89,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 1974.17,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 90,
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 1979.36,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 91,
        "product_id": "prod_motorola_edge_50",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1899.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 92,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 1899.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 93,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 1929.4,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 94,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 1944.59,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 95,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 1959.79,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 96,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 1974.99,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 97,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 1990.19,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 98,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 2005.39,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 99,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 2020.58,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 100,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 2035.78,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 101,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 2050.98,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 102,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 2066.18,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 103,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 2081.38,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 104,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 2096.58,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 105,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 2111.77,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 106,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 2126.88,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 107,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 2126.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 108,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 2126.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 109,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 2126.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 110,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 2126.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 111,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 2126.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 112,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 2126.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 113,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 2126.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 114,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 2126.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 115,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 2126.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 116,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 2126.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 117,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 2126.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 118,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 2126.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 119,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 2126.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 120,
        "product_id": "prod_motorola_edge_50",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 2126.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 121,
        "product_id": "prod_macbook_air_m5",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5899.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 122,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 5899.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 123,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 5935.31,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 124,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 5953.46,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 125,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 5971.61,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 126,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 5989.77,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 127,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 6007.92,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 128,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 6026.07,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 129,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 6044.23,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 130,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 6062.38,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 131,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 6080.54,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 132,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 6098.69,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 133,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 6116.84,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 134,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 6135.0,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 135,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 6153.15,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 136,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 6171.3,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 137,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 6189.46,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 138,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 6207.61,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 139,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 6225.76,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 140,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 6243.92,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 141,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 6262.07,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 142,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 6280.22,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 143,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 6298.38,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 144,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 6316.53,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 145,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 6334.69,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 146,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 6352.84,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 147,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 6370.99,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 148,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 6389.15,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 149,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 6407.3,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 150,
        "product_id": "prod_macbook_air_m5",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 6425.45,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 151,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4699.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 152,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 4699.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 153,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 4744.57,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 154,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 4767.36,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 155,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 4790.15,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 156,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 4812.94,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 157,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 4835.72,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 158,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 4858.51,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 159,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 4881.3,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 160,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 4904.08,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 161,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 4926.87,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 162,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 4949.66,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 163,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 4972.45,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 164,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 4995.23,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 165,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 5018.02,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 166,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 5040.81,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 167,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 5063.59,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 168,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 5086.38,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 169,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 5109.17,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 170,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 5131.96,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 171,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 5154.74,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 172,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 5177.53,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 173,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 5200.32,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 174,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 5223.1,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 175,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 5245.89,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 176,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 5262.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 177,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 5262.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 178,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 5262.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 179,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 5262.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 180,
        "product_id": "prod_asus_zenbook_14",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 5262.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 181,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 182,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 2499.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 183,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 2535.46,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 184,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 2553.68,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 185,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 2571.91,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 186,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 2590.14,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 187,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 2608.37,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 188,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 2626.59,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 189,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 2644.82,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 190,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 2663.05,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 191,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 2681.28,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 192,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 2699.5,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 193,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 2717.73,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 194,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 2735.96,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 195,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 2754.19,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 196,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 2772.41,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 197,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 2790.64,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 198,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 2798.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 199,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 2798.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 200,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 2798.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 201,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 2798.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 202,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 2798.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 203,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 2798.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 204,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 2798.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 205,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 2798.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 206,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 2798.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 207,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 2798.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 208,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 2798.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 209,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 2798.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 210,
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 2798.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 211,
        "product_id": "prod_lg_oled_tv",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3799.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 212,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 3799.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 213,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 3859.8,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 214,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 3890.19,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 215,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 3920.59,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 216,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 3950.99,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 217,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 3981.39,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 218,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 4011.79,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 219,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 4042.18,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 220,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 4072.58,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 221,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 4102.98,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 222,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 4133.38,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 223,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 4163.78,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 224,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 4194.18,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 225,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 4224.57,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 226,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 4254.88,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 227,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 4254.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 228,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 4254.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 229,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 4254.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 230,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 4254.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 231,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 4254.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 232,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 4254.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 233,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 4254.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 234,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 4254.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 235,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 4254.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 236,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 4254.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 237,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 4254.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 238,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 4254.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 239,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 4254.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 240,
        "product_id": "prod_lg_oled_tv",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 4254.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 241,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4499.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 242,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 4499.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 243,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 4591.3,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 244,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 4637.45,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 245,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 4683.6,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 246,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 4729.75,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 247,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 4775.9,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 248,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 4822.05,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 249,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 4868.21,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 250,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 4914.36,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 251,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 4960.51,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 252,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 5006.66,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 253,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 5038.88,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 254,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 5038.88,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 255,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 5038.88,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 256,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 5038.88,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 257,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 5038.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 258,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 5038.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 259,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 5038.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 260,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 5038.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 261,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 5038.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 262,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 5038.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 263,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 5038.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 264,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 5038.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 265,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 5038.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 266,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 5038.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 267,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 5038.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 268,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 5038.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 269,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 5038.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 270,
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 5038.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 271,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2299.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 272,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 2299.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 273,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 2345.46,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 274,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 2368.69,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 275,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 2391.92,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 276,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 2415.15,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 277,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 2438.38,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 278,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 2461.6,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 279,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 2484.83,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 280,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 2508.06,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 281,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 2531.29,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 282,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 2554.52,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 283,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 2574.88,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 284,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 2574.88,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 285,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 2574.88,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 286,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 2574.88,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 287,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 2574.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 288,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 2574.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 289,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 2574.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 290,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 2574.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 291,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 2574.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 292,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 2574.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 293,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 2574.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 294,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 2574.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 295,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 2574.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 296,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 2574.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 297,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 2574.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 298,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 2574.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 299,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 2574.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 300,
        "product_id": "prod_tcl_miniled_55",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 2574.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 301,
        "product_id": "prod_ipad_11",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1899.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 302,
        "product_id": "prod_ipad_11",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 1899.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 303,
        "product_id": "prod_ipad_11",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 1933.1,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 304,
        "product_id": "prod_ipad_11",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 1950.15,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 305,
        "product_id": "prod_ipad_11",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 1967.2,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 306,
        "product_id": "prod_ipad_11",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 1984.24,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 307,
        "product_id": "prod_ipad_11",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 2001.29,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 308,
        "product_id": "prod_ipad_11",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 2018.34,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 309,
        "product_id": "prod_ipad_11",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 2035.39,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 310,
        "product_id": "prod_ipad_11",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 2052.44,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 311,
        "product_id": "prod_ipad_11",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 2069.49,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 312,
        "product_id": "prod_ipad_11",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 2086.54,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 313,
        "product_id": "prod_ipad_11",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 2103.59,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 314,
        "product_id": "prod_ipad_11",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 2120.64,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 315,
        "product_id": "prod_ipad_11",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 2126.88,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 316,
        "product_id": "prod_ipad_11",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 2126.88,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 317,
        "product_id": "prod_ipad_11",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 2126.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 318,
        "product_id": "prod_ipad_11",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 2126.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 319,
        "product_id": "prod_ipad_11",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 2126.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 320,
        "product_id": "prod_ipad_11",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 2126.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 321,
        "product_id": "prod_ipad_11",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 2126.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 322,
        "product_id": "prod_ipad_11",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 2126.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 323,
        "product_id": "prod_ipad_11",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 2126.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 324,
        "product_id": "prod_ipad_11",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 2126.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 325,
        "product_id": "prod_ipad_11",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 2126.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 326,
        "product_id": "prod_ipad_11",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 2126.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 327,
        "product_id": "prod_ipad_11",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 2126.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 328,
        "product_id": "prod_ipad_11",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 2126.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 329,
        "product_id": "prod_ipad_11",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 2126.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 330,
        "product_id": "prod_ipad_11",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 2126.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 331,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3699.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 332,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 3699.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 333,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 3747.26,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 334,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 3771.39,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 335,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 3795.52,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 336,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 3819.65,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 337,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 3843.77,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 338,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 3867.9,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 339,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 3892.03,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 340,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 3916.16,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 341,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 3940.29,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 342,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 3964.42,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 343,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 3988.55,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 344,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 4012.68,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 345,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 4036.81,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 346,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 4060.94,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 347,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 4085.07,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 348,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 4109.2,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 349,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 4133.32,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 350,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 4142.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 351,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 4142.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 352,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 4142.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 353,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 4142.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 354,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 4142.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 355,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 4142.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 356,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 4142.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 357,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 4142.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 358,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 4142.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 359,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 4142.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 360,
        "product_id": "prod_samsung_tab_s10",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 4142.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 361,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1299.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 362,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 1299.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 363,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 1319.39,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 364,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 1329.58,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 365,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 1339.78,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 366,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 1349.97,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 367,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 1360.17,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 368,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 1370.36,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 369,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 1380.55,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 370,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 1390.75,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 371,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 1400.94,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 372,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 1411.14,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 373,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 1421.33,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 374,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 1431.53,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 375,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 1441.72,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 376,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 1451.91,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 377,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 1454.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 378,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 1454.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 379,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 1454.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 380,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 1454.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 381,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 1454.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 382,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 1454.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 383,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 1454.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 384,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 1454.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 385,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 1454.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 386,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 1454.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 387,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 1454.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 388,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 1454.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 389,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 1454.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 390,
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 1454.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 391,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1299.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 392,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 1299.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 393,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 1319.39,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 394,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 1329.58,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 395,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 1339.78,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 396,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 1349.97,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 397,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 1360.17,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 398,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 1370.36,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 399,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 1380.55,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 400,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 1390.75,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 401,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 1400.94,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 402,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 1411.14,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 403,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 1421.33,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 404,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 1431.53,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 405,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 1441.72,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 406,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 1451.91,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 407,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 1454.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 408,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 1454.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 409,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 1454.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 410,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 1454.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 411,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 1454.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 412,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 1454.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 413,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 1454.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 414,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 1454.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 415,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 1454.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 416,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 1454.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 417,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 1454.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 418,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 1454.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 419,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 1454.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 420,
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 1454.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 421,
        "product_id": "prod_airpods_pro_2",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 899.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 422,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 899.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 423,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 914.0,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 424,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 921.49,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 425,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 928.99,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 426,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 936.49,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 427,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 943.99,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 428,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 951.49,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 429,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 958.98,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 430,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 966.48,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 431,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 973.98,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 432,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 981.48,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 433,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 988.97,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 434,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 996.47,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 435,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 1003.97,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 436,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 1006.88,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 437,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 1006.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 438,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 1006.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 439,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 1006.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 440,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 1006.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 441,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 1006.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 442,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 1006.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 443,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 1006.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 444,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 1006.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 445,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 1006.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 446,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 1006.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 447,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 1006.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 448,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 1006.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 449,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 1006.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 450,
        "product_id": "prod_airpods_pro_2",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 1006.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 451,
        "product_id": "prod_ps5_slim",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 452,
        "product_id": "prod_ps5_slim",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 2499.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 453,
        "product_id": "prod_ps5_slim",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 2526.78,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 454,
        "product_id": "prod_ps5_slim",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 2540.66,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 455,
        "product_id": "prod_ps5_slim",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 2554.55,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 456,
        "product_id": "prod_ps5_slim",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 2568.44,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 457,
        "product_id": "prod_ps5_slim",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 2582.33,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 458,
        "product_id": "prod_ps5_slim",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 2596.22,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 459,
        "product_id": "prod_ps5_slim",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 2610.1,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 460,
        "product_id": "prod_ps5_slim",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 2623.99,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 461,
        "product_id": "prod_ps5_slim",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 2637.88,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 462,
        "product_id": "prod_ps5_slim",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 2651.77,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 463,
        "product_id": "prod_ps5_slim",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 2665.66,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 464,
        "product_id": "prod_ps5_slim",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 2679.54,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 465,
        "product_id": "prod_ps5_slim",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 2693.43,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 466,
        "product_id": "prod_ps5_slim",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 2707.32,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 467,
        "product_id": "prod_ps5_slim",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 2721.21,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 468,
        "product_id": "prod_ps5_slim",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 2735.1,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 469,
        "product_id": "prod_ps5_slim",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 2748.98,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 470,
        "product_id": "prod_ps5_slim",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 2762.87,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 471,
        "product_id": "prod_ps5_slim",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 2776.76,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 472,
        "product_id": "prod_ps5_slim",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 2790.65,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 473,
        "product_id": "prod_ps5_slim",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 2798.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 474,
        "product_id": "prod_ps5_slim",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 2798.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 475,
        "product_id": "prod_ps5_slim",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 2798.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 476,
        "product_id": "prod_ps5_slim",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 2798.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 477,
        "product_id": "prod_ps5_slim",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 2798.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 478,
        "product_id": "prod_ps5_slim",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 2798.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 479,
        "product_id": "prod_ps5_slim",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 2798.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 480,
        "product_id": "prod_ps5_slim",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 2798.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 481,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1399.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 482,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 1399.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 483,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 1419.74,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 484,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 1430.11,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 485,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 1440.47,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 486,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 1450.84,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 487,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 1461.21,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 488,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 1471.58,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 489,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 1481.95,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 490,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 1492.32,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 491,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 1502.69,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 492,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 1513.06,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 493,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 1523.42,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 494,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 1533.79,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 495,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 1544.16,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 496,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 1554.53,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 497,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 1564.9,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 498,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 1566.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 499,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 1566.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 500,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 1566.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 501,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 1566.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 502,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 1566.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 503,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 1566.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 504,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 1566.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 505,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 1566.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 506,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 1566.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 507,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 1566.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 508,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 1566.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 509,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 1566.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 510,
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 1566.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 511,
        "product_id": "prod_epson_l3250",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 749.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 512,
        "product_id": "prod_epson_l3250",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 749.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 513,
        "product_id": "prod_epson_l3250",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 761.5,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 514,
        "product_id": "prod_epson_l3250",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 767.74,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 515,
        "product_id": "prod_epson_l3250",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 773.99,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 516,
        "product_id": "prod_epson_l3250",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 780.24,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 517,
        "product_id": "prod_epson_l3250",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 786.49,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 518,
        "product_id": "prod_epson_l3250",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 792.74,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 519,
        "product_id": "prod_epson_l3250",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 798.98,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 520,
        "product_id": "prod_epson_l3250",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 805.23,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 521,
        "product_id": "prod_epson_l3250",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 811.48,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 522,
        "product_id": "prod_epson_l3250",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 817.73,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 523,
        "product_id": "prod_epson_l3250",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 823.97,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 524,
        "product_id": "prod_epson_l3250",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 830.22,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 525,
        "product_id": "prod_epson_l3250",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 836.47,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 526,
        "product_id": "prod_epson_l3250",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 838.88,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 527,
        "product_id": "prod_epson_l3250",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 838.88,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 528,
        "product_id": "prod_epson_l3250",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 838.88,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 529,
        "product_id": "prod_epson_l3250",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 838.88,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 530,
        "product_id": "prod_epson_l3250",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 838.88,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 531,
        "product_id": "prod_epson_l3250",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 838.88,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 532,
        "product_id": "prod_epson_l3250",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 838.88,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 533,
        "product_id": "prod_epson_l3250",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 838.88,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 534,
        "product_id": "prod_epson_l3250",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 838.88,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 535,
        "product_id": "prod_epson_l3250",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 838.88,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 536,
        "product_id": "prod_epson_l3250",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 838.88,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 537,
        "product_id": "prod_epson_l3250",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 838.88,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 538,
        "product_id": "prod_epson_l3250",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 838.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 539,
        "product_id": "prod_epson_l3250",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 838.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 540,
        "product_id": "prod_epson_l3250",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 838.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
    {
        "id": 541,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 9499.0,
        "recorded_at": "2026-10-31 12:00:00"
    },
    {
        "id": 542,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -1,
        "date_label": "Ayer",
        "price": 9499.0,
        "recorded_at": "2026-10-30 12:00:00"
    },
    {
        "id": 543,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -2,
        "date_label": "-2d",
        "price": 9585.36,
        "recorded_at": "2026-10-29 12:00:00"
    },
    {
        "id": 544,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -3,
        "date_label": "-3d",
        "price": 9628.54,
        "recorded_at": "2026-10-28 12:00:00"
    },
    {
        "id": 545,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -4,
        "date_label": "-4d",
        "price": 9671.72,
        "recorded_at": "2026-10-27 12:00:00"
    },
    {
        "id": 546,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -5,
        "date_label": "-5d",
        "price": 9714.91,
        "recorded_at": "2026-10-26 12:00:00"
    },
    {
        "id": 547,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -6,
        "date_label": "-6d",
        "price": 9758.09,
        "recorded_at": "2026-10-25 12:00:00"
    },
    {
        "id": 548,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -7,
        "date_label": "-7d",
        "price": 9801.27,
        "recorded_at": "2026-10-24 12:00:00"
    },
    {
        "id": 549,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -8,
        "date_label": "-8d",
        "price": 9844.45,
        "recorded_at": "2026-10-23 12:00:00"
    },
    {
        "id": 550,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -9,
        "date_label": "-9d",
        "price": 9887.63,
        "recorded_at": "2026-10-22 12:00:00"
    },
    {
        "id": 551,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -10,
        "date_label": "-10d",
        "price": 9930.81,
        "recorded_at": "2026-10-21 12:00:00"
    },
    {
        "id": 552,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -11,
        "date_label": "-11d",
        "price": 9973.99,
        "recorded_at": "2026-10-20 12:00:00"
    },
    {
        "id": 553,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -12,
        "date_label": "-12d",
        "price": 10017.17,
        "recorded_at": "2026-10-19 12:00:00"
    },
    {
        "id": 554,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -13,
        "date_label": "-13d",
        "price": 10060.36,
        "recorded_at": "2026-10-18 12:00:00"
    },
    {
        "id": 555,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -14,
        "date_label": "-14d",
        "price": 10103.54,
        "recorded_at": "2026-10-17 12:00:00"
    },
    {
        "id": 556,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -15,
        "date_label": "-15d",
        "price": 10146.72,
        "recorded_at": "2026-10-16 12:00:00"
    },
    {
        "id": 557,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -16,
        "date_label": "-16d",
        "price": 10189.9,
        "recorded_at": "2026-10-15 12:00:00"
    },
    {
        "id": 558,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -17,
        "date_label": "-17d",
        "price": 10233.08,
        "recorded_at": "2026-10-14 12:00:00"
    },
    {
        "id": 559,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -18,
        "date_label": "-18d",
        "price": 10276.26,
        "recorded_at": "2026-10-13 12:00:00"
    },
    {
        "id": 560,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -19,
        "date_label": "-19d",
        "price": 10319.44,
        "recorded_at": "2026-10-12 12:00:00"
    },
    {
        "id": 561,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -20,
        "date_label": "-20d",
        "price": 10362.62,
        "recorded_at": "2026-10-11 12:00:00"
    },
    {
        "id": 562,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -21,
        "date_label": "-21d",
        "price": 10405.81,
        "recorded_at": "2026-10-10 12:00:00"
    },
    {
        "id": 563,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -22,
        "date_label": "-22d",
        "price": 10448.99,
        "recorded_at": "2026-10-09 12:00:00"
    },
    {
        "id": 564,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -23,
        "date_label": "-23d",
        "price": 10492.17,
        "recorded_at": "2026-10-08 12:00:00"
    },
    {
        "id": 565,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -24,
        "date_label": "-24d",
        "price": 10535.35,
        "recorded_at": "2026-10-07 12:00:00"
    },
    {
        "id": 566,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -25,
        "date_label": "-25d",
        "price": 10578.53,
        "recorded_at": "2026-10-06 12:00:00"
    },
    {
        "id": 567,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -26,
        "date_label": "-26d",
        "price": 10621.71,
        "recorded_at": "2026-10-05 12:00:00"
    },
    {
        "id": 568,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -27,
        "date_label": "-27d",
        "price": 10638.88,
        "recorded_at": "2026-10-04 12:00:00"
    },
    {
        "id": 569,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -28,
        "date_label": "-28d",
        "price": 10638.88,
        "recorded_at": "2026-10-03 12:00:00"
    },
    {
        "id": 570,
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": -29,
        "date_label": "-29d",
        "price": 10638.88,
        "recorded_at": "2026-10-02 12:00:00"
    },
]

SEED_COMMUNITY_OFFERS = [
    {
        "id": "comm_chiclayo_xiaomi",
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
        "created_at": "2026-10-26 18:00:58"
    }
]

SEED_COMMUNITY_POSTS = [
    {
        "id": "post_chiclayo_xiaomi",
        "product_id": "prod_xiaomi_redmi_note",
        "title": "Oferta en Tiendas Efe Chiclayo Centro: Xiaomi Redmi Note 15 Pro 5G",
        "content": "Precio en liquidación de vitrina",
        "product_name": "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
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
        "created_at": "2026-10-26 18:00:58"
    }
]


async def sync_and_upsert_catalog(session: AsyncSession) -> int:
    """
    Sincronización UPSERT en Neon PostgreSQL / SQLite de alto rendimiento (< 200 ms):
    - Precarga existentes en memoria para evitar cientos de viajes de red WAN (Round Trips).
    - Actualiza si ya existe por ID o inserta si no existe.
    - Sincroniza ofertas por tienda (store_offers) e historial de precios (price_history).
    - Preserva y NO toca los datos de la comunidad ni reclamos de usuarios.
    """
    logger.info("Ejecutando sync_and_upsert_catalog de alto rendimiento...")
    now_dt = utc_now_naive()

    # Precarga en bloque (3 consultas en total en lugar de 650)
    prods_res = await session.execute(select(ProductEntity))
    existing_prods = {p.id: p for p in prods_res.scalars().all()}

    offers_res = await session.execute(select(StoreOfferEntity))
    existing_offers = {(o.product_id, o.store_id): o for o in offers_res.scalars().all()}

    hist_res = await session.execute(select(PriceHistoryEntity))
    existing_hist = {(h.product_id, h.day_offset): h for h in hist_res.scalars().all()}

    # 1. Upsert Productos
    for p in SEED_PRODUCTS:
        existing = existing_prods.get(p["id"])
        if existing:
            existing.title = p["title"]
            existing.category = p["category"]
            existing.brand = p["brand"]
            existing.best_price = p["best_price"]
            existing.original_price = p["original_price"]
            existing.best_store_name = p["best_store_name"]
            existing.discount_percentage = p["discount_percentage"]
            existing.available_stores_count = p["available_stores_count"]
            existing.image_url = p["image_url"]
            existing.description = p["description"]
            existing.features_json = p["features_json"]
            existing.tech_specs_json = p["tech_specs_json"]
            existing.historical_min_price = p.get("historical_min_price", p["best_price"])
            existing.is_historical_min = bool(p.get("is_historical_min", False))
            existing.updated_at = now_dt
        else:
            new_prod = ProductEntity(
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
                historical_min_price=p.get("historical_min_price", p["best_price"]),
                is_historical_min=bool(p.get("is_historical_min", False)),
                created_at=_parse_dt(p.get("created_at")),
                updated_at=now_dt,
            )
            session.add(new_prod)

    # 2. Upsert Ofertas por Tienda
    for o in SEED_STORE_OFFERS:
        existing_off = existing_offers.get((o["product_id"], o["store_id"]))
        if existing_off:
            existing_off.store_name = o["store_name"]
            existing_off.price = o["price"]
            existing_off.original_price = o.get("original_price")
            existing_off.offer_url = o["offer_url"]
            existing_off.is_best_price = bool(o.get("is_best_price", False))
            existing_off.last_scraped_at = now_dt
        else:
            new_off = StoreOfferEntity(
                product_id=o["product_id"],
                store_id=o["store_id"],
                store_name=o["store_name"],
                price=o["price"],
                original_price=o.get("original_price"),
                offer_url=o["offer_url"],
                is_best_price=bool(o.get("is_best_price", False)),
                last_scraped_at=now_dt,
            )
            session.add(new_off)

    # 3. Upsert Historial de Precios
    for h in SEED_PRICE_HISTORY:
        existing_h = existing_hist.get((h["product_id"], h["day_offset"]))
        if existing_h:
            existing_h.price = h["price"]
            existing_h.date_label = h["date_label"]
            existing_h.recorded_at = now_dt
        else:
            new_h = PriceHistoryEntity(
                product_id=h["product_id"],
                day_offset=h["day_offset"],
                date_label=h["date_label"],
                price=h["price"],
                recorded_at=_parse_dt(h.get("recorded_at")),
            )
            session.add(new_h)

    # 4. Asegurar ofertas comunitarias iniciales si la tabla está vacía
    c_count_q = await session.execute(select(func.count(CommunityOfferEntity.id)))
    c_count = c_count_q.scalar() or 0
    if c_count == 0:
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

    cp_count_q = await session.execute(select(func.count(CommunityPostEntity.id)))
    cp_count = cp_count_q.scalar() or 0
    if cp_count == 0:
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
    logger.info(f"sync_and_upsert_catalog completado con éxito: {len(SEED_PRODUCTS)} productos sincronizados.")
    return len(SEED_PRODUCTS)


async def seed_database_fast(session: AsyncSession) -> int:
    """Inserta o sincroniza el catálogo oficial en Neon PostgreSQL / SQLite."""
    return await sync_and_upsert_catalog(session)
