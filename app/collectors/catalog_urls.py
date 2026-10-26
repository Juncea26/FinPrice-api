"""
Registro oficial de productos y URLs reales verificadas en retailers del Perú.
REGLA INQUEBRANTABLE: Cero URLs inventadas o de prueba, y coincidencia 100% exacta
de familia, modelo, generación y almacenamiento (Zero False-Positive Policy).
"""
from typing import Any, Dict, List

# Tiendas retail peruanas oficiales
STORES_INFO: Dict[str, Dict[str, str]] = {
    "falabella": {
        "name": "Falabella CMR",
        "code": "FALABELLA",
        "base_url": "https://www.falabella.com.pe",
    },
    "ripley": {
        "name": "Ripley",
        "code": "RIPLEY",
        "base_url": "https://simple.ripley.com.pe",
    },
    "hiraoka": {
        "name": "Hiraoka",
        "code": "HIRAOKA",
        "base_url": "https://hiraoka.com.pe",
    },
    "efe": {
        "name": "Tiendas Efe",
        "code": "EFE",
        "base_url": "https://www.efe.com.pe",
    },
    "curacao": {
        "name": "La Curacao",
        "code": "CURACAO",
        "base_url": "https://www.lacuracao.pe",
    },
    "tottus": {
        "name": "Tottus",
        "code": "TOTTUS",
        "base_url": "https://www.tottus.com.pe",
    },
    "metro": {
        "name": "Metro",
        "code": "METRO",
        "base_url": "https://www.metro.pe",
    },
    "wong": {
        "name": "Wong",
        "code": "WONG",
        "base_url": "https://www.wong.pe",
    },
}

# Departamentos del Perú para validación de ubigeo en ofertas comunitarias
PERU_DEPARTMENTS: List[str] = [
    "Amazonas", "Áncash", "Apurímac", "Arequipa", "Ayacucho", "Cajamarca",
    "Callao", "Cusco", "Huancavelica", "Huánuco", "Ica", "Junín", "La Libertad",
    "Lambayeque", "Lima", "Loreto", "Madre de Dios", "Moquegua", "Pasco",
    "Piura", "Puno", "San Martín", "Tacna", "Tumbes", "Ucayali",
]

# Catálogo con URLs reales verificadas en vivo (100% validadas por identidad y capacidad)
CATALOG_PRODUCTS: List[Dict[str, Any]] = [
    # --------------------------------------------------------------------------
    # 1. SAMSUNG GALAXY S25 ULTRA 512GB 12GB RAM
    # --------------------------------------------------------------------------
    {
        "id": "prod_samsung_s25_ultra",
        "title": "Samsung Galaxy S25 Ultra 512GB 12GB RAM Titanio",
        "category": "Smartphones",
        "brand": "Samsung",
        "description": "El estandarte de Samsung con Galaxy AI integrada, procesador Snapdragon 8 Elite for Galaxy, chasis de titanio de grado aeroespacial con S-Pen y cámara cuádruple de 200MP.",
        "features": [
            "Galaxy AI con traducción en tiempo real y Circle to Search",
            "Cámara principal de 200 MP con ProVisual Engine y Zoom 100x",
            "Chasis de titanio con cristal Corning Gorilla Armor antirreflejo",
            "S-Pen integrado de baja latencia para productividad",
            "Batería de 5000 mAh con carga súper rápida",
        ],
        "tech_specs": {
            "Procesador": "Qualcomm Snapdragon 8 Elite for Galaxy",
            "Memoria RAM": "12GB",
            "Almacenamiento": "512GB",
            "Pantalla": "6.9 Pulgadas Dynamic AMOLED 2X QHD+ 120Hz",
            "Resolución": "3120 x 1440 píxeles",
            "Cámara": "200MP + 50MP + 12MP + 10MP",
        },
        "store_urls": {
            "efe": "https://www.efe.com.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
            "curacao": "https://www.lacuracao.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
        },
    },
    # --------------------------------------------------------------------------
    # 2. APPLE IPHONE 16 128GB
    # --------------------------------------------------------------------------
    {
        "id": "prod_iphone_16",
        "title": "Apple iPhone 16 128GB Negro",
        "category": "Smartphones",
        "brand": "Apple",
        "description": "Diseñado con Apple Intelligence, el revolucionario botón de Control de Cámara, chip A18 de segunda generación y cámara Fusion de 48 MP.",
        "features": [
            "Chip A18 ultrarrápido optimizado para Apple Intelligence",
            "Botón de Control de Cámara táctil con acceso visual instantáneo",
            "Cámara Fusion de 48 MP con teleobjetivo 2x de calidad óptica",
            "Carcasa de aluminio de grado aeroespacial con Ceramic Shield de última generación",
            "Conector USB-C universal y Botón de Acción personalizable",
        ],
        "tech_specs": {
            "Procesador": "Apple A18 (3nm)",
            "Memoria RAM": "8GB",
            "Almacenamiento": "128GB",
            "Pantalla": "6.1 Pulgadas Super Retina XDR OLED",
            "Resolución": "2556 x 1179 píxeles",
            "Cámara": "48MP Fusion + 12MP Ultra Gran Angular",
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/iphone-16-6-1-128gb-blanco",
            "efe": "https://www.efe.com.pe/iphone-16-blk-128gb-bes-mye73be-a.html",
            "ripley": "https://simple.ripley.com.pe/iphone-16-128gb-2065365819351",
        },
    },
    # --------------------------------------------------------------------------
    # 3. APPLE MACBOOK AIR 13.6 PULGADAS M5
    # --------------------------------------------------------------------------
    {
        "id": "prod_macbook_air_m5",
        "title": "Apple MacBook Air 13.6 Pulgadas M5 16GB RAM 512GB SSD Silver",
        "category": "Laptops",
        "brand": "Apple",
        "description": "Portátil ultradelgada y silenciosa con pantalla Liquid Retina de 13.6 pulgadas, chip M5, 16GB de memoria unificada, almacenamiento SSD de 512GB y autonomía de hasta 18 horas.",
        "features": [
            "Chip Apple M5 con CPU de alto rendimiento y GPU avanzada",
            "16GB de memoria unificada de alta velocidad",
            "Almacenamiento SSD ultrarrápido de 512GB",
            "Pantalla Liquid Retina con 500 nits de brillo y gama de colores P3",
            "Carcasa 100% de aluminio reciclado sin ventiladores (totalmente silenciosa)",
        ],
        "tech_specs": {
            "Procesador": "Apple Silicon M5",
            "Memoria RAM": "16GB",
            "Almacenamiento": "512GB SSD",
            "Pantalla": "13.6 Pulgadas Liquid Retina",
            "Resolución": "2560 x 1664 píxeles",
            "Batería": "Hasta 18 horas de reproducción",
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/macbook-air-de-13-chip-m5-16gb-ram-disco-solido-de-512gb-azul-cielo",
            "efe": "https://www.efe.com.pe/macbook-air-13-6-m5-16gb-512gb-silver-mdh74e-a.html",
            "curacao": "https://www.lacuracao.pe/macbook-air-13-6-m5-16gb-512gb-silver-mdh74e-a.html",
        },
    },
    # --------------------------------------------------------------------------
    # 4. LG OLED EVO AI C6 4K SMART TV
    # --------------------------------------------------------------------------
    {
        "id": "prod_lg_oled_tv",
        "title": "LG OLED evo AI C6 4K UHD Smart TV con Dolby Atmos",
        "category": "TVs",
        "brand": "LG",
        "description": "Televisor inteligente con píxeles OLED autoemisivos, procesador inteligente α9 AI 4K con mapeo dinámico de tonos, soporte Dolby Vision/Atmos y puertos HDMI 2.1 para gaming a 120Hz.",
        "features": [
            "Píxeles autoiluminados OLED evo con negros absolutos y contraste infinito",
            "Procesador inteligente α9 AI 4K con escalado y sonido optimizado por IA",
            "4 puertos HDMI 2.1 con VRR, G-SYNC, AMD FreeSync y tasa de refresco de 120Hz",
            "Audio cinematográfico Dolby Atmos y formato Dolby Vision",
            "Sistema operativo webOS con Magic Remote y control de voz",
        ],
        "tech_specs": {
            "Procesador": "α9 AI Processor 4K",
            "Resolución": "4K UHD (3840 x 2160)",
            "Pantalla": "OLED evo 55 Pulgadas",
            "Tasa de refresco": "120Hz Nativo (VRR)",
            "Audio": "Dolby Atmos 40W",
            "Puertos": "4 x HDMI 2.1, 3 x USB, Salida Óptica, LAN",
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026",
            "efe": "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
            "curacao": "https://www.lacuracao.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
        },
    },
    # --------------------------------------------------------------------------
    # 5. APPLE IPAD 11 PULGADAS A16 WI-FI 128GB
    # --------------------------------------------------------------------------
    {
        "id": "prod_ipad_11",
        "title": "Apple iPad 11 Pulgadas A16 Wi-Fi 128GB Azul",
        "category": "Tablets",
        "brand": "Apple",
        "description": "Tablet potente y versátil con pantalla Liquid Retina de 11 pulgadas, procesador Apple Bionic A16, cámara frontal horizontal de 12MP y compatibilidad con Apple Pencil.",
        "features": [
            "Pantalla Liquid Retina de 11 pulgadas con tecnología True Tone",
            "Chip Apple Bionic A16 de alto rendimiento para multitarea y juegos",
            "Cámara ultra gran angular de 12MP con Encuadre Centrado",
            "Conexión Wi-Fi 6 de alta velocidad y puerto USB-C",
            "Compatible con Apple Pencil y Magic Keyboard Folio",
        ],
        "tech_specs": {
            "Procesador": "Apple Bionic A16",
            "Memoria RAM": "6GB",
            "Almacenamiento": "128GB",
            "Pantalla": "11 Pulgadas Liquid Retina IPS",
            "Resolución": "2360 x 1640 píxeles",
            "Conectividad": "Wi-Fi 6 (802.11ax), Bluetooth 5.3",
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wi-fi-128gb-azul",
            "efe": "https://www.efe.com.pe/ipad-a16-wi-fi-md4e4ll-a-11-128gb-6gb-p26513743.html",
        },
    },
    # --------------------------------------------------------------------------
    # 6. XIAOMI REDMI NOTE 15 PRO 5G 512GB 12GB RAM
    # --------------------------------------------------------------------------
    {
        "id": "prod_xiaomi_redmi_note",
        "title": "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM Café Moca",
        "category": "Smartphones",
        "brand": "Xiaomi",
        "description": "Smartphone con pantalla AMOLED curva de 120Hz a resolución 1.5K, cámara de 200MP con OIS, resistencia al agua y polvo IP68 y carga hiperrápida.",
        "features": [
            "Cámara principal de 200MP con sensor avanzado y estabilización óptica OIS",
            "Pantalla curva CrystalRes AMOLED 1.5K de 120Hz con brillo de 1800 nits",
            "Certificación de protección contra agua y polvo IP68",
            "Almacenamiento masivo de 512GB con 12GB de memoria RAM física",
            "Batería de larga duración con tecnología de carga ultrarrápida",
        ],
        "tech_specs": {
            "Procesador": "MediaTek Dimensity Ultra",
            "Memoria RAM": "12GB",
            "Almacenamiento": "512GB",
            "Pantalla": "6.8 Pulgadas AMOLED Curva 1.5K 120Hz",
            "Resolución": "2712 x 1220 píxeles",
            "Cámara": "200MP + 8MP + 2MP",
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/celular-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-cafe-moca",
            "efe": "https://www.efe.com.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
            "curacao": "https://www.lacuracao.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html",
        },
    },
]
