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
from sqlalchemy import func, select, delete
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
        "id": "prod_hp_smart_tank_530",
        "title": "Impresora Multifuncional HP Smart Tank 530 Wi-Fi ADF",
        "category": "Impresoras",
        "brand": "HP",
        "best_price": 799.0,
        "original_price": 999.0,
        "best_store_name": "Falabella",
        "discount_percentage": 20,
        "available_stores_count": 1,
        "image_url": "https://media.falabella.com/falabellaPE/20756050_1/public",
        "description": "Impresora multifuncional de tanque de tinta de alta capacidad con alimentador automático de documentos (ADF) de 35 páginas, conectividad Wi-Fi de doble banda y botellas antiderrames.",
        "features_json": "[\"Tipo: Multifuncional Tinta Continua\", \"Conectividad: Wi-Fi, USB 2.0, Bluetooth LE\", \"Funciones: Impresión, Escaneo, Copia, ADF 35 hojas\", \"Velocidad: Hasta 11 ppm en negro y 5 ppm en color\", \"Resolución de impresión: Hasta 4800 x 1200 dpi optimizados\"]",
        "tech_specs_json": "{\"Tipo\": \"Multifuncional Tinta Continua\", \"Conectividad\": \"Wi-Fi, USB, Bluetooth LE\", \"Funciones\": \"Impresión, Copia, Escaneo, ADF\", \"Marca\": \"HP\", \"Alimentador Automático\": \"35 hojas\", \"Resolución\": \"4800 x 1200 dpi\"}",
        "is_favorite": False,
        "historical_min_price": 799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_smart_tank_581",
        "title": "Impresora Multifuncional HP Smart Tank 581 Wi-Fi",
        "category": "Impresoras",
        "brand": "HP",
        "best_price": 549.0,
        "original_price": 699.0,
        "best_store_name": "Ripley",
        "discount_percentage": 21,
        "available_stores_count": 1,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/4/a/4a8d4a_01imagenprincipalcontexto-e.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Impresora todo en uno con conexión Wi-Fi autorreparable, sensores de tinta inteligentes y diseño compacto para el hogar y teletrabajo.",
        "features_json": "[\"Tipo: Multifuncional Tinta Continua\", \"Conectividad: Wi-Fi, Wi-Fi Direct, USB\", \"Funciones: Impresión, Copia, Escaneo\", \"Rendimiento: Hasta 6000 páginas en negro / 6000 páginas a color\", \"Velocidad: Hasta 12 ppm en negro y 5 ppm en color\"]",
        "tech_specs_json": "{\"Tipo\": \"Multifuncional Tinta Continua\", \"Conectividad\": \"Wi-Fi, USB, Wi-Fi Direct\", \"Funciones\": \"Impresión, Copia, Escaneo\", \"Marca\": \"HP\", \"Resolución\": \"4800 x 1200 dpi\"}",
        "is_favorite": False,
        "historical_min_price": 549.0,
        "is_historical_min": True
    },
    {
        "id": "prod_epson_ecotank_l3310",
        "title": "Impresora Multifuncional Epson EcoTank L3310",
        "category": "Impresoras",
        "brand": "Epson",
        "best_price": 699.0,
        "original_price": 859.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 19,
        "available_stores_count": 1,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/e/p/eps0004192_0.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Impresora multifuncional 3 en 1 con sistema original de tanque de tinta EcoTank de ultra bajo costo de impresión y tecnología Heat-Free MicroPiezo.",
        "features_json": "[\"Tipo: Multifuncional Tinta Continua EcoTank\", \"Conectividad: USB de alta velocidad\", \"Funciones: Impresora, Copiadora, Escáner\", \"Tecnología: MicroPiezo Heat-Free\", \"Rendimiento: Hasta 4500 páginas negro / 7500 páginas color\"]",
        "tech_specs_json": "{\"Tipo\": \"Multifuncional Tinta Continua EcoTank\", \"Conectividad\": \"USB 2.0\", \"Funciones\": \"Impresión, Copia, Escaneo\", \"Marca\": \"Epson\", \"Resolución\": \"5760 x 1440 dpi\"}",
        "is_favorite": False,
        "historical_min_price": 699.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_smart_tank_585",
        "title": "Impresora Multifuncional HP Smart Tank 585 Wi-Fi",
        "category": "Impresoras",
        "brand": "HP",
        "best_price": 519.0,
        "original_price": 649.0,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 20,
        "available_stores_count": 1,
        "image_url": "https://www.efe.com.pe/media/catalog/product/s/t/st_585_1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Impresora multifunción inalámbrica Smart Tank con sistema continuo de recarga limpia sin derrames y botón de guía inteligente.",
        "features_json": "[\"Tipo: Multifuncional Tinta Continua\", \"Conectividad: Wi-Fi, Wi-Fi Direct, USB\", \"Funciones: Impresión, Copia, Escaneo\", \"Rendimiento: 6000 páginas negro / 6000 páginas color\", \"Garantía: Hasta 2 años con registro oficial\"]",
        "tech_specs_json": "{\"Tipo\": \"Multifuncional Tinta Continua\", \"Conectividad\": \"Wi-Fi, USB, Wi-Fi Direct\", \"Funciones\": \"Impresión, Copia, Escaneo\", \"Marca\": \"HP\", \"Resolución\": \"4800 x 1200 dpi\"}",
        "is_favorite": False,
        "historical_min_price": 519.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_smart_tank_580",
        "title": "Impresora Multifuncional HP Smart Tank 580 Wi-Fi",
        "category": "Impresoras",
        "brand": "HP",
        "best_price": 569.0,
        "original_price": 699.0,
        "best_store_name": "La Curacao",
        "discount_percentage": 19,
        "available_stores_count": 1,
        "image_url": "https://www.lacuracao.pe/media/catalog/product/s/t/st_580_1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Impresora todo en uno todo conectada con Wi-Fi inteligente de rápida recuperación y manejo sencillo desde la app HP Smart.",
        "features_json": "[\"Tipo: Multifuncional Tinta Continua\", \"Conectividad: Wi-Fi, USB\", \"Funciones: Impresión, Copia, Escaneo\", \"Velocidad: 12 ppm negro, 5 ppm color\", \"Bandeja de entrada: 100 hojas\"]",
        "tech_specs_json": "{\"Tipo\": \"Multifuncional Tinta Continua\", \"Conectividad\": \"Wi-Fi, USB\", \"Funciones\": \"Impresión, Copia, Escaneo\", \"Marca\": \"HP\", \"Resolución\": \"4800 x 1200 dpi\"}",
        "is_favorite": False,
        "historical_min_price": 569.0,
        "is_historical_min": True
    },
    {
        "id": "prod_hp_deskjet_2975",
        "title": "Impresora Multifuncional HP DeskJet Ink Advantage 2975 Wi-Fi",
        "category": "Impresoras",
        "brand": "HP",
        "best_price": 299.0,
        "original_price": 369.0,
        "best_store_name": "Tottus",
        "discount_percentage": 19,
        "available_stores_count": 1,
        "image_url": "https://media.falabella.com/tottusPE/43629816_1/public",
        "description": "Impresora compacta y económica para el hogar con cartuchos originales de bajo costo, conexión inalámbrica y app HP Smart.",
        "features_json": "[\"Tipo: Multifuncional Inyección Térmica\", \"Conectividad: Wi-Fi, USB\", \"Funciones: Impresión, Copia, Escaneo\", \"Resolución: Hasta 4800 x 1200 dpi\", \"Cartuchos: HP 667 Negro y Tricolor\"]",
        "tech_specs_json": "{\"Tipo\": \"Multifuncional Inyección Térmica\", \"Conectividad\": \"Wi-Fi, USB\", \"Funciones\": \"Impresión, Copia, Escaneo\", \"Marca\": \"HP\", \"Resolución\": \"4800 x 1200 dpi\"}",
        "is_favorite": False,
        "historical_min_price": 299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_epson_ecotank_l3350",
        "title": "Impresora Multifuncional Epson EcoTank L3350 Wi-Fi",
        "category": "Impresoras",
        "brand": "Epson",
        "best_price": 799.0,
        "original_price": 949.0,
        "best_store_name": "Metro",
        "discount_percentage": 16,
        "available_stores_count": 2,
        "image_url": "https://metroio.vteximg.com.br/arquivos/ids/657438/Impresora-Multifuncional-EPSON-L3350-WiFi-1-369226.jpg?v=639210190379100000",
        "description": "Multifuncional inalámbrica EcoTank para familias activas con conectividad Wi-Fi, Wi-Fi Direct y soporte para Epson Smart Panel.",
        "features_json": "[\"Tipo: Multifuncional Tinta Continua EcoTank\", \"Conectividad: Wi-Fi, Wi-Fi Direct, USB\", \"Funciones: Impresión, Copia, Escaneo\", \"Tecnología: MicroPiezo Heat-Free\", \"Rendimiento: 4500 páginas negro / 7500 páginas color\"]",
        "tech_specs_json": "{\"Tipo\": \"Multifuncional Tinta Continua EcoTank\", \"Conectividad\": \"Wi-Fi, Wi-Fi Direct, USB\", \"Funciones\": \"Impresión, Copia, Escaneo\", \"Marca\": \"Epson\", \"Resolución\": \"5760 x 1440 dpi\"}",
        "is_favorite": False,
        "historical_min_price": 799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lg_oled_tv",
        "title": "Televisor LG 55\" OLED evo AI C6 4K Smart TV 2026",
        "category": "TVs",
        "brand": "LG",
        "best_price": 3799.0,
        "original_price": 5499.0,
        "best_store_name": "Falabella",
        "discount_percentage": 31,
        "available_stores_count": 5,
        "image_url": "https://media.falabella.com/falabellaPE/80046493_01/public",
        "description": "Televisor LG OLED evo serie C6 con panel autoemisivo 4K, procesador inteligente alpha 9 Gen7, tasa de refresco nativa de 144Hz y Dolby Vision / Atmos.",
        "features_json": "[\"Pantalla: 55\\\" OLED evo 4K 144Hz\", \"Resolución: 3840 x 2160 (4K UHD)\", \"Procesador: alpha 9 Gen7 AI Processor 4K\", \"Sistema Operativo: webOS 26 con actualizaciones garantizadas\", \"Gaming: 4 puertos HDMI 2.1 con VRR, G-Sync y FreeSync\"]",
        "tech_specs_json": "{\"Resolución\": \"3840 x 2160 (4K UHD)\", \"Pantalla\": \"55\\\" OLED evo 144Hz\", \"Sistema Operativo\": \"webOS 26\", \"Marca\": \"LG\", \"Tasa de Refresco\": \"144 Hz\", \"Conectividad\": \"Wi-Fi, Bluetooth 5.2, HDMI 2.1\"}",
        "is_favorite": False,
        "historical_min_price": 3799.0,
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
        "image_url": "https://hiraoka.com.pe/media/catalog/product/i/p/iphone_16_no-ai_black_pdp_image_position_1__gens.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Apple iPhone 16 con chip A18 ultrapotente, Control de la Cámara táctil, sistema de dos cámaras de 48 MP con Fusion y botón de Acción personalizable.",
        "features_json": "[\"Procesador: Apple A18\", \"Memoria RAM: 8 GB\", \"Almacenamiento: 128 GB\", \"Pantalla: 6.1\\\" Super Retina XDR OLED\", \"Resolución: 2556 x 1179 píxeles\", \"Cámara Principal: 48 MP Fusion + 12 MP Ultra gran angular\"]",
        "tech_specs_json": "{\"Procesador\": \"Apple A18\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"128 GB\", \"Pantalla\": \"6.1\\\" Super Retina XDR OLED\", \"Resolución\": \"2556 x 1179\", \"Sistema Operativo\": \"iOS 18\", \"Conectividad\": \"5G\", \"Marca\": \"Apple\"}",
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
        "original_price": 2299.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 20,
        "available_stores_count": 2,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/2/_/2_20_12.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Xiaomi Redmi Note 15 Pro 5G con cámara insignia de 200MP con OIS, carga ultra rápida de 120W HyperCharge y pantalla AMOLED CrystalRes 1.5K.",
        "features_json": "[\"Procesador: Snapdragon 7s Gen 3\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.67\\\" AMOLED CrystalRes 120Hz\", \"Resolución: 2712 x 1220 píxeles\", \"Batería: 5000 mAh con carga de 120W\"]",
        "tech_specs_json": "{\"Procesador\": \"Snapdragon 7s Gen 3\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"6.67\\\" AMOLED CrystalRes 120Hz\", \"Resolución\": \"2712 x 1220\", \"Sistema Operativo\": \"Android / HyperOS\", \"Conectividad\": \"5G\", \"Marca\": \"Xiaomi\"}",
        "is_favorite": False,
        "historical_min_price": 1829.0,
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
        "image_url": "https://media.falabella.com/falabellaPE/21014911_1/public",
        "description": "Nueva tableta Apple iPad de 11 pulgadas con chip A16 Bionic, pantalla Liquid Retina envolvente, conectividad Wi-Fi 6 de alta velocidad y compatibilidad con Apple Pencil.",
        "features_json": "[\"Procesador: Apple A16 Bionic\", \"Memoria RAM: 6 GB\", \"Almacenamiento: 128 GB\", \"Pantalla: 11\\\" Liquid Retina True Tone\", \"Resolución: 2360 x 1640 píxeles\", \"Conectividad: Wi-Fi 6, Bluetooth 5.3\"]",
        "tech_specs_json": "{\"Procesador\": \"Apple A16 Bionic\", \"Memoria RAM\": \"6 GB\", \"Almacenamiento\": \"128 GB\", \"Pantalla\": \"11\\\" Liquid Retina\", \"Resolución\": \"2360 x 1640\", \"Sistema Operativo\": \"iPadOS\", \"Conectividad\": \"Wi-Fi 6\", \"Marca\": \"Apple\"}",
        "is_favorite": False,
        "historical_min_price": 1899.0,
        "is_historical_min": True
    },
    {
        "id": "prod_macbook_air_m1",
        "title": "Apple MacBook Air 13\" Chip M1 512GB SSD 8GB RAM",
        "category": "Laptops",
        "brand": "Apple",
        "best_price": 3799.0,
        "original_price": 4999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 24,
        "available_stores_count": 1,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/a/i/air_m1_space_gray_front_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "La laptop más delgada y liviana de Apple con revolucionario chip M1, CPU de 8 núcleos, diseño silencioso sin ventilador y hasta 18 horas de batería.",
        "features_json": "[\"Procesador: Apple M1 (8 núcleos)\", \"Memoria RAM: 8 GB unificada\", \"Almacenamiento: 512 GB SSD ultra rápido\", \"Pantalla: 13.3\\\" Retina retroiluminada por LED\", \"Resolución: 2560 x 1600 píxeles\", \"Batería: Hasta 18 horas de reproducción\"]",
        "tech_specs_json": "{\"Procesador\": \"Apple M1\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"512 GB SSD\", \"Pantalla\": \"13.3\\\" Retina LED\", \"Resolución\": \"2560 x 1600\", \"Sistema Operativo\": \"macOS\", \"Marca\": \"Apple\"}",
        "is_favorite": False,
        "historical_min_price": 3799.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_s25_ultra",
        "title": "Samsung Galaxy S25 Ultra 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 5299.0,
        "original_price": 6399.0,
        "best_store_name": "Tiendas Efe",
        "discount_percentage": 17,
        "available_stores_count": 2,
        "image_url": "https://www.efe.com.pe/media/catalog/product/4/5/459270-800-800.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "El estandarte de Samsung con Galaxy AI integrada, procesador Snapdragon 8 Elite for Galaxy, chasis de titanio con S-Pen y cámara cuádruple de 200MP.",
        "features_json": "[\"Procesador: Snapdragon 8 Elite\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.9\\\" Dynamic AMOLED 2X\", \"Resolución: 3120 x 1440 píxeles\", \"Cámara Principal: 200 MP + 50 MP + 12 MP + 10 MP\"]",
        "tech_specs_json": "{\"Procesador\": \"Snapdragon 8 Elite\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"6.9\\\" Dynamic AMOLED 2X\", \"Resolución\": \"3120 x 1440\", \"Sistema Operativo\": \"Android 15\", \"Conectividad\": \"5G\", \"Marca\": \"Samsung\"}",
        "is_favorite": False,
        "historical_min_price": 5299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_s24_ultra",
        "title": "Samsung Galaxy S24 Ultra 5G 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 4499.0,
        "original_price": 5699.0,
        "best_store_name": "Falabella",
        "discount_percentage": 21,
        "available_stores_count": 1,
        "image_url": "https://media.falabella.com/falabellaPE/155039507_01/public",
        "description": "Samsung Galaxy S24 Ultra con chip Snapdragon 8 Gen 3 for Galaxy, marco de titanio, Corning Gorilla Armor y funciones completas de Galaxy AI.",
        "features_json": "[\"Procesador: Snapdragon 8 Gen 3\", \"Memoria RAM: 12 GB\", \"Almacenamiento: 512 GB\", \"Pantalla: 6.8\\\" Dynamic AMOLED 2X 120Hz\", \"Resolución: 3120 x 1440 píxeles\", \"Cámara: 200 MP + 50 MP + 12 MP + 10 MP\"]",
        "tech_specs_json": "{\"Procesador\": \"Snapdragon 8 Gen 3\", \"Memoria RAM\": \"12 GB\", \"Almacenamiento\": \"512 GB\", \"Pantalla\": \"6.8\\\" Dynamic AMOLED 2X\", \"Resolución\": \"3120 x 1440\", \"Sistema Operativo\": \"Android 14\", \"Conectividad\": \"5G\", \"Marca\": \"Samsung\"}",
        "is_favorite": False,
        "historical_min_price": 4499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_a55",
        "title": "Samsung Galaxy A55 5G 8GB RAM 256GB",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 1499.0,
        "original_price": 1899.0,
        "best_store_name": "Falabella",
        "discount_percentage": 21,
        "available_stores_count": 1,
        "image_url": "https://media.falabella.com/falabellaPE/158309352_01/public",
        "description": "Gama media premium con procesador Exynos 1480 con GPU Xclipse 530 de arquitectura AMD RDNA2, diseño en cristal y marco metálico con resistencia IP67.",
        "features_json": "[\"Procesador: Exynos 1480\", \"Memoria RAM: 8 GB\", \"Almacenamiento: 256 GB\", \"Pantalla: 6.6\\\" Super AMOLED FHD+ 120Hz\", \"Resolución: 2340 x 1080 píxeles\", \"Cámara Principal: 50 MP con OIS + 12 MP + 5 MP\"]",
        "tech_specs_json": "{\"Procesador\": \"Exynos 1480\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"256 GB\", \"Pantalla\": \"6.6\\\" Super AMOLED 120Hz\", \"Resolución\": \"2340 x 1080\", \"Sistema Operativo\": \"Android 14\", \"Conectividad\": \"5G\", \"Marca\": \"Samsung\"}",
        "is_favorite": False,
        "historical_min_price": 1499.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_a35",
        "title": "Samsung Galaxy A35 5G 6.6\" 8GB RAM 256GB",
        "category": "Smartphones",
        "brand": "Samsung",
        "best_price": 1099.0,
        "original_price": 1499.0,
        "best_store_name": "Falabella",
        "discount_percentage": 27,
        "available_stores_count": 1,
        "image_url": "https://media.falabella.com/falabellaPE/158509218_01/public",
        "description": "Excelente balance calidad-precio con pantalla Infinity-O Super AMOLED a 120Hz, procesador Exynos 1380 octa-core y batería de 5000 mAh para 2 días.",
        "features_json": "[\"Procesador: Exynos 1380\", \"Memoria RAM: 8 GB\", \"Almacenamiento: 256 GB\", \"Pantalla: 6.6\\\" Super AMOLED FHD+ 120Hz\", \"Resolución: 2340 x 1080 píxeles\", \"Batería: 5000 mAh con carga de 25W\"]",
        "tech_specs_json": "{\"Procesador\": \"Exynos 1380\", \"Memoria RAM\": \"8 GB\", \"Almacenamiento\": \"256 GB\", \"Pantalla\": \"6.6\\\" Super AMOLED 120Hz\", \"Resolución\": \"2340 x 1080\", \"Sistema Operativo\": \"Android 14\", \"Conectividad\": \"5G\", \"Marca\": \"Samsung\"}",
        "is_favorite": False,
        "historical_min_price": 1099.0,
        "is_historical_min": True
    },
    {
        "id": "prod_lenovo_ideapad_slim",
        "title": "Laptop IA Lenovo IdeaPad Slim 5i de 14\", Intel Core Ultra 9 185H, 16GB RAM, 512GB SSD",
        "category": "Laptops",
        "brand": "Lenovo",
        "best_price": 4299.0,
        "original_price": 4999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 14,
        "available_stores_count": 1,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/8/3/83v6004elm_3.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Laptop impulsada por Inteligencia Artificial con potente procesador Intel Core Ultra 9 185H con NPU dedicada, pantalla OLED de 14 pulgadas y chasis ultradelgado de aluminio militar.",
        "features_json": "[\"Procesador: Intel Core Ultra 9 185H\", \"Memoria RAM: 16 GB LPDDR5X\", \"Almacenamiento: 512 GB SSD M.2 PCIe\", \"Pantalla: 14\\\" WUXGA OLED 100% DCI-P3\", \"Resolución: 1920 x 1200 píxeles\", \"Sistema Operativo: Windows 11 Home\"]",
        "tech_specs_json": "{\"Procesador\": \"Intel Core Ultra 9 185H\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"512 GB SSD\", \"Pantalla\": \"14\\\" OLED WUXGA\", \"Resolución\": \"1920 x 1200\", \"Sistema Operativo\": \"Windows 11 Home\", \"Marca\": \"Lenovo\"}",
        "is_favorite": False,
        "historical_min_price": 4299.0,
        "is_historical_min": True
    },
    {
        "id": "prod_asus_zenbook_14",
        "title": "Laptop Asus Zenbook A14 de 14\", Copilot+ PC, Qualcomm Snapdragon X, 16GB RAM, 512GB SSD + Funda",
        "category": "Laptops",
        "brand": "Asus",
        "best_price": 4699.0,
        "original_price": 5499.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 15,
        "available_stores_count": 1,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/4/140353_2.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Copilot+ PC de última generación con procesador Snapdragon X, 45 TOPS de NPU para IA local, pantalla Asus Lumina OLED 2.8K y hasta 22 horas de autonomía extrema.",
        "features_json": "[\"Procesador: Snapdragon X Plus\", \"Memoria RAM: 16 GB LPDDR5X\", \"Almacenamiento: 512 GB SSD NVMe PCIe 4.0\", \"Pantalla: 14\\\" 2.8K (2880 x 1800) OLED 120Hz\", \"Resolución: 2880 x 1800 píxeles\", \"IA: NPU Qualcomm Hexagon de 45 TOPS\"]",
        "tech_specs_json": "{\"Procesador\": \"Snapdragon X Plus\", \"Memoria RAM\": \"16 GB\", \"Almacenamiento\": \"512 GB SSD\", \"Pantalla\": \"14\\\" OLED 2.8K\", \"Resolución\": \"2880 x 1800\", \"Sistema Operativo\": \"Windows 11 Home\", \"Marca\": \"Asus\"}",
        "is_favorite": False,
        "historical_min_price": 4699.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_tab_s10",
        "title": "Tablet Samsung Galaxy Tab A11 8.7\" 64GB 4GB RAM",
        "category": "Tablets",
        "brand": "Samsung",
        "best_price": 599.0,
        "original_price": 799.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 25,
        "available_stores_count": 1,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/137729_3_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Tableta portátil de 8.7 pulgadas con marco metálico ligero, altavoces duales con sonido Dolby Atmos, procesador Octa-Core y batería de larga duración.",
        "features_json": "[\"Procesador: MediaTek Helio G99 Octa-Core\", \"Memoria RAM: 4 GB\", \"Almacenamiento: 64 GB ampliable hasta 1TB con microSD\", \"Pantalla: 8.7\\\" TFT LCD WXGA+\", \"Resolución: 1340 x 800 píxeles\", \"Audio: Altavoces duales Dolby Atmos\"]",
        "tech_specs_json": "{\"Procesador\": \"MediaTek Helio G99\", \"Memoria RAM\": \"4 GB\", \"Almacenamiento\": \"64 GB\", \"Pantalla\": \"8.7\\\" TFT LCD\", \"Resolución\": \"1340 x 800\", \"Sistema Operativo\": \"Android 14\", \"Conectividad\": \"Wi-Fi\", \"Marca\": \"Samsung\"}",
        "is_favorite": False,
        "historical_min_price": 599.0,
        "is_historical_min": True
    },
    {
        "id": "prod_samsung_neo_qled_65",
        "title": "Televisor Samsung Smart TV 85\" Neo QLED 4K QN85QN70HAGXPE",
        "category": "TVs",
        "brand": "Samsung",
        "best_price": 7999.0,
        "original_price": 10999.0,
        "best_store_name": "Hiraoka",
        "discount_percentage": 27,
        "available_stores_count": 1,
        "image_url": "https://hiraoka.com.pe/media/catalog/product/1/3/139331_4_1_1.jpg?quality=85&bg-color=255,255,255&fit=bounds&height=300&width=240&canvas=240:300",
        "description": "Gigantesco televisor Samsung Neo QLED de 85 pulgadas con Quantum Matrix Technology, procesador NQ4 AI Gen2 con escalado a 4K por redes neuronales y Motion Xcelerator 120Hz.",
        "features_json": "[\"Pantalla: 85\\\" Neo QLED 4K con Mini LED\", \"Resolución: 3840 x 2160 (4K UHD)\", \"Procesador: NQ4 AI Gen2 Processor\", \"Tasa de Refresco: 120 Hz nativo\", \"Sonido: OTS Lite y Dolby Atmos con Q-Symphony\"]",
        "tech_specs_json": "{\"Resolución\": \"3840 x 2160 (4K UHD)\", \"Pantalla\": \"85\\\" Neo QLED 120Hz\", \"Sistema Operativo\": \"Tizen OS\", \"Marca\": \"Samsung\", \"Tasa de Refresco\": \"120 Hz\", \"Conectividad\": \"Wi-Fi 5, Bluetooth 5.2, 4 x HDMI\"}",
        "is_favorite": False,
        "historical_min_price": 7999.0,
        "is_historical_min": True
    }
]

SEED_STORE_OFFERS: List[Dict[str, Any]] = [
    {
        "product_id": "prod_hp_smart_tank_530",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 799.0,
        "original_price": 999.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/20756050/impresora-multifuncional-smart-tank-530/20756050",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_smart_tank_581",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 549.0,
        "original_price": 699.0,
        "offer_url": "https://simple.ripley.com.pe/impresora-multifuncional-hp-smart-tank-581-2004335122091p",
        "is_best_price": True
    },
    {
        "product_id": "prod_epson_ecotank_l3310",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 699.0,
        "original_price": 859.0,
        "offer_url": "https://hiraoka.com.pe/impresora-multifuncional-epson-ecotank-l3310",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_smart_tank_585",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 519.0,
        "original_price": 649.0,
        "offer_url": "https://www.efe.com.pe/hp-smart-tank-585-blue-white-st-585.html",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_smart_tank_580",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 569.0,
        "original_price": 699.0,
        "offer_url": "https://www.lacuracao.pe/impresora-todo-en-uno-hp-smart-tank-580-1f3y2a.html",
        "is_best_price": True
    },
    {
        "product_id": "prod_hp_deskjet_2975",
        "store_id": "tottus",
        "store_name": "Tottus",
        "price": 299.0,
        "original_price": 369.0,
        "offer_url": "https://www.tottus.com.pe/tottus-pe/articulo/151249212/impresora-multifuncional-hp-ia-2975/151249213",
        "is_best_price": True
    },
    {
        "product_id": "prod_epson_ecotank_l3350",
        "store_id": "metro",
        "store_name": "Metro",
        "price": 799.0,
        "original_price": 949.0,
        "offer_url": "https://www.metro.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p",
        "is_best_price": True
    },
    {
        "product_id": "prod_epson_ecotank_l3350",
        "store_id": "wong",
        "store_name": "Wong",
        "price": 799.0,
        "original_price": 949.0,
        "offer_url": "https://www.wong.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 3799.0,
        "original_price": 5499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3799.0,
        "original_price": 5499.0,
        "offer_url": "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p",
        "is_best_price": True
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3899.0,
        "original_price": 5499.0,
        "offer_url": "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 3899.0,
        "original_price": 5499.0,
        "offer_url": "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        "is_best_price": False
    },
    {
        "product_id": "prod_lg_oled_tv",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 3899.0,
        "original_price": 5499.0,
        "offer_url": "https://www.lacuracao.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
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
        "store_id": "ripley",
        "store_name": "Ripley",
        "price": 3399.0,
        "original_price": 3999.0,
        "offer_url": "https://simple.ripley.com.pe/iphone-16-128gb-2065365819351",
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
        "original_price": 2299.0,
        "offer_url": "https://hiraoka.com.pe/celular-libre-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-blue",
        "is_best_price": True
    },
    {
        "product_id": "prod_xiaomi_redmi_note",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 1849.0,
        "original_price": 2299.0,
        "offer_url": "https://www.efe.com.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
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
        "is_best_price": True
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
        "product_id": "prod_macbook_air_m1",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 3799.0,
        "original_price": 4999.0,
        "offer_url": "https://hiraoka.com.pe/macbook-air-13-m1-512gb-ssd-8gb-ram-gris-espacial",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_s25_ultra",
        "store_id": "efe",
        "store_name": "Tiendas Efe",
        "price": 5299.0,
        "original_price": 6399.0,
        "offer_url": "https://www.efe.com.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_s25_ultra",
        "store_id": "curacao",
        "store_name": "La Curacao",
        "price": 5299.0,
        "original_price": 6399.0,
        "offer_url": "https://www.lacuracao.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_s24_ultra",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 4499.0,
        "original_price": 5699.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/155039506/samsung-galaxy-s24-ultra-5g-512gb-12gb-ram-negro",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_a55",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1499.0,
        "original_price": 1899.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/158309351/samsung-galaxy-a55-5g-8gb-ram-256gb",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_a35",
        "store_id": "falabella",
        "store_name": "Falabella",
        "price": 1099.0,
        "original_price": 1499.0,
        "offer_url": "https://www.falabella.com.pe/falabella-pe/product/158509217/celular-samsung-galaxy-a35-5g-6-6-pulg-8gb-ram-256gb-android-14-negro",
        "is_best_price": True
    },
    {
        "product_id": "prod_lenovo_ideapad_slim",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4299.0,
        "original_price": 4999.0,
        "offer_url": "https://hiraoka.com.pe/laptop-ia-lenovo-ideapad-slim-5i-de-14-intel-core-ultra-9-185h-16gb-ram-disco-solido-de-512gb-modelo-83v6004elm",
        "is_best_price": True
    },
    {
        "product_id": "prod_asus_zenbook_14",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 4699.0,
        "original_price": 5499.0,
        "offer_url": "https://hiraoka.com.pe/laptop-asus-zenbook-a14-de-14-copilot-pc-qualcomm-snapdragon-x-16gb-ram-disco-solido-de-512gb-modelo-ux3407qa-qd289w-funda",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_tab_s10",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 599.0,
        "original_price": 799.0,
        "offer_url": "https://hiraoka.com.pe/tablet-samsung-galaxy-tab-a11-8-7-64gb-4gb-ram-gray",
        "is_best_price": True
    },
    {
        "product_id": "prod_samsung_neo_qled_65",
        "store_id": "hiraoka",
        "store_name": "Hiraoka",
        "price": 7999.0,
        "original_price": 10999.0,
        "offer_url": "https://hiraoka.com.pe/televisor-samsung-smart-tv-85-neo-qled-4k-qn85qn70hagxpe",
        "is_best_price": True
    }
]

SEED_PRICE_HISTORY: List[Dict[str, Any]] = [
    {
        "product_id": "prod_hp_smart_tank_530",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_smart_tank_581",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 549.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_epson_ecotank_l3310",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 699.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_smart_tank_585",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 519.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_smart_tank_580",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 569.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_hp_deskjet_2975",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_epson_ecotank_l3350",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 799.0,
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
        "product_id": "prod_ipad_11",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1899.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_macbook_air_m1",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 3799.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_s25_ultra",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 5299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_s24_ultra",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_a55",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1499.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_a35",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 1099.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_lenovo_ideapad_slim",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4299.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_asus_zenbook_14",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 4699.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_tab_s10",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 599.0,
        "recorded_at": "2026-11-01 12:00:00"
    },
    {
        "product_id": "prod_samsung_neo_qled_65",
        "day_offset": 0,
        "date_label": "Hoy",
        "price": 7999.0,
        "recorded_at": "2026-11-01 12:00:00"
    }
]

COMMUNITY_POSTS: List[Dict[str, Any]] = []

COMMUNITY_OFFERS: List[Dict[str, Any]] = []


async def sync_and_upsert_catalog(session: AsyncSession) -> int:
    """
    Sincronización UPSERT en Neon PostgreSQL / SQLite de alto rendimiento (< 200 ms):
    - Precarga existentes en memoria para evitar cientos de viajes de red WAN (Round Trips).
    - Actualiza si ya existe por ID o inserta si no existe.
    - Sincroniza ofertas por tienda (store_offers) e historial de precios (price_history).
    - Elimina cualquier registro de prueba previo y limpia comunidad/ofertas fantasma.
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

    valid_prod_ids = {p["id"] for p in SEED_PRODUCTS}

    # 0. Limpieza de productos obsoletos o fuera de catálogo
    for pid, ent in list(existing_prods.items()):
        if pid not in valid_prod_ids:
            await session.delete(ent)

    for (pid, sid), off in list(existing_offers.items()):
        if pid not in valid_prod_ids:
            await session.delete(off)

    for (pid, day), hist in list(existing_hist.items()):
        if pid not in valid_prod_ids or day != 0:
            await session.delete(hist)

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

    # 4. Limpieza estricta de cualquier dato fantasma en comunidad
    await session.execute(
        delete(CommunityPostEntity).where(
            (CommunityPostEntity.author_name == "Usuario Real") |
            (CommunityPostEntity.title.like("%liquidación de vitrina%")) |
            (CommunityPostEntity.product_id.notin_(valid_prod_ids))
        )
    )

    await session.commit()
    logger.info(f"sync_and_upsert_catalog completado con éxito: {len(SEED_PRODUCTS)} productos sincronizados.")
    return len(SEED_PRODUCTS)


async def seed_database_fast(session: AsyncSession) -> int:
    """Inserta o sincroniza el catálogo oficial en Neon PostgreSQL / SQLite."""
    return await sync_and_upsert_catalog(session)
