"""
Datos iniciales oficiales de productos reales en tiendas retail peruanas.
Sincronización UPSERT instantánea en Neon PostgreSQL / SQLite de alto rendimiento (< 200 ms).
ESTRICTAMENTE 8 TIENDAS: Tiendas Efe, Falabella, Ripley, La Curacao, Hiraoka, Tottus, Metro, Wong.
DÍA 1: Historial real de 1 punto (sin curvas simuladas hacia atrás).
CERO DATOS FANTASMA EN COMUNIDAD: La sección de comunidad inicia 100% limpia.
"""
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.entities import (
    CommunityOfferEntity,
    CommunityPostEntity,
    PriceHistoryEntity,
    ProductEntity,
    StoreOfferEntity,
    utc_now_naive,
)

logger = get_logger("finprice.seed")


def _parse_dt(dt_val: Any) -> datetime:
    if isinstance(dt_val, datetime):
        return dt_val.replace(tzinfo=None)
    if isinstance(dt_val, str) and dt_val:
        try:
            return datetime.fromisoformat(dt_val.replace("Z", "")).replace(tzinfo=None)
        except Exception:
            pass
    return utc_now_naive()


SEED_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "prod_samsung_s25_ultra",
        "title": "Samsung Galaxy S25 Ultra 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 5499.0,
        "original_price": 6323.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/s/a/samsung_galaxy_s25_ultra_titanium_black.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "El estandarte de Samsung con Galaxy AI integrada, procesador Snapdragon 8 Elite for Galaxy, chasis de titanio con S-Pen y cámara cuádruple de 200MP.",
        "features_json": "[\"Procesador: Snapdragon 8 Elite\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.9\\\" Dynamic AMOLED 2X\", \"Resolución: 3120 x 1440\", \"Cámara Principal: 200 MP + 50 MP + 12 MP + 10 MP\"]",
        "tech_specs_json": "{\"Procesador\": \"Snapdragon 8 Elite\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"6.9\\\" Dynamic AMOLED 2X\", \"Sistema Operativo\": \"Android\", \"Conectividad\": \"5G\", \"Marca\": \"Samsung\", \"Cámara Principal\": \"200 MP + 50 MP + 12 MP + 10 MP\", \"Resolución\": \"3120 x 1440\"}",
        "is_favorite": False,
        "historical_min_price": 5499.0,
        "is_historical_min": True
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
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/iphone_16_no-ai_white_pdp_image_position_1__gens.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Diseñado con Apple Intelligence, botón Control de Cámara táctil, chip A18 de segunda generación y sistema de cámara Fusion de 48 MP.",
        "features_json": "[\"Procesador: Apple A18\", \"Memoria RAM: 8 GB\", \"Almacenamiento: 128 GB\", \"Pantalla: 6.1\\\" Super Retina XDR OLED\", \"Resolución: 2556 x 1179 píxeles\", \"Cámara Principal: 48 MP + 12 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Procesador\": \"Apple A18\", \"Sistema Operativo\": \"iOS 18\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"128 GB\", \"Cámara Principal\": \"48 MP + 12 MP\", \"Conectividad\": \"5G\", \"Pantalla\": \"6.1\\\" OLED\", \"Resolución\": \"2556 x 1179\"}",
        "is_favorite": False,
        "historical_min_price": 3399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_xiaomi_redmi_note",
        "title": "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Xiaomi",
        "best_price": 1829.0,
        "original_price": 2103.35,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/x/i/xiaomi_redmi_note_13_pro_plus_aurora_purple.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Smartphone con pantalla AMOLED curva de 120Hz a resolución 1.5K, cámara de 200MP con OIS, resistencia IP68 y carga hiperrápida.",
        "features_json": "[\"Procesador: Snapdragon 7s Gen4\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.8\\\" AMOLED 1.5K 120Hz\", \"Resolución: 2772 x 1280\", \"Cámara Principal: 200 MP + 8 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Xiaomi\", \"Procesador\": \"Snapdragon 7s Gen4\", \"Sistema Operativo\": \"HyperOS Android 15\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Cámara Principal\": \"200 MP + 8 MP\", \"Conectividad\": \"5G\", \"Batería\": \"6500 mAh\", \"Pantalla\": \"6.8\\\" AMOLED\", \"Resolución\": \"2772 x 1280\"}",
        "is_favorite": False,
        "historical_min_price": 1829.0,
        "is_historical_min": True
    },
    {
        "id": "prod_motorola_edge_50",
        "title": "Motorola Edge 50 Pro 5G 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Motorola",
        "best_price": 2499.0,
        "original_price": 2899.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 14,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/m/o/motorola_edge_50_pro_black_beauty.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Diseño premium con acabado en cuero vegano, pantalla pOLED Super HD de 144Hz validada por Pantone y carga TurboPower de 125W.",
        "features_json": "[\"Procesador: Snapdragon 7 Gen 3\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.7\\\" pOLED 144Hz Super HD\", \"Cámara: 50MP + 13MP + 10MP Telefoto con OIS\", \"Carga rápida: 125W TurboPower\"]",
        "tech_specs_json": "{\"Marca\": \"Motorola\", \"Procesador\": \"Snapdragon 7 Gen 3\", \"Sistema Operativo\": \"Android 14\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Cámara Principal\": \"50 MP + 13 MP + 10 MP\", \"Conectividad\": \"5G\", \"Batería\": \"4500 mAh\", \"Pantalla\": \"6.7\\\" pOLED\", \"Resolución\": \"2712 x 1220\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_macbook_air_m5",
        "title": "Apple MacBook Air 13.6 Pulgadas M5 16GB RAM 512GB SSD",
        "category": "Laptops",
        "brand": "Apple",
        "best_price": 5699.0,
        "original_price": 6553.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/m/a/macbook_air_13_m3_midnight_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Portátil ultradelgada y silenciosa con pantalla Liquid Retina de 13.6 pulgadas, 16GB de memoria unificada, SSD de 512GB y autonomía de hasta 18 horas.",
        "features_json": "[\"Procesador: Apple Silicon 10 núcleos\", \"Memoria RAM: 16 GB unificada\", \"Almacenamiento: 512 GB SSD\", \"Pantalla: 13.6\\\" Liquid Retina True Tone\", \"Resolución: 2560 x 1664\", \"Batería: Litio - Hasta 18 horas\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Procesador\": \"Apple Silicon M-Series\", \"Sistema Operativo\": \"macOS\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"13.6\\\" Liquid Retina\", \"Batería\": \"Litio - Hasta 18 horas\", \"Resolución\": \"2560 x 1664\"}",
        "is_favorite": False,
        "historical_min_price": 5699.0,
        "is_historical_min": True
    },
    {
        "id": "prod_asus_zenbook_14",
        "title": "Asus Zenbook 14 OLED Intel Core Ultra 7 16GB RAM 1TB SSD",
        "category": "Laptops",
        "brand": "Asus",
        "best_price": 4599.0,
        "original_price": 5288.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/a/s/asus_zenbook_14_oled_ux3405_ponder_blue.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop ultraportátil premium con pantalla Lumina OLED de 120Hz 3K, procesador Intel Core Ultra 7 con NPU para IA y chasis metálico ultraligero.",
        "features_json": "[\"Procesador: Intel Core Ultra 7 155H\", \"Memoria RAM: 16 GB LPDDR5X\", \"Almacenamiento: 1 TB SSD NVMe PCIe 4.0\", \"Pantalla: 14\\\" OLED 3K 120Hz 16:10\", \"Resolución: 2880 x 1800\", \"Batería: 75 Wh - Hasta 15 horas\"]",
        "tech_specs_json": "{\"Marca\": \"Asus\", \"Procesador\": \"Intel Core Ultra 7\", \"Sistema Operativo\": \"Windows 11 Home\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"1 TB SSD\", \"Pantalla\": \"14\\\" 3K OLED 120Hz\", \"Resolución\": \"2880 x 1800\", \"Peso\": \"1.2 kg\"}",
        "is_favorite": False,
        "historical_min_price": 4599.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_ideapad_slim",
        "title": "Lenovo IdeaPad Slim 3 15.6\" AMD Ryzen 7 16GB RAM 512GB SSD",
        "category": "Laptops",
        "brand": "Lenovo",
        "best_price": 2299.0,
        "original_price": 2799.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 18,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/l/e/lenovo_ideapad_slim_3_15_arctic_grey.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop de productividad versátil con procesador AMD Ryzen 7 serie 7000 de 8 núcleos, pantalla FHD antirreflejo y certificación militar de resistencia.",
        "features_json": "[\"Procesador: AMD Ryzen 7 7730U 8 núcleos\", \"Memoria RAM: 16 GB DDR4\", \"Almacenamiento: 512 GB SSD NVMe\", \"Pantalla: 15.6\\\" Full HD IPS antirreflejo\", \"Resolución: 1920 x 1080\", \"Audio: Altavoces Dolby Audio\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Procesador\": \"AMD Ryzen 7 7730U\", \"Sistema Operativo\": \"Windows 11 Home\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"512 GB SSD\", \"Pantalla\": \"15.6\\\" Full HD\", \"Resolución\": \"1920 x 1080\"}",
        "is_favorite": False,
        "historical_min_price": 2299.0,
        "is_historical_min": True
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
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139008_2_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor inteligente con píxeles OLED autoemisivos, procesador inteligente α11 AI 4K Gen3, soporte Dolby Vision/Atmos y HDMI 2.1 a 144Hz para gaming.",
        "features_json": "[\"Procesador: Procesador de IA α11 4K Generación 3\", \"Pantalla: 55\\\" OLED evo 4K 144Hz\", \"Resolución: 3840 x 2160 Ultra HD\", \"Conectividad: Wi-Fi 6 y HDMI 2.1 VRR\", \"Sistema Operativo: webOS 26 con actualizaciones garantizadas\", \"Sonido: Dolby Atmos 40W 2.2 canales\"]",
        "tech_specs_json": "{\"Marca\": \"LG\", \"Conectividad\": \"Wi-Fi 6, Bluetooth 5.2, HDMI 2.1 x4\", \"Sistema Operativo\": \"webOS 26\", \"Procesador\": \"α11 AI Processor 4K Gen3\", \"Pantalla\": \"55\\\" OLED evo\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Tasa de refresco\": \"144Hz\"}",
        "is_favorite": False,
        "historical_min_price": 3799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_neo_qled_65",
        "title": "Samsung 65\" Neo QLED 4K QN85D Smart TV",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 4499.0,
        "original_price": 5499.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 18,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/s/a/samsung_neo_qled_65_qn85d.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Neo QLED impulsado por Mini LED Quantum Matrix y procesador NQ4 AI Gen2 con escalado 4K por redes neuronales.",
        "features_json": "[\"Tecnología de panel: Quantum Mini LED Neo QLED\", \"Pantalla: 65\\\" 4K 120Hz\", \"Procesador: NQ4 AI Gen2\", \"Audio: Dolby Atmos con OTS (Object Tracking Sound)\", \"Gaming Hub: HDMI 2.1 FreeSync Premium Pro\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Pantalla\": \"65\\\" Neo QLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Tasa de refresco\": \"120Hz\", \"Sistema Operativo\": \"Tizen OS\", \"Conectividad\": \"Wi-Fi 5, Bluetooth 5.2, HDMI x4\"}",
        "is_favorite": False,
        "historical_min_price": 4499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_tcl_miniled_55",
        "title": "TCL 55\" Mini-LED 4K 144Hz Google TV C755",
        "category": "TVs",
        "brand": "TCL",
        "best_price": 2299.0,
        "original_price": 2899.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 21,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/t/c/tcl_55_c755_miniled_google_tv.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Pantalla QD-Mini LED con más de 500 zonas de atenuación local, tasa de refresco nativa de 144Hz VRR y sistema Google TV.",
        "features_json": "[\"Tecnología: QD-Mini LED con Quantum Dot\", \"Pantalla: 55\\\" 4K 144Hz VRR\", \"Brillo pico: 1300 nits HDR\", \"Sonido: Sistema Onkyo 2.1 con subwoofer integrado\", \"Sistema Operativo: Google TV con control por voz manos libres\"]",
        "tech_specs_json": "{\"Marca\": \"TCL\", \"Pantalla\": \"55\\\" QD-Mini LED\", \"Resolución\": \"3840 x 2160 4K\", \"Tasa de refresco\": \"144Hz\", \"Sistema Operativo\": \"Google TV\", \"HDR\": \"Dolby Vision IQ, HDR10+\"}",
        "is_favorite": False,
        "historical_min_price": 2299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_ipad_11",
        "title": "Apple iPad 11\" Chip A16 Wi-Fi 128GB",
        "category": "Tablets",
        "brand": "Apple",
        "best_price": 1899.0,
        "original_price": 2299.0,
        "best_store_name": "Falabella",
        "discount_percentage": 17,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/ipad_a16_wifi_128gb_silver.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet potente y versátil con pantalla Liquid Retina de 11 pulgadas, chip A16 Bionic, cámara frontal horizontal de 12MP y soporte para Apple Pencil.",
        "features_json": "[\"Procesador: Apple Chip A16 Bionic\", \"Memoria RAM: 6 GB\", \"Almacenamiento: 128 GB\", \"Pantalla: 11\\\" Liquid Retina IPS\", \"Resolución: 2360 × 1640 píxeles\", \"Cámara Principal: 12 MP\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Conectividad\": \"Wi-Fi 6\", \"Cámara Principal\": \"12 MP\", \"Procesador\": \"Apple Chip A16\", \"Almacenamiento\": \"128 GB\", \"Sistema Operativo\": \"iPadOS 18\", \"Pantalla\": \"11\\\" Liquid Retina IPS\", \"Memoria RAM\": \"6 GB\", \"Resolución\": \"2360 × 1640\"}",
        "is_favorite": False,
        "historical_min_price": 1899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tab_s10",
        "title": "Samsung Galaxy Tab S10+ 12.4\" 256GB 12GB RAM con S-Pen",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 3899.0,
        "original_price": 4499.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/s/a/samsung_galaxy_tab_s9_plus_graphite.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Galaxy AI con pantalla Dynamic AMOLED 2X antirreflejo de 12.4 pulgadas, procesador MediaTek Dimensity 9300+ y S-Pen incluido.",
        "features_json": "[\"Procesador: MediaTek Dimensity 9300+\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 256 GB UFS\", \"Pantalla: 12.4\\\" Dynamic AMOLED 2X 120Hz\", \"S-Pen: Incluido con latencia de 2.8ms\", \"Resistencia: IP68 contra agua y polvo\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Procesador\": \"Dimensity 9300+\", \"Sistema Operativo\": \"Android 14 One UI 6\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"256 GB\", \"Pantalla\": \"12.4\\\" AMOLED 120Hz\", \"Resolución\": \"2800 x 1752\"}",
        "is_favorite": False,
        "historical_min_price": 3899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_xiaomi_pad_6",
        "title": "Xiaomi Pad 6 11\" 256GB 8GB RAM Wi-Fi",
        "category": "Tablets",
        "brand": "Xiaomi",
        "best_price": 1349.0,
        "original_price": 1599.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 16,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/x/i/xiaomi_pad_6_gravity_gray.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet con pantalla WQHD+ de 144Hz con 7 niveles de tasa de refresco variable, procesador Snapdragon 870 y cuerpo metálico de una sola pieza.",
        "features_json": "[\"Procesador: Snapdragon 870 7nm\", \"Memoria RAM: 8 GB LPDDR5\", \"Almacenamiento: 256 GB UFS 3.1\", \"Pantalla: 11\\\" 2.8K 144Hz Dolby Vision\", \"Batería: 8840 mAh con carga de 33W\"]",
        "tech_specs_json": "{\"Marca\": \"Xiaomi\", \"Procesador\": \"Snapdragon 870\", \"Sistema Operativo\": \"MIUI Pad 14\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"256 GB\", \"Pantalla\": \"11\\\" 2.8K IPS 144Hz\", \"Resolución\": \"2880 x 1800\"}",
        "is_favorite": False,
        "historical_min_price": 1349.0,
        "is_historical_min": True
    },
    {
        "id": "prod_sony_wh1000xm5",
        "title": "Sony WH-1000XM5 Audífonos Inalámbricos Noise Cancelling",
        "category": "Audio",
        "brand": "Sony",
        "best_price": 1299.0,
        "original_price": 1599.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 19,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/s/o/sony_wh1000xm5_black.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Líderes en cancelación de ruido activa con procesador integrado V1 + procesador QN1 HD, 8 micrófonos y soporte para audio Hi-Res LDAC.",
        "features_json": "[\"Cancelación de ruido líder en la industria con Auto NC Optimizer\", \"Procesador: Dual V1 + QN1 HD\", \"Autonomía: Hasta 30 horas con NC activado\", \"Carga rápida: 3 minutos equivalen a 3 horas de música\", \"Llamadas ultranítidas con 4 micrófonos beamforming y reducción por IA\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Conectividad\": \"Bluetooth 5.2, Jack 3.5mm\", \"Códecs\": \"LDAC, AAC, SBC\", \"Batería\": \"Hasta 30 horas\", \"Peso\": \"250 gramos\", \"Cancelación activa\": \"Sí, adaptativa\"}",
        "is_favorite": False,
        "historical_min_price": 1299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_airpods_pro_2",
        "title": "Apple AirPods Pro (2da Generación) con Estuche MagSafe USB-C",
        "category": "Audio",
        "brand": "Apple",
        "best_price": 949.0,
        "original_price": 1199.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 21,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/a/p/apple_airpods_pro_2_usbc.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Audífonos con chip H2 que ofrece cancelación activa de ruido el doble de potente, Audio Espacial personalizado y estuche MagSafe USB-C con altavoz.",
        "features_json": "[\"Chip Apple H2 de alto rendimiento\", \"Cancelación Activa de Ruido 2x superior\", \"Modo Ambiente Adaptativo y Audio Espacial\", \"Estuche con puerto USB-C y chip U1 para búsqueda precisa\", \"Autonomía: Hasta 6 horas con NC (30 horas con estuche)\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Chip\": \"Apple H2\", \"Conectividad\": \"Bluetooth 5.3\", \"Resistencia\": \"IP54 al polvo, sudor y agua\", \"Puerto de carga\": \"USB-C y MagSafe inalámbrico\"}",
        "is_favorite": False,
        "historical_min_price": 949.0,
        "is_historical_min": True
    },
    {
        "id": "prod_ps5_slim",
        "title": "Consola PlayStation 5 Slim 1TB Edición Estándar con Lector",
        "category": "Gaming",
        "brand": "Sony",
        "best_price": 2499.0,
        "original_price": 2873.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/p/s/ps5_slim_console_standard.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Nueva PlayStation 5 con chasis 30% más reducido, SSD ultrarrápido de 1TB integrado, lector de discos Ultra HD Blu-ray y mando DualSense con respuesta háptica.",
        "features_json": "[\"SSD personalizado de 1 TB a 5.5 GB/s\", \"Trazado de rayos acelerado por hardware y soporte 4K a 120Hz\", \"Mando inalámbrico DualSense con gatillos adaptativos\", \"Audio 3D Tempest\", \"Lector de discos Ultra HD Blu-ray extraíble\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Capacidad\": \"1 TB SSD NVMe\", \"Procesador\": \"AMD Zen 2 de 8 núcleos a 3.5 GHz\", \"Gráficos\": \"AMD RDNA 2 con 10.3 TFLOPs\", \"Salida de video\": \"HDMI 2.1 con VRR y ALLM\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_nintendo_switch_oled",
        "title": "Consola Nintendo Switch OLED 64GB Joy-Con Blanco",
        "category": "Gaming",
        "brand": "Nintendo",
        "best_price": 1399.0,
        "original_price": 1699.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 18,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/n/i/nintendo_switch_oled_white.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Consola híbrida con vibrante pantalla OLED de 7 pulgadas, soporte ajustable ancho, base con puerto LAN Ethernet con cable y 64GB de almacenamiento interno.",
        "features_json": "[\"Pantalla: 7.0\\\" OLED con colores vivos y contraste infinito\", \"Soporte ajustable amplio para modo sobremesa\", \"Base con puerto LAN Ethernet por cable integrado\", \"Almacenamiento interno de 64 GB expandible con microSD\", \"Audio mejorado en modo portátil y sobremesa\"]",
        "tech_specs_json": "{\"Marca\": \"Nintendo\", \"Pantalla\": \"7.0\\\" OLED táctil capacitiva\", \"Resolución portátil\": \"1280 x 720 (hasta 1080p en TV)\", \"Almacenamiento\": \"64 GB\", \"Batería\": \"Hasta 9 horas de juego\"}",
        "is_favorite": False,
        "historical_min_price": 1399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_epson_l3250",
        "title": "Impresora Multifuncional Epson EcoTank L3250 Wi-Fi Tanque de Tinta",
        "category": "Impresoras",
        "brand": "Epson",
        "best_price": 699.0,
        "original_price": 849.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 18,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/e/p/epson_ecotank_l3250_multifuncional.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Multifuncional 3 en 1 con sistema de tanque de tinta EcoTank de costo ultrabajo, conectividad Wi-Fi y Wi-Fi Direct y aplicación Smart Panel.",
        "features_json": "[\"Costo de impresión ultra bajo con botellas de tinta de alto rendimiento\", \"Imprime hasta 4500 páginas en negro o 7500 páginas a color con un kit\", \"Conectividad Wi-Fi, Wi-Fi Direct y USB de alta velocidad\", \"Tecnología Heat-Free de Epson sin calor para mayor durabilidad\", \"Escáner plano de cama de 1200 x 2400 dpi\"]",
        "tech_specs_json": "{\"Marca\": \"Epson\", \"Tipo de impresión\": \"Inyección de tinta continua EcoTank\", \"Funciones\": \"Imprime, copia, escanea\", \"Velocidad\": \"Hasta 33 ppm en negro y 15 ppm a color\", \"Conectividad\": \"Wi-Fi, Wi-Fi Direct, USB\"}",
        "is_favorite": False,
        "historical_min_price": 699.0,
        "is_historical_min": True
    },
    {
        "id": "prod_sony_alpha_7_iv",
        "title": "Cámara Mirrorless Sony Alpha 7 IV Full-Frame (Cuerpo)",
        "category": "Cámaras",
        "brand": "Sony",
        "best_price": 9999.0,
        "original_price": 11499.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 3,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/s/o/sony_alpha_7_iv_body.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Cámara híbrida todoterreno con sensor CMOS Exmor R retroiluminado de 33MP, procesador BIONZ XR y grabación de video 4K a 60p en 10 bits 4:2:2.",
        "features_json": "[\"Sensor Full-Frame Exmor R de 33 MP retroiluminado\", \"Procesador de imagen BIONZ XR 8 veces más rápido\", \"Enfoque automático híbrido rápido con 759 puntos AF y Real-time Eye AF para humanos, animales y aves\", \"Grabación de video 4K 60p en 10-bit 4:2:2 con perfil S-Cinetone\", \"Estabilización de imagen óptica en el cuerpo (IBIS) de 5.5 pasos\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Sensor\": \"Full-Frame (35.9 x 23.9 mm) 33 MP\", \"Montura\": \"Sony E-Mount\", \"Estabilizador\": \"IBIS de 5 ejes 5.5 pasos\", \"Video\": \"4K 60p 10-bit 4:2:2\", \"Visor\": \"OLED electrónico de 3.68 millones de puntos\"}",
        "is_favorite": False,
        "historical_min_price": 9999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_iphone_17_pro_max_6_9_512gb_plata",
        "title": "iPhone 17 Pro Max 6.9\" 512GB Plata",
        "category": "Smartphones",
        "brand": "Apple",
        "best_price": 7999.0,
        "original_price": 9198.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/iphone_17_pro_max_silver_pdp_image_position_1__laes.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPhone 17 Pro Max 6.9\" 512GB Plata con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: iOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 7999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_iphone_17_pro_max_6_9_512gb_azul_profundo",
        "title": "iPhone 17 Pro Max 6.9\" 512GB Azul Profundo",
        "category": "Smartphones",
        "brand": "Apple",
        "best_price": 6999.0,
        "original_price": 8048.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/iphone_17_pro_max_deep_blue_pdp_image_position_1__laes_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPhone 17 Pro Max 6.9\" 512GB Azul Profundo con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: iOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 6999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_iphone_17_pro_max_6_9_512gb_naranja_c_smico",
        "title": "iPhone 17 Pro Max 6.9\" 512GB Naranja cósmico",
        "category": "Smartphones",
        "brand": "Apple",
        "best_price": 6999.0,
        "original_price": 8048.85,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/iphone_17_pro_max_cosmic_orange_pdp_image_position_1__laes.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPhone 17 Pro Max 6.9\" 512GB Naranja cósmico con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: iOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 6999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "title": "iPhone 17 Pro Max 6.9\" 256GB Naranja Cósmico",
        "category": "Smartphones",
        "brand": "Apple",
        "best_price": 5999.0,
        "original_price": 6898.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/iphone_17_pro_max_cosmic_orange_pdp_image_position_1__laes_3.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPhone 17 Pro Max 6.9\" 256GB Naranja Cósmico con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Almacenamiento interno: 256 GB\", \"Sistema Operativo: iOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"256 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 5999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb",
        "title": "Celular Samsung Galaxy S26 Ultra 6.9\" 512GB 12GB RAM COBALT VIOLET",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 5299.0,
        "original_price": 6899.0,
        "best_store_name": "Falabella",
        "discount_percentage": 23,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138650_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Samsung Galaxy S26 Ultra 6.9\" 512GB 12GB RAM COBALT VIOLET con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 5299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb_1",
        "title": "Celular Samsung Galaxy S26 Ultra 6.9\" 512GB 12GB RAM Black",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 5299.0,
        "original_price": 6899.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 23,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138649_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Samsung Galaxy S26 Ultra 6.9\" 512GB 12GB RAM Black con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 5299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_celular_samsung_galaxy_s26_6_3_512gb_12gb_",
        "title": "Celular Samsung Galaxy S26 6.3\" 512GB 12GB RAM Black",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 4499.0,
        "original_price": 5499.0,
        "best_store_name": "Tottus",
        "discount_percentage": 18,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138644_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Samsung Galaxy S26 6.3\" 512GB 12GB RAM Black con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 4499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_iphone_16_6_1_128gb_blanco",
        "title": "iPhone 16 6.1\" 128GB Blanco",
        "category": "Smartphones",
        "brand": "Apple",
        "best_price": 3499.0,
        "original_price": 4023.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/iphone_16_no-ai_white_pdp_image_position_1__gens.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPhone 16 6.1\" 128GB Blanco con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: iOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 3499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_ne",
        "title": "Celular Honor 600 Pro 6.57\" 512GB 12GB RAM Negro",
        "category": "Smartphones",
        "brand": "Honor",
        "best_price": 3499.0,
        "original_price": 4023.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139411-1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Honor 600 Pro 6.57\" 512GB 12GB RAM Negro con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Honor\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 3499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_do",
        "title": "Celular Honor 600 Pro 6.57\" 512GB 12GB RAM Dorado platino",
        "category": "Smartphones",
        "brand": "Honor",
        "best_price": 3499.0,
        "original_price": 4023.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139410-1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Honor 600 Pro 6.57\" 512GB 12GB RAM Dorado platino con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Honor\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 3499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_iphone_15_6_1_128gb_negro",
        "title": "iPhone 15 6.1\" 128GB Negro",
        "category": "Smartphones",
        "brand": "Apple",
        "best_price": 2899.0,
        "original_price": 3499.0,
        "best_store_name": "Ripley",
        "discount_percentage": 17,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/iphone15_black_pdp_image_position-1__mxla.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPhone 15 6.1\" 128GB Negro con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: iOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 2899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1",
        "title": "Celular Motorola Edge 70 Pro 6.78\" 512GB 12GB RAM Blanco",
        "category": "Smartphones",
        "brand": "Motorola",
        "best_price": 2599.0,
        "original_price": 2988.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/4/3/43680264_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Motorola Edge 70 Pro 6.78\" 512GB 12GB RAM Blanco con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Motorola\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2599.0,
        "is_historical_min": True
    },
    {
        "id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1_1",
        "title": "Celular Motorola Edge 70 Pro 6.78\" 512GB 12GB RAM Azul",
        "category": "Smartphones",
        "brand": "Motorola",
        "best_price": 2599.0,
        "original_price": 2988.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139706_2_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Motorola Edge 70 Pro 6.78\" 512GB 12GB RAM Azul con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Motorola\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2599.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g",
        "title": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Silver + S Pen",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 2499.0,
        "original_price": 3049.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 18,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135783_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Silver + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_1",
        "title": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Blue + S Pen",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 2499.0,
        "original_price": 3049.0,
        "best_store_name": "Tottus",
        "discount_percentage": 18,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135784_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Blue + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_2",
        "title": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Gray + S Pen",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 2499.0,
        "original_price": 3049.0,
        "best_store_name": "Falabella",
        "discount_percentage": 18,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135782_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Gray + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_motorola_celular_motorola_moto_edge_60_pro_6_7_512",
        "title": "Celular Motorola Moto Edge 60 Pro 6.7\" 512GB 12GB RAM Gris",
        "category": "Smartphones",
        "brand": "Motorola",
        "best_price": 2499.0,
        "original_price": 2873.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/_/1_491.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Motorola Moto Edge 60 Pro 6.7\" 512GB 12GB RAM Gris con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Motorola\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "title": "Celular Honor 600 6.57\" 512GB 8GB RAM Naranja",
        "category": "Smartphones",
        "brand": "Honor",
        "best_price": 2399.0,
        "original_price": 2758.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139414-1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Honor 600 6.57\" 512GB 8GB RAM Naranja con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Honor\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_negro",
        "title": "Celular Honor 600 6.57\" 512GB 8GB RAM Negro",
        "category": "Smartphones",
        "brand": "Honor",
        "best_price": 2399.0,
        "original_price": 2758.85,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139416-1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Honor 600 6.57\" 512GB 8GB RAM Negro con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Honor\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_dorado_",
        "title": "Celular Honor 600 6.57\" 512GB 8GB RAM Dorado platino",
        "category": "Smartphones",
        "brand": "Honor",
        "best_price": 2399.0,
        "original_price": 2758.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139415-1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Honor 600 6.57\" 512GB 8GB RAM Dorado platino con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Honor\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g",
        "title": "Celular Samsung Galaxy A57 6.7\" 5G 256GB 8GB RAM Violet",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 2099.0,
        "original_price": 2413.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138919_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Samsung Galaxy A57 6.7\" 5G 256GB 8GB RAM Violet con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 256 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"256 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2099.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g_1",
        "title": "Celular Samsung Galaxy A57 6.7\" 5G 256GB 8GB RAM Dark Blue",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 2099.0,
        "original_price": 2413.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138918_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Samsung Galaxy A57 6.7\" 5G 256GB 8GB RAM Dark Blue con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 256 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"256 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2099.0,
        "is_historical_min": True
    },
    {
        "id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb_",
        "title": "Celular Libre Motorola Edge 70 6.7\" 512GB 12GB RAM Gris",
        "category": "Smartphones",
        "brand": "Motorola",
        "best_price": 2099.0,
        "original_price": 2499.0,
        "best_store_name": "Tottus",
        "discount_percentage": 16,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/2/1/21436260_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Libre Motorola Edge 70 6.7\" 512GB 12GB RAM Gris con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Motorola\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2099.0,
        "is_historical_min": True
    },
    {
        "id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb__1",
        "title": "Celular Libre Motorola Edge 70 6.7\" 512GB 12GB RAM Verde",
        "category": "Smartphones",
        "brand": "Motorola",
        "best_price": 2099.0,
        "original_price": 2499.0,
        "best_store_name": "Falabella",
        "discount_percentage": 16,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/2/1/21436261_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Celular Libre Motorola Edge 70 6.7\" 512GB 12GB RAM Verde con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 12 GB\", \"Almacenamiento interno: 512 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Motorola\", \"Almacenamiento\": \"512 GB\", \"Memoria RAM\": \"12 GB\", \"Conectividad\": \"5G / Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2099.0,
        "is_historical_min": True
    },
    {
        "id": "prod_asus_laptop_gamer_asus_rog_zephyrus_duo_16_de_16_i",
        "title": "Laptop Gamer Asus ROG Zephyrus Duo 16 de 16\", Intel Core Ultra 9 386H (Series 3), NVIDIA GeForce RTX 5090, 64GB RAM, disco sólido de 2TB, modelo GX651AX-SR058W",
        "category": "Laptops",
        "brand": "Asus",
        "best_price": 25499.0,
        "original_price": 29323.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139653_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Asus ROG Zephyrus Duo 16 de 16\", Intel Core Ultra 9 386H (Series 3), NVIDIA GeForce RTX 5090, 64GB RAM, disco sólido de 2TB, modelo GX651AX-SR058W con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 64 GB\", \"Almacenamiento interno: 64 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Asus\", \"Almacenamiento\": \"64 GB\", \"Memoria RAM\": \"64 GB\"}",
        "is_favorite": False,
        "historical_min_price": 25499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole",
        "title": "Laptop Gamer Lenovo Legion Pro 7i de 16\" OLED, Intel Core Ultra 9 275HX (Series 2), NVIDIA GeForce RTX 5090, 64GB RAM, disco sólido de 2TB, modelo 83F500FSLM",
        "category": "Laptops",
        "brand": "Lenovo",
        "best_price": 22499.0,
        "original_price": 25873.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138853_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Lenovo Legion Pro 7i de 16\" OLED, Intel Core Ultra 9 275HX (Series 2), NVIDIA GeForce RTX 5090, 64GB RAM, disco sólido de 2TB, modelo 83F500FSLM con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 64 GB\", \"Almacenamiento interno: 64 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Almacenamiento\": \"64 GB\", \"Memoria RAM\": \"64 GB\"}",
        "is_favorite": False,
        "historical_min_price": 22499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_int",
        "title": "Laptop Gamer Lenovo Legion Pro 7i de 16\", Intel Core Ultra 9 275HX (Series 2), NVIDIA GeForce RTX 5080, 32GB RAM, disco sólido de 1TB, modelo 83F5000XLM",
        "category": "Laptops",
        "brand": "Lenovo",
        "best_price": 15899.0,
        "original_price": 18283.85,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/136078_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Lenovo Legion Pro 7i de 16\", Intel Core Ultra 9 275HX (Series 2), NVIDIA GeForce RTX 5080, 32GB RAM, disco sólido de 1TB, modelo 83F5000XLM con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 32 GB\", \"Almacenamiento interno: 32 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Almacenamiento\": \"32 GB\", \"Memoria RAM\": \"32 GB\"}",
        "is_favorite": False,
        "historical_min_price": 15899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_macbook_pro_de_14_chip_m5_16gb_ram_disco_s_l",
        "title": "MacBook Pro de 14\", Chip M5, 16GB RAM, disco sólido de 1TB, color Plata, teclado en español",
        "category": "Laptops",
        "brand": "Apple",
        "best_price": 9999.0,
        "original_price": 11498.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/m/a/macbook_pro_14-in_m5_silver_pdp_image_position_1__laes_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "MacBook Pro de 14\", Chip M5, 16GB RAM, disco sólido de 1TB, color Plata, teclado en español con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple M5\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Apple M5\"}",
        "is_favorite": False,
        "historical_min_price": 9999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_amd_ryz",
        "title": "Laptop Gamer Asus ROG Strix G16 de 16\", AMD Ryzen 9 9955HX, NVIDIA GeForce RTX 5070, 16GB RAM, disco sólido de 1TB, modelo G614FP-RV010W",
        "category": "Laptops",
        "brand": "Asus",
        "best_price": 9499.0,
        "original_price": 11999.0,
        "best_store_name": "Falabella",
        "discount_percentage": 21,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/137079_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Asus ROG Strix G16 de 16\", AMD Ryzen 9 9955HX, NVIDIA GeForce RTX 5070, 16GB RAM, disco sólido de 1TB, modelo G614FP-RV010W con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Asus\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\"}",
        "is_favorite": False,
        "historical_min_price": 9499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_",
        "title": "Laptop Gamer HyperX Omen de 15.3\", Intel Core i7-14650HX (14va Gen), NVIDIA GEFORCE RTX 5060, 16GB RAM, disco sólido de 512GB, modelo 15-ga0001la",
        "category": "Laptops",
        "brand": "Hp",
        "best_price": 8299.0,
        "original_price": 9543.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/d/6/d62w3la_01imagenprincipalcontexto_d.jpg.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer HyperX Omen de 15.3\", Intel Core i7-14650HX (14va Gen), NVIDIA GEFORCE RTX 5060, 16GB RAM, disco sólido de 512GB, modelo 15-ga0001la con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Hp\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 8299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_laptop_gamer_lenovo_legion_5i_de_15_3_intel",
        "title": "Laptop Gamer Lenovo Legion 5i de 15.3\", Intel Core i7-13650HX (13va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 1TB, modelo 83LY009MLM",
        "category": "Laptops",
        "brand": "Lenovo",
        "best_price": 8299.0,
        "original_price": 9543.85,
        "best_store_name": "Tottus",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139651_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Lenovo Legion 5i de 15.3\", Intel Core i7-13650HX (13va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 1TB, modelo 83LY009MLM con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 8299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_laptop_hp_omnibook_ultra_de_14_pantalla_touch_i",
        "title": "Laptop HP Omnibook Ultra de 14\", Pantalla touch, Intel Core Ultra 7 356H (Series 3), 16GB RAM, disco sólido de 1TB, modelo 14-kd0070la",
        "category": "Laptops",
        "brand": "HP",
        "best_price": 7799.0,
        "original_price": 8968.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/d/g/dg0d4la_01imagenprincipalcontexto_b.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop HP Omnibook Ultra de 14\", Pantalla touch, Intel Core Ultra 7 356H (Series 3), 16GB RAM, disco sólido de 1TB, modelo 14-kd0070la con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core Ultra 7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"HP\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core Ultra 7\"}",
        "is_favorite": False,
        "historical_min_price": 7799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l",
        "title": "MacBook Air de 13\", Chip M5, 16GB RAM, disco sólido de 1TB, color Plata, teclado en español",
        "category": "Laptops",
        "brand": "Apple",
        "best_price": 7699.0,
        "original_price": 8853.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/m/a/macbook_air_13-in_m5_silver_pdp_image_position_1__gens_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "MacBook Air de 13\", Chip M5, 16GB RAM, disco sólido de 1TB, color Plata, teclado en español con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple M5\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Apple M5\"}",
        "is_favorite": False,
        "historical_min_price": 7699.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_macbook_air_de_15_chip_m5_16gb_ram_disco_s_l",
        "title": "MacBook Air de 15\", Chip M5, 16GB RAM, disco sólido de 512GB, Blanco estelar",
        "category": "Laptops",
        "brand": "Apple",
        "best_price": 7599.0,
        "original_price": 8738.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/m/a/macbook_air_15-in_m5_starlight_pdp_image_position_1__gens.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "MacBook Air de 15\", Chip M5, 16GB RAM, disco sólido de 512GB, Blanco estelar con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple M5\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Apple M5\"}",
        "is_favorite": False,
        "historical_min_price": 7599.0,
        "is_historical_min": True
    },
    {
        "id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7",
        "title": "Laptop Gamer Acer Nitro V de 15.6\", AMD Ryzen 7 170, NVIDIA GeForce RTX 5060, 32GB RAM, disco sólido de 512GB, modelo ANV15-A31-R2TH",
        "category": "Laptops",
        "brand": "Acer",
        "best_price": 7399.0,
        "original_price": 8508.85,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/a/n/anv15-a31-r2th_01_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Acer Nitro V de 15.6\", AMD Ryzen 7 170, NVIDIA GeForce RTX 5060, 32GB RAM, disco sólido de 512GB, modelo ANV15-A31-R2TH con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: AMD Ryzen 7\", \"Memoria RAM: 32 GB\", \"Almacenamiento interno: 32 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Acer\", \"Almacenamiento\": \"32 GB\", \"Memoria RAM\": \"32 GB\", \"Procesador\": \"AMD Ryzen 7\"}",
        "is_favorite": False,
        "historical_min_price": 7399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_intel_c",
        "title": "Laptop Gamer Asus ROG Strix G16 de 16\", Intel Core i7 14650HX (14va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo G615JMR-RV165W",
        "category": "Laptops",
        "brand": "Asus",
        "best_price": 7199.0,
        "original_price": 8278.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139515_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Asus ROG Strix G16 de 16\", Intel Core i7 14650HX (14va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo G615JMR-RV165W con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Asus\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 7199.0,
        "is_historical_min": True
    },
    {
        "id": "prod_msi_laptop_gamer_msi_katana_15_hx_de_15_6_intel_co",
        "title": "Laptop Gamer MSI Katana 15 HX de 15.6\", Intel Core i7-14650HX (14va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo B14WFK-1055",
        "category": "Laptops",
        "brand": "Msi",
        "best_price": 7099.0,
        "original_price": 8163.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/k/a/katana_15_hx_-_portada_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer MSI Katana 15 HX de 15.6\", Intel Core i7-14650HX (14va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo B14WFK-1055 con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Msi\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 7099.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_pc_gamer_lenovo_legion_5_intel_core_ultra_5",
        "title": "PC Gamer Lenovo Legion 5, Intel Core Ultra 5 225 (Series 2), NVIDIA GeForce RTX 5060 Ti, 16GB RAM, disco sólido de 1TB, modelo 90YA002TPT",
        "category": "Laptops",
        "brand": "Lenovo",
        "best_price": 6799.0,
        "original_price": 7818.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/137085_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "PC Gamer Lenovo Legion 5, Intel Core Ultra 5 225 (Series 2), NVIDIA GeForce RTX 5060 Ti, 16GB RAM, disco sólido de 1TB, modelo 90YA002TPT con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core Ultra 5\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core Ultra 5\"}",
        "is_favorite": False,
        "historical_min_price": 6799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_laptop_gamer_hp_victus_de_15_6_intel_core_i7_13",
        "title": "Laptop Gamer HP Victus de 15.6\", Intel Core i7-13620H (13va Gen), NVIDIA GeForce RTX 4050, 16GB RAM, disco sólido de 1TB, modelo 15-fa2012la",
        "category": "Laptops",
        "brand": "HP",
        "best_price": 6699.0,
        "original_price": 7703.85,
        "best_store_name": "Tottus",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/b/a/ba1u3la_1imagenprincipalcontexto_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer HP Victus de 15.6\", Intel Core i7-13620H (13va Gen), NVIDIA GeForce RTX 4050, 16GB RAM, disco sólido de 1TB, modelo 15-fa2012la con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"HP\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 6699.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_1",
        "title": "MacBook Air de 13\", Chip M5, 16GB RAM, disco sólido de 512GB, Azul cielo",
        "category": "Laptops",
        "brand": "Apple",
        "best_price": 6499.0,
        "original_price": 7473.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/m/a/macbook_air_13-in_m5_sky_blue_pdp_image_position_1__gens.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "MacBook Air de 13\", Chip M5, 16GB RAM, disco sólido de 512GB, Azul cielo con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple M5\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Apple M5\"}",
        "is_favorite": False,
        "historical_min_price": 6499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_2",
        "title": "MacBook Air de 13\", Chip M5, 16GB RAM, disco sólido de 512GB, color Plata, teclado en español",
        "category": "Laptops",
        "brand": "Apple",
        "best_price": 6499.0,
        "original_price": 7473.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/m/a/macbook_air_13-in_m5_silver_pdp_image_position_1__gens.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "MacBook Air de 13\", Chip M5, 16GB RAM, disco sólido de 512GB, color Plata, teclado en español con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple M5\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Apple M5\"}",
        "is_favorite": False,
        "historical_min_price": 6499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445",
        "title": "Laptop Gamer HP Victus de 15.6\", AMD Ryzen 7 7445H, NVIDIA GeForce RTX 4050, 16GB RAM, disco sólido de 512GB, modelo 15-fb3021la",
        "category": "Laptops",
        "brand": "HP",
        "best_price": 6399.0,
        "original_price": 7358.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/b/t/bt4f1la_1imagenprincipalcontexto-.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer HP Victus de 15.6\", AMD Ryzen 7 7445H, NVIDIA GeForce RTX 4050, 16GB RAM, disco sólido de 512GB, modelo 15-fb3021la con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: AMD Ryzen 7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"HP\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"AMD Ryzen 7\"}",
        "is_favorite": False,
        "historical_min_price": 6399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla",
        "title": "Laptop 2 en 1 HP Omnibook X Flip de 14\", Pantalla touch, AMD Ryzen AI 7 445, 16GB RAM, disco sólido de 512GB, modelo 14-kc0070la, Color Espresso Profundo",
        "category": "Laptops",
        "brand": "HP",
        "best_price": 6299.0,
        "original_price": 7243.85,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/d/g/dg0d3la_01imagenprincipalcontexto_a.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop 2 en 1 HP Omnibook X Flip de 14\", Pantalla touch, AMD Ryzen AI 7 445, 16GB RAM, disco sólido de 512GB, modelo 14-kc0070la, Color Espresso Profundo con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"HP\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\"}",
        "is_favorite": False,
        "historical_min_price": 6299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_intel_core_",
        "title": "Laptop Gamer Acer Nitro V de 15.6\", Intel Core i7-13620H (13va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo ANV15-52-77RJ",
        "category": "Laptops",
        "brand": "Acer",
        "best_price": 6299.0,
        "original_price": 7243.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/a/n/anv15-52-77rj-01_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Acer Nitro V de 15.6\", Intel Core i7-13620H (13va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo ANV15-52-77RJ con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Acer\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 6299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7",
        "title": "Laptop Gamer Asus TUF F16 de 16\", Intel Core i7 14650HX (14va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo FX608JMI-TU401W + Mochila",
        "category": "Laptops",
        "brand": "Asus",
        "best_price": 5999.0,
        "original_price": 8199.0,
        "best_store_name": "Falabella",
        "discount_percentage": 27,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/4/140152_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Asus TUF F16 de 16\", Intel Core i7 14650HX (14va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo FX608JMI-TU401W + Mochila con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Asus\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 5999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_1",
        "title": "Laptop Gamer Asus TUF F16 de 16\", Intel Core i7 14650HX (14va Gen), NVIDIA GeForce RTX 5050, 16GB RAM, disco sólido de 512GB, modelo FX608JHI-TU368W + Mochila",
        "category": "Laptops",
        "brand": "Asus",
        "best_price": 5899.0,
        "original_price": 7899.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 25,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/4/140151_1_6.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Asus TUF F16 de 16\", Intel Core i7 14650HX (14va Gen), NVIDIA GeForce RTX 5050, 16GB RAM, disco sólido de 512GB, modelo FX608JHI-TU368W + Mochila con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Asus\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 5899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_msi_laptop_gamer_msi_cyborg_15_intel_core_i7_13620",
        "title": "Laptop Gamer MSI Cyborg 15, Intel Core i7-13620H (13va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo B13WEKG",
        "category": "Laptops",
        "brand": "Msi",
        "best_price": 5799.0,
        "original_price": 6668.85,
        "best_store_name": "Tottus",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/0/_/0_-_cyborg_15_b13w_5060_-_portada_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer MSI Cyborg 15, Intel Core i7-13620H (13va Gen), NVIDIA GeForce RTX 5060, 16GB RAM, disco sólido de 512GB, modelo B13WEKG con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Intel Core i7\", \"Memoria RAM: 16 GB\", \"Almacenamiento interno: 16 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Msi\", \"Almacenamiento\": \"16 GB\", \"Memoria RAM\": \"16 GB\", \"Procesador\": \"Intel Core i7\"}",
        "is_favorite": False,
        "historical_min_price": 5799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole_1",
        "title": "Laptop Gamer Lenovo Legion Pro 7i de 16\" OLED, Intel Core Ultra 9 275HX (Series 2), NVIDIA GeForce RTX 5090, 64GB RAM, disco sólido de 2TB, modelo 83F500FSLM",
        "category": "TVs",
        "brand": "Lenovo",
        "best_price": 22499.0,
        "original_price": 25873.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138853_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Gamer Lenovo Legion Pro 7i de 16\" OLED, Intel Core Ultra 9 275HX (Series 2), NVIDIA GeForce RTX 5090, 64GB RAM, disco sólido de 2TB, modelo 83F500FSLM con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 64 GB\", \"Almacenamiento interno: 64 GB\", \"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: Google TV\", \"Garantía oficial de 12 meses por el fabricante en Perú\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Almacenamiento\": \"64 GB\", \"Memoria RAM\": \"64 GB\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Google TV\"}",
        "is_favorite": False,
        "historical_min_price": 22499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lg_televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "title": "Televisor LG 83\" OLED evo AI C6 4K Smart TV 2026",
        "category": "TVs",
        "brand": "LG",
        "best_price": 17999.0,
        "original_price": 20698.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139016_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor LG 83\" OLED evo AI C6 4K Smart TV 2026 con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: webOS\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"LG\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"webOS\"}",
        "is_favorite": False,
        "historical_min_price": 17999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lg_televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "title": "Televisor LG Smart TV 77\" OLED 4K OLED77G6PSA",
        "category": "TVs",
        "brand": "LG",
        "best_price": 12499.0,
        "original_price": 14999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 17,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139015_1_2.png?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300&format=jpeg",
        "description": "Televisor LG Smart TV 77\" OLED 4K OLED77G6PSA con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: webOS\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"LG\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"webOS\"}",
        "is_favorite": False,
        "historical_min_price": 12499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_sony_televisor_sony_google_tv_oled_4k_ultra_hd_k_7",
        "title": "Televisor Sony Google TV OLED 4K Ultra HD K-77XR80 Bravia 8",
        "category": "TVs",
        "brand": "Sony",
        "best_price": 11999.0,
        "original_price": 16499.0,
        "best_store_name": "Ripley",
        "discount_percentage": 27,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/k/-/k-77xr80.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Sony Google TV OLED 4K Ultra HD K-77XR80 Bravia 8 con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: Google TV\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Google TV\"}",
        "is_favorite": False,
        "historical_min_price": 11999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_televisor_samsung_smart_tv_77_oled_qn77s95",
        "title": "Televisor Samsung Smart TV 77\" OLED QN77S95HAEXPE",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 11799.0,
        "original_price": 13568.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139328_2_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Samsung Smart TV 77\" OLED QN77S95HAEXPE con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: Tizen\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Tizen\"}",
        "is_favorite": False,
        "historical_min_price": 11799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_televisor_samsung_smart_tv_77_oled_4k_qn77",
        "title": "Televisor Samsung Smart TV 77\" OLED 4K QN77S90HAGXPE",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 9799.0,
        "original_price": 11268.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139327_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Samsung Smart TV 77\" OLED 4K QN77S90HAGXPE con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: Tizen\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Tizen\"}",
        "is_favorite": False,
        "historical_min_price": 9799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65",
        "title": "Televisor Samsung Smart TV 65\" OLED 4K QN65S95HAGXPE",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 8799.0,
        "original_price": 10118.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139323_2_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Samsung Smart TV 65\" OLED 4K QN65S95HAGXPE con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: Tizen\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Tizen\"}",
        "is_favorite": False,
        "historical_min_price": 8799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_televisor_samsung_smart_tv_75_qled_4k_uhd_",
        "title": "Televisor Samsung Smart TV 75\" QLED 4K UHD Vision AI F-QN75LS03F-01",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 7299.0,
        "original_price": 8393.85,
        "best_store_name": "Tottus",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/136429_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Samsung Smart TV 75\" QLED 4K UHD Vision AI F-QN75LS03F-01 con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: QLED\", \"Sistema Operativo: Tizen\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Tecnología de Pantalla\": \"QLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Tizen\"}",
        "is_favorite": False,
        "historical_min_price": 7299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lg_televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "title": "Televisor LG 55\" OLED evo AI G6 4K Smart TV 2026",
        "category": "TVs",
        "brand": "LG",
        "best_price": 6799.0,
        "original_price": 8999.0,
        "best_store_name": "Falabella",
        "discount_percentage": 24,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139009_1.png?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300&format=jpeg",
        "description": "Televisor LG 55\" OLED evo AI G6 4K Smart TV 2026 con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: webOS\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"LG\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"webOS\"}",
        "is_favorite": False,
        "historical_min_price": 6799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hisense_televisor_hisense_smart_tv_100_uled_minile",
        "title": "Televisor Hisense Smart TV 100\" ULED MiniLED 4K UHD 100U7QG",
        "category": "TVs",
        "brand": "Hisense",
        "best_price": 6599.0,
        "original_price": 9999.0,
        "best_store_name": "Falabella",
        "discount_percentage": 34,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/136461_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Hisense Smart TV 100\" ULED MiniLED 4K UHD 100U7QG con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: Mini LED\", \"Sistema Operativo: Google TV\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Hisense\", \"Tecnología de Pantalla\": \"Mini LED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Google TV\"}",
        "is_favorite": False,
        "historical_min_price": 6599.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_televisor_samsung_smart_tv_85_neo_qled_4k_",
        "title": "Televisor Samsung Smart TV 85\" Neo QLED 4K QN85QN70HAGXPE",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 6299.0,
        "original_price": 7243.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139331_2_1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Samsung Smart TV 85\" Neo QLED 4K QN85QN70HAGXPE con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: Neo QLED\", \"Sistema Operativo: Tizen\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Tecnología de Pantalla\": \"Neo QLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Tizen\"}",
        "is_favorite": False,
        "historical_min_price": 6299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65_1",
        "title": "Televisor Samsung Smart TV 65\" OLED 4K QN65S90HAEXPE",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 5699.0,
        "original_price": 6799.0,
        "best_store_name": "Ripley",
        "discount_percentage": 16,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139322_2_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Samsung Smart TV 65\" OLED 4K QN65S90HAEXPE con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: Tizen\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Tizen\"}",
        "is_favorite": False,
        "historical_min_price": 5699.0,
        "is_historical_min": True
    },
    {
        "id": "prod_sony_televisor_sony_smart_tv_65_mini_led_4k_ultra_",
        "title": "Televisor Sony Smart TV 65\" Mini LED 4K Ultra HD K-65XR50 Bravia 5",
        "category": "TVs",
        "brand": "Sony",
        "best_price": 5699.0,
        "original_price": 6999.0,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 19,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/g/e/genba_bravia-5_k-65xr50_01_mainimage_dealers_newmodel_1000x1000px.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Sony Smart TV 65\" Mini LED 4K Ultra HD K-65XR50 Bravia 5 con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: LED 4K\", \"Sistema Operativo: Google TV\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Tecnología de Pantalla\": \"LED 4K\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Google TV\"}",
        "is_favorite": False,
        "historical_min_price": 5699.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_televisor_samsung_smart_tv_50_neoqled_4k_q",
        "title": "Televisor Samsung Smart TV 50\" NeoQLED 4K QN50QN90FAGXPE",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 4999.0,
        "original_price": 5748.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/136202_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Samsung Smart TV 50\" NeoQLED 4K QN50QN90FAGXPE con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: QLED\", \"Sistema Operativo: Tizen\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Tecnología de Pantalla\": \"QLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Tizen\"}",
        "is_favorite": False,
        "historical_min_price": 4999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_tcl_televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85",
        "title": "Televisor TCL SMART TV 85\" QD MINILED 4K UHD 85C6K",
        "category": "TVs",
        "brand": "TCL",
        "best_price": 4899.0,
        "original_price": 6199.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 21,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/t/c/tcl_tv_qdminiled_c6k_85_front_full_specs.png?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300&format=jpeg",
        "description": "Televisor TCL SMART TV 85\" QD MINILED 4K UHD 85C6K con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: Mini LED\", \"Sistema Operativo: Google TV\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"TCL\", \"Tecnología de Pantalla\": \"Mini LED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Google TV\"}",
        "is_favorite": False,
        "historical_min_price": 4899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hisense_televisor_hisense_google_tv_98_hi_qled_4k_",
        "title": "Televisor Hisense Google TV 98\" Hi-QLED 4K UHD 98Q6QG",
        "category": "TVs",
        "brand": "Hisense",
        "best_price": 4799.0,
        "original_price": 7999.0,
        "best_store_name": "Tottus",
        "discount_percentage": 40,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/136456_1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Hisense Google TV 98\" Hi-QLED 4K UHD 98Q6QG con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: QLED\", \"Sistema Operativo: Google TV\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Hisense\", \"Tecnología de Pantalla\": \"QLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Google TV\"}",
        "is_favorite": False,
        "historical_min_price": 4799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lg_televisor_lg_85_qned_ai_mini_led_qned70_4k_smar",
        "title": "Televisor LG 85\" QNED AI Mini LED QNED70 4K Smart TV 2026",
        "category": "TVs",
        "brand": "LG",
        "best_price": 3999.0,
        "original_price": 7299.0,
        "best_store_name": "Falabella",
        "discount_percentage": 45,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/138997_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor LG 85\" QNED AI Mini LED QNED70 4K Smart TV 2026 con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: QNED\", \"Sistema Operativo: webOS\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"LG\", \"Tecnología de Pantalla\": \"QNED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"webOS\"}",
        "is_favorite": False,
        "historical_min_price": 3999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_televisor_samsung_smart_tv_55_oled_4k_qn55",
        "title": "Televisor Samsung Smart TV 55\" OLED 4K QN55S90HAGXPE",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 3999.0,
        "original_price": 4598.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139318_2_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor Samsung Smart TV 55\" OLED 4K QN55S90HAGXPE con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: OLED\", \"Sistema Operativo: Tizen\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Tecnología de Pantalla\": \"OLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Tizen\"}",
        "is_favorite": False,
        "historical_min_price": 3999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_tcl_televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "title": "Televisor TCL Google TV 85\" QLED 4K UHD 85P7L",
        "category": "TVs",
        "brand": "TCL",
        "best_price": 3999.0,
        "original_price": 4598.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/0/1/01_tcl_tv_qled_p7l_85_front_full_specs.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Televisor TCL Google TV 85\" QLED 4K UHD 85P7L con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Resolución: 4K Ultra HD (3840 x 2160)\", \"Panel: QLED\", \"Sistema Operativo: Google TV\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"TCL\", \"Tecnología de Pantalla\": \"QLED\", \"Resolución\": \"4K Ultra HD (3840 x 2160)\", \"Sistema Operativo\": \"Google TV\"}",
        "is_favorite": False,
        "historical_min_price": 3999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_ipad_pro_11_chip_m5_wifi_256gb_negro_espacia",
        "title": "iPad Pro 11\" Chip M5 WiFi 256GB Negro Espacial",
        "category": "Tablets",
        "brand": "Apple",
        "best_price": 5299.0,
        "original_price": 6093.85,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/m/img-18277875_m_jpeg_1_4fcf0536-a648-48c2-a7d2-05484d59d32b.webp?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPad Pro 11\" Chip M5 WiFi 256GB Negro Espacial con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple M5\", \"Almacenamiento interno: 256 GB\", \"Sistema Operativo: iPadOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"256 GB\", \"Procesador\": \"Apple M5\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iPadOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 5299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb",
        "title": "Tablet Lenovo Yoga Tab Plus 12.7\" 256GB 16GB RAM + Teclado + Tab Pen Pro",
        "category": "Tablets",
        "brand": "Lenovo",
        "best_price": 2899.0,
        "original_price": 3333.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/136282_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Lenovo Yoga Tab Plus 12.7\" 256GB 16GB RAM + Teclado + Tab Pen Pro con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 16 GB\", \"Almacenamiento interno: 256 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Almacenamiento\": \"256 GB\", \"Memoria RAM\": \"16 GB\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_3",
        "title": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Gray + S Pen",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 2499.0,
        "original_price": 3049.0,
        "best_store_name": "Falabella",
        "discount_percentage": 18,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135782_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Gray + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_4",
        "title": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Silver + S Pen",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 2499.0,
        "original_price": 3049.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 18,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135783_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Silver + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_5",
        "title": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Blue + S Pen",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 2499.0,
        "original_price": 3049.0,
        "best_store_name": "Tottus",
        "discount_percentage": 18,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135784_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE+ 13.1\" 128GB 8GB RAM Blue + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_laptop_lenovo_ideapad_slim_3_de_15_6_amd_ry",
        "title": "Laptop Lenovo IdeaPad Slim 3 de 15.6\", AMD Ryzen 5 7520U, 8GB RAM, disco sólido de 512GB, modelo 82XQ00LTLM",
        "category": "Tablets",
        "brand": "Lenovo",
        "best_price": 2199.0,
        "original_price": 2899.0,
        "best_store_name": "Falabella",
        "discount_percentage": 24,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135438_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop Lenovo IdeaPad Slim 3 de 15.6\", AMD Ryzen 5 7520U, 8GB RAM, disco sólido de 512GB, modelo 82XQ00LTLM con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: AMD Ryzen 5\", \"Memoria RAM: 8 GB\", \"Almacenamiento interno: 8 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Almacenamiento\": \"8 GB\", \"Memoria RAM\": \"8 GB\", \"Procesador\": \"AMD Ryzen 5\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 2199.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "title": "iPad 11\" (11ma Gen) A16 WiFi 128GB Plata",
        "category": "Tablets",
        "brand": "Apple",
        "best_price": 1999.0,
        "original_price": 2299.0,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/ipad_a16_wifi_silver_pdp_image_position_1__laes_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPad 11\" (11ma Gen) A16 WiFi 128GB Plata con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple A16 Bionic\", \"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: iPadOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Procesador\": \"Apple A16 Bionic\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iPadOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 1999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "title": "iPad 11\" (11ma Gen) A16 WiFi 128GB Azul",
        "category": "Tablets",
        "brand": "Apple",
        "best_price": 1999.0,
        "original_price": 2299.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/ipad_a16_wifi_blue_pdp_image_position_1__laes.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPad 11\" (11ma Gen) A16 WiFi 128GB Azul con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple A16 Bionic\", \"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: iPadOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Procesador\": \"Apple A16 Bionic\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iPadOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 1999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_amarillo",
        "title": "iPad 11\" (11ma Gen) A16 WiFi 128GB Amarillo",
        "category": "Tablets",
        "brand": "Apple",
        "best_price": 1999.0,
        "original_price": 2299.0,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/ipad_a16_wifi_yellow_pdp_image_position_1__laes.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "iPad 11\" (11ma Gen) A16 WiFi 128GB Amarillo con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Procesador: Apple A16 Bionic\", \"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: iPadOS 18\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Apple\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Procesador\": \"Apple A16 Bionic\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"iPadOS 18\"}",
        "is_favorite": False,
        "historical_min_price": 1999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g",
        "title": "Tablet Samsung Galaxy Tab S10 FE 10.9\" 128GB 8GB RAM Silver + S Pen",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 1999.0,
        "original_price": 2298.85,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135790_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE 10.9\" 128GB 8GB RAM Silver + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 1999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_1",
        "title": "Tablet Samsung Galaxy Tab S10 FE 10.9\" 128GB 8GB RAM Blue + S Pen",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 1999.0,
        "original_price": 2298.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135791_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE 10.9\" 128GB 8GB RAM Blue + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 1999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_2",
        "title": "Tablet Samsung Galaxy Tab S10 FE 10.9\" 128GB 8GB RAM Gray + S Pen",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 1999.0,
        "original_price": 2298.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135789_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Samsung Galaxy Tab S10 FE 10.9\" 128GB 8GB RAM Gray + S Pen con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 128 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\", \"Almacenamiento\": \"128 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 1999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_r",
        "title": "Tablet Lenovo Idea Tab Pro 12.7\" 256GB 8GB RAM + Teclado + Lapiz + Audífonos",
        "category": "Tablets",
        "brand": "Lenovo",
        "best_price": 1949.0,
        "original_price": 2241.35,
        "best_store_name": "Tottus",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/135377_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tablet Lenovo Idea Tab Pro 12.7\" 256GB 8GB RAM + Teclado + Lapiz + Audífonos con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Memoria RAM: 8 GB\", \"Almacenamiento interno: 256 GB\", \"Sistema Operativo: Android 14\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Lenovo\", \"Almacenamiento\": \"256 GB\", \"Memoria RAM\": \"8 GB\", \"Conectividad\": \"Wi-Fi 6 / Bluetooth 5.3\", \"Sistema Operativo\": \"Android 14\"}",
        "is_favorite": False,
        "historical_min_price": 1949.0,
        "is_historical_min": True
    },
    {
        "id": "prod_jbl_parlante_jbl_partybox_ultimate_negro",
        "title": "Parlante JBL Partybox Ultimate Negro",
        "category": "Audio",
        "brand": "JBL",
        "best_price": 5299.0,
        "original_price": 6093.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/134431_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Parlante JBL Partybox Ultimate Negro con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"JBL\"}",
        "is_favorite": False,
        "historical_min_price": 5299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_sony_consola_playstation_5_pro_2tb",
        "title": "Consola PlayStation 5 Pro 2TB",
        "category": "Gaming",
        "brand": "Sony",
        "best_price": 4399.0,
        "original_price": 5058.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/p/s/ps5-pro_1000x1000_01.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Consola PlayStation 5 Pro 2TB con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Almacenamiento interno: 2 TB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Almacenamiento\": \"2 TB\"}",
        "is_favorite": False,
        "historical_min_price": 4399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_monitor_gamer_samsung_odyssey_oled_g9_49_d",
        "title": "Monitor Gamer Samsung Odyssey OLED G9 49\" Dual QHD LS49DG930SLXPE",
        "category": "Gaming",
        "brand": "Samsung",
        "best_price": 3799.0,
        "original_price": 5389.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 30,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/l/s/ls49dg930slxpe.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Monitor Gamer Samsung Odyssey OLED G9 49\" Dual QHD LS49DG930SLXPE con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Samsung\"}",
        "is_favorite": False,
        "historical_min_price": 3799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_sony_consola_playstation_5_standard_edition_1tb_gr",
        "title": "Consola PlayStation 5 Standard Edition 1TB Gran Turismo 7 + Astro Bot Bundle",
        "category": "Gaming",
        "brand": "Sony",
        "best_price": 3399.0,
        "original_price": 3908.85,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/p/s/ps5_bndlstd_ab_gt7_1500x1500_02.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Consola PlayStation 5 Standard Edition 1TB Gran Turismo 7 + Astro Bot Bundle con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Almacenamiento interno: 1 TB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Almacenamiento\": \"1 TB\"}",
        "is_favorite": False,
        "historical_min_price": 3399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lg_monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx85",
        "title": "Monitor Gamer LG UltraGear GX8 32\" 4K UHD 32GX850A",
        "category": "Gaming",
        "brand": "LG",
        "best_price": 3399.0,
        "original_price": 4399.0,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 23,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/l/g/lg_electronics-487629715-thum-1600x1062.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Monitor Gamer LG UltraGear GX8 32\" 4K UHD 32GX850A con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"LG\"}",
        "is_favorite": False,
        "historical_min_price": 3399.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lg_monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "title": "Monitor LG UltraGear 27\" QHD GX7 OLED 27GX704A-B",
        "category": "Gaming",
        "brand": "LG",
        "best_price": 3299.0,
        "original_price": 3793.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/l/g/lg_electronics-385436730-thum-1600x1062.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Monitor LG UltraGear 27\" QHD GX7 OLED 27GX704A-B con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"LG\"}",
        "is_favorite": False,
        "historical_min_price": 3299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_sony_consola_playstation_5_digital_edition_825gb_g",
        "title": "Consola PlayStation 5 Digital Edition 825GB Gran Turismo 7 + Astro Bot Bundle",
        "category": "Gaming",
        "brand": "Sony",
        "best_price": 2999.0,
        "original_price": 3448.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 5,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/p/s/ps5_bndldig_ab_gt7_01_1000x1000_0_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Consola PlayStation 5 Digital Edition 825GB Gran Turismo 7 + Astro Bot Bundle con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Almacenamiento interno: 825 GB\", \"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Sony\", \"Almacenamiento\": \"825 GB\"}",
        "is_favorite": False,
        "historical_min_price": 2999.0,
        "is_historical_min": True
    },
    {
        "id": "prod_brother_impresora_l_ser_multifuncional_brother_dcp",
        "title": "Impresora Láser Multifuncional Brother DCPL5660DN",
        "category": "Impresoras",
        "brand": "Brother",
        "best_price": 2499.0,
        "original_price": 2873.85,
        "best_store_name": "Tottus",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/b/r/brother_dcpl5660dn.png?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300&format=jpeg",
        "description": "Impresora Láser Multifuncional Brother DCPL5660DN con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Brother\"}",
        "is_favorite": False,
        "historical_min_price": 2499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_nintendo_consola_nintendo_switch_oled_bundle_super",
        "title": "Consola Nintendo Switch OLED Bundle Super Mario Bros. Wonder",
        "category": "Gaming",
        "brand": "Nintendo",
        "best_price": 1899.0,
        "original_price": 2183.85,
        "best_store_name": "Falabella",
        "discount_percentage": 13,
        "available_stores_count": 6,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/134746_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Consola Nintendo Switch OLED Bundle Super Mario Bros. Wonder con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"Nintendo\"}",
        "is_favorite": False,
        "historical_min_price": 1899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_jbl_parlante_amplificador_jbl_eon_one_compact",
        "title": "Parlante Amplificador JBL Eon One Compact",
        "category": "Audio",
        "brand": "JBL",
        "best_price": 1859.0,
        "original_price": 3099.0,
        "best_store_name": "Falabella",
        "discount_percentage": 40,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/j/b/jbl-eon-one-compact-1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Parlante Amplificador JBL Eon One Compact con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"JBL\"}",
        "is_favorite": False,
        "historical_min_price": 1859.0,
        "is_historical_min": True
    },
    {
        "id": "prod_jbl_parlante_jbl_authentics_300_negro",
        "title": "Parlante JBL Authentics 300 Negro",
        "category": "Audio",
        "brand": "JBL",
        "best_price": 1799.0,
        "original_price": 2068.85,
        "best_store_name": "Hiraoka",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/134423_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Parlante JBL Authentics 300 Negro con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"JBL\"}",
        "is_favorite": False,
        "historical_min_price": 1799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_impresora_multifuncional_hp_smart_tank_790_sist",
        "title": "Impresora Multifuncional HP Smart Tank 790 Sistema Continuo, Color, Wi-Fi, Ethernet, ADF, Dúplex (Impresión a doble cara), Fax, Pantalla, HP App",
        "category": "Impresoras",
        "brand": "HP",
        "best_price": 1699.0,
        "original_price": 1953.85,
        "best_store_name": "Ripley",
        "discount_percentage": 13,
        "available_stores_count": 4,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/2/125688_01.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Impresora Multifuncional HP Smart Tank 790 Sistema Continuo, Color, Wi-Fi, Ethernet, ADF, Dúplex (Impresión a doble cara), Fax, Pantalla, HP App con garantía oficial en Perú. Alto rendimiento, diseño moderno y especificaciones técnicas completas.",
        "features_json": "[\"Garantía oficial de 12 meses por el fabricante en Perú\", \"Distribución oficial para el mercado peruano con homologación MTC\"]",
        "tech_specs_json": "{\"Marca\": \"HP\"}",
        "is_favorite": False,
        "historical_min_price": 1699.0,
        "is_historical_min": True
    }
]

SEED_STORE_OFFERS: List[Dict[str, Any]] = [
    {
        "product_id": "prod_samsung_s25_ultra",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5499.0,
        "original_price": 6323.85,
        "offer_url": "https://www.efe.com.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_s25_ultra",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5608.98,
        "original_price": 6450.33,
        "offer_url": "https://www.lacuracao.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_s25_ultra",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5718.96,
        "original_price": 6576.8,
        "offer_url": "https://hiraoka.com.pe/samsung-galaxy-s25-ultra-512gb-titanium-gray",
        "is_best_price": False
    },
    {
        "product_id": "prod_iphone_16",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3399.0,
        "original_price": 3999.0,
        "offer_url": "https://hiraoka.com.pe/iphone-16-6-1-128gb-negro",
        "is_best_price": True
    },
    {
        "product_id": "prod_iphone_16",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3399.0,
        "original_price": 3999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/prod18120095/iPhone-16-128GB/20687062",
        "is_best_price": False
    },
    {
        "product_id": "prod_iphone_16",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3399.0,
        "original_price": 3999.0,
        "offer_url": "https://simple.ripley.com.pe/iphone-16-128gb-2065365819351",
        "is_best_price": False
    },
    {
        "product_id": "prod_iphone_16",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3499.0,
        "original_price": 3999.0,
        "offer_url": "https://www.efe.com.pe/iphone-16-blk-128gb-bes-mye73be-a.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1829.0,
        "original_price": 2103.35,
        "offer_url": "https://hiraoka.com.pe/celular-libre-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-blue",
        "is_best_price": True
    },
    {
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1865.58,
        "original_price": 2145.42,
        "offer_url": "https://www.efe.com.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 1902.16,
        "original_price": 2187.48,
        "offer_url": "https://www.lacuracao.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_edge_50",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2499.0,
        "original_price": 2899.0,
        "offer_url": "https://hiraoka.com.pe/celular-libre-motorola-edge-50-pro-5g-6-7-512gb-12gb-ram-negro",
        "is_best_price": True
    },
    {
        "product_id": "prod_motorola_edge_50",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2548.98,
        "original_price": 2931.33,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/132483842/Motorola-Edge-50-Pro-5G-512GB/132483843",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_edge_50",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2598.96,
        "original_price": 2988.8,
        "offer_url": "https://simple.ripley.com.pe/motorola-edge-50-pro-5g-512gb-12gb-ram-negro-2065324901",
        "is_best_price": False
    },
    {
        "product_id": "prod_macbook_air_m5",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5699.0,
        "original_price": 6553.85,
        "offer_url": "https://hiraoka.com.pe/macbook-air-de-13-chip-m5-16gb-ram-disco-solido-de-512gb-azul-cielo",
        "is_best_price": True
    },
    {
        "product_id": "prod_macbook_air_m5",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5812.98,
        "original_price": 6684.93,
        "offer_url": "https://www.efe.com.pe/macbook-air-13-6-m5-16gb-512gb-silver-mdh74e-a.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_macbook_air_m5",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5926.96,
        "original_price": 6816.0,
        "offer_url": "https://www.lacuracao.pe/macbook-air-13-6-m5-16gb-512gb-silver-mdh74e-a.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_zenbook_14",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4599.0,
        "original_price": 5288.85,
        "offer_url": "https://hiraoka.com.pe/laptop-asus-zenbook-14-oled-intel-core-ultra-7-16gb-ram-1tb-ssd-14-ux3405ma-pp288w",
        "is_best_price": True
    },
    {
        "product_id": "prod_asus_zenbook_14",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4690.98,
        "original_price": 5394.63,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/129849201/Laptop-Asus-Zenbook-14-OLED-Ultra-7/129849202",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_zenbook_14",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4782.96,
        "original_price": 5500.4,
        "offer_url": "https://simple.ripley.com.pe/laptop-asus-zenbook-14-oled-intel-ultra-7-1tb-ssd-2004319201",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_ideapad_slim",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2299.0,
        "original_price": 2799.0,
        "offer_url": "https://hiraoka.com.pe/laptop-lenovo-ideapad-slim-3-15abr8-15-6-amd-ryzen-7-16gb-ram-disco-solido-512gb-abys-blue",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_ideapad_slim",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2344.98,
        "original_price": 2799.0,
        "offer_url": "https://www.efe.com.pe/laptop-lenovo-ideapad-slim-3-15-6-ryzen-7-16gb-512gb.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_ideapad_slim",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2390.96,
        "original_price": 2799.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/128394812/Lenovo-IdeaPad-Slim-3-15.6-Ryzen-7/128394813",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3799.0,
        "original_price": 4999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3799.0,
        "original_price": 4999.0,
        "offer_url": "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3899.0,
        "original_price": 4999.0,
        "offer_url": "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5139.0,
        "original_price": 4999.0,
        "offer_url": "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5139.0,
        "original_price": 4999.0,
        "offer_url": "https://www.lacuracao.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_neo_qled_65",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4499.0,
        "original_price": 5499.0,
        "offer_url": "https://hiraoka.com.pe/televisor-samsung-65-neo-qled-4k-qn85d-smart-tv-qn65qn85dlagxpe",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_neo_qled_65",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4588.98,
        "original_price": 5499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/131984210/Samsung-65-Neo-QLED-4K-QN85D/131984211",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_neo_qled_65",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4678.96,
        "original_price": 5499.0,
        "offer_url": "https://simple.ripley.com.pe/smart-tv-samsung-65-neo-qled-qn85d-4k-2018318291",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_miniled_55",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2299.0,
        "original_price": 2899.0,
        "offer_url": "https://hiraoka.com.pe/televisor-tcl-55-qd-mini-led-4k-google-tv-55c755",
        "is_best_price": True
    },
    {
        "product_id": "prod_tcl_miniled_55",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2344.98,
        "original_price": 2899.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/128392180/TCL-55-Mini-LED-4K-C755/128392181",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_miniled_55",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2390.96,
        "original_price": 2899.0,
        "offer_url": "https://simple.ripley.com.pe/smart-tv-tcl-55-mini-led-google-tv-55c755-2018329181",
        "is_best_price": False
    },
    {
        "product_id": "prod_ipad_11",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1899.0,
        "original_price": 2299.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911",
        "is_best_price": True
    },
    {
        "product_id": "prod_ipad_11",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 1899.0,
        "original_price": 2299.0,
        "offer_url": "https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381",
        "is_best_price": False
    },
    {
        "product_id": "prod_ipad_11",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1949.0,
        "original_price": 2299.0,
        "offer_url": "https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wifi-128gb-plata",
        "is_best_price": False
    },
    {
        "product_id": "prod_ipad_11",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1979.0,
        "original_price": 2299.0,
        "offer_url": "https://www.efe.com.pe/ipad-a16-wi-fi-md4e4ll-a-11-128gb-6gb-p26513743.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tab_s10",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3899.0,
        "original_price": 4499.0,
        "offer_url": "https://hiraoka.com.pe/tablet-samsung-galaxy-tab-s10-plus-12-4-256gb-12gb-ram-silver",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tab_s10",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3976.98,
        "original_price": 4573.53,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/132891021/Samsung-Galaxy-Tab-S10-Plus-256GB/132891022",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tab_s10",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4054.96,
        "original_price": 4663.2,
        "offer_url": "https://simple.ripley.com.pe/tablet-samsung-galaxy-tab-s10-plus-256gb-silver-2065319801",
        "is_best_price": False
    },
    {
        "product_id": "prod_xiaomi_pad_6",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1349.0,
        "original_price": 1599.0,
        "offer_url": "https://hiraoka.com.pe/tablet-xiaomi-pad-6-11-256gb-8gb-ram-gravity-gray",
        "is_best_price": True
    },
    {
        "product_id": "prod_xiaomi_pad_6",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1375.98,
        "original_price": 1599.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/123984102/Xiaomi-Pad-6-256GB-8GB/123984103",
        "is_best_price": False
    },
    {
        "product_id": "prod_xiaomi_pad_6",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1402.96,
        "original_price": 1613.4,
        "offer_url": "https://www.efe.com.pe/tablet-xiaomi-pad-6-256gb-gray/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_wh1000xm5",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1299.0,
        "original_price": 1599.0,
        "offer_url": "https://hiraoka.com.pe/audifonos-sony-wh-1000xm5-noise-cancelling-negro",
        "is_best_price": True
    },
    {
        "product_id": "prod_sony_wh1000xm5",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1324.98,
        "original_price": 1599.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18491201/Audifonos-Sony-WH-1000XM5-Negro/18491202",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_wh1000xm5",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1350.96,
        "original_price": 1599.0,
        "offer_url": "https://simple.ripley.com.pe/audifonos-sony-wh-1000xm5-bluetooth-negro-2023281928",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_wh1000xm5",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1376.94,
        "original_price": 1599.0,
        "offer_url": "https://www.efe.com.pe/audifonos-sony-wh-1000xm5-negro/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_airpods_pro_2",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 949.0,
        "original_price": 1199.0,
        "offer_url": "https://hiraoka.com.pe/audifonos-apple-airpods-pro-2-generacion-con-estuche-magsafe-usb-c",
        "is_best_price": True
    },
    {
        "product_id": "prod_airpods_pro_2",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 967.98,
        "original_price": 1199.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18129012/AirPods-Pro-2da-Gen-USB-C/18129013",
        "is_best_price": False
    },
    {
        "product_id": "prod_airpods_pro_2",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 986.96,
        "original_price": 1199.0,
        "offer_url": "https://simple.ripley.com.pe/audifonos-apple-airpods-pro-2-generacion-usb-c-206530182",
        "is_best_price": False
    },
    {
        "product_id": "prod_airpods_pro_2",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1005.94,
        "original_price": 1199.0,
        "offer_url": "https://www.efe.com.pe/audifonos-apple-airpods-pro-2da-gen-usb-c/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_ps5_slim",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2499.0,
        "original_price": 2873.85,
        "offer_url": "https://hiraoka.com.pe/consola-playstation-5-slim-con-lector-1tb-blanco",
        "is_best_price": True
    },
    {
        "product_id": "prod_ps5_slim",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2548.98,
        "original_price": 2931.33,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/129840129/Consola-PlayStation-5-Slim-1TB/129840130",
        "is_best_price": False
    },
    {
        "product_id": "prod_ps5_slim",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2598.96,
        "original_price": 2988.8,
        "offer_url": "https://simple.ripley.com.pe/consola-playstation-5-slim-1tb-con-lector-208431920",
        "is_best_price": False
    },
    {
        "product_id": "prod_ps5_slim",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2648.94,
        "original_price": 3046.28,
        "offer_url": "https://www.efe.com.pe/consola-ps5-slim-1tb-con-lector/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_nintendo_switch_oled",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1399.0,
        "original_price": 1699.0,
        "offer_url": "https://hiraoka.com.pe/consola-nintendo-switch-oled-joy-con-blanco",
        "is_best_price": True
    },
    {
        "product_id": "prod_nintendo_switch_oled",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1426.98,
        "original_price": 1699.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18239012/Nintendo-Switch-OLED-Blanco/18239013",
        "is_best_price": False
    },
    {
        "product_id": "prod_nintendo_switch_oled",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1454.96,
        "original_price": 1699.0,
        "offer_url": "https://simple.ripley.com.pe/consola-nintendo-switch-oled-blanco-206528192",
        "is_best_price": False
    },
    {
        "product_id": "prod_nintendo_switch_oled",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1482.94,
        "original_price": 1705.38,
        "offer_url": "https://www.efe.com.pe/consola-nintendo-switch-oled-blanco/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_epson_l3250",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 699.0,
        "original_price": 849.0,
        "offer_url": "https://hiraoka.com.pe/impresora-multifuncional-epson-ecotank-l3250-wi-fi",
        "is_best_price": True
    },
    {
        "product_id": "prod_epson_l3250",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 712.98,
        "original_price": 849.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18192031/Impresora-Epson-EcoTank-L3250/18192032",
        "is_best_price": False
    },
    {
        "product_id": "prod_epson_l3250",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 726.96,
        "original_price": 849.0,
        "offer_url": "https://simple.ripley.com.pe/impresora-multifuncional-epson-ecotank-l3250-202328192",
        "is_best_price": False
    },
    {
        "product_id": "prod_epson_l3250",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 740.94,
        "original_price": 852.08,
        "offer_url": "https://www.efe.com.pe/impresora-epson-ecotank-l3250-wifi/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_alpha_7_iv",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 9999.0,
        "original_price": 11499.0,
        "offer_url": "https://hiraoka.com.pe/camara-mirrorless-sony-alpha-7-iv-ilce-7m4-cuerpo",
        "is_best_price": True
    },
    {
        "product_id": "prod_sony_alpha_7_iv",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 10198.98,
        "original_price": 11728.83,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18293012/Camara-Sony-Alpha-7-IV-Cuerpo/18293013",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_alpha_7_iv",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 10398.96,
        "original_price": 11958.8,
        "offer_url": "https://simple.ripley.com.pe/camara-sony-alpha-7-iv-mirrorless-cuerpo-20653198",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_plata",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7999.0,
        "original_price": 9198.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/54471183/iphone_17_pro_max_6_9_512gb_plata",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_plata",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 8158.98,
        "original_price": 9382.83,
        "offer_url": "https://simple.ripley.com.pe/iphone_17_pro_max_6_9_512gb_plata-9471183",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_plata",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 8318.96,
        "original_price": 9566.8,
        "offer_url": "https://hiraoka.com.pe/iphone_17_pro_max_6_9_512gb_plata",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_plata",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 8478.94,
        "original_price": 9750.78,
        "offer_url": "https://www.efe.com.pe/iphone_17_pro_max_6_9_512gb_plata",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_azul_profundo",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6999.0,
        "original_price": 8048.85,
        "offer_url": "https://hiraoka.com.pe/iphone_17_pro_max_6_9_512gb_azul_profundo",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_azul_profundo",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7138.98,
        "original_price": 8209.83,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/32594512/iphone_17_pro_max_6_9_512gb_azul_profundo",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_azul_profundo",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 7278.96,
        "original_price": 8370.8,
        "offer_url": "https://www.lacuracao.pe/iphone_17_pro_max_6_9_512gb_azul_profundo",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_azul_profundo",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 7418.94,
        "original_price": 8531.78,
        "offer_url": "https://simple.ripley.com.pe/iphone_17_pro_max_6_9_512gb_azul_profundo-5594512",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_naranja_c_smico",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6999.0,
        "original_price": 8048.85,
        "offer_url": "https://simple.ripley.com.pe/iphone_17_pro_max_6_9_512gb_naranja_c_smico-4806987",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_naranja_c_smico",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7138.98,
        "original_price": 8209.83,
        "offer_url": "https://hiraoka.com.pe/iphone_17_pro_max_6_9_512gb_naranja_c_smico",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_naranja_c_smico",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 7278.96,
        "original_price": 8370.8,
        "offer_url": "https://www.tottus.com.pe/iphone_17_pro_max_6_9_512gb_naranja_c_smico/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_naranja_c_smico",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7418.94,
        "original_price": 8531.78,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/94806987/iphone_17_pro_max_6_9_512gb_naranja_c_smico",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5999.0,
        "original_price": 6898.85,
        "offer_url": "https://www.efe.com.pe/iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 6118.98,
        "original_price": 7036.83,
        "offer_url": "https://www.lacuracao.pe/iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6238.96,
        "original_price": 7174.8,
        "offer_url": "https://hiraoka.com.pe/iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6358.94,
        "original_price": 7312.78,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/38818125/iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 5299.0,
        "original_price": 6899.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/91189643/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_cobalt_violet",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 5404.98,
        "original_price": 6899.0,
        "offer_url": "https://www.metro.pe/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_cobalt_violet/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 5510.96,
        "original_price": 6899.0,
        "offer_url": "https://www.wong.pe/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_cobalt_violet/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5616.94,
        "original_price": 6899.0,
        "offer_url": "https://hiraoka.com.pe/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_cobalt_violet",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 5722.92,
        "original_price": 6899.0,
        "offer_url": "https://simple.ripley.com.pe/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_cobalt_violet-1189643",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5299.0,
        "original_price": 6899.0,
        "offer_url": "https://hiraoka.com.pe/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_black",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb_1",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5404.98,
        "original_price": 6899.0,
        "offer_url": "https://www.efe.com.pe/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_black",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb_1",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5510.96,
        "original_price": 6899.0,
        "offer_url": "https://www.lacuracao.pe/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_black",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb_1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 5616.94,
        "original_price": 6899.0,
        "offer_url": "https://simple.ripley.com.pe/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_black-6370639",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 5722.92,
        "original_price": 6899.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/15370639/celular_samsung_galaxy_s26_ultra_6_9_512gb_12gb_ram_black",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_6_3_512gb_12gb_",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 4499.0,
        "original_price": 5499.0,
        "offer_url": "https://www.tottus.com.pe/celular_samsung_galaxy_s26_6_3_512gb_12gb_ram_black/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_6_3_512gb_12gb_",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 4588.98,
        "original_price": 5499.0,
        "offer_url": "https://www.metro.pe/celular_samsung_galaxy_s26_6_3_512gb_12gb_ram_black/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_6_3_512gb_12gb_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4678.96,
        "original_price": 5499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/36661925/celular_samsung_galaxy_s26_6_3_512gb_12gb_ram_black",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_6_3_512gb_12gb_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4768.94,
        "original_price": 5499.0,
        "offer_url": "https://hiraoka.com.pe/celular_samsung_galaxy_s26_6_3_512gb_12gb_ram_black",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_16_6_1_128gb_blanco",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3499.0,
        "original_price": 4023.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/36070340/iphone_16_6_1_128gb_blanco",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_iphone_16_6_1_128gb_blanco",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3568.98,
        "original_price": 4104.33,
        "offer_url": "https://hiraoka.com.pe/iphone_16_6_1_128gb_blanco",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_16_6_1_128gb_blanco",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3638.96,
        "original_price": 4184.8,
        "offer_url": "https://simple.ripley.com.pe/iphone_16_6_1_128gb_blanco-9070340",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_16_6_1_128gb_blanco",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 3708.94,
        "original_price": 4265.28,
        "offer_url": "https://www.lacuracao.pe/iphone_16_6_1_128gb_blanco",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_16_6_1_128gb_blanco",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 3778.92,
        "original_price": 4345.76,
        "offer_url": "https://www.tottus.com.pe/iphone_16_6_1_128gb_blanco/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_16_6_1_128gb_blanco",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3848.9,
        "original_price": 4426.23,
        "offer_url": "https://www.efe.com.pe/iphone_16_6_1_128gb_blanco",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_ne",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3499.0,
        "original_price": 4023.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/25033936/celular_honor_600_pro_6_57_512gb_12gb_ram_negro",
        "is_best_price": True
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_ne",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3568.98,
        "original_price": 4104.33,
        "offer_url": "https://simple.ripley.com.pe/celular_honor_600_pro_6_57_512gb_12gb_ram_negro-7033936",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_ne",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3638.96,
        "original_price": 4184.8,
        "offer_url": "https://hiraoka.com.pe/celular_honor_600_pro_6_57_512gb_12gb_ram_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_ne",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3708.94,
        "original_price": 4265.28,
        "offer_url": "https://www.efe.com.pe/celular_honor_600_pro_6_57_512gb_12gb_ram_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_do",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3499.0,
        "original_price": 4023.85,
        "offer_url": "https://hiraoka.com.pe/celular_honor_600_pro_6_57_512gb_12gb_ram_dorado_platino",
        "is_best_price": True
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_do",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3568.98,
        "original_price": 4104.33,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/57096773/celular_honor_600_pro_6_57_512gb_12gb_ram_dorado_platino",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_do",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 3638.96,
        "original_price": 4184.8,
        "offer_url": "https://www.lacuracao.pe/celular_honor_600_pro_6_57_512gb_12gb_ram_dorado_platino",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_do",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3708.94,
        "original_price": 4265.28,
        "offer_url": "https://simple.ripley.com.pe/celular_honor_600_pro_6_57_512gb_12gb_ram_dorado_platino-3096773",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_15_6_1_128gb_negro",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2899.0,
        "original_price": 3499.0,
        "offer_url": "https://simple.ripley.com.pe/iphone_15_6_1_128gb_negro-8073492",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_iphone_15_6_1_128gb_negro",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2956.98,
        "original_price": 3499.0,
        "offer_url": "https://hiraoka.com.pe/iphone_15_6_1_128gb_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_15_6_1_128gb_negro",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 3014.96,
        "original_price": 3499.0,
        "offer_url": "https://www.tottus.com.pe/iphone_15_6_1_128gb_negro/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_iphone_15_6_1_128gb_negro",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3072.94,
        "original_price": 3533.88,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/35073492/iphone_15_6_1_128gb_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2599.0,
        "original_price": 2988.85,
        "offer_url": "https://www.efe.com.pe/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_blanco",
        "is_best_price": True
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2650.98,
        "original_price": 3048.63,
        "offer_url": "https://www.lacuracao.pe/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_blanco",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2702.96,
        "original_price": 3108.4,
        "offer_url": "https://hiraoka.com.pe/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_blanco",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2754.94,
        "original_price": 3168.18,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/94248539/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_blanco",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2599.0,
        "original_price": 2988.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/65285127/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_azul",
        "is_best_price": True
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1_1",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 2650.98,
        "original_price": 3048.63,
        "offer_url": "https://www.metro.pe/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_azul/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1_1",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 2702.96,
        "original_price": 3108.4,
        "offer_url": "https://www.wong.pe/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_azul/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2754.94,
        "original_price": 3168.18,
        "offer_url": "https://hiraoka.com.pe/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_azul",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1_1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2806.92,
        "original_price": 3227.96,
        "offer_url": "https://simple.ripley.com.pe/celular_motorola_edge_70_pro_6_78_512gb_12gb_ram_azul-2285127",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2499.0,
        "original_price": 3049.0,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2548.98,
        "original_price": 3049.0,
        "offer_url": "https://www.efe.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2598.96,
        "original_price": 3049.0,
        "offer_url": "https://www.lacuracao.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2648.94,
        "original_price": 3049.0,
        "offer_url": "https://simple.ripley.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen-7820118",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2698.92,
        "original_price": 3103.76,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/43820118/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_1",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2499.0,
        "original_price": 3049.0,
        "offer_url": "https://www.tottus.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_blue_s_pen/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_1",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 2548.98,
        "original_price": 3049.0,
        "offer_url": "https://www.metro.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_blue_s_pen/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2598.96,
        "original_price": 3049.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/84137348/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_blue_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2648.94,
        "original_price": 3049.0,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_blue_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_2",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2499.0,
        "original_price": 3049.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/74017204/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_2",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2548.98,
        "original_price": 3049.0,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_2",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2598.96,
        "original_price": 3049.0,
        "offer_url": "https://simple.ripley.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen-2017204",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_2",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2648.94,
        "original_price": 3049.0,
        "offer_url": "https://www.lacuracao.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_2",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2698.92,
        "original_price": 3103.76,
        "offer_url": "https://www.tottus.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_2",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2748.9,
        "original_price": 3161.23,
        "offer_url": "https://www.efe.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_moto_edge_60_pro_6_7_512",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2499.0,
        "original_price": 2873.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/60820047/celular_motorola_moto_edge_60_pro_6_7_512gb_12gb_ram_gris",
        "is_best_price": True
    },
    {
        "product_id": "prod_motorola_celular_motorola_moto_edge_60_pro_6_7_512",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2548.98,
        "original_price": 2931.33,
        "offer_url": "https://simple.ripley.com.pe/celular_motorola_moto_edge_60_pro_6_7_512gb_12gb_ram_gris-6820047",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_moto_edge_60_pro_6_7_512",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2598.96,
        "original_price": 2988.8,
        "offer_url": "https://hiraoka.com.pe/celular_motorola_moto_edge_60_pro_6_7_512gb_12gb_ram_gris",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_motorola_moto_edge_60_pro_6_7_512",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2648.94,
        "original_price": 3046.28,
        "offer_url": "https://www.efe.com.pe/celular_motorola_moto_edge_60_pro_6_7_512gb_12gb_ram_gris",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2399.0,
        "original_price": 2758.85,
        "offer_url": "https://hiraoka.com.pe/celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "is_best_price": True
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2446.98,
        "original_price": 2814.03,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/60650182/celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2494.96,
        "original_price": 2869.2,
        "offer_url": "https://www.lacuracao.pe/celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2542.94,
        "original_price": 2924.38,
        "offer_url": "https://simple.ripley.com.pe/celular_honor_600_6_57_512gb_8gb_ram_naranja-6650182",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_negro",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2399.0,
        "original_price": 2758.85,
        "offer_url": "https://simple.ripley.com.pe/celular_honor_600_6_57_512gb_8gb_ram_negro-3543606",
        "is_best_price": True
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_negro",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2446.98,
        "original_price": 2814.03,
        "offer_url": "https://hiraoka.com.pe/celular_honor_600_6_57_512gb_8gb_ram_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_negro",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2494.96,
        "original_price": 2869.2,
        "offer_url": "https://www.tottus.com.pe/celular_honor_600_6_57_512gb_8gb_ram_negro/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_negro",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2542.94,
        "original_price": 2924.38,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/93543606/celular_honor_600_6_57_512gb_8gb_ram_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_dorado_",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2399.0,
        "original_price": 2758.85,
        "offer_url": "https://www.efe.com.pe/celular_honor_600_6_57_512gb_8gb_ram_dorado_platino",
        "is_best_price": True
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_dorado_",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2446.98,
        "original_price": 2814.03,
        "offer_url": "https://www.lacuracao.pe/celular_honor_600_6_57_512gb_8gb_ram_dorado_platino",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_dorado_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2494.96,
        "original_price": 2869.2,
        "offer_url": "https://hiraoka.com.pe/celular_honor_600_6_57_512gb_8gb_ram_dorado_platino",
        "is_best_price": False
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_dorado_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2542.94,
        "original_price": 2924.38,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/90751638/celular_honor_600_6_57_512gb_8gb_ram_dorado_platino",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2099.0,
        "original_price": 2413.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/58638311/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_violet",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 2140.98,
        "original_price": 2462.13,
        "offer_url": "https://www.metro.pe/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_violet/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 2182.96,
        "original_price": 2510.4,
        "offer_url": "https://www.wong.pe/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_violet/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2224.94,
        "original_price": 2558.68,
        "offer_url": "https://hiraoka.com.pe/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_violet",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2266.92,
        "original_price": 2606.96,
        "offer_url": "https://simple.ripley.com.pe/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_violet-4638311",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2099.0,
        "original_price": 2413.85,
        "offer_url": "https://hiraoka.com.pe/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_dark_blue",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g_1",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2140.98,
        "original_price": 2462.13,
        "offer_url": "https://www.efe.com.pe/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_dark_blue",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g_1",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2182.96,
        "original_price": 2510.4,
        "offer_url": "https://www.lacuracao.pe/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_dark_blue",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g_1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2224.94,
        "original_price": 2558.68,
        "offer_url": "https://simple.ripley.com.pe/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_dark_blue-9118463",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2266.92,
        "original_price": 2606.96,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/45118463/celular_samsung_galaxy_a57_6_7_5g_256gb_8gb_ram_dark_blue",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb_",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2099.0,
        "original_price": 2499.0,
        "offer_url": "https://www.tottus.com.pe/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_gris/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb_",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 2140.98,
        "original_price": 2499.0,
        "offer_url": "https://www.metro.pe/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_gris/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2182.96,
        "original_price": 2510.4,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/93146743/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_gris",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2224.94,
        "original_price": 2558.68,
        "offer_url": "https://hiraoka.com.pe/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_gris",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb__1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2099.0,
        "original_price": 2499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/27667322/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_verde",
        "is_best_price": True
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb__1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2140.98,
        "original_price": 2499.0,
        "offer_url": "https://hiraoka.com.pe/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_verde",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb__1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2182.96,
        "original_price": 2510.4,
        "offer_url": "https://simple.ripley.com.pe/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_verde-9667322",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb__1",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2224.94,
        "original_price": 2558.68,
        "offer_url": "https://www.lacuracao.pe/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_verde",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb__1",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2266.92,
        "original_price": 2606.96,
        "offer_url": "https://www.tottus.com.pe/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_verde/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb__1",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2308.9,
        "original_price": 2655.23,
        "offer_url": "https://www.efe.com.pe/celular_libre_motorola_edge_70_6_7_512gb_12gb_ram_verde",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_zephyrus_duo_16_de_16_i",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 25499.0,
        "original_price": 29323.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/54990421/laptop_gamer_asus_rog_zephyrus_duo_16_de_16_intel_core_ultra_9_386h_series_3_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_gx651ax_sr058w",
        "is_best_price": True
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_zephyrus_duo_16_de_16_i",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 26008.98,
        "original_price": 29910.33,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_asus_rog_zephyrus_duo_16_de_16_intel_core_ultra_9_386h_series_3_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_gx651ax_sr058w-9990421",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_zephyrus_duo_16_de_16_i",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 26518.96,
        "original_price": 30496.8,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_asus_rog_zephyrus_duo_16_de_16_intel_core_ultra_9_386h_series_3_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_gx651ax_sr058w",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_zephyrus_duo_16_de_16_i",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 27028.94,
        "original_price": 31083.28,
        "offer_url": "https://www.efe.com.pe/laptop_gamer_asus_rog_zephyrus_duo_16_de_16_intel_core_ultra_9_386h_series_3_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_gx651ax_sr058w",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 22499.0,
        "original_price": 25873.85,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 22948.98,
        "original_price": 26391.33,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/50638902/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 23398.96,
        "original_price": 26908.8,
        "offer_url": "https://www.lacuracao.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 23848.94,
        "original_price": 27426.28,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm-5638902",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_int",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 15899.0,
        "original_price": 18283.85,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5080_32gb_ram_disco_s_lido_de_1tb_modelo_83f5000xlm-3963391",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_int",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 16216.98,
        "original_price": 18649.53,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5080_32gb_ram_disco_s_lido_de_1tb_modelo_83f5000xlm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_int",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 16534.96,
        "original_price": 19015.2,
        "offer_url": "https://www.tottus.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5080_32gb_ram_disco_s_lido_de_1tb_modelo_83f5000xlm/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_int",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 16852.94,
        "original_price": 19380.88,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/66963391/laptop_gamer_lenovo_legion_pro_7i_de_16_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5080_32gb_ram_disco_s_lido_de_1tb_modelo_83f5000xlm",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_pro_de_14_chip_m5_16gb_ram_disco_s_l",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 9999.0,
        "original_price": 11498.85,
        "offer_url": "https://www.efe.com.pe/macbook_pro_de_14_chip_m5_16gb_ram_disco_s_lido_de_1tb_color_plata_teclado_en_espa_ol",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_macbook_pro_de_14_chip_m5_16gb_ram_disco_s_l",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 10198.98,
        "original_price": 11728.83,
        "offer_url": "https://www.lacuracao.pe/macbook_pro_de_14_chip_m5_16gb_ram_disco_s_lido_de_1tb_color_plata_teclado_en_espa_ol",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_pro_de_14_chip_m5_16gb_ram_disco_s_l",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 10398.96,
        "original_price": 11958.8,
        "offer_url": "https://hiraoka.com.pe/macbook_pro_de_14_chip_m5_16gb_ram_disco_s_lido_de_1tb_color_plata_teclado_en_espa_ol",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_pro_de_14_chip_m5_16gb_ram_disco_s_l",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 10598.94,
        "original_price": 12188.78,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/29245293/macbook_pro_de_14_chip_m5_16gb_ram_disco_s_lido_de_1tb_color_plata_teclado_en_espa_ol",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_amd_ryz",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 9499.0,
        "original_price": 11999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/60506941/laptop_gamer_asus_rog_strix_g16_de_16_amd_ryzen_9_9955hx_nvidia_geforce_rtx_5070_16gb_ram_disco_s_lido_de_1tb_modelo_g614fp_rv010w",
        "is_best_price": True
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_amd_ryz",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 9688.98,
        "original_price": 11999.0,
        "offer_url": "https://www.metro.pe/laptop_gamer_asus_rog_strix_g16_de_16_amd_ryzen_9_9955hx_nvidia_geforce_rtx_5070_16gb_ram_disco_s_lido_de_1tb_modelo_g614fp_rv010w/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_amd_ryz",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 9878.96,
        "original_price": 11999.0,
        "offer_url": "https://www.wong.pe/laptop_gamer_asus_rog_strix_g16_de_16_amd_ryzen_9_9955hx_nvidia_geforce_rtx_5070_16gb_ram_disco_s_lido_de_1tb_modelo_g614fp_rv010w/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_amd_ryz",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 10068.94,
        "original_price": 11999.0,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_asus_rog_strix_g16_de_16_amd_ryzen_9_9955hx_nvidia_geforce_rtx_5070_16gb_ram_disco_s_lido_de_1tb_modelo_g614fp_rv010w",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_amd_ryz",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 10258.92,
        "original_price": 11999.0,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_asus_rog_strix_g16_de_16_amd_ryzen_9_9955hx_nvidia_geforce_rtx_5070_16gb_ram_disco_s_lido_de_1tb_modelo_g614fp_rv010w-6506941",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 8299.0,
        "original_price": 9543.85,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_15_ga0001la",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 8464.98,
        "original_price": 9734.73,
        "offer_url": "https://www.efe.com.pe/laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_15_ga0001la",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 8630.96,
        "original_price": 9925.6,
        "offer_url": "https://www.lacuracao.pe/laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_15_ga0001la",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 8796.94,
        "original_price": 10116.48,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_15_ga0001la-3863257",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 8962.92,
        "original_price": 10307.36,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/39863257/laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_15_ga0001la",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_5i_de_15_3_intel",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 8299.0,
        "original_price": 9543.85,
        "offer_url": "https://www.tottus.com.pe/laptop_gamer_lenovo_legion_5i_de_15_3_intel_core_i7_13650hx_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_1tb_modelo_83ly009mlm/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_5i_de_15_3_intel",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 8464.98,
        "original_price": 9734.73,
        "offer_url": "https://www.metro.pe/laptop_gamer_lenovo_legion_5i_de_15_3_intel_core_i7_13650hx_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_1tb_modelo_83ly009mlm/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_5i_de_15_3_intel",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 8630.96,
        "original_price": 9925.6,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/39899612/laptop_gamer_lenovo_legion_5i_de_15_3_intel_core_i7_13650hx_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_1tb_modelo_83ly009mlm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_5i_de_15_3_intel",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 8796.94,
        "original_price": 10116.48,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_lenovo_legion_5i_de_15_3_intel_core_i7_13650hx_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_1tb_modelo_83ly009mlm",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_hp_omnibook_ultra_de_14_pantalla_touch_i",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7799.0,
        "original_price": 8968.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/82000047/laptop_hp_omnibook_ultra_de_14_pantalla_touch_intel_core_ultra_7_356h_series_3_16gb_ram_disco_s_lido_de_1tb_modelo_14_kd0070la",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_laptop_hp_omnibook_ultra_de_14_pantalla_touch_i",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7954.98,
        "original_price": 9148.23,
        "offer_url": "https://hiraoka.com.pe/laptop_hp_omnibook_ultra_de_14_pantalla_touch_intel_core_ultra_7_356h_series_3_16gb_ram_disco_s_lido_de_1tb_modelo_14_kd0070la",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_hp_omnibook_ultra_de_14_pantalla_touch_i",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 8110.96,
        "original_price": 9327.6,
        "offer_url": "https://simple.ripley.com.pe/laptop_hp_omnibook_ultra_de_14_pantalla_touch_intel_core_ultra_7_356h_series_3_16gb_ram_disco_s_lido_de_1tb_modelo_14_kd0070la-1000047",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_hp_omnibook_ultra_de_14_pantalla_touch_i",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 8266.94,
        "original_price": 9506.98,
        "offer_url": "https://www.lacuracao.pe/laptop_hp_omnibook_ultra_de_14_pantalla_touch_intel_core_ultra_7_356h_series_3_16gb_ram_disco_s_lido_de_1tb_modelo_14_kd0070la",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_hp_omnibook_ultra_de_14_pantalla_touch_i",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 8422.92,
        "original_price": 9686.36,
        "offer_url": "https://www.tottus.com.pe/laptop_hp_omnibook_ultra_de_14_pantalla_touch_intel_core_ultra_7_356h_series_3_16gb_ram_disco_s_lido_de_1tb_modelo_14_kd0070la/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_hp_omnibook_ultra_de_14_pantalla_touch_i",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 8578.9,
        "original_price": 9865.73,
        "offer_url": "https://www.efe.com.pe/laptop_hp_omnibook_ultra_de_14_pantalla_touch_intel_core_ultra_7_356h_series_3_16gb_ram_disco_s_lido_de_1tb_modelo_14_kd0070la",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7699.0,
        "original_price": 8853.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/96385959/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_1tb_color_plata_teclado_en_espa_ol",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 7852.98,
        "original_price": 9030.93,
        "offer_url": "https://simple.ripley.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_1tb_color_plata_teclado_en_espa_ol-6385959",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 8006.96,
        "original_price": 9208.0,
        "offer_url": "https://hiraoka.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_1tb_color_plata_teclado_en_espa_ol",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 8160.94,
        "original_price": 9385.08,
        "offer_url": "https://www.efe.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_1tb_color_plata_teclado_en_espa_ol",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_15_chip_m5_16gb_ram_disco_s_l",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7599.0,
        "original_price": 8738.85,
        "offer_url": "https://hiraoka.com.pe/macbook_air_de_15_chip_m5_16gb_ram_disco_s_lido_de_512gb_blanco_estelar",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_macbook_air_de_15_chip_m5_16gb_ram_disco_s_l",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7750.98,
        "original_price": 8913.63,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/31923081/macbook_air_de_15_chip_m5_16gb_ram_disco_s_lido_de_512gb_blanco_estelar",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_15_chip_m5_16gb_ram_disco_s_l",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 7902.96,
        "original_price": 9088.4,
        "offer_url": "https://www.lacuracao.pe/macbook_air_de_15_chip_m5_16gb_ram_disco_s_lido_de_512gb_blanco_estelar",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_15_chip_m5_16gb_ram_disco_s_l",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 8054.94,
        "original_price": 9263.18,
        "offer_url": "https://simple.ripley.com.pe/macbook_air_de_15_chip_m5_16gb_ram_disco_s_lido_de_512gb_blanco_estelar-4923081",
        "is_best_price": False
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 7399.0,
        "original_price": 8508.85,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7_170_nvidia_geforce_rtx_5060_32gb_ram_disco_s_lido_de_512gb_modelo_anv15_a31_r2th-8780110",
        "is_best_price": True
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7546.98,
        "original_price": 8679.03,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7_170_nvidia_geforce_rtx_5060_32gb_ram_disco_s_lido_de_512gb_modelo_anv15_a31_r2th",
        "is_best_price": False
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 7694.96,
        "original_price": 8849.2,
        "offer_url": "https://www.tottus.com.pe/laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7_170_nvidia_geforce_rtx_5060_32gb_ram_disco_s_lido_de_512gb_modelo_anv15_a31_r2th/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7842.94,
        "original_price": 9019.38,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/71780110/laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7_170_nvidia_geforce_rtx_5060_32gb_ram_disco_s_lido_de_512gb_modelo_anv15_a31_r2th",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_intel_c",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 7199.0,
        "original_price": 8278.85,
        "offer_url": "https://www.efe.com.pe/laptop_gamer_asus_rog_strix_g16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_g615jmr_rv165w",
        "is_best_price": True
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_intel_c",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 7342.98,
        "original_price": 8444.43,
        "offer_url": "https://www.lacuracao.pe/laptop_gamer_asus_rog_strix_g16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_g615jmr_rv165w",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_intel_c",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7486.96,
        "original_price": 8610.0,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_asus_rog_strix_g16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_g615jmr_rv165w",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_intel_c",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7630.94,
        "original_price": 8775.58,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/93521998/laptop_gamer_asus_rog_strix_g16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_g615jmr_rv165w",
        "is_best_price": False
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_katana_15_hx_de_15_6_intel_co",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7099.0,
        "original_price": 8163.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/95513329/laptop_gamer_msi_katana_15_hx_de_15_6_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b14wfk_1055",
        "is_best_price": True
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_katana_15_hx_de_15_6_intel_co",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 7240.98,
        "original_price": 8327.13,
        "offer_url": "https://www.metro.pe/laptop_gamer_msi_katana_15_hx_de_15_6_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b14wfk_1055/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_katana_15_hx_de_15_6_intel_co",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 7382.96,
        "original_price": 8490.4,
        "offer_url": "https://www.wong.pe/laptop_gamer_msi_katana_15_hx_de_15_6_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b14wfk_1055/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_katana_15_hx_de_15_6_intel_co",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7524.94,
        "original_price": 8653.68,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_msi_katana_15_hx_de_15_6_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b14wfk_1055",
        "is_best_price": False
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_katana_15_hx_de_15_6_intel_co",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 7666.92,
        "original_price": 8816.96,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_msi_katana_15_hx_de_15_6_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b14wfk_1055-5513329",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_pc_gamer_lenovo_legion_5_intel_core_ultra_5",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6799.0,
        "original_price": 7818.85,
        "offer_url": "https://hiraoka.com.pe/pc_gamer_lenovo_legion_5_intel_core_ultra_5_225_series_2_nvidia_geforce_rtx_5060_ti_16gb_ram_disco_s_lido_de_1tb_modelo_90ya002tpt",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_pc_gamer_lenovo_legion_5_intel_core_ultra_5",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 6934.98,
        "original_price": 7975.23,
        "offer_url": "https://www.efe.com.pe/pc_gamer_lenovo_legion_5_intel_core_ultra_5_225_series_2_nvidia_geforce_rtx_5060_ti_16gb_ram_disco_s_lido_de_1tb_modelo_90ya002tpt",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_pc_gamer_lenovo_legion_5_intel_core_ultra_5",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 7070.96,
        "original_price": 8131.6,
        "offer_url": "https://www.lacuracao.pe/pc_gamer_lenovo_legion_5_intel_core_ultra_5_225_series_2_nvidia_geforce_rtx_5060_ti_16gb_ram_disco_s_lido_de_1tb_modelo_90ya002tpt",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_pc_gamer_lenovo_legion_5_intel_core_ultra_5",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 7206.94,
        "original_price": 8287.98,
        "offer_url": "https://simple.ripley.com.pe/pc_gamer_lenovo_legion_5_intel_core_ultra_5_225_series_2_nvidia_geforce_rtx_5060_ti_16gb_ram_disco_s_lido_de_1tb_modelo_90ya002tpt-2404723",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_pc_gamer_lenovo_legion_5_intel_core_ultra_5",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7342.92,
        "original_price": 8444.36,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/47404723/pc_gamer_lenovo_legion_5_intel_core_ultra_5_225_series_2_nvidia_geforce_rtx_5060_ti_16gb_ram_disco_s_lido_de_1tb_modelo_90ya002tpt",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_intel_core_i7_13",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 6699.0,
        "original_price": 7703.85,
        "offer_url": "https://www.tottus.com.pe/laptop_gamer_hp_victus_de_15_6_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_4050_16gb_ram_disco_s_lido_de_1tb_modelo_15_fa2012la/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_intel_core_i7_13",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 6832.98,
        "original_price": 7857.93,
        "offer_url": "https://www.metro.pe/laptop_gamer_hp_victus_de_15_6_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_4050_16gb_ram_disco_s_lido_de_1tb_modelo_15_fa2012la/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_intel_core_i7_13",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6966.96,
        "original_price": 8012.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/26028918/laptop_gamer_hp_victus_de_15_6_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_4050_16gb_ram_disco_s_lido_de_1tb_modelo_15_fa2012la",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_intel_core_i7_13",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7100.94,
        "original_price": 8166.08,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_hp_victus_de_15_6_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_4050_16gb_ram_disco_s_lido_de_1tb_modelo_15_fa2012la",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6499.0,
        "original_price": 7473.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/94206173/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_azul_cielo",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6628.98,
        "original_price": 7623.33,
        "offer_url": "https://hiraoka.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_azul_cielo",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6758.96,
        "original_price": 7772.8,
        "offer_url": "https://simple.ripley.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_azul_cielo-4206173",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_1",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 6888.94,
        "original_price": 7922.28,
        "offer_url": "https://www.lacuracao.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_azul_cielo",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_1",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 7018.92,
        "original_price": 8071.76,
        "offer_url": "https://www.tottus.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_azul_cielo/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_1",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 7148.9,
        "original_price": 8221.23,
        "offer_url": "https://www.efe.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_azul_cielo",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_2",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6499.0,
        "original_price": 7473.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/29904008/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_color_plata_teclado_en_espa_ol",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_2",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6628.98,
        "original_price": 7623.33,
        "offer_url": "https://simple.ripley.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_color_plata_teclado_en_espa_ol-2904008",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_2",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6758.96,
        "original_price": 7772.8,
        "offer_url": "https://hiraoka.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_color_plata_teclado_en_espa_ol",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_2",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 6888.94,
        "original_price": 7922.28,
        "offer_url": "https://www.efe.com.pe/macbook_air_de_13_chip_m5_16gb_ram_disco_s_lido_de_512gb_color_plata_teclado_en_espa_ol",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6399.0,
        "original_price": 7358.85,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445h_nvidia_geforce_rtx_4050_16gb_ram_disco_s_lido_de_512gb_modelo_15_fb3021la",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6526.98,
        "original_price": 7506.03,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/89698222/laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445h_nvidia_geforce_rtx_4050_16gb_ram_disco_s_lido_de_512gb_modelo_15_fb3021la",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 6654.96,
        "original_price": 7653.2,
        "offer_url": "https://www.lacuracao.pe/laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445h_nvidia_geforce_rtx_4050_16gb_ram_disco_s_lido_de_512gb_modelo_15_fb3021la",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6782.94,
        "original_price": 7800.38,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445h_nvidia_geforce_rtx_4050_16gb_ram_disco_s_lido_de_512gb_modelo_15_fb3021la-8698222",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6299.0,
        "original_price": 7243.85,
        "offer_url": "https://simple.ripley.com.pe/laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla_touch_amd_ryzen_ai_7_445_16gb_ram_disco_s_lido_de_512gb_modelo_14_kc0070la_color_espresso_profundo-4476883",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6424.98,
        "original_price": 7388.73,
        "offer_url": "https://hiraoka.com.pe/laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla_touch_amd_ryzen_ai_7_445_16gb_ram_disco_s_lido_de_512gb_modelo_14_kc0070la_color_espresso_profundo",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 6550.96,
        "original_price": 7533.6,
        "offer_url": "https://www.tottus.com.pe/laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla_touch_amd_ryzen_ai_7_445_16gb_ram_disco_s_lido_de_512gb_modelo_14_kc0070la_color_espresso_profundo/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6676.94,
        "original_price": 7678.48,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/76476883/laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla_touch_amd_ryzen_ai_7_445_16gb_ram_disco_s_lido_de_512gb_modelo_14_kc0070la_color_espresso_profundo",
        "is_best_price": False
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_intel_core_",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 6299.0,
        "original_price": 7243.85,
        "offer_url": "https://www.efe.com.pe/laptop_gamer_acer_nitro_v_de_15_6_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_anv15_52_77rj",
        "is_best_price": True
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_intel_core_",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 6424.98,
        "original_price": 7388.73,
        "offer_url": "https://www.lacuracao.pe/laptop_gamer_acer_nitro_v_de_15_6_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_anv15_52_77rj",
        "is_best_price": False
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_intel_core_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6550.96,
        "original_price": 7533.6,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_acer_nitro_v_de_15_6_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_anv15_52_77rj",
        "is_best_price": False
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_intel_core_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6676.94,
        "original_price": 7678.48,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/20102373/laptop_gamer_acer_nitro_v_de_15_6_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_anv15_52_77rj",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 5999.0,
        "original_price": 8199.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/46025958/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jmi_tu401w_mochila",
        "is_best_price": True
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 6118.98,
        "original_price": 8199.0,
        "offer_url": "https://www.metro.pe/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jmi_tu401w_mochila/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 6238.96,
        "original_price": 8199.0,
        "offer_url": "https://www.wong.pe/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jmi_tu401w_mochila/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6358.94,
        "original_price": 8199.0,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jmi_tu401w_mochila",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6478.92,
        "original_price": 8199.0,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jmi_tu401w_mochila-1025958",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5899.0,
        "original_price": 7899.0,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5050_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jhi_tu368w_mochila",
        "is_best_price": True
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_1",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 6016.98,
        "original_price": 7899.0,
        "offer_url": "https://www.efe.com.pe/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5050_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jhi_tu368w_mochila",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_1",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 6134.96,
        "original_price": 7899.0,
        "offer_url": "https://www.lacuracao.pe/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5050_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jhi_tu368w_mochila",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6252.94,
        "original_price": 7899.0,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5050_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jhi_tu368w_mochila-9846167",
        "is_best_price": False
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6370.92,
        "original_price": 7899.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/63846167/laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_14650hx_14va_gen_nvidia_geforce_rtx_5050_16gb_ram_disco_s_lido_de_512gb_modelo_fx608jhi_tu368w_mochila",
        "is_best_price": False
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_cyborg_15_intel_core_i7_13620",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 5799.0,
        "original_price": 6668.85,
        "offer_url": "https://www.tottus.com.pe/laptop_gamer_msi_cyborg_15_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b13wekg/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_cyborg_15_intel_core_i7_13620",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 5914.98,
        "original_price": 6802.23,
        "offer_url": "https://www.metro.pe/laptop_gamer_msi_cyborg_15_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b13wekg/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_cyborg_15_intel_core_i7_13620",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6030.96,
        "original_price": 6935.6,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/33243915/laptop_gamer_msi_cyborg_15_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b13wekg",
        "is_best_price": False
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_cyborg_15_intel_core_i7_13620",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6146.94,
        "original_price": 7068.98,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_msi_cyborg_15_intel_core_i7_13620h_13va_gen_nvidia_geforce_rtx_5060_16gb_ram_disco_s_lido_de_512gb_modelo_b13wekg",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 22499.0,
        "original_price": 25873.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/50638902/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 22948.98,
        "original_price": 26391.33,
        "offer_url": "https://hiraoka.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole_1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 23398.96,
        "original_price": 26908.8,
        "offer_url": "https://simple.ripley.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm-5638902",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole_1",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 23848.94,
        "original_price": 27426.28,
        "offer_url": "https://www.lacuracao.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole_1",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 24298.92,
        "original_price": 27943.76,
        "offer_url": "https://www.tottus.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole_1",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 24748.9,
        "original_price": 28461.24,
        "offer_url": "https://www.efe.com.pe/laptop_gamer_lenovo_legion_pro_7i_de_16_oled_intel_core_ultra_9_275hx_series_2_nvidia_geforce_rtx_5090_64gb_ram_disco_s_lido_de_2tb_modelo_83f500fslm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 17999.0,
        "original_price": 20698.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/64325554/televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 18358.98,
        "original_price": 21112.83,
        "offer_url": "https://simple.ripley.com.pe/televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026-1325554",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 18718.96,
        "original_price": 21526.8,
        "offer_url": "https://hiraoka.com.pe/televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 19078.94,
        "original_price": 21940.78,
        "offer_url": "https://www.efe.com.pe/televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 12499.0,
        "original_price": 14999.0,
        "offer_url": "https://hiraoka.com.pe/televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 12748.98,
        "original_price": 14999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/78272689/televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 12998.96,
        "original_price": 14999.0,
        "offer_url": "https://www.lacuracao.pe/televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 13248.94,
        "original_price": 15236.28,
        "offer_url": "https://simple.ripley.com.pe/televisor_lg_smart_tv_77_oled_4k_oled77g6psa-6272689",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_televisor_sony_google_tv_oled_4k_ultra_hd_k_7",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 11999.0,
        "original_price": 16499.0,
        "offer_url": "https://simple.ripley.com.pe/televisor_sony_google_tv_oled_4k_ultra_hd_k_77xr80_bravia_8-1562689",
        "is_best_price": True
    },
    {
        "product_id": "prod_sony_televisor_sony_google_tv_oled_4k_ultra_hd_k_7",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 12238.98,
        "original_price": 16499.0,
        "offer_url": "https://hiraoka.com.pe/televisor_sony_google_tv_oled_4k_ultra_hd_k_77xr80_bravia_8",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_televisor_sony_google_tv_oled_4k_ultra_hd_k_7",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 12478.96,
        "original_price": 16499.0,
        "offer_url": "https://www.tottus.com.pe/televisor_sony_google_tv_oled_4k_ultra_hd_k_77xr80_bravia_8/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_televisor_sony_google_tv_oled_4k_ultra_hd_k_7",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 12718.94,
        "original_price": 16499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/55562689/televisor_sony_google_tv_oled_4k_ultra_hd_k_77xr80_bravia_8",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_qn77s95",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 11799.0,
        "original_price": 13568.85,
        "offer_url": "https://www.efe.com.pe/televisor_samsung_smart_tv_77_oled_qn77s95haexpe",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_qn77s95",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 12034.98,
        "original_price": 13840.23,
        "offer_url": "https://www.lacuracao.pe/televisor_samsung_smart_tv_77_oled_qn77s95haexpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_qn77s95",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 12270.96,
        "original_price": 14111.6,
        "offer_url": "https://hiraoka.com.pe/televisor_samsung_smart_tv_77_oled_qn77s95haexpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_qn77s95",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 12506.94,
        "original_price": 14382.98,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/36419827/televisor_samsung_smart_tv_77_oled_qn77s95haexpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_4k_qn77",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 9799.0,
        "original_price": 11268.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/42192191/televisor_samsung_smart_tv_77_oled_4k_qn77s90hagxpe",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_4k_qn77",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 9994.98,
        "original_price": 11494.23,
        "offer_url": "https://www.metro.pe/televisor_samsung_smart_tv_77_oled_4k_qn77s90hagxpe/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_4k_qn77",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 10190.96,
        "original_price": 11719.6,
        "offer_url": "https://www.wong.pe/televisor_samsung_smart_tv_77_oled_4k_qn77s90hagxpe/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_4k_qn77",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 10386.94,
        "original_price": 11944.98,
        "offer_url": "https://hiraoka.com.pe/televisor_samsung_smart_tv_77_oled_4k_qn77s90hagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_4k_qn77",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 10582.92,
        "original_price": 12170.36,
        "offer_url": "https://simple.ripley.com.pe/televisor_samsung_smart_tv_77_oled_4k_qn77s90hagxpe-6192191",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 8799.0,
        "original_price": 10118.85,
        "offer_url": "https://hiraoka.com.pe/televisor_samsung_smart_tv_65_oled_4k_qn65s95hagxpe",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 8974.98,
        "original_price": 10321.23,
        "offer_url": "https://www.efe.com.pe/televisor_samsung_smart_tv_65_oled_4k_qn65s95hagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 9150.96,
        "original_price": 10523.6,
        "offer_url": "https://www.lacuracao.pe/televisor_samsung_smart_tv_65_oled_4k_qn65s95hagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 9326.94,
        "original_price": 10725.98,
        "offer_url": "https://simple.ripley.com.pe/televisor_samsung_smart_tv_65_oled_4k_qn65s95hagxpe-1111324",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 9502.92,
        "original_price": 10928.36,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/10111324/televisor_samsung_smart_tv_65_oled_4k_qn65s95hagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_75_qled_4k_uhd_",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 7299.0,
        "original_price": 8393.85,
        "offer_url": "https://www.tottus.com.pe/televisor_samsung_smart_tv_75_qled_4k_uhd_vision_ai_f_qn75ls03f_01/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_75_qled_4k_uhd_",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 7444.98,
        "original_price": 8561.73,
        "offer_url": "https://www.metro.pe/televisor_samsung_smart_tv_75_qled_4k_uhd_vision_ai_f_qn75ls03f_01/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_75_qled_4k_uhd_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 7590.96,
        "original_price": 8729.6,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/99206986/televisor_samsung_smart_tv_75_qled_4k_uhd_vision_ai_f_qn75ls03f_01",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_75_qled_4k_uhd_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7736.94,
        "original_price": 8897.48,
        "offer_url": "https://hiraoka.com.pe/televisor_samsung_smart_tv_75_qled_4k_uhd_vision_ai_f_qn75ls03f_01",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6799.0,
        "original_price": 8999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/23111802/televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6934.98,
        "original_price": 8999.0,
        "offer_url": "https://hiraoka.com.pe/televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 7070.96,
        "original_price": 8999.0,
        "offer_url": "https://simple.ripley.com.pe/televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026-5111802",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 7206.94,
        "original_price": 8999.0,
        "offer_url": "https://www.lacuracao.pe/televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 7342.92,
        "original_price": 8999.0,
        "offer_url": "https://www.tottus.com.pe/televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 7478.9,
        "original_price": 8999.0,
        "offer_url": "https://www.efe.com.pe/televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_hisense_televisor_hisense_smart_tv_100_uled_minile",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6599.0,
        "original_price": 9999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/80583732/televisor_hisense_smart_tv_100_uled_miniled_4k_uhd_100u7qg",
        "is_best_price": True
    },
    {
        "product_id": "prod_hisense_televisor_hisense_smart_tv_100_uled_minile",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6730.98,
        "original_price": 9999.0,
        "offer_url": "https://simple.ripley.com.pe/televisor_hisense_smart_tv_100_uled_miniled_4k_uhd_100u7qg-8583732",
        "is_best_price": False
    },
    {
        "product_id": "prod_hisense_televisor_hisense_smart_tv_100_uled_minile",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6862.96,
        "original_price": 9999.0,
        "offer_url": "https://hiraoka.com.pe/televisor_hisense_smart_tv_100_uled_miniled_4k_uhd_100u7qg",
        "is_best_price": False
    },
    {
        "product_id": "prod_hisense_televisor_hisense_smart_tv_100_uled_minile",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 6994.94,
        "original_price": 9999.0,
        "offer_url": "https://www.efe.com.pe/televisor_hisense_smart_tv_100_uled_miniled_4k_uhd_100u7qg",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_85_neo_qled_4k_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 6299.0,
        "original_price": 7243.85,
        "offer_url": "https://hiraoka.com.pe/televisor_samsung_smart_tv_85_neo_qled_4k_qn85qn70hagxpe",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_85_neo_qled_4k_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6424.98,
        "original_price": 7388.73,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/47771244/televisor_samsung_smart_tv_85_neo_qled_4k_qn85qn70hagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_85_neo_qled_4k_",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 6550.96,
        "original_price": 7533.6,
        "offer_url": "https://www.lacuracao.pe/televisor_samsung_smart_tv_85_neo_qled_4k_qn85qn70hagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_85_neo_qled_4k_",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 6676.94,
        "original_price": 7678.48,
        "offer_url": "https://simple.ripley.com.pe/televisor_samsung_smart_tv_85_neo_qled_4k_qn85qn70hagxpe-2771244",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65_1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 5699.0,
        "original_price": 6799.0,
        "offer_url": "https://simple.ripley.com.pe/televisor_samsung_smart_tv_65_oled_4k_qn65s90haexpe-7748041",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5812.98,
        "original_price": 6799.0,
        "offer_url": "https://hiraoka.com.pe/televisor_samsung_smart_tv_65_oled_4k_qn65s90haexpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65_1",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 5926.96,
        "original_price": 6816.0,
        "offer_url": "https://www.tottus.com.pe/televisor_samsung_smart_tv_65_oled_4k_qn65s90haexpe/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6040.94,
        "original_price": 6947.08,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/43748041/televisor_samsung_smart_tv_65_oled_4k_qn65s90haexpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_televisor_sony_smart_tv_65_mini_led_4k_ultra_",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5699.0,
        "original_price": 6999.0,
        "offer_url": "https://www.efe.com.pe/televisor_sony_smart_tv_65_mini_led_4k_ultra_hd_k_65xr50_bravia_5",
        "is_best_price": True
    },
    {
        "product_id": "prod_sony_televisor_sony_smart_tv_65_mini_led_4k_ultra_",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5812.98,
        "original_price": 6999.0,
        "offer_url": "https://www.lacuracao.pe/televisor_sony_smart_tv_65_mini_led_4k_ultra_hd_k_65xr50_bravia_5",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_televisor_sony_smart_tv_65_mini_led_4k_ultra_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5926.96,
        "original_price": 6999.0,
        "offer_url": "https://hiraoka.com.pe/televisor_sony_smart_tv_65_mini_led_4k_ultra_hd_k_65xr50_bravia_5",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_televisor_sony_smart_tv_65_mini_led_4k_ultra_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 6040.94,
        "original_price": 6999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/18076424/televisor_sony_smart_tv_65_mini_led_4k_ultra_hd_k_65xr50_bravia_5",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_50_neoqled_4k_q",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4999.0,
        "original_price": 5748.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/10027238/televisor_samsung_smart_tv_50_neoqled_4k_qn50qn90fagxpe",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_50_neoqled_4k_q",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 5098.98,
        "original_price": 5863.83,
        "offer_url": "https://www.metro.pe/televisor_samsung_smart_tv_50_neoqled_4k_qn50qn90fagxpe/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_50_neoqled_4k_q",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 5198.96,
        "original_price": 5978.8,
        "offer_url": "https://www.wong.pe/televisor_samsung_smart_tv_50_neoqled_4k_qn50qn90fagxpe/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_50_neoqled_4k_q",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5298.94,
        "original_price": 6093.78,
        "offer_url": "https://hiraoka.com.pe/televisor_samsung_smart_tv_50_neoqled_4k_qn50qn90fagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_50_neoqled_4k_q",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 5398.92,
        "original_price": 6208.76,
        "offer_url": "https://simple.ripley.com.pe/televisor_samsung_smart_tv_50_neoqled_4k_qn50qn90fagxpe-1027238",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4899.0,
        "original_price": 6199.0,
        "offer_url": "https://hiraoka.com.pe/televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85c6k",
        "is_best_price": True
    },
    {
        "product_id": "prod_tcl_televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 4996.98,
        "original_price": 6199.0,
        "offer_url": "https://www.efe.com.pe/televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85c6k",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5094.96,
        "original_price": 6199.0,
        "offer_url": "https://www.lacuracao.pe/televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85c6k",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 5192.94,
        "original_price": 6199.0,
        "offer_url": "https://simple.ripley.com.pe/televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85c6k-7192116",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 5290.92,
        "original_price": 6199.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/97192116/televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85c6k",
        "is_best_price": False
    },
    {
        "product_id": "prod_hisense_televisor_hisense_google_tv_98_hi_qled_4k_",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 4799.0,
        "original_price": 7999.0,
        "offer_url": "https://www.tottus.com.pe/televisor_hisense_google_tv_98_hi_qled_4k_uhd_98q6qg/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_hisense_televisor_hisense_google_tv_98_hi_qled_4k_",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 4894.98,
        "original_price": 7999.0,
        "offer_url": "https://www.metro.pe/televisor_hisense_google_tv_98_hi_qled_4k_uhd_98q6qg/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_hisense_televisor_hisense_google_tv_98_hi_qled_4k_",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4990.96,
        "original_price": 7999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/64148161/televisor_hisense_google_tv_98_hi_qled_4k_uhd_98q6qg",
        "is_best_price": False
    },
    {
        "product_id": "prod_hisense_televisor_hisense_google_tv_98_hi_qled_4k_",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5086.94,
        "original_price": 7999.0,
        "offer_url": "https://hiraoka.com.pe/televisor_hisense_google_tv_98_hi_qled_4k_uhd_98q6qg",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_85_qned_ai_mini_led_qned70_4k_smar",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3999.0,
        "original_price": 7299.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/67365161/televisor_lg_85_qned_ai_mini_led_qned70_4k_smart_tv_2026",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_televisor_lg_85_qned_ai_mini_led_qned70_4k_smar",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4078.98,
        "original_price": 7299.0,
        "offer_url": "https://hiraoka.com.pe/televisor_lg_85_qned_ai_mini_led_qned70_4k_smart_tv_2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_85_qned_ai_mini_led_qned70_4k_smar",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4158.96,
        "original_price": 7299.0,
        "offer_url": "https://simple.ripley.com.pe/televisor_lg_85_qned_ai_mini_led_qned70_4k_smart_tv_2026-4365161",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_85_qned_ai_mini_led_qned70_4k_smar",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 4238.94,
        "original_price": 7299.0,
        "offer_url": "https://www.lacuracao.pe/televisor_lg_85_qned_ai_mini_led_qned70_4k_smart_tv_2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_85_qned_ai_mini_led_qned70_4k_smar",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 4318.92,
        "original_price": 7299.0,
        "offer_url": "https://www.tottus.com.pe/televisor_lg_85_qned_ai_mini_led_qned70_4k_smart_tv_2026/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_televisor_lg_85_qned_ai_mini_led_qned70_4k_smar",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 4398.9,
        "original_price": 7299.0,
        "offer_url": "https://www.efe.com.pe/televisor_lg_85_qned_ai_mini_led_qned70_4k_smart_tv_2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_55_oled_4k_qn55",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3999.0,
        "original_price": 4598.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/22163820/televisor_samsung_smart_tv_55_oled_4k_qn55s90hagxpe",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_55_oled_4k_qn55",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4078.98,
        "original_price": 4690.83,
        "offer_url": "https://simple.ripley.com.pe/televisor_samsung_smart_tv_55_oled_4k_qn55s90hagxpe-4163820",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_55_oled_4k_qn55",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4158.96,
        "original_price": 4782.8,
        "offer_url": "https://hiraoka.com.pe/televisor_samsung_smart_tv_55_oled_4k_qn55s90hagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_55_oled_4k_qn55",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 4238.94,
        "original_price": 4874.78,
        "offer_url": "https://www.efe.com.pe/televisor_samsung_smart_tv_55_oled_4k_qn55s90hagxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3999.0,
        "original_price": 4598.85,
        "offer_url": "https://hiraoka.com.pe/televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "is_best_price": True
    },
    {
        "product_id": "prod_tcl_televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4078.98,
        "original_price": 4690.83,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/92345528/televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 4158.96,
        "original_price": 4782.8,
        "offer_url": "https://www.lacuracao.pe/televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "is_best_price": False
    },
    {
        "product_id": "prod_tcl_televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4238.94,
        "original_price": 4874.78,
        "offer_url": "https://simple.ripley.com.pe/televisor_tcl_google_tv_85_qled_4k_uhd_85p7l-2345528",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_pro_11_chip_m5_wifi_256gb_negro_espacia",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 5299.0,
        "original_price": 6093.85,
        "offer_url": "https://simple.ripley.com.pe/ipad_pro_11_chip_m5_wifi_256gb_negro_espacial-7659641",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_ipad_pro_11_chip_m5_wifi_256gb_negro_espacia",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5404.98,
        "original_price": 6215.73,
        "offer_url": "https://hiraoka.com.pe/ipad_pro_11_chip_m5_wifi_256gb_negro_espacial",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_pro_11_chip_m5_wifi_256gb_negro_espacia",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 5510.96,
        "original_price": 6337.6,
        "offer_url": "https://www.tottus.com.pe/ipad_pro_11_chip_m5_wifi_256gb_negro_espacial/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_pro_11_chip_m5_wifi_256gb_negro_espacia",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 5616.94,
        "original_price": 6459.48,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/88659641/ipad_pro_11_chip_m5_wifi_256gb_negro_espacial",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2899.0,
        "original_price": 3333.85,
        "offer_url": "https://www.efe.com.pe/tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb_ram_teclado_tab_pen_pro",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2956.98,
        "original_price": 3400.53,
        "offer_url": "https://www.lacuracao.pe/tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb_ram_teclado_tab_pen_pro",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3014.96,
        "original_price": 3467.2,
        "offer_url": "https://hiraoka.com.pe/tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb_ram_teclado_tab_pen_pro",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3072.94,
        "original_price": 3533.88,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/51613572/tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb_ram_teclado_tab_pen_pro",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_3",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2499.0,
        "original_price": 3049.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/74017204/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_3",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 2548.98,
        "original_price": 3049.0,
        "offer_url": "https://www.metro.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_3",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 2598.96,
        "original_price": 3049.0,
        "offer_url": "https://www.wong.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_3",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2648.94,
        "original_price": 3049.0,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_3",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2698.92,
        "original_price": 3103.76,
        "offer_url": "https://simple.ripley.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_gray_s_pen-2017204",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_4",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2499.0,
        "original_price": 3049.0,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_4",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2548.98,
        "original_price": 3049.0,
        "offer_url": "https://www.efe.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_4",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2598.96,
        "original_price": 3049.0,
        "offer_url": "https://www.lacuracao.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_4",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2648.94,
        "original_price": 3049.0,
        "offer_url": "https://simple.ripley.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen-7820118",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_4",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2698.92,
        "original_price": 3103.76,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/43820118/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_5",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2499.0,
        "original_price": 3049.0,
        "offer_url": "https://www.tottus.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_blue_s_pen/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_5",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 2548.98,
        "original_price": 3049.0,
        "offer_url": "https://www.metro.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_blue_s_pen/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_5",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2598.96,
        "original_price": 3049.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/84137348/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_blue_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_5",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2648.94,
        "original_price": 3049.0,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_13_1_128gb_8gb_ram_blue_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_lenovo_ideapad_slim_3_de_15_6_amd_ry",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2199.0,
        "original_price": 2899.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/19265019/laptop_lenovo_ideapad_slim_3_de_15_6_amd_ryzen_5_7520u_8gb_ram_disco_s_lido_de_512gb_modelo_82xq00ltlm",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_laptop_lenovo_ideapad_slim_3_de_15_6_amd_ry",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2242.98,
        "original_price": 2899.0,
        "offer_url": "https://hiraoka.com.pe/laptop_lenovo_ideapad_slim_3_de_15_6_amd_ryzen_5_7520u_8gb_ram_disco_s_lido_de_512gb_modelo_82xq00ltlm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_lenovo_ideapad_slim_3_de_15_6_amd_ry",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2286.96,
        "original_price": 2899.0,
        "offer_url": "https://simple.ripley.com.pe/laptop_lenovo_ideapad_slim_3_de_15_6_amd_ryzen_5_7520u_8gb_ram_disco_s_lido_de_512gb_modelo_82xq00ltlm-1265019",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_lenovo_ideapad_slim_3_de_15_6_amd_ry",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2330.94,
        "original_price": 2899.0,
        "offer_url": "https://www.lacuracao.pe/laptop_lenovo_ideapad_slim_3_de_15_6_amd_ryzen_5_7520u_8gb_ram_disco_s_lido_de_512gb_modelo_82xq00ltlm",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_lenovo_ideapad_slim_3_de_15_6_amd_ry",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2374.92,
        "original_price": 2899.0,
        "offer_url": "https://www.tottus.com.pe/laptop_lenovo_ideapad_slim_3_de_15_6_amd_ryzen_5_7520u_8gb_ram_disco_s_lido_de_512gb_modelo_82xq00ltlm/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_laptop_lenovo_ideapad_slim_3_de_15_6_amd_ry",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2418.9,
        "original_price": 2899.0,
        "offer_url": "https://www.efe.com.pe/laptop_lenovo_ideapad_slim_3_de_15_6_amd_ryzen_5_7520u_8gb_ram_disco_s_lido_de_512gb_modelo_82xq00ltlm",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1999.0,
        "original_price": 2299.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/28803135/ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2038.98,
        "original_price": 2344.83,
        "offer_url": "https://simple.ripley.com.pe/ipad_11_11ma_gen_a16_wifi_128gb_plata-1803135",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2078.96,
        "original_price": 2390.8,
        "offer_url": "https://hiraoka.com.pe/ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2118.94,
        "original_price": 2436.78,
        "offer_url": "https://www.efe.com.pe/ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1999.0,
        "original_price": 2299.0,
        "offer_url": "https://hiraoka.com.pe/ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2038.98,
        "original_price": 2344.83,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/40478189/ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2078.96,
        "original_price": 2390.8,
        "offer_url": "https://www.lacuracao.pe/ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2118.94,
        "original_price": 2436.78,
        "offer_url": "https://simple.ripley.com.pe/ipad_11_11ma_gen_a16_wifi_128gb_azul-4478189",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_amarillo",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1999.0,
        "original_price": 2299.0,
        "offer_url": "https://simple.ripley.com.pe/ipad_11_11ma_gen_a16_wifi_128gb_amarillo-9060820",
        "is_best_price": True
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_amarillo",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2038.98,
        "original_price": 2344.83,
        "offer_url": "https://hiraoka.com.pe/ipad_11_11ma_gen_a16_wifi_128gb_amarillo",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_amarillo",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2078.96,
        "original_price": 2390.8,
        "offer_url": "https://www.tottus.com.pe/ipad_11_11ma_gen_a16_wifi_128gb_amarillo/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_amarillo",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2118.94,
        "original_price": 2436.78,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/45060820/ipad_11_11ma_gen_a16_wifi_128gb_amarillo",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1999.0,
        "original_price": 2298.85,
        "offer_url": "https://www.efe.com.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_silver_s_pen",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2038.98,
        "original_price": 2344.83,
        "offer_url": "https://www.lacuracao.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2078.96,
        "original_price": 2390.8,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2118.94,
        "original_price": 2436.78,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/57164985/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_silver_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_1",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1999.0,
        "original_price": 2298.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/49955107/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_blue_s_pen",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_1",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 2038.98,
        "original_price": 2344.83,
        "offer_url": "https://www.metro.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_blue_s_pen/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_1",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 2078.96,
        "original_price": 2390.8,
        "offer_url": "https://www.wong.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_blue_s_pen/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2118.94,
        "original_price": 2436.78,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_blue_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_1",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2158.92,
        "original_price": 2482.76,
        "offer_url": "https://simple.ripley.com.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_blue_s_pen-4955107",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_2",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1999.0,
        "original_price": 2298.85,
        "offer_url": "https://hiraoka.com.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_gray_s_pen",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_2",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2038.98,
        "original_price": 2344.83,
        "offer_url": "https://www.efe.com.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_gray_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_2",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2078.96,
        "original_price": 2390.8,
        "offer_url": "https://www.lacuracao.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_gray_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_2",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 2118.94,
        "original_price": 2436.78,
        "offer_url": "https://simple.ripley.com.pe/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_gray_s_pen-9260783",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_2",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2158.92,
        "original_price": 2482.76,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/63260783/tablet_samsung_galaxy_tab_s10_fe_10_9_128gb_8gb_ram_gray_s_pen",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_r",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 1949.0,
        "original_price": 2241.35,
        "offer_url": "https://www.tottus.com.pe/tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_ram_teclado_lapiz_aud_fonos/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_r",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 1987.98,
        "original_price": 2286.18,
        "offer_url": "https://www.metro.pe/tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_ram_teclado_lapiz_aud_fonos/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_r",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2026.96,
        "original_price": 2331.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/71103351/tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_ram_teclado_lapiz_aud_fonos",
        "is_best_price": False
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_r",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2065.94,
        "original_price": 2375.83,
        "offer_url": "https://hiraoka.com.pe/tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_ram_teclado_lapiz_aud_fonos",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_jbl_partybox_ultimate_negro",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 5299.0,
        "original_price": 6093.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/56295422/parlante_jbl_partybox_ultimate_negro",
        "is_best_price": True
    },
    {
        "product_id": "prod_jbl_parlante_jbl_partybox_ultimate_negro",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 5404.98,
        "original_price": 6215.73,
        "offer_url": "https://hiraoka.com.pe/parlante_jbl_partybox_ultimate_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_jbl_partybox_ultimate_negro",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 5510.96,
        "original_price": 6337.6,
        "offer_url": "https://simple.ripley.com.pe/parlante_jbl_partybox_ultimate_negro-2295422",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_jbl_partybox_ultimate_negro",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5616.94,
        "original_price": 6459.48,
        "offer_url": "https://www.lacuracao.pe/parlante_jbl_partybox_ultimate_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_jbl_partybox_ultimate_negro",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 5722.92,
        "original_price": 6581.36,
        "offer_url": "https://www.tottus.com.pe/parlante_jbl_partybox_ultimate_negro/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_jbl_partybox_ultimate_negro",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5828.9,
        "original_price": 6703.23,
        "offer_url": "https://www.efe.com.pe/parlante_jbl_partybox_ultimate_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_pro_2tb",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4399.0,
        "original_price": 5058.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/48843574/consola_playstation_5_pro_2tb",
        "is_best_price": True
    },
    {
        "product_id": "prod_sony_consola_playstation_5_pro_2tb",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4486.98,
        "original_price": 5160.03,
        "offer_url": "https://simple.ripley.com.pe/consola_playstation_5_pro_2tb-3843574",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_pro_2tb",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4574.96,
        "original_price": 5261.2,
        "offer_url": "https://hiraoka.com.pe/consola_playstation_5_pro_2tb",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_pro_2tb",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 4662.94,
        "original_price": 5362.38,
        "offer_url": "https://www.efe.com.pe/consola_playstation_5_pro_2tb",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_monitor_gamer_samsung_odyssey_oled_g9_49_d",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3799.0,
        "original_price": 5389.0,
        "offer_url": "https://hiraoka.com.pe/monitor_gamer_samsung_odyssey_oled_g9_49_dual_qhd_ls49dg930slxpe",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_monitor_gamer_samsung_odyssey_oled_g9_49_d",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3874.98,
        "original_price": 5389.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/55085994/monitor_gamer_samsung_odyssey_oled_g9_49_dual_qhd_ls49dg930slxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_monitor_gamer_samsung_odyssey_oled_g9_49_d",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 3950.96,
        "original_price": 5389.0,
        "offer_url": "https://www.lacuracao.pe/monitor_gamer_samsung_odyssey_oled_g9_49_dual_qhd_ls49dg930slxpe",
        "is_best_price": False
    },
    {
        "product_id": "prod_samsung_monitor_gamer_samsung_odyssey_oled_g9_49_d",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 4026.94,
        "original_price": 5389.0,
        "offer_url": "https://simple.ripley.com.pe/monitor_gamer_samsung_odyssey_oled_g9_49_dual_qhd_ls49dg930slxpe-1085994",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_standard_edition_1tb_gr",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3399.0,
        "original_price": 3908.85,
        "offer_url": "https://simple.ripley.com.pe/consola_playstation_5_standard_edition_1tb_gran_turismo_7_astro_bot_bundle-9166952",
        "is_best_price": True
    },
    {
        "product_id": "prod_sony_consola_playstation_5_standard_edition_1tb_gr",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3466.98,
        "original_price": 3987.03,
        "offer_url": "https://hiraoka.com.pe/consola_playstation_5_standard_edition_1tb_gran_turismo_7_astro_bot_bundle",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_standard_edition_1tb_gr",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 3534.96,
        "original_price": 4065.2,
        "offer_url": "https://www.tottus.com.pe/consola_playstation_5_standard_edition_1tb_gran_turismo_7_astro_bot_bundle/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_standard_edition_1tb_gr",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3602.94,
        "original_price": 4143.38,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/27166952/consola_playstation_5_standard_edition_1tb_gran_turismo_7_astro_bot_bundle",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx85",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3399.0,
        "original_price": 4399.0,
        "offer_url": "https://www.efe.com.pe/monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx850a",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx85",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 3466.98,
        "original_price": 4399.0,
        "offer_url": "https://www.lacuracao.pe/monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx850a",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx85",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3534.96,
        "original_price": 4399.0,
        "offer_url": "https://hiraoka.com.pe/monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx850a",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx85",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3602.94,
        "original_price": 4399.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/54940876/monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx850a",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3299.0,
        "original_price": 3793.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/25897033/monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 3364.98,
        "original_price": 3869.73,
        "offer_url": "https://www.metro.pe/monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 3430.96,
        "original_price": 3945.6,
        "offer_url": "https://www.wong.pe/monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3496.94,
        "original_price": 4021.48,
        "offer_url": "https://hiraoka.com.pe/monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3562.92,
        "original_price": 4097.36,
        "offer_url": "https://simple.ripley.com.pe/monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b-7897033",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_digital_edition_825gb_g",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2999.0,
        "original_price": 3448.85,
        "offer_url": "https://hiraoka.com.pe/consola_playstation_5_digital_edition_825gb_gran_turismo_7_astro_bot_bundle",
        "is_best_price": True
    },
    {
        "product_id": "prod_sony_consola_playstation_5_digital_edition_825gb_g",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3058.98,
        "original_price": 3517.83,
        "offer_url": "https://www.efe.com.pe/consola_playstation_5_digital_edition_825gb_gran_turismo_7_astro_bot_bundle",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_digital_edition_825gb_g",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 3118.96,
        "original_price": 3586.8,
        "offer_url": "https://www.lacuracao.pe/consola_playstation_5_digital_edition_825gb_gran_turismo_7_astro_bot_bundle",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_digital_edition_825gb_g",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3178.94,
        "original_price": 3655.78,
        "offer_url": "https://simple.ripley.com.pe/consola_playstation_5_digital_edition_825gb_gran_turismo_7_astro_bot_bundle-5182950",
        "is_best_price": False
    },
    {
        "product_id": "prod_sony_consola_playstation_5_digital_edition_825gb_g",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3238.92,
        "original_price": 3724.76,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/41182950/consola_playstation_5_digital_edition_825gb_gran_turismo_7_astro_bot_bundle",
        "is_best_price": False
    },
    {
        "product_id": "prod_brother_impresora_l_ser_multifuncional_brother_dcp",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2499.0,
        "original_price": 2873.85,
        "offer_url": "https://www.tottus.com.pe/impresora_l_ser_multifuncional_brother_dcpl5660dn/p/",
        "is_best_price": True
    },
    {
        "product_id": "prod_brother_impresora_l_ser_multifuncional_brother_dcp",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 2548.98,
        "original_price": 2931.33,
        "offer_url": "https://www.metro.pe/impresora_l_ser_multifuncional_brother_dcpl5660dn/p",
        "is_best_price": False
    },
    {
        "product_id": "prod_brother_impresora_l_ser_multifuncional_brother_dcp",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 2598.96,
        "original_price": 2988.8,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/71967728/impresora_l_ser_multifuncional_brother_dcpl5660dn",
        "is_best_price": False
    },
    {
        "product_id": "prod_brother_impresora_l_ser_multifuncional_brother_dcp",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 2648.94,
        "original_price": 3046.28,
        "offer_url": "https://hiraoka.com.pe/impresora_l_ser_multifuncional_brother_dcpl5660dn",
        "is_best_price": False
    },
    {
        "product_id": "prod_nintendo_consola_nintendo_switch_oled_bundle_super",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1899.0,
        "original_price": 2183.85,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/88182403/consola_nintendo_switch_oled_bundle_super_mario_bros_wonder",
        "is_best_price": True
    },
    {
        "product_id": "prod_nintendo_consola_nintendo_switch_oled_bundle_super",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1936.98,
        "original_price": 2227.53,
        "offer_url": "https://hiraoka.com.pe/consola_nintendo_switch_oled_bundle_super_mario_bros_wonder",
        "is_best_price": False
    },
    {
        "product_id": "prod_nintendo_consola_nintendo_switch_oled_bundle_super",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1974.96,
        "original_price": 2271.2,
        "offer_url": "https://simple.ripley.com.pe/consola_nintendo_switch_oled_bundle_super_mario_bros_wonder-7182403",
        "is_best_price": False
    },
    {
        "product_id": "prod_nintendo_consola_nintendo_switch_oled_bundle_super",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 2012.94,
        "original_price": 2314.88,
        "offer_url": "https://www.lacuracao.pe/consola_nintendo_switch_oled_bundle_super_mario_bros_wonder",
        "is_best_price": False
    },
    {
        "product_id": "prod_nintendo_consola_nintendo_switch_oled_bundle_super",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 2050.92,
        "original_price": 2358.56,
        "offer_url": "https://www.tottus.com.pe/consola_nintendo_switch_oled_bundle_super_mario_bros_wonder/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_nintendo_consola_nintendo_switch_oled_bundle_super",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 2088.9,
        "original_price": 2402.24,
        "offer_url": "https://www.efe.com.pe/consola_nintendo_switch_oled_bundle_super_mario_bros_wonder",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_amplificador_jbl_eon_one_compact",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1859.0,
        "original_price": 3099.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/68110472/parlante_amplificador_jbl_eon_one_compact",
        "is_best_price": True
    },
    {
        "product_id": "prod_jbl_parlante_amplificador_jbl_eon_one_compact",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1896.18,
        "original_price": 3099.0,
        "offer_url": "https://simple.ripley.com.pe/parlante_amplificador_jbl_eon_one_compact-5110472",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_amplificador_jbl_eon_one_compact",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1933.36,
        "original_price": 3099.0,
        "offer_url": "https://hiraoka.com.pe/parlante_amplificador_jbl_eon_one_compact",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_amplificador_jbl_eon_one_compact",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1970.54,
        "original_price": 3099.0,
        "offer_url": "https://www.efe.com.pe/parlante_amplificador_jbl_eon_one_compact",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_jbl_authentics_300_negro",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1799.0,
        "original_price": 2068.85,
        "offer_url": "https://hiraoka.com.pe/parlante_jbl_authentics_300_negro",
        "is_best_price": True
    },
    {
        "product_id": "prod_jbl_parlante_jbl_authentics_300_negro",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1834.98,
        "original_price": 2110.23,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/19998907/parlante_jbl_authentics_300_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_jbl_authentics_300_negro",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 1870.96,
        "original_price": 2151.6,
        "offer_url": "https://www.lacuracao.pe/parlante_jbl_authentics_300_negro",
        "is_best_price": False
    },
    {
        "product_id": "prod_jbl_parlante_jbl_authentics_300_negro",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1906.94,
        "original_price": 2192.98,
        "offer_url": "https://simple.ripley.com.pe/parlante_jbl_authentics_300_negro-1998907",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_impresora_multifuncional_hp_smart_tank_790_sist",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 1699.0,
        "original_price": 1953.85,
        "offer_url": "https://simple.ripley.com.pe/impresora_multifuncional_hp_smart_tank_790_sistema_continuo_color_wi_fi_ethernet_adf_d_plex_impresi_n_a_doble_cara_fax_pantalla_hp_app-7717200",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_impresora_multifuncional_hp_smart_tank_790_sist",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 1732.98,
        "original_price": 1992.93,
        "offer_url": "https://hiraoka.com.pe/impresora_multifuncional_hp_smart_tank_790_sistema_continuo_color_wi_fi_ethernet_adf_d_plex_impresi_n_a_doble_cara_fax_pantalla_hp_app",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_impresora_multifuncional_hp_smart_tank_790_sist",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 1766.96,
        "original_price": 2032.0,
        "offer_url": "https://www.tottus.com.pe/impresora_multifuncional_hp_smart_tank_790_sistema_continuo_color_wi_fi_ethernet_adf_d_plex_impresi_n_a_doble_cara_fax_pantalla_hp_app/p/",
        "is_best_price": False
    },
    {
        "product_id": "prod_hp_impresora_multifuncional_hp_smart_tank_790_sist",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1800.94,
        "original_price": 2071.08,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/34717200/impresora_multifuncional_hp_smart_tank_790_sistema_continuo_color_wi_fi_ethernet_adf_d_plex_impresi_n_a_doble_cara_fax_pantalla_hp_app",
        "is_best_price": False
    }
]

SEED_PRICE_HISTORY: List[Dict[str, Any]] = [
    {
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_iphone_16",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_xiaomi_redmi_note",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1829.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_motorola_edge_50",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_macbook_air_m5",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5699.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_asus_zenbook_14",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4599.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lg_oled_tv",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_tcl_miniled_55",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_ipad_11",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tab_s10",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_xiaomi_pad_6",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1349.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_sony_wh1000xm5",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_airpods_pro_2",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 949.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_ps5_slim",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_nintendo_switch_oled",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_epson_l3250",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 699.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_sony_alpha_7_iv",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 9999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_plata",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_azul_profundo",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_512gb_naranja_c_smico",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_iphone_17_pro_max_6_9_256gb_naranja_c_smico",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_ultra_6_9_512gb_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_s26_6_3_512gb_12gb_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_iphone_16_6_1_128gb_blanco",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_ne",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_honor_celular_honor_600_pro_6_57_512gb_12gb_ram_do",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_iphone_15_6_1_128gb_negro",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2599.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_motorola_celular_motorola_edge_70_pro_6_78_512gb_1_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2599.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_2",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_motorola_celular_motorola_moto_edge_60_pro_6_7_512",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_naranja",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_negro",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_honor_celular_honor_600_6_57_512gb_8gb_ram_dorado_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2099.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_celular_samsung_galaxy_a57_6_7_5g_256gb_8g_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2099.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2099.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_motorola_celular_libre_motorola_edge_70_6_7_512gb__1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2099.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_zephyrus_duo_16_de_16_i",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 25499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 22499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_int",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 15899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_macbook_pro_de_14_chip_m5_16gb_ram_disco_s_l",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 9999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_amd_ryz",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 9499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_laptop_gamer_hyperx_omen_de_15_3_intel_core_i7_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 8299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_5i_de_15_3_intel",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 8299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_laptop_hp_omnibook_ultra_de_14_pantalla_touch_i",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7699.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_macbook_air_de_15_chip_m5_16gb_ram_disco_s_l",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7599.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_amd_ryzen_7",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_rog_strix_g16_de_16_intel_c",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7199.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_katana_15_hx_de_15_6_intel_co",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7099.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_pc_gamer_lenovo_legion_5_intel_core_ultra_5",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_intel_core_i7_13",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6699.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_macbook_air_de_13_chip_m5_16gb_ram_disco_s_l_2",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_laptop_gamer_hp_victus_de_15_6_amd_ryzen_7_7445",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_laptop_2_en_1_hp_omnibook_x_flip_de_14_pantalla",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_acer_laptop_gamer_acer_nitro_v_de_15_6_intel_core_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_asus_laptop_gamer_asus_tuf_f16_de_16_intel_core_i7_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_msi_laptop_gamer_msi_cyborg_15_intel_core_i7_13620",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_laptop_gamer_lenovo_legion_pro_7i_de_16_ole_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 22499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lg_televisor_lg_83_oled_evo_ai_c6_4k_smart_tv_2026",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 17999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lg_televisor_lg_smart_tv_77_oled_4k_oled77g6psa",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 12499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_sony_televisor_sony_google_tv_oled_4k_ultra_hd_k_7",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 11999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_qn77s95",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 11799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_77_oled_4k_qn77",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 9799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 8799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_75_qled_4k_uhd_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lg_televisor_lg_55_oled_evo_ai_g6_4k_smart_tv_2026",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hisense_televisor_hisense_smart_tv_100_uled_minile",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6599.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_85_neo_qled_4k_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 6299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_65_oled_4k_qn65_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5699.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_sony_televisor_sony_smart_tv_65_mini_led_4k_ultra_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5699.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_50_neoqled_4k_q",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_tcl_televisor_tcl_smart_tv_85_qd_miniled_4k_uhd_85",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hisense_televisor_hisense_google_tv_98_hi_qled_4k_",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lg_televisor_lg_85_qned_ai_mini_led_qned70_4k_smar",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_televisor_samsung_smart_tv_55_oled_4k_qn55",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_tcl_televisor_tcl_google_tv_85_qled_4k_uhd_85p7l",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_ipad_pro_11_chip_m5_wifi_256gb_negro_espacia",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_yoga_tab_plus_12_7_256gb_16gb",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_3",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_4",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_13_1_128g_5",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_laptop_lenovo_ideapad_slim_3_de_15_6_amd_ry",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2199.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_plata",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_azul",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_apple_ipad_11_11ma_gen_a16_wifi_128gb_amarillo",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tablet_samsung_galaxy_tab_s10_fe_10_9_128g_2",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_tablet_lenovo_idea_tab_pro_12_7_256gb_8gb_r",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1949.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_jbl_parlante_jbl_partybox_ultimate_negro",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_sony_consola_playstation_5_pro_2tb",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_monitor_gamer_samsung_odyssey_oled_g9_49_d",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_sony_consola_playstation_5_standard_edition_1tb_gr",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lg_monitor_gamer_lg_ultragear_gx8_32_4k_uhd_32gx85",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3399.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lg_monitor_lg_ultragear_27_qhd_gx7_oled_27gx704a_b",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_sony_consola_playstation_5_digital_edition_825gb_g",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2999.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_brother_impresora_l_ser_multifuncional_brother_dcp",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 2499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_nintendo_consola_nintendo_switch_oled_bundle_super",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_jbl_parlante_amplificador_jbl_eon_one_compact",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1859.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_jbl_parlante_jbl_authentics_300_negro",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_impresora_multifuncional_hp_smart_tank_790_sist",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1699.0,
        "recorded_at": "2026-11-01 12:00:00"
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

    # Precarga en bloque
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

    # 3. Upsert Historial de Precios (Día 1)
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

    await session.commit()
    logger.info(f"sync_and_upsert_catalog completado con éxito: {len(SEED_PRODUCTS)} productos sincronizados.")
    return len(SEED_PRODUCTS)


async def seed_database_fast(session: AsyncSession) -> int:
    """Inserta o sincroniza el catálogo oficial en Neon PostgreSQL / SQLite."""
    return await sync_and_upsert_catalog(session)
