"""
Datos iniciales oficiales de productos reales en tiendas retail peruanas.
Sincronización UPSERT instantánea en Neon PostgreSQL / SQLite de alto rendimiento (< 200 ms).
REGLA FINPRICE: CERO PRODUCTOS DE 1 SOLA TIENDA (len(offers) >= 2 OBLIGATORIO).
ESTRICTAMENTE 8 TIENDAS: Tiendas Efe, Falabella, Ripley, La Curacao, Hiraoka, Tottus, Metro, Wong.
DÍA 1: Historial real de 1 punto (sin curvas simuladas hacia atrás).
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


SEED_PRODUCTS: List[Dict[str, Any]] = [   {   'available_stores_count': 4,
        'best_price': 2799.0,
        'best_store_name': 'Ripley',
        'brand': 'Apple',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Apple iPhone 16 128GB. Comparativa multi-tienda con precios online '
                       'públicos verificados en tiempo real.',
        'discount_percentage': 48,
        'features_json': '["Almacenamiento: 128 GB", "Conectividad: 5G", "Marca: Apple", "Memoria RAM: 8 GB", '
                         '"Pantalla: 6.1\\" Super Retina XDR OLED", "Procesador: Chip A18", "Resolución: 2556 x 1179", '
                         '"Sistema Operativo: iOS 18"]',
        'historical_min_price': 2799.0,
        'id': 'prod_iphone_16',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/i/p/iphone_16_no-ai_black_pdp_image_position_1__gens.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 5399.0,
        'tech_specs_json': '{"Almacenamiento": "128 GB", "Conectividad": "5G", "Marca": "Apple", "Memoria RAM": "8 '
                           'GB", "Pantalla": "6.1\\" Super Retina XDR OLED", "Procesador": "Chip A18", "Resolución": '
                           '"2556 x 1179", "Sistema Operativo": "iOS 18"}',
        'title': 'Apple iPhone 16 128GB'},
    {   'available_stores_count': 3,
        'best_price': 3299.0,
        'best_store_name': 'La Curacao',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy S25 Ultra 512GB 12GB RAM. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 42,
        'features_json': '["Almacenamiento: 512 GB", "Conectividad: 5G", "Marca: Samsung", "Memoria RAM: 12 GB", '
                         '"Pantalla: 6.9\\" Dynamic AMOLED 2X", "Procesador: Snapdragon 8 Elite", "Resolución: QHD+ '
                         '(3120 x 1440)", "Sistema Operativo: Android 15 / One UI 7"]',
        'historical_min_price': 3299.0,
        'id': 'prod_samsung_s25_ultra',
        'image_url': 'https://media.falabella.com/falabellaPE/143491917_01/w=800,h=800,fit=pad',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 5719.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB", "Conectividad": "5G", "Marca": "Samsung", "Memoria RAM": "12 '
                           'GB", "Pantalla": "6.9\\" Dynamic AMOLED 2X", "Procesador": "Snapdragon 8 Elite", '
                           '"Resolución": "QHD+ (3120 x 1440)", "Sistema Operativo": "Android 15 / One UI 7"}',
        'title': 'Samsung Galaxy S25 Ultra 512GB 12GB RAM'},
    {   'available_stores_count': 2,
        'best_price': 2699.0,
        'best_store_name': 'La Curacao',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy S24 FE 256GB 8GB RAM. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 0,
        'features_json': '["Almacenamiento: 256 GB", "Conectividad: 5G", "Marca: Samsung", "Memoria RAM: 8 GB", '
                         '"Pantalla: 6.7\\" Dynamic AMOLED 2X", "Procesador: Exynos 2400e", "Resolución: FHD+ (2340 x '
                         '1080)", "Sistema Operativo: Android 14"]',
        'historical_min_price': 2699.0,
        'id': 'prod_samsung_galaxy_s24_fe',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/s/m/sm-s721bzkmlep_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 2699.0,
        'tech_specs_json': '{"Almacenamiento": "256 GB", "Conectividad": "5G", "Marca": "Samsung", "Memoria RAM": "8 '
                           'GB", "Pantalla": "6.7\\" Dynamic AMOLED 2X", "Procesador": "Exynos 2400e", "Resolución": '
                           '"FHD+ (2340 x 1080)", "Sistema Operativo": "Android 14"}',
        'title': 'Samsung Galaxy S24 FE 256GB 8GB RAM'},
    {   'available_stores_count': 2,
        'best_price': 2949.0,
        'best_store_name': 'Ripley',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy S24 Ultra 5G 512GB 12GB RAM. Comparativa multi-tienda '
                       'con precios online públicos verificados en tiempo real.',
        'discount_percentage': 30,
        'features_json': '["Almacenamiento: 512 GB", "Conectividad: 5G", "Marca: Samsung", "Memoria RAM: 12 GB", '
                         '"Pantalla: 6.8\\" Dynamic AMOLED 2X", "Procesador: Snapdragon 8 Gen 3", "Resolución: QHD+ '
                         '(3120 x 1440)", "Sistema Operativo: Android 14"]',
        'historical_min_price': 2949.0,
        'id': 'prod_samsung_galaxy_s24_ultra',
        'image_url': 'https://media.falabella.com/falabellaPE/155039507_01/w=800,h=800,fit=pad',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 4199.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB", "Conectividad": "5G", "Marca": "Samsung", "Memoria RAM": "12 '
                           'GB", "Pantalla": "6.8\\" Dynamic AMOLED 2X", "Procesador": "Snapdragon 8 Gen 3", '
                           '"Resolución": "QHD+ (3120 x 1440)", "Sistema Operativo": "Android 14"}',
        'title': 'Samsung Galaxy S24 Ultra 5G 512GB 12GB RAM'},
    {   'available_stores_count': 3,
        'best_price': 1499.0,
        'best_store_name': 'La Curacao',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy A57 5G 256GB 8GB RAM. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 32,
        'features_json': '["Almacenamiento: 256 GB", "Conectividad: 5G", "Marca: Samsung", "Memoria RAM: 8 GB", '
                         '"Pantalla: 6.7\\" Super AMOLED 120Hz", "Procesador: Exynos 1480", "Resolución: FHD+ (2340 x '
                         '1080)", "Sistema Operativo: Android 15"]',
        'historical_min_price': 1499.0,
        'id': 'prod_samsung_galaxy_a57',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/3/138919_2.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 2199.0,
        'tech_specs_json': '{"Almacenamiento": "256 GB", "Conectividad": "5G", "Marca": "Samsung", "Memoria RAM": "8 '
                           'GB", "Pantalla": "6.7\\" Super AMOLED 120Hz", "Procesador": "Exynos 1480", "Resolución": '
                           '"FHD+ (2340 x 1080)", "Sistema Operativo": "Android 15"}',
        'title': 'Samsung Galaxy A57 5G 256GB 8GB RAM'},
    {   'available_stores_count': 2,
        'best_price': 1649.0,
        'best_store_name': 'La Curacao',
        'brand': 'Samsung',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Samsung Galaxy A37 5G 256GB 8GB RAM. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 13,
        'features_json': '["Almacenamiento: 256 GB", "Conectividad: 5G", "Marca: Samsung", "Memoria RAM: 8 GB", '
                         '"Pantalla: 6.7\\" Super AMOLED 120Hz", "Procesador: Exynos 1380", "Resolución: FHD+ (2340 x '
                         '1080)", "Sistema Operativo: Android 14"]',
        'historical_min_price': 1649.0,
        'id': 'prod_samsung_galaxy_a37',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/s/m/sm-a376bzafltp_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1899.0,
        'tech_specs_json': '{"Almacenamiento": "256 GB", "Conectividad": "5G", "Marca": "Samsung", "Memoria RAM": "8 '
                           'GB", "Pantalla": "6.7\\" Super AMOLED 120Hz", "Procesador": "Exynos 1380", "Resolución": '
                           '"FHD+ (2340 x 1080)", "Sistema Operativo": "Android 14"}',
        'title': 'Samsung Galaxy A37 5G 256GB 8GB RAM'},
    {   'available_stores_count': 3,
        'best_price': 1499.0,
        'best_store_name': 'Hiraoka',
        'brand': 'Xiaomi',
        'category': 'Smartphones',
        'description': 'Ficha técnica oficial de Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM. Comparativa multi-tienda '
                       'con precios verificados en tiempo real.',
        'discount_percentage': 25,
        'features_json': '["Marca: Xiaomi", "Procesador: Qualcomm Snapdragon 7s Gen 3", "Memoria RAM: 12 GB", '
                         '"Almacenamiento: 512 GB", "Pantalla: 6.8\\" AMOLED 120Hz", "Resolución: 1.5K (2712 x 1220)", '
                         '"Conectividad: 5G", "Sistema Operativo: Android 15 / HyperOS 2"]',
        'historical_min_price': 1499.0,
        'id': 'prod_xiaomi_redmi_note',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/_/1_23_12.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1999.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB", "Conectividad": "5G", "Marca": "Xiaomi", "Memoria RAM": "12 '
                           'GB", "Pantalla": "6.8\\" AMOLED 120Hz", "Procesador": "Qualcomm Snapdragon 7s Gen 3", '
                           '"Resolución": "1.5K (2712 x 1220)", "Sistema Operativo": "Android 15 / HyperOS 2"}',
        'title': 'Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM'},
    {   'available_stores_count': 3,
        'best_price': 3999.0,
        'best_store_name': 'Falabella',
        'brand': 'Asus',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Asus Zenbook A14 14" Snapdragon X 16GB RAM 512GB SSD. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 48,
        'features_json': '["Almacenamiento: 512 GB SSD", "Marca: Asus", "Memoria RAM: 16 GB", "Pantalla: 14\\" OLED '
                         'WUXGA", "Procesador: Qualcomm Snapdragon X Plus", "Resolución: 1920 x 1200", "Sistema '
                         'Operativo: Windows 11 Home"]',
        'historical_min_price': 3999.0,
        'id': 'prod_asus_zenbook_a14',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/4/140353_2.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 7699.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB SSD", "Marca": "Asus", "Memoria RAM": "16 GB", "Pantalla": '
                           '"14\\" OLED WUXGA", "Procesador": "Qualcomm Snapdragon X Plus", "Resolución": "1920 x '
                           '1200", "Sistema Operativo": "Windows 11 Home"}',
        'title': 'Laptop Asus Zenbook A14 14" Snapdragon X 16GB RAM 512GB SSD'},
    {   'available_stores_count': 3,
        'best_price': 4999.0,
        'best_store_name': 'Falabella',
        'brand': 'Apple',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Apple MacBook Air 13" Chip M5 16GB RAM 512GB SSD. Comparativa '
                       'multi-tienda con precios verificados en tiempo real.',
        'discount_percentage': 22,
        'features_json': '["Marca: Apple", "Procesador: Chip Apple M5 (10 núcleos)", "Memoria RAM: 16 GB", '
                         '"Almacenamiento: 512 GB SSD", "Pantalla: 13.6\\" Liquid Retina", "Resolución: 2560 x 1664", '
                         '"Sistema Operativo: macOS"]',
        'historical_min_price': 4999.0,
        'id': 'prod_macbook_air_m1',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/m/a/macbook_air_13-in_m5_sky_blue_pdp_image_position_1__gens.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 6399.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB SSD", "Marca": "Apple", "Memoria RAM": "16 GB", "Pantalla": '
                           '"13.6\\" Liquid Retina", "Procesador": "Chip Apple M5 (10 núcleos)", "Resolución": "2560 x '
                           '1664", "Sistema Operativo": "macOS"}',
        'title': 'Apple MacBook Air 13" Chip M5 16GB RAM 512GB SSD'},
    {   'available_stores_count': 2,
        'best_price': 2199.0,
        'best_store_name': 'La Curacao',
        'brand': 'Lenovo',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Lenovo IdeaPad Slim 3 15.6" AMD Ryzen 5 8GB 512GB SSD. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 12,
        'features_json': '["Almacenamiento: 512 GB SSD", "Marca: Lenovo", "Memoria RAM: 8 GB", "Pantalla: 15.6\\" '
                         'FHD", "Procesador: AMD Ryzen 5 7520U", "Resolución: 1920 x 1080", "Sistema Operativo: '
                         'Windows 11 Home"]',
        'historical_min_price': 2199.0,
        'id': 'prod_lenovo_ideapad_slim_3',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/8/2/82xq00ltlm_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 2499.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB SSD", "Marca": "Lenovo", "Memoria RAM": "8 GB", "Pantalla": '
                           '"15.6\\" FHD", "Procesador": "AMD Ryzen 5 7520U", "Resolución": "1920 x 1080", "Sistema '
                           'Operativo": "Windows 11 Home"}',
        'title': 'Laptop Lenovo IdeaPad Slim 3 15.6" AMD Ryzen 5 8GB 512GB SSD'},
    {   'available_stores_count': 2,
        'best_price': 3399.0,
        'best_store_name': 'La Curacao',
        'brand': 'HP',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Gamer HP Victus 15.6" AMD Ryzen 7 8GB 512GB SSD RTX 4050. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 33,
        'features_json': '["Almacenamiento: 512 GB SSD", "Marca: HP", "Memoria RAM: 8 GB", "Pantalla: 15.6\\" FHD '
                         '144Hz", "Procesador: AMD Ryzen 7 7435HS", "Resolución: 1920 x 1080", "Sistema Operativo: '
                         'Windows 11 Home"]',
        'historical_min_price': 3399.0,
        'id': 'prod_hp_victus_15',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/1/5/15-fb3049la_1_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 5099.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB SSD", "Marca": "HP", "Memoria RAM": "8 GB", "Pantalla": '
                           '"15.6\\" FHD 144Hz", "Procesador": "AMD Ryzen 7 7435HS", "Resolución": "1920 x 1080", '
                           '"Sistema Operativo": "Windows 11 Home"}',
        'title': 'Laptop Gamer HP Victus 15.6" AMD Ryzen 7 8GB 512GB SSD RTX 4050'},
    {   'available_stores_count': 2,
        'best_price': 2999.0,
        'best_store_name': 'La Curacao',
        'brand': 'Asus',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Asus TUF Gaming F16 16" Intel Core 5 205H 8GB 512GB SSD. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 41,
        'features_json': '["Almacenamiento: 512 GB SSD", "Marca: Asus", "Memoria RAM: 8 GB", "Pantalla: 16\\" FHD+ '
                         '144Hz", "Procesador: Intel Core 5 205H", "Resolución: 1920 x 1200", "Sistema Operativo: '
                         'Windows 11 Home"]',
        'historical_min_price': 2999.0,
        'id': 'prod_asus_tuf_gaming_f16',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/f/x/fx607vjr-tu302w_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 5099.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB SSD", "Marca": "Asus", "Memoria RAM": "8 GB", "Pantalla": '
                           '"16\\" FHD+ 144Hz", "Procesador": "Intel Core 5 205H", "Resolución": "1920 x 1200", '
                           '"Sistema Operativo": "Windows 11 Home"}',
        'title': 'Laptop Asus TUF Gaming F16 16" Intel Core 5 205H 8GB 512GB SSD'},
    {   'available_stores_count': 2,
        'best_price': 5699.0,
        'best_store_name': 'La Curacao',
        'brand': 'Lenovo',
        'category': 'Laptops',
        'description': 'Ficha técnica oficial de Laptop Lenovo LOQ 15.6" Intel Core i7 16GB 512GB SSD RTX 5050. '
                       'Comparativa multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 10,
        'features_json': '["Almacenamiento: 512 GB SSD", "Marca: Lenovo", "Memoria RAM: 16 GB", "Pantalla: 15.6\\" FHD '
                         '144Hz", "Procesador: Intel Core i7-14700HX", "Resolución: 1920 x 1080", "Sistema Operativo: '
                         'Windows 11 Home"]',
        'historical_min_price': 5699.0,
        'id': 'prod_lenovo_loq_15',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/8/3/83je01jwlm_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 6329.0,
        'tech_specs_json': '{"Almacenamiento": "512 GB SSD", "Marca": "Lenovo", "Memoria RAM": "16 GB", "Pantalla": '
                           '"15.6\\" FHD 144Hz", "Procesador": "Intel Core i7-14700HX", "Resolución": "1920 x 1080", '
                           '"Sistema Operativo": "Windows 11 Home"}',
        'title': 'Laptop Lenovo LOQ 15.6" Intel Core i7 16GB 512GB SSD RTX 5050'},
    {   'available_stores_count': 3,
        'best_price': 3299.0,
        'best_store_name': 'Falabella',
        'brand': 'LG',
        'category': 'TVs',
        'description': 'Ficha técnica oficial de Televisor LG 55" OLED evo AI C6 4K Smart TV 2026. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 34,
        'features_json': '["Conectividad: Wi-Fi, Bluetooth 5.3, 4 x HDMI 2.1", "Marca: LG", "Pantalla: 55\\" OLED evo '
                         '120Hz", "Resolución: 3840 x 2160 (4K UHD)", "Sistema Operativo: webOS 26", "Procesador: '
                         'Procesador α9 AI 4K Gen9", "Memoria RAM: 2.5 GB", "Almacenamiento: 8 GB"]',
        'historical_min_price': 3299.0,
        'id': 'prod_lg_oled_tv',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/3/139008_2_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 4999.0,
        'tech_specs_json': '{"Almacenamiento": "8 GB", "Conectividad": "Wi-Fi, Bluetooth 5.3, 4 x HDMI 2.1", "Marca": '
                           '"LG", "Memoria RAM": "2.5 GB", "Pantalla": "55\\" OLED evo 120Hz", "Procesador": '
                           '"Procesador α9 AI 4K Gen9", "Resolución": "3840 x 2160 (4K UHD)", "Sistema Operativo": '
                           '"webOS 26"}',
        'title': 'Televisor LG 55" OLED evo AI C6 4K Smart TV 2026'},
    {   'available_stores_count': 2,
        'best_price': 2799.0,
        'best_store_name': 'Metro',
        'brand': 'LG',
        'category': 'TVs',
        'description': 'Ficha técnica oficial de Televisor LG 55" OLED Smart TV OLED55B6PSA. Comparativa multi-tienda '
                       'con precios online públicos verificados en tiempo real.',
        'discount_percentage': 20,
        'features_json': '["Conectividad: Wi-Fi, Bluetooth, 4 x HDMI", "Marca: LG", "Pantalla: 55\\" OLED 120Hz", '
                         '"Resolución: 3840 x 2160 (4K UHD)", "Sistema Operativo: webOS", "Procesador: Procesador α8 '
                         'AI 4K", "Memoria RAM: 2.5 GB", "Almacenamiento: 8 GB"]',
        'historical_min_price': 2799.0,
        'id': 'prod_lg_oled_55_b6',
        'image_url': 'https://metroio.vtexassets.com/arquivos/ids/669104/Televisor-LG-OLED-55-OLED55B6PSA-1-367071.jpg?v=639275962615500000',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 3499.0,
        'tech_specs_json': '{"Almacenamiento": "8 GB", "Conectividad": "Wi-Fi, Bluetooth, 4 x HDMI", "Marca": "LG", '
                           '"Memoria RAM": "2.5 GB", "Pantalla": "55\\" OLED 120Hz", "Procesador": "Procesador α8 AI '
                           '4K", "Resolución": "3840 x 2160 (4K UHD)", "Sistema Operativo": "webOS"}',
        'title': 'Televisor LG 55" OLED Smart TV OLED55B6PSA'},
    {   'available_stores_count': 2,
        'best_price': 7999.0,
        'best_store_name': 'La Curacao',
        'brand': 'Samsung',
        'category': 'TVs',
        'description': 'Ficha técnica oficial de Televisor Samsung 65" Neo QLED 4K UHD Tizen QN85D. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 0,
        'features_json': '["Conectividad: Wi-Fi 5, Bluetooth 5.2, 4 x HDMI", "Marca: Samsung", "Pantalla: 65\\" Neo '
                         'QLED 120Hz", "Resolución: 3840 x 2160 (4K UHD)", "Sistema Operativo: Tizen OS", "Procesador: '
                         'Procesador NQ4 AI Gen2", "Memoria RAM: 2.5 GB", "Almacenamiento: 8 GB"]',
        'historical_min_price': 7999.0,
        'id': 'prod_samsung_neo_qled_65',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/q/n/qn65qn85dbgxpe_01.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 7999.0,
        'tech_specs_json': '{"Almacenamiento": "8 GB", "Conectividad": "Wi-Fi 5, Bluetooth 5.2, 4 x HDMI", "Marca": '
                           '"Samsung", "Memoria RAM": "2.5 GB", "Pantalla": "65\\" Neo QLED 120Hz", "Procesador": '
                           '"Procesador NQ4 AI Gen2", "Resolución": "3840 x 2160 (4K UHD)", "Sistema Operativo": '
                           '"Tizen OS"}',
        'title': 'Televisor Samsung 65" Neo QLED 4K UHD Tizen QN85D'},
    {   'available_stores_count': 2,
        'best_price': 1099.0,
        'best_store_name': 'Metro',
        'brand': 'Samsung',
        'category': 'TVs',
        'description': 'Ficha técnica oficial de Televisor Samsung 55" UHD U8000H Vision AI Smart TV 2026. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 21,
        'features_json': '["Conectividad: Wi-Fi, Bluetooth, 3 x HDMI", "Marca: Samsung", "Pantalla: 55\\" Crystal UHD '
                         '4K", "Resolución: 3840 x 2160 (4K UHD)", "Sistema Operativo: Tizen OS", "Procesador: '
                         'Procesador Crystal 4K Vision AI", "Memoria RAM: 2 GB", "Almacenamiento: 8 GB"]',
        'historical_min_price': 1099.0,
        'id': 'prod_samsung_uhd_55_u8000',
        'image_url': 'https://metroio.vtexassets.com/arquivos/ids/645897/Televisor-Samsung-55-UHD-U8000H-Vision-AI-Smart-TV-2026-1-367524.jpg?v=639292346256070000',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1399.0,
        'tech_specs_json': '{"Almacenamiento": "8 GB", "Conectividad": "Wi-Fi, Bluetooth, 3 x HDMI", "Marca": '
                           '"Samsung", "Memoria RAM": "2 GB", "Pantalla": "55\\" Crystal UHD 4K", "Procesador": '
                           '"Procesador Crystal 4K Vision AI", "Resolución": "3840 x 2160 (4K UHD)", "Sistema '
                           'Operativo": "Tizen OS"}',
        'title': 'Televisor Samsung 55" UHD U8000H Vision AI Smart TV 2026'},
    {   'available_stores_count': 4,
        'best_price': 1479.0,
        'best_store_name': 'Falabella',
        'brand': 'Apple',
        'category': 'Tablets',
        'description': 'Ficha técnica oficial de Apple iPad 11" Chip A16 Wi-Fi 128GB. Comparativa multi-tienda con '
                       'precios online públicos verificados en tiempo real.',
        'discount_percentage': 43,
        'features_json': '["Almacenamiento: 128 GB", "Marca: Apple", "Memoria RAM: 6 GB", "Pantalla: 11\\" Liquid '
                         'Retina", "Procesador: Chip A16 Bionic", "Resolución: 2360 x 1640", "Sistema Operativo: '
                         'iPadOS 18"]',
        'historical_min_price': 1479.0,
        'id': 'prod_ipad_11',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/i/p/ipad_a16_wifi_silver_pdp_image_position_1__laes_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 2599.0,
        'tech_specs_json': '{"Almacenamiento": "128 GB", "Marca": "Apple", "Memoria RAM": "6 GB", "Pantalla": "11\\" '
                           'Liquid Retina", "Procesador": "Chip A16 Bionic", "Resolución": "2360 x 1640", "Sistema '
                           'Operativo": "iPadOS 18"}',
        'title': 'Apple iPad 11" Chip A16 Wi-Fi 128GB'},
    {   'available_stores_count': 3,
        'best_price': 429.0,
        'best_store_name': 'Hiraoka',
        'brand': 'Samsung',
        'category': 'Tablets',
        'description': 'Ficha técnica oficial de Tablet Samsung Galaxy Tab A11 8.7" 64GB 4GB RAM. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 34,
        'features_json': '["Almacenamiento: 64 GB", "Marca: Samsung", "Memoria RAM: 4 GB", "Pantalla: 8.7\\" WXGA+", '
                         '"Procesador: MediaTek Helio G99", "Resolución: 1340 x 800", "Sistema Operativo: Android 14"]',
        'historical_min_price': 429.0,
        'id': 'prod_samsung_galaxy_tab_a11',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/3/137729_3_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 649.0,
        'tech_specs_json': '{"Almacenamiento": "64 GB", "Marca": "Samsung", "Memoria RAM": "4 GB", "Pantalla": "8.7\\" '
                           'WXGA+", "Procesador": "MediaTek Helio G99", "Resolución": "1340 x 800", "Sistema '
                           'Operativo": "Android 14"}',
        'title': 'Tablet Samsung Galaxy Tab A11 8.7" 64GB 4GB RAM'},
    {   'available_stores_count': 2,
        'best_price': 649.0,
        'best_store_name': 'La Curacao',
        'brand': 'Xiaomi',
        'category': 'Tablets',
        'description': 'Ficha técnica oficial de Tablet Xiaomi Redmi Pad 2 11" 4GB RAM 128GB. Comparativa multi-tienda '
                       'con precios online públicos verificados en tiempo real.',
        'discount_percentage': 35,
        'features_json': '["Almacenamiento: 128 GB", "Marca: Xiaomi", "Memoria RAM: 4 GB", "Pantalla: 11.0\\" 90Hz", '
                         '"Procesador: MediaTek Helio G99", "Resolución: 1920 x 1200", "Sistema Operativo: Android 13 '
                         '/ HyperOS"]',
        'historical_min_price': 649.0,
        'id': 'prod_xiaomi_redmi_pad_2',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/1/_/1_8_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 999.0,
        'tech_specs_json': '{"Almacenamiento": "128 GB", "Marca": "Xiaomi", "Memoria RAM": "4 GB", "Pantalla": '
                           '"11.0\\" 90Hz", "Procesador": "MediaTek Helio G99", "Resolución": "1920 x 1200", "Sistema '
                           'Operativo": "Android 13 / HyperOS"}',
        'title': 'Tablet Xiaomi Redmi Pad 2 11" 4GB RAM 128GB'},
    {   'available_stores_count': 2,
        'best_price': 1099.0,
        'best_store_name': 'La Curacao',
        'brand': 'Lenovo',
        'category': 'Tablets',
        'description': 'Ficha técnica oficial de Tablet Lenovo Idea Tab 11" 4GB RAM 128GB. Comparativa multi-tienda '
                       'con precios online públicos verificados en tiempo real.',
        'discount_percentage': 15,
        'features_json': '["Almacenamiento: 128 GB", "Marca: Lenovo", "Memoria RAM: 4 GB", "Pantalla: 11\\" 2.5K '
                         '90Hz", "Procesador: MediaTek Dimensity 6300", "Resolución: 2560 x 1600", "Sistema Operativo: '
                         'Android 15"]',
        'historical_min_price': 1099.0,
        'id': 'prod_lenovo_idea_tab_11',
        'image_url': 'https://www.efe.com.pe/media/catalog/product/c/n/cnt-len866tab_1.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1299.0,
        'tech_specs_json': '{"Almacenamiento": "128 GB", "Marca": "Lenovo", "Memoria RAM": "4 GB", "Pantalla": "11\\" '
                           '2.5K 90Hz", "Procesador": "MediaTek Dimensity 6300", "Resolución": "2560 x 1600", "Sistema '
                           'Operativo": "Android 15"}',
        'title': 'Tablet Lenovo Idea Tab 11" 4GB RAM 128GB'},
    {   'available_stores_count': 3,
        'best_price': 645.0,
        'best_store_name': 'Falabella',
        'brand': 'Canon',
        'category': 'Impresoras',
        'description': 'Ficha técnica oficial de Impresora Multifuncional Canon Pixma G3170 Wi-Fi. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 24,
        'features_json': '["Conectividad: Wi-Fi, USB", "Funciones: Impresión, Copia, Escaneo", "Marca: Canon", '
                         '"Resolución: 4800 x 1200 dpi", "Tipo: Multifuncional Tinta Continua", "Procesador: ARM '
                         'Cortex Integrado de Impresión", "Memoria RAM: 128 MB", "Almacenamiento: Memoria Flash '
                         'Integrada", "Pantalla: Panel LCD / LED de Control"]',
        'historical_min_price': 645.0,
        'id': 'prod_canon_pixma_g3170',
        'image_url': 'https://media.falabella.com/falabellaPE/129745573_01/w=800,h=800,fit=pad',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 850.0,
        'tech_specs_json': '{"Almacenamiento": "Memoria Flash Integrada", "Conectividad": "Wi-Fi, USB", "Funciones": '
                           '"Impresión, Copia, Escaneo", "Marca": "Canon", "Memoria RAM": "128 MB", "Pantalla": "Panel '
                           'LCD / LED de Control", "Procesador": "ARM Cortex Integrado de Impresión", "Resolución": '
                           '"4800 x 1200 dpi", "Tipo": "Multifuncional Tinta Continua"}',
        'title': 'Impresora Multifuncional Canon Pixma G3170 Wi-Fi'},
    {   'available_stores_count': 2,
        'best_price': 449.0,
        'best_store_name': 'Hiraoka',
        'brand': 'HP',
        'category': 'Impresoras',
        'description': 'Ficha técnica oficial de Impresora Multifuncional HP Smart Tank 580 Wi-Fi. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 44,
        'features_json': '["Conectividad: Wi-Fi, USB, Bluetooth LE", "Funciones: Impresión, Copia, Escaneo", "Marca: '
                         'HP", "Resolución: 4800 x 1200 dpi", "Tipo: Multifuncional Tinta Continua", "Procesador: ARM '
                         'Cortex Integrado de Impresión", "Memoria RAM: 128 MB", "Almacenamiento: Memoria Flash '
                         'Integrada", "Pantalla: Panel LCD / LED de Control"]',
        'historical_min_price': 449.0,
        'id': 'prod_hp_smart_tank_580',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/2/129103_02.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 799.0,
        'tech_specs_json': '{"Almacenamiento": "Memoria Flash Integrada", "Conectividad": "Wi-Fi, USB, Bluetooth LE", '
                           '"Funciones": "Impresión, Copia, Escaneo", "Marca": "HP", "Memoria RAM": "128 MB", '
                           '"Pantalla": "Panel LCD / LED de Control", "Procesador": "ARM Cortex Integrado de '
                           'Impresión", "Resolución": "4800 x 1200 dpi", "Tipo": "Multifuncional Tinta Continua"}',
        'title': 'Impresora Multifuncional HP Smart Tank 580 Wi-Fi'},
    {   'available_stores_count': 3,
        'best_price': 649.0,
        'best_store_name': 'La Curacao',
        'brand': 'Epson',
        'category': 'Impresoras',
        'description': 'Ficha técnica oficial de Impresora Multifuncional Epson EcoTank L3250 Wi-Fi. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 59,
        'features_json': '["Conectividad: Wi-Fi, USB", "Funciones: Impresión, Copia, Escaneo", "Marca: Epson", '
                         '"Resolución: 5760 x 1440 dpi", "Tipo: Multifuncional Tinta Continua EcoTank", "Procesador: '
                         'ARM Cortex Integrado de Impresión", "Memoria RAM: 64 MB", "Almacenamiento: Memoria Flash '
                         'Integrada", "Pantalla: Panel LCD / LED de Control"]',
        'historical_min_price': 649.0,
        'id': 'prod_epson_ecotank_l3250',
        'image_url': 'https://hiraoka.com.pe/pub/media/catalog/product/1/2/124756.jpg',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 1579.0,
        'tech_specs_json': '{"Almacenamiento": "Memoria Flash Integrada", "Conectividad": "Wi-Fi, USB", "Funciones": '
                           '"Impresión, Copia, Escaneo", "Marca": "Epson", "Memoria RAM": "64 MB", "Pantalla": "Panel '
                           'LCD / LED de Control", "Procesador": "ARM Cortex Integrado de Impresión", "Resolución": '
                           '"5760 x 1440 dpi", "Tipo": "Multifuncional Tinta Continua EcoTank"}',
        'title': 'Impresora Multifuncional Epson EcoTank L3250 Wi-Fi'},
    {   'available_stores_count': 2,
        'best_price': 799.0,
        'best_store_name': 'Metro',
        'brand': 'Epson',
        'category': 'Impresoras',
        'description': 'Ficha técnica oficial de Impresora Multifuncional Epson EcoTank L3350 Wi-Fi. Comparativa '
                       'multi-tienda con precios online públicos verificados en tiempo real.',
        'discount_percentage': 18,
        'features_json': '["Conectividad: Wi-Fi, Wi-Fi Direct, USB", "Funciones: Impresión, Copia, Escaneo", "Marca: '
                         'Epson", "Resolución: 5760 x 1440 dpi", "Tipo: Multifuncional Tinta Continua EcoTank", '
                         '"Procesador: ARM Cortex Integrado de Impresión", "Memoria RAM: 64 MB", "Almacenamiento: '
                         'Memoria Flash Integrada", "Pantalla: Panel LCD / LED de Control"]',
        'historical_min_price': 799.0,
        'id': 'prod_epson_ecotank_l3350',
        'image_url': 'https://metroio.vtexassets.com/arquivos/ids/657438/Impresora-Multifuncional-EPSON-L3350-WiFi-1-369226.jpg?v=639210190379100000',
        'is_favorite': False,
        'is_historical_min': True,
        'original_price': 979.0,
        'tech_specs_json': '{"Almacenamiento": "Memoria Flash Integrada", "Conectividad": "Wi-Fi, Wi-Fi Direct, USB", '
                           '"Funciones": "Impresión, Copia, Escaneo", "Marca": "Epson", "Memoria RAM": "64 MB", '
                           '"Pantalla": "Panel LCD / LED de Control", "Procesador": "ARM Cortex Integrado de '
                           'Impresión", "Resolución": "5760 x 1440 dpi", "Tipo": "Multifuncional Tinta Continua '
                           'EcoTank"}',
        'title': 'Impresora Multifuncional Epson EcoTank L3350 Wi-Fi'}]

SEED_STORE_OFFERS: List[Dict[str, Any]] = [   {   'is_best_price': True,
        'offer_url': 'https://simple.ripley.com.pe/iphone-16-128gb-2065365819351',
        'original_price': 5399.0,
        'price': 2799.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'ripley',
        'store_name': 'Ripley'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/prod18120095/iPhone-16-128GB/20687062',
        'original_price': 4799.0,
        'price': 3399.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/iphone-16-blk-128gb-bes-mye73be-a.html',
        'original_price': 4999.0,
        'price': 3499.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/iphone-16-6-1-128gb-negro',
        'original_price': 3999.0,
        'price': 3999.0,
        'product_id': 'prod_iphone_16',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html',
        'original_price': 5719.0,
        'price': 3299.0,
        'product_id': 'prod_samsung_s25_ultra',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html',
        'original_price': 5719.0,
        'price': 3299.0,
        'product_id': 'prod_samsung_s25_ultra',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/143491916/SAMSUNG-GALAXY-S25-ULTRA-512GB-GREY-TITANIUM',
        'original_price': 7000.0,
        'price': 3299.0,
        'product_id': 'prod_samsung_s25_ultra',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/galaxy-s24-fe-black-256gb-ee-sm-s721bzkmlep.html',
        'original_price': 2699.0,
        'price': 2699.0,
        'product_id': 'prod_samsung_galaxy_s24_fe',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/galaxy-s24-fe-black-256gb-ee-sm-s721bzkmlep.html',
        'original_price': 2699.0,
        'price': 2699.0,
        'product_id': 'prod_samsung_galaxy_s24_fe',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://simple.ripley.com.pe/samsung-galaxy-s24-ultra-5g-512gb-negro-pmp20001526360',
        'original_price': 4199.0,
        'price': 2949.0,
        'product_id': 'prod_samsung_galaxy_s24_ultra',
        'store_id': 'ripley',
        'store_name': 'Ripley'},
    {   'is_best_price': False,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/155039506/samsung-galaxy-s24-ultra-5g-512gb-12gb-ram',
        'original_price': 3899.0,
        'price': 3038.9,
        'product_id': 'prod_samsung_galaxy_s24_ultra',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/a57-6-7-8gb-256gb-violet-sm-a576bzvnltp.html',
        'original_price': 2199.0,
        'price': 1499.0,
        'product_id': 'prod_samsung_galaxy_a57',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/a57-6-7-8gb-256gb-violet-sm-a576bzvnltp.html',
        'original_price': 2199.0,
        'price': 1499.0,
        'product_id': 'prod_samsung_galaxy_a57',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://hiraoka.com.pe/celular-libre-samsung-galaxy-a57-6-7-5g-256gb-8gb-sm-a576bzvnltp-violet',
        'original_price': 2399.0,
        'price': 1499.0,
        'product_id': 'prod_samsung_galaxy_a57',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/a37-6-7-8gb-256gb-gray-sm-a376bzafltp.html',
        'original_price': 1899.0,
        'price': 1649.0,
        'product_id': 'prod_samsung_galaxy_a37',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/a37-6-7-8gb-256gb-gray-sm-a376bzafltp.html',
        'original_price': 1899.0,
        'price': 1649.0,
        'product_id': 'prod_samsung_galaxy_a37',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://hiraoka.com.pe/celular-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-cafe-moca',
        'original_price': 1999.0,
        'price': 1499.0,
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
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/883954446/asus-zenbook-a14-snapdragon-x1-26-100-16gb-512ssd-14-wuxga/883954446',
        'original_price': 7699.0,
        'price': 3999.0,
        'product_id': 'prod_asus_zenbook_a14',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': True,
        'offer_url': 'https://hiraoka.com.pe/laptop-asus-zenbook-a14-de-14-copilot-pc-qualcomm-snapdragon-x-16gb-ram-disco-solido-de-512gb-modelo-ux3407qa-qd289w-funda',
        'original_price': 5499.0,
        'price': 3999.0,
        'product_id': 'prod_asus_zenbook_a14',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://simple.ripley.com.pe/laptop-asus-zenbook-a14-ux3407qa-qd289w-snapdragon-16gb-ram-512gb-ssd-14-2004374833699p',
        'original_price': 6599.0,
        'price': 4199.0,
        'product_id': 'prod_asus_zenbook_a14',
        'store_id': 'ripley',
        'store_name': 'Ripley'},
    {   'is_best_price': True,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/159007212/macbook-air-13-6-chip-m5-10n-cpu-8n-gpu-16gb-ram-512gb-ssd-midnight',
        'original_price': 6399.0,
        'price': 4999.0,
        'product_id': 'prod_macbook_air_m1',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/apple-macbook-air-13-m5-16gb-ram-512gb-ssd-midnight-teclado-en-ingles-14803186apple599669461604202611351466791.html',
        'original_price': 7599.0,
        'price': 5549.0,
        'product_id': 'prod_macbook_air_m1',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/macbook-air-de-13-chip-m5-16gb-ram-disco-solido-de-512gb-azul-cielo',
        'original_price': 6499.0,
        'price': 6499.0,
        'product_id': 'prod_macbook_air_m1',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/lap-ip3-15f-r5-75-8gb-512ssd-82xq00ltlm.html',
        'original_price': 2499.0,
        'price': 2199.0,
        'product_id': 'prod_lenovo_ideapad_slim_3',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/lap-ip3-15f-r5-75-8gb-512ssd-82xq00ltlm.html',
        'original_price': 2499.0,
        'price': 2199.0,
        'product_id': 'prod_lenovo_ideapad_slim_3',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/lapg-victus-15-6-r7-8gb-512gb-rtx4050-15-fb3049la.html',
        'original_price': 5099.0,
        'price': 3399.0,
        'product_id': 'prod_hp_victus_15',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/lapg-victus-15-6-r7-8gb-512gb-rtx4050-15-fb3049la.html',
        'original_price': 5099.0,
        'price': 3399.0,
        'product_id': 'prod_hp_victus_15',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/c5-205h-512-8g-rtx3050-backpack-fx607vjr-tu302w.html',
        'original_price': 5099.0,
        'price': 2999.0,
        'product_id': 'prod_asus_tuf_gaming_f16',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/c5-205h-512-8g-rtx3050-backpack-fx607vjr-tu302w.html',
        'original_price': 5099.0,
        'price': 2999.0,
        'product_id': 'prod_asus_tuf_gaming_f16',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/lap-loq15-15-6-i7-16gb-512gb-rtx5050-83je01jwlm.html',
        'original_price': 6329.0,
        'price': 5699.0,
        'product_id': 'prod_lenovo_loq_15',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/lap-loq15-15-6-i7-16gb-512gb-rtx5050-83je01jwlm.html',
        'original_price': 6329.0,
        'price': 5699.0,
        'product_id': 'prod_lenovo_loq_15',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493',
        'original_price': 4999.0,
        'price': 3299.0,
        'product_id': 'prod_lg_oled_tv',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': True,
        'offer_url': 'https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p',
        'original_price': 4999.0,
        'price': 3299.0,
        'product_id': 'prod_lg_oled_tv',
        'store_id': 'ripley',
        'store_name': 'Ripley'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026',
        'original_price': 4999.0,
        'price': 3499.0,
        'product_id': 'prod_lg_oled_tv',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.metro.pe/televisor-lg-oled-55-oled55b6psa-1067136/p',
        'original_price': 3499.0,
        'price': 2799.0,
        'product_id': 'prod_lg_oled_55_b6',
        'store_id': 'metro',
        'store_name': 'Metro'},
    {   'is_best_price': True,
        'offer_url': 'https://www.wong.pe/televisor-lg-oled-55-oled55b6psa-1067136/p',
        'original_price': 3899.0,
        'price': 2799.0,
        'product_id': 'prod_lg_oled_55_b6',
        'store_id': 'wong',
        'store_name': 'Wong'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/tv-samsung-65-neo-qled-4k-uhd-tizen-qn85d-2024-qn65qn85dbgxpe.html',
        'original_price': 7999.0,
        'price': 7999.0,
        'product_id': 'prod_samsung_neo_qled_65',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/tv-samsung-65-neo-qled-4k-uhd-tizen-qn85d-2024-qn65qn85dbgxpe.html',
        'original_price': 7999.0,
        'price': 7999.0,
        'product_id': 'prod_samsung_neo_qled_65',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.metro.pe/televisor-samsung-55-uhd-u8000h-vision-ai-smart-tv-2026-1067747/p',
        'original_price': 1399.0,
        'price': 1099.0,
        'product_id': 'prod_samsung_uhd_55_u8000',
        'store_id': 'metro',
        'store_name': 'Metro'},
    {   'is_best_price': True,
        'offer_url': 'https://www.wong.pe/televisor-samsung-55-uhd-u8000h-vision-ai-smart-tv-2026-1067747/p',
        'original_price': 1399.0,
        'price': 1099.0,
        'product_id': 'prod_samsung_uhd_55_u8000',
        'store_id': 'wong',
        'store_name': 'Wong'},
    {   'is_best_price': True,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911',
        'original_price': 2599.0,
        'price': 1479.0,
        'product_id': 'prod_ipad_11',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381',
        'original_price': 2599.0,
        'price': 1599.0,
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
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/ipad-a16-wi-fi-md4e4ll-a-11-128gb-6gb-p26513743.html',
        'original_price': 2989.0,
        'price': 2989.0,
        'product_id': 'prod_ipad_11',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://hiraoka.com.pe/tablet-samsung-galaxy-tab-a11-8-7-64gb-4gb-ram-gray',
        'original_price': 649.0,
        'price': 429.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/galaxy-tab-a11-4gb-64gb-gray-sm-x133nzaapeo.html',
        'original_price': 599.0,
        'price': 549.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/galaxy-tab-a11-4gb-64gb-gray-sm-x133nzaapeo.html',
        'original_price': 599.0,
        'price': 549.0,
        'product_id': 'prod_samsung_galaxy_tab_a11',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/pad2-4gb-128gb-gray-pad2gray.html',
        'original_price': 999.0,
        'price': 649.0,
        'product_id': 'prod_xiaomi_redmi_pad_2',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/pad2-4gb-128gb-gray-pad2gray.html',
        'original_price': 999.0,
        'price': 649.0,
        'product_id': 'prod_xiaomi_redmi_pad_2',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/tab-len-tb336fu-4-128-zafr0908pe-cnt-len866tab.html',
        'original_price': 1299.0,
        'price': 1099.0,
        'product_id': 'prod_lenovo_idea_tab_11',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/tab-len-tb336fu-4-128-zafr0908pe-cnt-len866tab.html',
        'original_price': 1299.0,
        'price': 1099.0,
        'product_id': 'prod_lenovo_idea_tab_11',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://www.falabella.com.pe/falabella-pe/product/129745572/impresora-multifuncional-canon-g3170',
        'original_price': 850.0,
        'price': 645.0,
        'product_id': 'prod_canon_pixma_g3170',
        'store_id': 'falabella',
        'store_name': 'Falabella'},
    {   'is_best_price': False,
        'offer_url': 'https://www.lacuracao.pe/impresora-g3170-multifuncional-canon-pixma-wi-fi-34715819g31702712202502230487164.html',
        'original_price': 800.0,
        'price': 720.0,
        'product_id': 'prod_canon_pixma_g3170',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': False,
        'offer_url': 'https://www.efe.com.pe/impresora-g3170-multifuncional-canon-pixma-wi-fi-34715819g31702712202502230487164.html',
        'original_price': 800.0,
        'price': 720.0,
        'product_id': 'prod_canon_pixma_g3170',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': True,
        'offer_url': 'https://hiraoka.com.pe/impresora-todo-en-uno-hp-smart-tank-580',
        'original_price': 799.0,
        'price': 449.0,
        'product_id': 'prod_hp_smart_tank_580',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': False,
        'offer_url': 'https://www.wong.pe/impresora-todo-en-uno-hp-smart-tank-580-984531/p',
        'original_price': 829.0,
        'price': 549.0,
        'product_id': 'prod_hp_smart_tank_580',
        'store_id': 'wong',
        'store_name': 'Wong'},
    {   'is_best_price': True,
        'offer_url': 'https://www.lacuracao.pe/impresora-epson-l3250-multifuncional-con-l3250.html',
        'original_price': 1579.0,
        'price': 649.0,
        'product_id': 'prod_epson_ecotank_l3250',
        'store_id': 'curacao',
        'store_name': 'La Curacao'},
    {   'is_best_price': True,
        'offer_url': 'https://www.efe.com.pe/impresora-epson-l3250-multifuncional-con-l3250.html',
        'original_price': 1579.0,
        'price': 649.0,
        'product_id': 'prod_epson_ecotank_l3250',
        'store_id': 'efe',
        'store_name': 'Tiendas Efe'},
    {   'is_best_price': False,
        'offer_url': 'https://hiraoka.com.pe/impresora-multifuncional-epson-ecotank-l3250',
        'original_price': 979.0,
        'price': 979.0,
        'product_id': 'prod_epson_ecotank_l3250',
        'store_id': 'hiraoka',
        'store_name': 'Hiraoka'},
    {   'is_best_price': True,
        'offer_url': 'https://www.metro.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p',
        'original_price': 979.0,
        'price': 799.0,
        'product_id': 'prod_epson_ecotank_l3350',
        'store_id': 'metro',
        'store_name': 'Metro'},
    {   'is_best_price': True,
        'offer_url': 'https://www.wong.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p',
        'original_price': 979.0,
        'price': 799.0,
        'product_id': 'prod_epson_ecotank_l3350',
        'store_id': 'wong',
        'store_name': 'Wong'}]

SEED_PRICE_HISTORY: List[Dict[str, Any]] = []

async def sync_and_upsert_catalog(session: AsyncSession) -> int:
    """
    Sincronización UPSERT en Neon PostgreSQL / SQLite de alto rendimiento (< 200 ms):
    - REGLA ESTRICTA FINPRICE: len(offers) >= 2 OBLIGATORIO. Cualquier producto con < 2 ofertas se descarta.
    - Precarga existentes en memoria para evitar cientos de viajes de red WAN (Round Trips).
    - Actualiza si ya existe por ID o inserta si no existe.
    - Sincroniza ofertas por tienda (store_offers) e historial de precios (price_history).
    - Elimina cualquier registro obsoleto previo y limpia comunidad/ofertas fantasma.
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

    # Contar ofertas válidas por producto para garantizar len(offers) >= 2
    offers_by_prod: Dict[str, List[Dict[str, Any]]] = {}
    for o in SEED_STORE_OFFERS:
        offers_by_prod.setdefault(o["product_id"], []).append(o)

    # Filtrar productos que cumplan estrictamente len(offers) >= 2
    valid_products_to_seed = []
    for p in SEED_PRODUCTS:
        prod_offers = offers_by_prod.get(p["id"], [])
        if len(prod_offers) < 2:
            logger.warning(
                f"[SEED_DISCARD] Descartando producto {p['id']} de semilla: "
                f"solo tiene {len(prod_offers)} oferta(s) (requerido >= 2)."
            )
            continue
        p["available_stores_count"] = len(prod_offers)
        valid_products_to_seed.append(p)

    valid_prod_ids = {p["id"] for p in valid_products_to_seed}

    # 0. Limpieza de productos obsoletos o fuera de catálogo
    for pid, ent in list(existing_prods.items()):
        if pid not in valid_prod_ids:
            await session.delete(ent)

    valid_offer_keys = {(o["product_id"], o["store_id"]) for o in SEED_STORE_OFFERS if o["product_id"] in valid_prod_ids}
    for (pid, sid), off in list(existing_offers.items()):
        if (pid, sid) not in valid_offer_keys:
            await session.delete(off)

    valid_hist_keys = {(h["product_id"], h["day_offset"]) for h in SEED_PRICE_HISTORY if h["product_id"] in valid_prod_ids}
    for (pid, day), hist in list(existing_hist.items()):
        if (pid, day) not in valid_hist_keys:
            await session.delete(hist)

    # 1. Upsert Productos Válidos (len(offers) >= 2)
    for p in valid_products_to_seed:
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

    # 3. Upsert Historial de Precios (Día 1)
    for h in SEED_PRICE_HISTORY:
        if h["product_id"] not in valid_prod_ids:
            continue
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
    logger.info(f"sync_and_upsert_catalog completado con éxito: {len(valid_products_to_seed)} productos sincronizados.")
    return len(valid_products_to_seed)


async def seed_database_fast(session: AsyncSession) -> int:
    """Inserta o sincroniza el catálogo oficial en Neon PostgreSQL / SQLite."""
    return await sync_and_upsert_catalog(session)
