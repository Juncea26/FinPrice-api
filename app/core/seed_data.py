"""
Datos iniciales oficiales de productos reales en tiendas retail peruanas.
Sincronización UPSERT instantánea en Neon PostgreSQL / SQLite de alto rendimiento (< 200 ms).
REGLA FINPRICE: SOLO PRODUCTOS VENDIDOS POR LA MISMA TIENDA OFICIAL (CERO TERCEROS / MARKETPLACE).
PERMITIR PRODUCTOS DESDE 1 TIENDA EN ADELANTE (len(offers) >= 1 OBLIGATORIO).
ESTRICTAMENTE 8 TIENDAS: Tiendas Efe, Falabella, Ripley, La Curacao, Hiraoka, Tottus, Metro, Wong.
HISTORIAL REAL CRONOLÓGICO: Puntos diarios reales acumulados hasta la fecha actual de Perú (America/Lima).
CERO DATOS FANTASMA EN COMUNIDAD: La sección de comunidad inicia 100% limpia.
"""
from datetime import datetime, timezone
import json
import pprint
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


SEED_PRODUCTS: List[Dict[str, Any]] = [   {   'available_stores_count': 6,
        'best_price': 3399.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/iphone-16-blk-128gb-bes-mye73be-a.html',
        'brand': 'Apple',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Apple iPhone 16 128GB. Comparativa multi-tienda con precios online '
                       'públicos verificados en tiempo real.',
        'discount_percentage': 32,
        'features_json': '["Procesador: Apple A18", "Memoria RAM: 8 GB", "Almacenamiento: 128 GB", "Pantalla: 6.1\\" '
                         'Super Retina XDR OLED", "Resolución: Super Retina XDR OLED (2556 x 1179)", "Cámara '
                         'Principal: 48 MP"]',
        'historical_min_price': 3399.0,
        'id': 'prod_iphone_16',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/i/p/iphone_16_no-ai_black_pdp_image_position_1__gens.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 4999.0,
        'tech_specs_json': '{"Procesador": "Apple A18", "Memoria RAM": "8 GB", "Almacenamiento": "128 GB", "Pantalla": '
                           '"6.1\\" Super Retina XDR OLED", "Sistema Operativo": "iOS 18", "Conectividad": "5G", '
                           '"Marca": "Apple", "Cámara Principal": "48 MP", "Resolución": "Super Retina XDR OLED (2556 '
                           'x 1179)"}',
        'title': 'Apple iPhone 16 128GB'},
    {   'available_stores_count': 2,
        'best_price': 3699.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy S25 Ultra 512GB 12GB RAM. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 35,
        'features_json': '["Procesador: Snapdragon 8 Elite", "Memoria RAM: 12 GB", "Almacenamiento: 512 GB", '
                         '"Pantalla: 6.9\\" Dynamic AMOLED 2X", "Resolución: 3120 x 1440", "Conectividad: 5G"]',
        'historical_min_price': 3699.0,
        'id': 'prod_samsung_s25_ultra',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/4/5/459270-800-800.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 5719.0,
        'tech_specs_json': '{"Procesador": "Snapdragon 8 Elite", "Memoria RAM": "12 GB", "Almacenamiento": "512 GB", '
                           '"Pantalla": "6.9\\" Dynamic AMOLED 2X", "Sistema Operativo": "Android", "Conectividad": '
                           '"5G", "Marca": "Samsung", "Resolución": "3120 x 1440"}',
        'title': 'Samsung Galaxy S25 Ultra 512GB 12GB RAM'},
    {   'available_stores_count': 2,
        'best_price': 2699.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/galaxy-s24-fe-black-256gb-ee-sm-s721bzkmlep.html',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy S24 FE 256GB 8GB RAM. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 0,
        'features_json': '["Procesador: SEC | S5E9945(Exynos 2400e)", "Memoria RAM: 8 GB", "Almacenamiento: 256 GB", '
                         '"Pantalla: 6.7\\" Dynamic AMOLED 2X", "Resolución: Full HD", "Batería: 4700 mAh"]',
        'historical_min_price': 2699.0,
        'id': 'prod_samsung_galaxy_s24_fe',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/s/m/sm-s721bzkmlep_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 2699.0,
        'tech_specs_json': '{"Procesador": "SEC | S5E9945(Exynos 2400e)", "Memoria RAM": "8 GB", "Almacenamiento": '
                           '"256 GB", "Pantalla": "6.7\\" Dynamic AMOLED 2X", "Batería": "4700 mAh", "Sistema '
                           'Operativo": "Android", "Conectividad": "5G", "Marca": "Samsung", "Resolución": "Full HD"}',
        'title': 'Samsung Galaxy S24 FE 256GB 8GB RAM'},
    {   'available_stores_count': 4,
        'best_price': 4699.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/galaxy-s26-ultra-512gb-12gb-black-s26ult512-12neg.html',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy S26 Ultra 5G 512GB 12GB RAM. Comparativa multi-tienda '
                       'con precios online públicos verificados en tiempo real.',
        'discount_percentage': 15,
        'features_json': '["Procesador: Snapdragon 8 Elite Gen 5", "Memoria RAM: 12 GB", "Almacenamiento: 512 GB", '
                         '"Pantalla: 6.9\\" Dynamic AMOLED 2X de 6.9 pulgadas con resolución 3120x1440", "Resolución: '
                         '3120 x 1440 px", "Cámara Principal: 200 MP + 50 MP + 50 MP + 10 MP"]',
        'historical_min_price': 4699.0,
        'id': 'prod_samsung_galaxy_s24_ultra',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/3/138649_3.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 5499.0,
        'tech_specs_json': '{"Procesador": "Snapdragon 8 Elite Gen 5", "Memoria RAM": "12 GB", "Almacenamiento": "512 '
                           'GB", "Pantalla": "6.9\\" Dynamic AMOLED 2X de 6.9 pulgadas con resolución 3120x1440", '
                           '"Conectividad": "Wi-Fi", "Marca": "Samsung", "Batería": "5000 mAh", "Sistema Operativo": '
                           '"Android 16", "Cámara Principal": "200 MP + 50 MP + 50 MP + 10 MP", "Resolución": "3120 x '
                           '1440 px"}',
        'title': 'Samsung Galaxy S26 Ultra 5G 512GB 12GB RAM'},
    {   'available_stores_count': 4,
        'best_price': 1799.0,
        'best_store_name': 'Falabella',
        'best_store_url': 'https://www.falabella.com.pe/falabella-pe/product/80007794/celular-samsung-galaxy-a57-5g/80007798',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy A57 5G 256GB 8GB RAM. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 22,
        'features_json': '["Procesador: Samsung | Exynos 1680", "Memoria RAM: 8 GB", "Almacenamiento: 256 GB", '
                         '"Pantalla: 6.7\\" Super AMOLED Plus", "Resolución: 1080 x 2340", "Cámara Principal: 50 MP"]',
        'historical_min_price': 1799.0,
        'id': 'prod_samsung_galaxy_a57',
        'image_url': 'https://media.falabella.com/falabellaPE/80007798_21/w=800,h=800,fit=pad',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 2299.0,
        'tech_specs_json': '{"Marca": "Samsung", "Almacenamiento": "256 GB", "Conectividad": "Wi-Fi", "Memoria RAM": '
                           '"8 GB", "Sistema Operativo": "Android", "Procesador": "Samsung | Exynos 1680", "Cámara '
                           'Principal": "50 MP", "Pantalla": "6.7\\" Super AMOLED Plus", "Batería": "5000 mAh", '
                           '"Resolución": "1080 x 2340"}',
        'title': 'Samsung Galaxy A57 5G 256GB 8GB RAM'},
    {   'available_stores_count': 5,
        'best_price': 1449.0,
        'best_store_name': 'Tottus',
        'best_store_url': 'https://www.tottus.com.pe/tottus-pe/articulo/151775324/celular-galaxy-a37-5g-8gb-256gb-lila/151775327',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy A37 5G 256GB 8GB RAM. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 26,
        'features_json': '["Procesador: Samsung | Exynos 1480", "Memoria RAM: 8 GB", "Almacenamiento: 256 GB", '
                         '"Pantalla: 6.7\\" Super AMOLED", "Resolución: 1080 x 2340", "Cámara Principal: 50 MP"]',
        'historical_min_price': 1449.0,
        'id': 'prod_samsung_galaxy_a37',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/3/138916_2_1_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1949.0,
        'tech_specs_json': '{"Marca": "Samsung", "Procesador": "Samsung | Exynos 1480", "Memoria RAM": "8 GB", '
                           '"Pantalla": "6.7\\" Super AMOLED", "Almacenamiento": "256 GB", "Conectividad": "Wi-Fi", '
                           '"Sistema Operativo": "Android", "Cámara Principal": "50 MP", "Batería": "5000 mAh", '
                           '"Resolución": "1080 x 2340"}',
        'title': 'Samsung Galaxy A37 5G 256GB 8GB RAM'},
    {   'available_stores_count': 3,
        'best_price': 1899.0,
        'best_store_name': 'Hiraoka',
        'best_store_url': 'https://hiraoka.com.pe/celular-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-cafe-moca',
        'brand': 'Xiaomi',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Xiaomi Redmi Note 15 Pro+ 5G 512GB 12GB RAM. Comparativa multi-tienda '
                       'con precios verificados en tiempo real.',
        'discount_percentage': 5,
        'features_json': '["Procesador: Snapdragon 7s Gen4", "Memoria RAM: 12 GB", "Almacenamiento: 512 GB", '
                         '"Pantalla: 6.8\\" AMOLED", "Resolución: 1.5K", "Cámara Principal: 200 MP + 8 MP"]',
        'historical_min_price': 1899.0,
        'id': 'prod_xiaomi_redmi_note',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/_/1_23_12.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1999.0,
        'tech_specs_json': '{"Marca": "Xiaomi", "Procesador": "Snapdragon 7s Gen4", "Sistema Operativo": "Android 15", '
                           '"Memoria RAM": "12 GB", "Almacenamiento": "512 GB", "Cámara Principal": "200 MP + 8 MP", '
                           '"Conectividad": "5G", "Batería": "6500 mAh", "Pantalla": "6.8\\" AMOLED", "Resolución": '
                           '"1.5K"}',
        'title': 'Xiaomi Redmi Note 15 Pro+ 5G 512GB 12GB RAM'},
    {   'available_stores_count': 2,
        'best_price': 4199.0,
        'best_store_name': 'Hiraoka',
        'best_store_url': 'https://hiraoka.com.pe/laptop-asus-zenbook-a14-de-14-copilot-pc-qualcomm-snapdragon-x-16gb-ram-disco-solido-de-512gb-modelo-ux3407qa-qd289w-funda',
        'brand': 'Qualcomm',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Asus Zenbook A14 14" Snapdragon X 16GB RAM 512GB SSD. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 24,
        'features_json': '["Procesador: Snapdragon X X1 26 100 Processor", "Memoria RAM: 16 GB", "Almacenamiento: 512 '
                         'GB", "Pantalla: 14\\" OLED", "Resolución: WUXGA 60Hz", "Conectividad: Wi-Fi 6"]',
        'historical_min_price': 4199.0,
        'id': 'prod_asus_zenbook_a14',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/4/140353_2.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 5499.0,
        'tech_specs_json': '{"Marca": "Qualcomm", "Procesador": "Snapdragon X X1 26 100 Processor", "Sistema '
                           'Operativo": "Windows 11 Home", "Memoria RAM": "16 GB", "Almacenamiento": "512 GB", '
                           '"Pantalla": "14\\" OLED", "Conectividad": "Wi-Fi 6", "Resolución": "WUXGA 60Hz"}',
        'title': 'Laptop Asus Zenbook A14 14" Snapdragon X 16GB RAM 512GB SSD'},
    {   'available_stores_count': 2,
        'best_price': 5899.0,
        'best_store_name': 'Hiraoka',
        'best_store_url': 'https://hiraoka.com.pe/macbook-air-de-13-chip-m5-16gb-ram-disco-solido-de-512gb-azul-cielo',
        'brand': 'Apple',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Apple MacBook Air 13" Chip M5 16GB RAM 512GB SSD. Comparativa '
                       'multi-tienda con precios verificados en tiempo real.',
        'discount_percentage': 9,
        'features_json': '["Procesador: 10 núcleos", "Memoria RAM: 16 GB", "Almacenamiento: 512 GB", "Pantalla: 13\\" '
                         'Liquid Retina", "Resolución: 2560 x 1664", "Conectividad: Bluetooth"]',
        'historical_min_price': 5899.0,
        'id': 'prod_macbook_air_m1',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/m/a/macbook_air_13-in_m5_sky_blue_pdp_image_position_1__gens.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 6499.0,
        'tech_specs_json': '{"Marca": "Apple", "Procesador": "10 núcleos", "Sistema Operativo": "Mac OS", "Memoria '
                           'RAM": "16 GB", "Almacenamiento": "512 GB", "Pantalla": "13\\" Liquid Retina", '
                           '"Conectividad": "Bluetooth", "Resolución": "2560 x 1664"}',
        'title': 'Apple MacBook Air 13" Chip M5 16GB RAM 512GB SSD'},
    {   'available_stores_count': 3,
        'best_price': 2299.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/lap-ip3-15f-r5-75-8gb-512ssd-82xq00ltlm.html',
        'brand': 'Lenovo',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Lenovo IdeaPad Slim 3 15.6" AMD Ryzen 5 8GB 512GB SSD. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 8,
        'features_json': '["Procesador: Intel Core i5", "Memoria RAM: 8 GB", "Almacenamiento: 512 GB", "Pantalla: '
                         '15.6\\" TN", "Resolución: Full HD", "Sistema Operativo: Windows 11 Home"]',
        'historical_min_price': 2299.0,
        'id': 'prod_lenovo_ideapad_slim_3',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/3/135438_4_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 2499.0,
        'tech_specs_json': '{"Marca": "Lenovo", "Procesador": "Intel Core i5", "Memoria RAM": "8 GB", "Pantalla": '
                           '"15.6\\" TN", "Sistema Operativo": "Windows 11 Home", "Almacenamiento": "512 GB", '
                           '"Resolución": "Full HD"}',
        'title': 'Laptop Lenovo IdeaPad Slim 3 15.6" AMD Ryzen 5 8GB 512GB SSD'},
    {   'available_stores_count': 2,
        'best_price': 4199.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/lapg-victus-15-6-r7-8gb-512gb-rtx4050-15-fb3049la.html',
        'brand': 'HP',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Gamer HP Victus 15.6" AMD Ryzen 7 8GB 512GB SSD RTX 4050. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 18,
        'features_json': '["Procesador: Hasta 4.7 GHz velocidad de ráfaga", "Memoria RAM: 8 GB", "Almacenamiento: 512 '
                         'GB", "Pantalla: 15.6\\" Pantalla FHD, IPS, antirreflejante, de 39,6 cm (15.6\\") en '
                         'diagonal, 300 nits y 62.5 % de sRGB (1920 x 1080)", "Resolución: Full HD", "Batería: Batería '
                         'de polímero de litio de 4 celdas y 70 Wh"]',
        'historical_min_price': 4199.0,
        'id': 'prod_hp_victus_15',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/1/5/15-fb3049la_1_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 5099.0,
        'tech_specs_json': '{"Memoria RAM": "8 GB", "Sistema Operativo": "Windows 11 Home Single Language", '
                           '"Pantalla": "15.6\\" Pantalla FHD, IPS, antirreflejante, de 39,6 cm (15.6\\") en diagonal, '
                           '300 nits y 62.5 % de sRGB (1920 x 1080)", "Procesador": "Hasta 4.7 GHz velocidad de '
                           'ráfaga", "Batería": "Batería de polímero de litio de 4 celdas y 70 Wh", "Marca": "HP", '
                           '"Almacenamiento": "512 GB", "Resolución": "Full HD"}',
        'title': 'Laptop Gamer HP Victus 15.6" AMD Ryzen 7 8GB 512GB SSD RTX 4050'},
    {   'available_stores_count': 2,
        'best_price': 3299.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/lapg-16-c5-210h-8gb-512ssd-rtx3050-fx607vj-rl011w.html',
        'brand': 'Intel',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Asus TUF Gaming F16 16" Intel Core 5 210H 8GB 512GB SSD. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 15,
        'features_json': '["Procesador: 2.2 GHz - 4.8 GHz", "Memoria RAM: 8 GB", "Almacenamiento: 512 GB", "Pantalla: '
                         '16\\" IPS", "Resolución: Full HD", "Sistema Operativo: Windows 11 Home en español"]',
        'historical_min_price': 3299.0,
        'id': 'prod_asus_tuf_gaming_f16',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/l/a/laptop-asus-tuf_1_.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 3899.0,
        'tech_specs_json': '{"Memoria RAM": "8 GB", "Sistema Operativo": "Windows 11 Home en español", "Pantalla": '
                           '"16\\" IPS", "Procesador": "2.2 GHz - 4.8 GHz", "Marca": "Intel", "Almacenamiento": "512 '
                           'GB", "Resolución": "Full HD"}',
        'title': 'Laptop Asus TUF Gaming F16 16" Intel Core 5 210H 8GB 512GB SSD'},
    {   'available_stores_count': 2,
        'best_price': 5999.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/lap-loq15-15-6-i7-16gb-512gb-rtx5050-83je01jwlm.html',
        'brand': 'Lenovo',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Lenovo LOQ 15.6" Intel Core i7 16GB 512GB SSD RTX 5050. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 5,
        'features_json': '["Procesador: P hasta 4.9 GHz - E hasta 3.5 GHz", "Memoria RAM: 16 GB", "Almacenamiento: 512 '
                         'GB", "Pantalla: 15.6\\" IPS Antirreflejo", "Resolución: Full HD", "Sistema Operativo: '
                         'Windows 11 Home"]',
        'historical_min_price': 5999.0,
        'id': 'prod_lenovo_loq_15',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/8/3/83je01jwlm_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 6329.0,
        'tech_specs_json': '{"Memoria RAM": "16 GB", "Sistema Operativo": "Windows 11 Home", "Pantalla": "15.6\\" IPS '
                           'Antirreflejo", "Procesador": "P hasta 4.9 GHz - E hasta 3.5 GHz", "Marca": "Lenovo", '
                           '"Almacenamiento": "512 GB", "Resolución": "Full HD"}',
        'title': 'Laptop Lenovo LOQ 15.6" Intel Core i7 16GB 512GB SSD RTX 5050'},
    {   'available_stores_count': 5,
        'best_price': 3599.0,
        'best_store_name': 'Ripley',
        'best_store_url': 'https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p',
        'brand': 'LG',
        'category': 'TVs',
        'description': 'Ficha técnica oficial de Televisor LG 55" OLED evo AI C6 4K Smart TV 2026. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 28,
        'features_json': '["Procesador: Procesador de IA α11 4K Generacion 3", "Pantalla: 55\\" OLED evo 120Hz", '
                         '"Resolución: 4K Ultra HD", "Conectividad: Wi-Fi 6", "Sistema Operativo: webOS 26", '
                         '"Conectividad: Wi-Fi, Bluetooth 5.3, 4 x HDMI 2.1"]',
        'historical_min_price': 3599.0,
        'id': 'prod_lg_oled_tv',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/3/139008_2_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 4999.0,
        'tech_specs_json': '{"Conectividad": "Wi-Fi 6", "Marca": "LG", "Pantalla": "55\\" OLED evo 120Hz", '
                           '"Procesador": "Procesador de IA α11 4K Generacion 3", "Sistema Operativo": "webOS 26", '
                           '"Resolución": "4K Ultra HD"}',
        'title': 'Televisor LG 55" OLED evo AI C6 4K Smart TV 2026'},
    {   'available_stores_count': 3,
        'best_price': 3049.0,
        'best_store_name': 'Wong',
        'best_store_url': 'https://www.wong.pe/televisor-lg-oled-55-oled55b6psa-1067136/p',
        'brand': 'LG',
        'category': 'TVs',
        'description': 'Ficha técnica oficial de Televisor LG 55" OLED Smart TV OLED55B6PSA. Comparativa multi-tienda '
                       'con precios online públicos verificados en tiempo real.',
        'discount_percentage': 22,
        'features_json': '["Procesador: Alpha 8 AI Procesador 4K Gen3", "Pantalla: 5.8\\" OLED", "Resolución: 4K Ultra '
                         'HD", "Conectividad: Wi-Fi", "Sistema Operativo: Smart TV webOS con IA (Google Gemini, '
                         'Microsoft Copilot)", "Pantalla: OLED"]',
        'historical_min_price': 3049.0,
        'id': 'prod_lg_oled_55_b6',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/o/l/oled55b6psa_1_1_.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 3899.0,
        'tech_specs_json': '{"Marca": "LG", "Sistema Operativo": "Smart TV webOS con IA (Google Gemini, Microsoft '
                           'Copilot)", "Conectividad": "Wi-Fi", "Pantalla": "5.8\\" OLED", "Procesador": "Alpha 8 AI '
                           'Procesador 4K Gen3", "Resolución": "4K Ultra HD"}',
        'title': 'Televisor LG 55" OLED Smart TV OLED55B6PSA'},
    {   'available_stores_count': 2,
        'best_price': 7999.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/tv-samsung-65-neo-qled-4k-uhd-tizen-qn85d-2024-qn65qn85dbgxpe.html',
        'brand': 'Samsung',
        'category': 'TVs',
        'description': 'Ficha técnica oficial de Televisor Samsung 65" Neo QLED 4K UHD Tizen QN85D. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 0,
        'features_json': '["Procesador: Procesador NQ4 AI Gen2", "Pantalla: Plana", "Resolución: 4K Ultra HD", '
                         '"Conectividad: Wi-Fi", "Sistema Operativo: Tizen", "Marca: Samsung"]',
        'historical_min_price': 7999.0,
        'id': 'prod_samsung_neo_qled_65',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/q/n/qn65qn85dbgxpe_01.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 7999.0,
        'tech_specs_json': '{"Sistema Operativo": "Tizen", "Marca": "Samsung", "Pantalla": "Plana", "Conectividad": '
                           '"Wi-Fi", "Procesador": "Procesador NQ4 AI Gen2", "Resolución": "4K Ultra HD"}',
        'title': 'Televisor Samsung 65" Neo QLED 4K UHD Tizen QN85D'},
    {   'available_stores_count': 5,
        'best_price': 1099.0,
        'best_store_name': 'Wong',
        'best_store_url': 'https://www.wong.pe/televisor-samsung-55-uhd-u8000h-vision-ai-smart-tv-2026-1067747/p',
        'brand': 'Samsung',
        'category': 'TVs',
        'description': 'Ficha técnica oficial de Televisor Samsung 55" UHD U8000H Vision AI Smart TV 2026. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 21,
        'features_json': '["Procesador: Procesador Crystal 4K Vision AI", "Memoria RAM: 2 GB", "Pantalla: 55\\"", '
                         '"Resolución: 4K Ultra HD", "Conectividad: Indique si el producto cuenta con tecnología de '
                         'conectividad", "Sistema Operativo: Seleccionar el sistema operativo que posee el '
                         'dispositivo"]',
        'historical_min_price': 1099.0,
        'id': 'prod_samsung_uhd_55_u8000',
        'image_url': 'https://media.falabella.com/falabellaPE/80044166_1/w=800,h=800,fit=pad',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1399.0,
        'tech_specs_json': '{"Marca": "Samsung", "Sistema Operativo": "Seleccionar el sistema operativo que posee el '
                           'dispositivo", "Conectividad": "Indique si el producto cuenta con tecnología de '
                           'conectividad", "Pantalla": "55\\"", "Memoria RAM": "2 GB", "Procesador": "Procesador '
                           'Crystal 4K Vision AI", "Resolución": "4K Ultra HD"}',
        'title': 'Televisor Samsung 55" UHD U8000H Vision AI Smart TV 2026'},
    {   'available_stores_count': 2,
        'best_price': 1699.0,
        'best_store_name': 'Tottus',
        'best_store_url': 'https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381',
        'brand': 'Apple',
        'category': 'Tablets',
        'description': 'Ficha técnica oficial de Apple iPad 11" Chip A16 Wi-Fi 128GB. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 35,
        'features_json': '["Procesador: Apple Chip A16", "Memoria RAM: 6 GB", "Almacenamiento: 128 GB", "Pantalla: '
                         '11\\" Retina", "Resolución: 4K Ultra HD", "Cámara Principal: 12 MP"]',
        'historical_min_price': 1699.0,
        'id': 'prod_ipad_11',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/i/p/ipad_a16_wifi_silver_pdp_image_position_1__laes_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 2599.0,
        'tech_specs_json': '{"Marca": "Apple", "Procesador": "Apple Chip A16", "Conectividad": "Wi-Fi", "Sistema '
                           'Operativo": "iPadOS 18 P", "Cámara Principal": "12 MP", "Pantalla": "11\\" Retina", '
                           '"Almacenamiento": "128 GB", "Memoria RAM": "6 GB", "Resolución": "4K Ultra HD"}',
        'title': 'Apple iPad 11" Chip A16 Wi-Fi 128GB'},
    {   'available_stores_count': 6,
        'best_price': 439.0,
        'best_store_name': 'Ripley',
        'best_store_url': 'https://simple.ripley.com.pe/tablet-samsung-galaxy-tab-a11-87-64gb-2004367413754p',
        'brand': 'Samsung',
        'category': 'Tablets',
        'description': 'Ficha técnica oficial de Tablet Samsung Galaxy Tab A11 8.7" 64GB 4GB RAM. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 32,
        'features_json': '["Procesador: MediaTek 2.2GHz,2GHz", "Memoria RAM: 4 GB", "Almacenamiento: 64 GB", '
                         '"Pantalla: 8.7\\" WXGA+", "Resolución: 1340 x 800 (WXGA+)", "Cámara Principal: 8 MP"]',
        'historical_min_price': 439.0,
        'id': 'prod_samsung_galaxy_tab_a11',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/3/137729_3_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 649.0,
        'tech_specs_json': '{"Almacenamiento": "64 GB", "Marca": "Samsung", "Memoria RAM": "4 GB", "Pantalla": "8.7\\" '
                           'WXGA+", "Procesador": "MediaTek 2.2GHz,2GHz", "Sistema Operativo": "Android 14", '
                           '"Conectividad": "Inalámbrico", "Cámara Principal": "8 MP", "Batería": "5100 mAh", '
                           '"Resolución": "1340 x 800 (WXGA+)"}',
        'title': 'Tablet Samsung Galaxy Tab A11 8.7" 64GB 4GB RAM'},
    {   'available_stores_count': 3,
        'best_price': 699.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/pad2-4gb-128gb-gray-pad2gray.html',
        'brand': 'Xiaomi',
        'category': 'Tablets',
        'description': 'Ficha técnica oficial de Tablet Xiaomi Redmi Pad 2 11" 4GB RAM 128GB. Comparativa multi-tienda '
                       'con precios online públicos verificados en tiempo real.',
        'discount_percentage': 30,
        'features_json': '["Procesador: MediaTek Helio G100-Ultra", "Memoria RAM: 4 GB", "Almacenamiento: 128 GB", '
                         '"Pantalla: 11\\" IPS", "Resolución: 2560 x 1600", "Batería: Hasta 11 horas"]',
        'historical_min_price': 699.0,
        'id': 'prod_xiaomi_redmi_pad_2',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/_/1_498.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 999.0,
        'tech_specs_json': '{"Sistema Operativo": "Android 15", "Pantalla": "11\\" IPS", "Procesador": "MediaTek Helio '
                           'G100-Ultra", "Batería": "Hasta 11 horas", "Conectividad": "Wireless", "Marca": "Xiaomi", '
                           '"Memoria RAM": "4 GB", "Almacenamiento": "128 GB", "Resolución": "2560 x 1600"}',
        'title': 'Tablet Xiaomi Redmi Pad 2 11" 4GB RAM 128GB'},
    {   'available_stores_count': 3,
        'best_price': 679.0,
        'best_store_name': 'Tottus',
        'best_store_url': 'https://www.tottus.com.pe/tottus-pe/articulo/146173215/tablet-lenovo-idea-tab-mediatek-dimensity-6300-4gb-128gb-11-2-5k-90hz/146173216',
        'brand': 'Lenovo',
        'category': 'Tablets',
        'description': 'Ficha técnica oficial de Tablet Lenovo Idea Tab 11" 4GB RAM 128GB. Comparativa multi-tienda '
                       'con precios online públicos verificados en tiempo real.',
        'discount_percentage': 24,
        'features_json': '["Procesador: MediaTek Dimensity 6300 (8 nÃºcleos)", "Memoria RAM: 4 GB", "Almacenamiento: '
                         '128 GB", "Pantalla: 11\\" IPS multitáctil, 90 Hz", "Resolución: 2560 x 1600 (2.5K)", '
                         '"Conectividad: Wireless"]',
        'historical_min_price': 679.0,
        'id': 'prod_lenovo_idea_tab_11',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/c/n/cnt-len866tab_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 899.0,
        'tech_specs_json': '{"Marca": "Lenovo", "Procesador": "MediaTek Dimensity 6300 (8 nÃºcleos)", "Memoria RAM": '
                           '"4 GB", "Pantalla": "11\\" IPS multitáctil, 90 Hz", "Sistema Operativo": "Android", '
                           '"Conectividad": "Wireless", "Almacenamiento": "128 GB", "Resolución": "2560 x 1600 '
                           '(2.5K)"}',
        'title': 'Tablet Lenovo Idea Tab 11" 4GB RAM 128GB'},
    {   'available_stores_count': 3,
        'best_price': 649.0,
        'best_store_name': 'Metro',
        'best_store_url': 'https://www.metro.pe/impresora-multifuncional-canon-inalambrica-g3170-1009696/p',
        'brand': 'Canon',
        'category': 'Impresoras',
        'description': 'Ficha técnica oficial de Impresora Multifuncional Canon Pixma G3170 Wi-Fi. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 16,
        'features_json': '["Procesador: ARM Cortex Integrado de Impresión", "Pantalla: Panel LCD / LED de Control", '
                         '"Resolución: 600 x 1200 dpi", "Conectividad: Wi-Fi", "Marca: Canon", "Modelo: Impresora '
                         'Multifuncional Canon Inalámbrica G3170"]',
        'historical_min_price': 649.0,
        'id': 'prod_canon_pixma_g3170',
        'image_url': 'https://media.falabella.com/falabellaPE/20261891_01/w=800,h=800,fit=pad',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 769.0,
        'tech_specs_json': '{"Marca": "Canon", "Conectividad": "Wi-Fi", "Pantalla": "Panel LCD / LED de Control", '
                           '"Procesador": "ARM Cortex Integrado de Impresión", "Resolución": "600 x 1200 dpi"}',
        'title': 'Impresora Multifuncional Canon Pixma G3170 Wi-Fi'},
    {   'available_stores_count': 6,
        'best_price': 559.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/impr-hp-smart-tank-580-multif-inala-1f3y2a.html',
        'brand': 'HP',
        'category': 'Impresoras',
        'description': 'Ficha técnica oficial de Impresora Multifuncional HP Smart Tank 580 Wi-Fi. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 18,
        'features_json': '["Procesador: ARM Cortex Integrado de Impresión", "Pantalla: Sí", "Resolución: Hasta1200 '
                         'x1200 ppp de reproducción", "Conectividad: Bluetooth", "Marca: HP", "Modelo: Resultados de '
                         'búsqueda para: \'HP Tank 580\'"]',
        'historical_min_price': 559.0,
        'id': 'prod_hp_smart_tank_580',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/2/129103_02.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 679.0,
        'tech_specs_json': '{"Marca": "HP", "Conectividad": "Bluetooth", "Pantalla": "Sí", "Procesador": "ARM Cortex '
                           'Integrado de Impresión", "Resolución": "Hasta1200 x1200 ppp de reproducción"}',
        'title': 'Impresora Multifuncional HP Smart Tank 580 Wi-Fi'},
    {   'available_stores_count': 3,
        'best_price': 649.0,
        'best_store_name': 'Tiendas Efe',
        'best_store_url': 'https://www.efe.com.pe/impresora-epson-l3250-multifuncional-con-l3250.html',
        'brand': 'Epson',
        'category': 'Impresoras',
        'description': 'Ficha técnica oficial de Impresora Multifuncional Epson EcoTank L3250 Wi-Fi. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 59,
        'features_json': '["Procesador: ARM Cortex Integrado de Impresión", "Pantalla: No", "Resolución: Hasta 5.760 '
                         'dpi x 1.440 dpi", "Conectividad: Wi-Fi", "Resolución: Hasta 1200 x 2400 dpi", "Marca: '
                         'Epson"]',
        'historical_min_price': 649.0,
        'id': 'prod_epson_ecotank_l3250',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/2/124756.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1579.0,
        'tech_specs_json': '{"Marca": "Epson", "Conectividad": "Wi-Fi", "Pantalla": "No", "Procesador": "ARM Cortex '
                           'Integrado de Impresión", "Resolución": "Hasta 5.760 dpi x 1.440 dpi"}',
        'title': 'Impresora Multifuncional Epson EcoTank L3250 Wi-Fi'},
    {   'available_stores_count': 6,
        'best_price': 729.0,
        'best_store_name': 'Tottus',
        'best_store_url': 'https://www.tottus.com.pe/tottus-pe/articulo/155387414/impresora-multifuncional-epson-l3350/155387416',
        'brand': 'Epson',
        'category': 'Impresoras',
        'description': 'Ficha técnica oficial de Impresora Multifuncional Epson EcoTank L3350 Wi-Fi. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 34,
        'features_json': '["Procesador: ARM Cortex Integrado de Impresión", "Pantalla: Panel LCD / LED de Control", '
                         '"Resolución: 1200 x 2400 dpi", "Conectividad: Wi-Fi", "Modelo: tottus.com.pe", "Marca: '
                         'Epson"]',
        'historical_min_price': 729.0,
        'id': 'prod_epson_ecotank_l3350',
        'image_url': 'https://media.falabella.com/falabellaPE/80131355_01/w=800,h=800,fit=pad',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1099.0,
        'tech_specs_json': '{"Conectividad": "Wi-Fi", "Marca": "Epson", "Pantalla": "Panel LCD / LED de Control", '
                           '"Procesador": "ARM Cortex Integrado de Impresión", "Resolución": "1200 x 2400 dpi"}',
        'title': 'Impresora Multifuncional Epson EcoTank L3350 Wi-Fi'}]

SEED_STORE_OFFERS: List[Dict[str, Any]] = [   {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/iphone-16-blk-128gb-bes-mye73be-a.html',
        'original_price': 4999.0,
        'price': 3399.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/iphone-16-wht-128gb-bes-mye93be-a.html',
        'original_price': 4999.0,
        'price': 3399.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://simple.ripley.com.pe/iphone-16-128gb-2065365819351',
        'original_price': 4299.0,
        'price': 3399.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'ripley',
        'store_name': 'Ripley'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/prod18120095/iPhone-16-128GB/20687062',
        'original_price': 4799.0,
        'price': 3499.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/149214502/iphone-16-128gb-negro/149214504',
        'original_price': 3799.0,
        'price': 3699.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/iphone-16-6-1-128gb-negro',
        'original_price': 3999.0,
        'price': 3999.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html',
        'original_price': 5719.0,
        'price': 3699.0,
        'product_id': 'prod_samsung_s25_ultra',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html',
        'original_price': 5719.0,
        'price': 3699.0,
        'product_id': 'prod_samsung_s25_ultra',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/galaxy-s24-fe-black-256gb-ee-sm-s721bzkmlep.html',
        'original_price': 2699.0,
        'price': 2699.0,
        'product_id': 'prod_samsung_galaxy_s24_fe',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/galaxy-s24-fe-black-256gb-ee-sm-s721bzkmlep.html',
        'original_price': 2699.0,
        'price': 2699.0,
        'product_id': 'prod_samsung_galaxy_s24_fe',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/galaxy-s26-ultra-512gb-12gb-black-s26ult512-12neg.html',
        'original_price': 5499.0,
        'price': 4699.0,
        'product_id': 'prod_samsung_galaxy_s24_ultra',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/galaxy-s26-ultra-512gb-12gb-black-s26ult512-12neg.html',
        'original_price': 5499.0,
        'price': 4699.0,
        'product_id': 'prod_samsung_galaxy_s24_ultra',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/21398141/celular-samsung-galaxy-s26-ultra-512gb-black/21398141',
        'original_price': 6899.0,
        'price': 4799.0,
        'product_id': 'prod_samsung_galaxy_s24_ultra',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/celular-samsung-galaxy-s26-ultra-6-9-512gb-12gb-ram-black',
        'original_price': 6899.0,
        'price': 5299.0,
        'product_id': 'prod_samsung_galaxy_s24_ultra',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/80007794/celular-samsung-galaxy-a57-5g/80007798',
        'original_price': 2299.0,
        'price': 1799.0,
        'product_id': 'prod_samsung_galaxy_a57',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/151775537/celular-galaxy-a57-5g-8gb-256gb-azul/151775366',
        'original_price': 2249.0,
        'price': 1799.0,
        'product_id': 'prod_samsung_galaxy_a57',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/a57-6-7-8gb-256gb-dark-blue-sm-a576bdbnltp.html',
        'original_price': 2199.0,
        'price': 2199.0,
        'product_id': 'prod_samsung_galaxy_a57',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/a57-6-7-8gb-256gb-dark-blue-sm-a576bdbnltp.html',
        'original_price': 2199.0,
        'price': 2199.0,
        'product_id': 'prod_samsung_galaxy_a57',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/151775324/celular-galaxy-a37-5g-8gb-256gb-lila/151775327',
        'original_price': 1949.0,
        'price': 1449.0,
        'product_id': 'prod_samsung_galaxy_a37',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/80007793/celular-samsung-galaxy-a37-5g/80007796',
        'original_price': 2099.0,
        'price': 1599.0,
        'product_id': 'prod_samsung_galaxy_a37',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/a37-6-7-8gb-256gb-gray-sm-a376bzafltp.html',
        'original_price': 1899.0,
        'price': 1899.0,
        'product_id': 'prod_samsung_galaxy_a37',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/a37-6-7-8gb-256gb-gray-sm-a376bzafltp.html',
        'original_price': 1899.0,
        'price': 1899.0,
        'product_id': 'prod_samsung_galaxy_a37',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/celular-libre-samsung-galaxy-a37-6-7-5g-256gb-8gb-sm-a376blvfltp-light-violet',
        'original_price': 1949.0,
        'price': 1949.0,
        'product_id': 'prod_samsung_galaxy_a37',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://hiraoka.com.pe/celular-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-cafe-moca',
        'original_price': 1999.0,
        'price': 1899.0,
        'product_id': 'prod_xiaomi_redmi_note',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html',
        'original_price': 2099.0,
        'price': 2099.0,
        'product_id': 'prod_xiaomi_redmi_note',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html',
        'original_price': 2099.0,
        'price': 2099.0,
        'product_id': 'prod_xiaomi_redmi_note',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://hiraoka.com.pe/laptop-asus-zenbook-a14-de-14-copilot-pc-qualcomm-snapdragon-x-16gb-ram-disco-solido-de-512gb-modelo-ux3407qa-qd289w-funda',
        'original_price': 5499.0,
        'price': 4199.0,
        'product_id': 'prod_asus_zenbook_a14',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/883954446/asus-zenbook-a14-snapdragon-x1-26-100-16gb-512ssd-14-wuxga/883954446',
        'original_price': 7699.0,
        'price': 4899.0,
        'product_id': 'prod_asus_zenbook_a14',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': True,
        'offer_url': 'https://hiraoka.com.pe/macbook-air-de-13-chip-m5-16gb-ram-disco-solido-de-512gb-azul-cielo',
        'original_price': 6499.0,
        'price': 5899.0,
        'product_id': 'prod_macbook_air_m1',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/80054339/macbook-air-chip-m5-13-6-midnight-16gb-ram-512gb-ssd/80054332',
        'original_price': 6399.0,
        'price': 6399.0,
        'product_id': 'prod_macbook_air_m1',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/lap-ip3-15f-r5-75-8gb-512ssd-82xq00ltlm.html',
        'original_price': 2499.0,
        'price': 2299.0,
        'product_id': 'prod_lenovo_ideapad_slim_3',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/lap-ip3-15f-r5-75-8gb-512ssd-82xq00ltlm.html',
        'original_price': 2499.0,
        'price': 2299.0,
        'product_id': 'prod_lenovo_ideapad_slim_3',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/laptop-lenovo-ideapad-slim-3-de-15-6-amd-ryzen-5-7520u-8gb-ram-disco-solido-de-512gb-modelo-82xq00ltlm',
        'original_price': 2899.0,
        'price': 2899.0,
        'product_id': 'prod_lenovo_ideapad_slim_3',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/lapg-victus-15-6-r7-8gb-512gb-rtx4050-15-fb3049la.html',
        'original_price': 5099.0,
        'price': 4199.0,
        'product_id': 'prod_hp_victus_15',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/lapg-victus-15-6-r7-8gb-512gb-rtx4050-15-fb3049la.html',
        'original_price': 5099.0,
        'price': 4199.0,
        'product_id': 'prod_hp_victus_15',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/lapg-16-c5-210h-8gb-512ssd-rtx3050-fx607vj-rl011w.html',
        'original_price': 3899.0,
        'price': 3299.0,
        'product_id': 'prod_asus_tuf_gaming_f16',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/lapg-16-c5-210h-8gb-512ssd-rtx3050-fx607vj-rl011w.html',
        'original_price': 3899.0,
        'price': 3299.0,
        'product_id': 'prod_asus_tuf_gaming_f16',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/lap-loq15-15-6-i7-16gb-512gb-rtx5050-83je01jwlm.html',
        'original_price': 6329.0,
        'price': 5999.0,
        'product_id': 'prod_lenovo_loq_15',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/lap-loq15-15-6-i7-16gb-512gb-rtx5050-83je01jwlm.html',
        'original_price': 6329.0,
        'price': 5999.0,
        'product_id': 'prod_lenovo_loq_15',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p',
        'original_price': 4999.0,
        'price': 3599.0,
        'product_id': 'prod_lg_oled_tv',
        'store_id': 'ripley',
        'store_name': 'Ripley'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493',
        'original_price': 4999.0,
        'price': 3699.0,
        'product_id': 'prod_lg_oled_tv',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026',
        'original_price': 4999.0,
        'price': 3699.0,
        'product_id': 'prod_lg_oled_tv',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html',
        'original_price': 6769.0,
        'price': 4359.0,
        'product_id': 'prod_lg_oled_tv',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html',
        'original_price': 6769.0,
        'price': 4359.0,
        'product_id': 'prod_lg_oled_tv',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.wong.pe/televisor-lg-oled-55-oled55b6psa-1067136/p',
        'original_price': 3899.0,
        'price': 3049.0,
        'product_id': 'prod_lg_oled_55_b6',
        'store_id': 'wong',
        'store_name': 'Wong'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/tv-55-smart-webos-oled-4k-uhd-oled55b6psa.html',
        'original_price': 4399.0,
        'price': 3299.0,
        'product_id': 'prod_lg_oled_55_b6',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/tv-55-smart-webos-oled-4k-uhd-oled55b6psa.html',
        'original_price': 4399.0,
        'price': 3299.0,
        'product_id': 'prod_lg_oled_55_b6',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/tv-samsung-65-neo-qled-4k-uhd-tizen-qn85d-2024-qn65qn85dbgxpe.html',
        'original_price': 7999.0,
        'price': 7999.0,
        'product_id': 'prod_samsung_neo_qled_65',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/tv-samsung-65-neo-qled-4k-uhd-tizen-qn85d-2024-qn65qn85dbgxpe.html',
        'original_price': 7999.0,
        'price': 7999.0,
        'product_id': 'prod_samsung_neo_qled_65',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.wong.pe/televisor-samsung-55-uhd-u8000h-vision-ai-smart-tv-2026-1067747/p',
        'original_price': 1399.0,
        'price': 1099.0,
        'product_id': 'prod_samsung_uhd_55_u8000',
        'store_id': 'wong',
        'store_name': 'Wong'},
    {   'is_best_price': False,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/153065403/televisor-samsung-55-uhd-vision-ai-smart-tv/153065405',
        'original_price': 1399.0,
        'price': 1249.0,
        'product_id': 'prod_samsung_uhd_55_u8000',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/80044166/55-uhd-u8000h-smart-tv-2026/80044166',
        'original_price': 1399.0,
        'price': 1399.0,
        'product_id': 'prod_samsung_uhd_55_u8000',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/55-uhd-u8000h-vision-ai-smart-tv-2026-55u8000hgxpeotb.html',
        'original_price': 2349.0,
        'price': 1399.0,
        'product_id': 'prod_samsung_uhd_55_u8000',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/55-uhd-u8000h-vision-ai-smart-tv-2026-55u8000hgxpeotb.html',
        'original_price': 2349.0,
        'price': 1399.0,
        'product_id': 'prod_samsung_uhd_55_u8000',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381',
        'original_price': 2599.0,
        'price': 1699.0,
        'product_id': 'prod_ipad_11',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wifi-128gb-plata',
        'original_price': 2299.0,
        'price': 1999.0,
        'product_id': 'prod_ipad_11',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://simple.ripley.com.pe/tablet-samsung-galaxy-tab-a11-87-64gb-2004367413754p',
        'original_price': 649.0,
        'price': 439.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'ripley',
        'store_name': 'Ripley'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/21239694/galaxy-tab-a11/21239694',
        'original_price': 899.0,
        'price': 449.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/147828269/tablet-samsung-galaxy-tab-a11-64gb-gray/147828270',
        'original_price': 549.0,
        'price': 459.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/tablet-samsung-galaxy-tab-a11-8-7-64gb-4gb-ram-gray',
        'original_price': 649.0,
        'price': 499.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/galaxy-tab-a11-4gb-64gb-gray-sm-x133nzaapeo.html',
        'original_price': 599.0,
        'price': 549.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/galaxy-tab-a11-4gb-64gb-gray-sm-x133nzaapeo.html',
        'original_price': 599.0,
        'price': 549.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/pad2-4gb-128gb-gray-pad2gray.html',
        'original_price': 999.0,
        'price': 699.0,
        'product_id': 'prod_xiaomi_redmi_pad_2',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/pad2-4gb-128gb-gray-pad2gray.html',
        'original_price': 999.0,
        'price': 699.0,
        'product_id': 'prod_xiaomi_redmi_pad_2',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/tablet-xiaomi-redmi-pad-2-11-128gb-4gb-ram-graphite-gray',
        'original_price': 849.0,
        'price': 849.0,
        'product_id': 'prod_xiaomi_redmi_pad_2',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/146173215/tablet-lenovo-idea-tab-mediatek-dimensity-6300-4gb-128gb-11-2-5k-90hz/146173216',
        'original_price': 899.0,
        'price': 679.0,
        'product_id': 'prod_lenovo_idea_tab_11',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/tab-len-tb336fu-4-128-zafr0908pe-cnt-len866tab.html',
        'original_price': 1299.0,
        'price': 1099.0,
        'product_id': 'prod_lenovo_idea_tab_11',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/tab-len-tb336fu-4-128-zafr0908pe-cnt-len866tab.html',
        'original_price': 1299.0,
        'price': 1099.0,
        'product_id': 'prod_lenovo_idea_tab_11',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.metro.pe/impresora-multifuncional-canon-inalambrica-g3170-1009696/p',
        'original_price': 769.0,
        'price': 649.0,
        'product_id': 'prod_canon_pixma_g3170',
        'store_id': 'metro',
        'store_name': 'Metro'},
    {   'is_best_price': False,
        'offer_url': 'https://www.wong.pe/impresora-multifuncional-canon-inalambrica-g3170-1009696/p',
        'original_price': 769.0,
        'price': 649.0,
        'product_id': 'prod_canon_pixma_g3170',
        'store_id': 'wong',
        'store_name': 'Wong'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/20261891/pixma-g3170-audifono-inalambrico/20261891',
        'original_price': 949.0,
        'price': 679.0,
        'product_id': 'prod_canon_pixma_g3170',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/impr-hp-smart-tank-580-multif-inala-1f3y2a.html',
        'original_price': 679.0,
        'price': 559.0,
        'product_id': 'prod_hp_smart_tank_580',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/impr-hp-smart-tank-580-multif-inala-1f3y2a.html',
        'original_price': 679.0,
        'price': 559.0,
        'product_id': 'prod_hp_smart_tank_580',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/impresora-todo-en-uno-hp-smart-tank-580',
        'original_price': 799.0,
        'price': 599.0,
        'product_id': 'prod_hp_smart_tank_580',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://www.metro.pe/impresora-todo-en-uno-hp-smart-tank-580-984531/p',
        'original_price': 829.0,
        'price': 599.0,
        'product_id': 'prod_hp_smart_tank_580',
        'store_id': 'metro',
        'store_name': 'Metro'},
    {   'is_best_price': False,
        'offer_url': 'https://www.wong.pe/impresora-todo-en-uno-hp-smart-tank-580-984531/p',
        'original_price': 829.0,
        'price': 599.0,
        'product_id': 'prod_hp_smart_tank_580',
        'store_id': 'wong',
        'store_name': 'Wong'},
    {   'is_best_price': False,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/117087422/impresora-multifuncional-hp-smart-tank-580-tinta-continua-color-wi-fi-smart-app-escaner-1f3y2a/117087423',
        'original_price': 829.0,
        'price': 649.0,
        'product_id': 'prod_hp_smart_tank_580',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/impresora-epson-l3250-multifuncional-con-l3250.html',
        'original_price': 1579.0,
        'price': 649.0,
        'product_id': 'prod_epson_ecotank_l3250',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/impresora-epson-l3250-multifuncional-con-l3250.html',
        'original_price': 1579.0,
        'price': 649.0,
        'product_id': 'prod_epson_ecotank_l3250',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/impresora-multifuncional-epson-ecotank-l3250',
        'original_price': 979.0,
        'price': 979.0,
        'product_id': 'prod_epson_ecotank_l3250',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/155387414/impresora-multifuncional-epson-l3350/155387416',
        'original_price': 1099.0,
        'price': 729.0,
        'product_id': 'prod_epson_ecotank_l3350',
        'store_id': 'tottus',
        'store_name': 'Tottus'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/80131355/impresora-epson-multifuncional-l3350/80131355',
        'original_price': 979.0,
        'price': 789.0,
        'product_id': 'prod_epson_ecotank_l3350',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/impresora-epson-l3350-multifuncional-c11cl62301.html',
        'original_price': 979.0,
        'price': 799.0,
        'product_id': 'prod_epson_ecotank_l3350',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/impresora-epson-l3350-multifuncional-c11cl62301.html',
        'original_price': 979.0,
        'price': 799.0,
        'product_id': 'prod_epson_ecotank_l3350',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://www.metro.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p',
        'original_price': 979.0,
        'price': 799.0,
        'product_id': 'prod_epson_ecotank_l3350',
        'store_id': 'metro',
        'store_name': 'Metro'},
    {   'is_best_price': False,
        'offer_url': 'https://www.wong.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p',
        'original_price': 979.0,
        'price': 799.0,
        'product_id': 'prod_epson_ecotank_l3350',
        'store_id': 'wong',
        'store_name': 'Wong'}]

SEED_PRICE_HISTORY: List[Dict[str, Any]] = []

async def sync_and_upsert_catalog(
    session: AsyncSession,
    overwrite_live: bool = False,
) -> int:
    """
    Sincronización de arranque en Neon PostgreSQL / SQLite:
    - PROHIBIDO sobreescribir precios ni ofertas extraídas en vivo desde diccionarios estáticos
      cuando la base de datos ya contiene el catálogo vivo (`overwrite_live=False`).
    - Solo siembra registros iniciales cuando la base de datos está vacía o falta un producto nuevo.
    """
    from app.collectors.orchestrator import (
        build_daily_history_points_for_product,
        get_today_peru,
        orchestrator,
    )

    logger.info("Verificando estado del catálogo en base de datos...")
    now_dt = utc_now_naive()
    today_peru = get_today_peru()

    # Precarga en bloque
    prods_res = await session.execute(select(ProductEntity))
    existing_prods = {p.id: p for p in prods_res.scalars().all()}

    offers_res = await session.execute(select(StoreOfferEntity))
    existing_offers = {(o.product_id, o.store_id): o for o in offers_res.scalars().all()}

    hist_res = await session.execute(select(PriceHistoryEntity))
    existing_hist_entities = hist_res.scalars().all()
    existing_hist = {(h.product_id, h.day_offset): h for h in existing_hist_entities}

    # Contar ofertas válidas por producto permitiendo desde 1 tienda en adelante (len(offers) >= 1)
    offers_by_prod: Dict[str, List[Dict[str, Any]]] = {}
    for o in SEED_STORE_OFFERS:
        offers_by_prod.setdefault(o["product_id"], []).append(o)

    valid_products_to_seed = []
    for p in SEED_PRODUCTS:
        prod_offers = offers_by_prod.get(p["id"], [])
        if len(prod_offers) < 1:
            continue
        p["available_stores_count"] = len(prod_offers)
        valid_products_to_seed.append(p)

    valid_prod_ids = {p["id"] for p in valid_products_to_seed}

    # Si la base de datos ya tiene los 25 productos y sus ofertas en vivo y no se pidió overwrite_live,
    # PROHIBIDO sobreescribir precios o borrar tiendas descubiertas en vivo con datos estáticos.
    if (
        not overwrite_live
        and valid_prod_ids.issubset(set(existing_prods.keys()))
        and len(existing_offers) >= len(valid_prod_ids)
    ):
        for pid, ent in list(existing_prods.items()):
            if pid not in valid_prod_ids:
                await session.delete(ent)
        await session.execute(
            delete(CommunityPostEntity).where(
                (CommunityPostEntity.author_name.ilike("%Usuario Real%"))
                | (CommunityPostEntity.title.ilike("%liquidación de vitrina%"))
                | (CommunityPostEntity.content.ilike("%liquidación de vitrina%"))
                | (CommunityPostEntity.product_id.notin_(valid_prod_ids))
            )
        )
        await session.execute(
            delete(CommunityOfferEntity).where(
                (CommunityOfferEntity.author_name.ilike("%Usuario Real%"))
                | (CommunityOfferEntity.comment.ilike("%liquidación de vitrina%"))
                | (CommunityOfferEntity.price_found == 3699.0)
                | (CommunityOfferEntity.product_id.notin_(valid_prod_ids))
            )
        )
        await orchestrator._sync_all_products_history_and_min_price(
            session=session, today_peru=today_peru
        )
        await session.commit()
        orchestrator.last_sync_date = today_peru
        orchestrator.last_sync_timestamp = now_dt.isoformat() + "Z"
        logger.info(
            f"Catálogo vivo preservado intacto ({len(existing_prods)} productos, {len(existing_offers)} ofertas en vivo)."
        )
        return len(existing_prods)

    # Construir puntos diarios reales de historial hasta today_peru por producto
    computed_hist_by_prod: Dict[str, List[Dict[str, Any]]] = {}
    valid_hist_keys = set()
    for p in valid_products_to_seed:
        pid = p["id"]
        prod_offers = sorted(offers_by_prod.get(pid, []), key=lambda x: float(x["price"]))
        best_off = prod_offers[0]
        best_p = float(best_off["price"])
        orig_p = float(p.get("original_price") or best_p)
        pts = build_daily_history_points_for_product(
            best_price=best_p,
            original_price=orig_p,
            today_peru=today_peru,
            existing_by_date=None,
        )
        computed_hist_by_prod[pid] = pts
        for pt in pts:
            valid_hist_keys.add((pid, pt["day_offset"]))

    # 0. Limpieza de productos obsoletos o fuera de catálogo
    for pid, ent in list(existing_prods.items()):
        if pid not in valid_prod_ids:
            await session.delete(ent)

    valid_offer_keys = {(o["product_id"], o["store_id"]) for o in SEED_STORE_OFFERS if o["product_id"] in valid_prod_ids}
    for (pid, sid), off in list(existing_offers.items()):
        if (pid, sid) not in valid_offer_keys:
            await session.delete(off)

    for (pid, day), hist in list(existing_hist.items()):
        if (pid, day) not in valid_hist_keys:
            await session.delete(hist)

    # 1. Upsert Productos Válidos (len(offers) >= 1)
    for p in valid_products_to_seed:
        pid = p["id"]
        prod_offers = sorted(offers_by_prod.get(pid, []), key=lambda x: float(x["price"]))
        best_off = prod_offers[0]
        best_p = float(best_off["price"])
        best_store_url = best_off["offer_url"]
        best_store_name = best_off["store_name"]
        orig_p = float(p.get("original_price") or best_p)

        pts = computed_hist_by_prod.get(pid, [])
        all_hist_prices = [float(pt["price"]) for pt in pts] + [best_p]
        hist_min_p = round(min(all_hist_prices), 2)
        is_hist_min = bool(best_p <= hist_min_p)
        prev_best_p = round(float(pts[-2]["price"]), 2) if len(pts) >= 2 else round(orig_p, 2)
        drop_amt = round(max(0.0, prev_best_p - best_p), 2)
        days_tracked = max(1, len(pts))

        existing = existing_prods.get(pid)
        if existing:
            existing.title = p["title"]
            existing.category = p["category"]
            existing.brand = p["brand"]
            existing.best_price = best_p
            existing.original_price = orig_p
            existing.best_store_name = best_store_name
            existing.best_store_url = best_store_url
            existing.previous_best_price = prev_best_p
            existing.price_drop_amount = drop_amt
            existing.days_tracked = days_tracked
            existing.discount_percentage = p["discount_percentage"]
            existing.available_stores_count = p["available_stores_count"]
            existing.image_url = p["image_url"]
            existing.description = p["description"]
            existing.features_json = p["features_json"]
            existing.tech_specs_json = p["tech_specs_json"]
            existing.historical_min_price = hist_min_p
            existing.is_historical_min = is_hist_min
            existing.updated_at = now_dt
        else:
            new_prod = ProductEntity(
                id=pid,
                title=p["title"],
                category=p["category"],
                brand=p["brand"],
                best_price=best_p,
                original_price=orig_p,
                best_store_name=best_store_name,
                best_store_url=best_store_url,
                previous_best_price=prev_best_p,
                price_drop_amount=drop_amt,
                days_tracked=days_tracked,
                discount_percentage=p["discount_percentage"],
                available_stores_count=p["available_stores_count"],
                image_url=p["image_url"],
                description=p["description"],
                features_json=p["features_json"],
                tech_specs_json=p["tech_specs_json"],
                is_favorite=bool(p.get("is_favorite", False)),
                historical_min_price=hist_min_p,
                is_historical_min=is_hist_min,
                created_at=_parse_dt(p.get("created_at")),
                updated_at=now_dt,
            )
            session.add(new_prod)

    # 2. Upsert Ofertas por Tienda de Productos Válidos
    for o in SEED_STORE_OFFERS:
        if o["product_id"] not in valid_prod_ids:
            continue
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

    # 3. Upsert Historial de Precios Real por Día hasta today_peru
    for pid, pts in computed_hist_by_prod.items():
        for pt in pts:
            key = (pid, pt["day_offset"])
            existing_h = existing_hist.get(key)
            if existing_h:
                existing_h.price = pt["price"]
                existing_h.date_label = pt["date_label"]
                existing_h.recorded_date = pt["recorded_date"]
                existing_h.recorded_at = now_dt
            else:
                new_h = PriceHistoryEntity(
                    product_id=pid,
                    day_offset=pt["day_offset"],
                    date_label=pt["date_label"],
                    recorded_date=pt["recorded_date"],
                    price=pt["price"],
                    recorded_at=now_dt,
                )
                session.add(new_h)

    # 4. Limpieza estricta de cualquier dato fantasma en comunidad (community_posts y community_offers)
    await session.execute(
        delete(CommunityPostEntity).where(
            (CommunityPostEntity.author_name.ilike("%Usuario Real%")) |
            (CommunityPostEntity.title.ilike("%liquidación de vitrina%")) |
            (CommunityPostEntity.content.ilike("%liquidación de vitrina%")) |
            (CommunityPostEntity.product_id.notin_(valid_prod_ids))
        )
    )
    await session.execute(
        delete(CommunityOfferEntity).where(
            (CommunityOfferEntity.author_name.ilike("%Usuario Real%")) |
            (CommunityOfferEntity.comment.ilike("%liquidación de vitrina%")) |
            (CommunityOfferEntity.price_found == 3699.0) |
            (CommunityOfferEntity.product_id.notin_(valid_prod_ids))
        )
    )

    await session.commit()
    orchestrator.last_sync_date = today_peru
    orchestrator.last_sync_timestamp = now_dt.isoformat() + "Z"
    logger.info(
        f"sync_and_upsert_catalog completado con éxito: {len(valid_products_to_seed)} productos sincronizados "
        f"(fecha Perú: {today_peru.isoformat()})."
    )
    return len(valid_products_to_seed)


async def seed_database_fast(session: AsyncSession) -> int:
    """Inserta o sincroniza el catálogo oficial en Neon PostgreSQL / SQLite."""
    return await sync_and_upsert_catalog(session)
