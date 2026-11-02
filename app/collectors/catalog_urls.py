"""
Registro oficial de productos, semilla de URLs reales verificadas en retailers del Perú
y caché persistente de URLs verificadas sincronizada con la base de datos.
REGLA INQUEBRANTABLE: Cero URLs inventadas o de prueba, y coincidencia 100% exacta
de familia, modelo, generación y almacenamiento (Zero False-Positive Policy).
ESTRICTAMENTE 8 TIENDAS: Tiendas Efe, Falabella, Ripley, La Curacao, Hiraoka, Tottus, Metro, Wong.
"""
from typing import Any, Dict, List, Optional
from app.collectors.url_utils import canonicalize_store_url

# Tiendas retail peruanas oficiales (ESTRICTAMENTE 8 TIENDAS)
STORES_INFO: Dict[str, Dict[str, str]] = {
    "efe": {
        "name": "Tiendas Efe",
        "code": "EFE",
        "base_url": "https://www.efe.com.pe",
    },
    "falabella": {
        "name": "Falabella",
        "code": "FALABELLA",
        "base_url": "https://www.falabella.com.pe",
    },
    "ripley": {
        "name": "Ripley",
        "code": "RIPLEY",
        "base_url": "https://simple.ripley.com.pe",
    },
    "curacao": {
        "name": "La Curacao",
        "code": "CURACAO",
        "base_url": "https://www.lacuracao.pe",
    },
    "hiraoka": {
        "name": "Hiraoka",
        "code": "HIRAOKA",
        "base_url": "https://hiraoka.com.pe",
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
    {
        "id": "prod_hp_smart_tank_530",
        "title": "Impresora Multifuncional HP Smart Tank 530 Wi-Fi ADF",
        "category": "Impresoras",
        "brand": "HP",
        "fingerprint": {
            "brand": "hp",
            "family_tokens": [
                "smart",
                "tank",
                "530"
            ],
            "screen_inches": None,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "580",
                "581",
                "585"
            ]
        },
        "description": "Impresora multifuncional de tanque de tinta de alta capacidad con alimentador automático de documentos (ADF) de 35 páginas, conectividad Wi-Fi de doble banda y botellas antiderrames.",
        "features": [
            "Tipo: Multifuncional Tinta Continua",
            "Conectividad: Wi-Fi, USB 2.0, Bluetooth LE",
            "Funciones: Impresión, Escaneo, Copia, ADF 35 hojas",
            "Velocidad: Hasta 11 ppm en negro y 5 ppm en color",
            "Resolución de impresión: Hasta 4800 x 1200 dpi optimizados"
        ],
        "tech_specs": {
            "Tipo": "Multifuncional Tinta Continua",
            "Conectividad": "Wi-Fi, USB, Bluetooth LE",
            "Funciones": "Impresión, Copia, Escaneo, ADF",
            "Marca": "HP",
            "Alimentador Automático": "35 hojas",
            "Resolución": "4800 x 1200 dpi"
        },
        "store_urls": {
            "falabella": "https://www.falabella.com.pe/falabella-pe/product/20756050/impresora-multifuncional-smart-tank-530/20756050"
        }
    },
    {
        "id": "prod_hp_smart_tank_581",
        "title": "Impresora Multifuncional HP Smart Tank 581 Wi-Fi",
        "category": "Impresoras",
        "brand": "HP",
        "fingerprint": {
            "brand": "hp",
            "family_tokens": [
                "smart",
                "tank",
                "581"
            ],
            "screen_inches": None,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "530",
                "580",
                "585"
            ]
        },
        "description": "Impresora todo en uno con conexión Wi-Fi autorreparable, sensores de tinta inteligentes y diseño compacto para el hogar y teletrabajo.",
        "features": [
            "Tipo: Multifuncional Tinta Continua",
            "Conectividad: Wi-Fi, Wi-Fi Direct, USB",
            "Funciones: Impresión, Copia, Escaneo",
            "Rendimiento: Hasta 6000 páginas en negro / 6000 páginas a color",
            "Velocidad: Hasta 12 ppm en negro y 5 ppm en color"
        ],
        "tech_specs": {
            "Tipo": "Multifuncional Tinta Continua",
            "Conectividad": "Wi-Fi, USB, Wi-Fi Direct",
            "Funciones": "Impresión, Copia, Escaneo",
            "Marca": "HP",
            "Resolución": "4800 x 1200 dpi"
        },
        "store_urls": {
            "ripley": "https://simple.ripley.com.pe/impresora-multifuncional-hp-smart-tank-581-2004335122091p"
        }
    },
    {
        "id": "prod_epson_ecotank_l3310",
        "title": "Impresora Multifuncional Epson EcoTank L3310",
        "category": "Impresoras",
        "brand": "Epson",
        "fingerprint": {
            "brand": "epson",
            "family_tokens": [
                "ecotank",
                "l3310"
            ],
            "screen_inches": None,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "l3350",
                "l3250",
                "l4260"
            ]
        },
        "description": "Impresora multifuncional 3 en 1 con sistema original de tanque de tinta EcoTank de ultra bajo costo de impresión y tecnología Heat-Free MicroPiezo.",
        "features": [
            "Tipo: Multifuncional Tinta Continua EcoTank",
            "Conectividad: USB de alta velocidad",
            "Funciones: Impresora, Copiadora, Escáner",
            "Tecnología: MicroPiezo Heat-Free",
            "Rendimiento: Hasta 4500 páginas negro / 7500 páginas color"
        ],
        "tech_specs": {
            "Tipo": "Multifuncional Tinta Continua EcoTank",
            "Conectividad": "USB 2.0",
            "Funciones": "Impresión, Copia, Escaneo",
            "Marca": "Epson",
            "Resolución": "5760 x 1440 dpi"
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/impresora-multifuncional-epson-ecotank-l3310"
        }
    },
    {
        "id": "prod_hp_smart_tank_585",
        "title": "Impresora Multifuncional HP Smart Tank 585 Wi-Fi",
        "category": "Impresoras",
        "brand": "HP",
        "fingerprint": {
            "brand": "hp",
            "family_tokens": [
                "smart",
                "tank",
                "585"
            ],
            "screen_inches": None,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "530",
                "580",
                "581"
            ]
        },
        "description": "Impresora multifunción inalámbrica Smart Tank con sistema continuo de recarga limpia sin derrames y botón de guía inteligente.",
        "features": [
            "Tipo: Multifuncional Tinta Continua",
            "Conectividad: Wi-Fi, Wi-Fi Direct, USB",
            "Funciones: Impresión, Copia, Escaneo",
            "Rendimiento: 6000 páginas negro / 6000 páginas color",
            "Garantía: Hasta 2 años con registro oficial"
        ],
        "tech_specs": {
            "Tipo": "Multifuncional Tinta Continua",
            "Conectividad": "Wi-Fi, USB, Wi-Fi Direct",
            "Funciones": "Impresión, Copia, Escaneo",
            "Marca": "HP",
            "Resolución": "4800 x 1200 dpi"
        },
        "store_urls": {
            "efe": "https://www.efe.com.pe/hp-smart-tank-585-blue-white-st-585.html"
        }
    },
    {
        "id": "prod_hp_smart_tank_580",
        "title": "Impresora Multifuncional HP Smart Tank 580 Wi-Fi",
        "category": "Impresoras",
        "brand": "HP",
        "fingerprint": {
            "brand": "hp",
            "family_tokens": [
                "smart",
                "tank",
                "580"
            ],
            "screen_inches": None,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "530",
                "581",
                "585"
            ]
        },
        "description": "Impresora todo en uno todo conectada con Wi-Fi inteligente de rápida recuperación y manejo sencillo desde la app HP Smart.",
        "features": [
            "Tipo: Multifuncional Tinta Continua",
            "Conectividad: Wi-Fi, USB",
            "Funciones: Impresión, Copia, Escaneo",
            "Velocidad: 12 ppm negro, 5 ppm color",
            "Bandeja de entrada: 100 hojas"
        ],
        "tech_specs": {
            "Tipo": "Multifuncional Tinta Continua",
            "Conectividad": "Wi-Fi, USB",
            "Funciones": "Impresión, Copia, Escaneo",
            "Marca": "HP",
            "Resolución": "4800 x 1200 dpi"
        },
        "store_urls": {
            "curacao": "https://www.lacuracao.pe/impresora-todo-en-uno-hp-smart-tank-580-1f3y2a.html"
        }
    },
    {
        "id": "prod_hp_deskjet_2975",
        "title": "Impresora Multifuncional HP DeskJet Ink Advantage 2975 Wi-Fi",
        "category": "Impresoras",
        "brand": "HP",
        "fingerprint": {
            "brand": "hp",
            "family_tokens": [
                "deskjet",
                "2975"
            ],
            "screen_inches": None,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "smart",
                "tank"
            ]
        },
        "description": "Impresora compacta y económica para el hogar con cartuchos originales de bajo costo, conexión inalámbrica y app HP Smart.",
        "features": [
            "Tipo: Multifuncional Inyección Térmica",
            "Conectividad: Wi-Fi, USB",
            "Funciones: Impresión, Copia, Escaneo",
            "Resolución: Hasta 4800 x 1200 dpi",
            "Cartuchos: HP 667 Negro y Tricolor"
        ],
        "tech_specs": {
            "Tipo": "Multifuncional Inyección Térmica",
            "Conectividad": "Wi-Fi, USB",
            "Funciones": "Impresión, Copia, Escaneo",
            "Marca": "HP",
            "Resolución": "4800 x 1200 dpi"
        },
        "store_urls": {
            "tottus": "https://www.tottus.com.pe/tottus-pe/articulo/151249212/impresora-multifuncional-hp-ia-2975/151249213"
        }
    },
    {
        "id": "prod_epson_ecotank_l3350",
        "title": "Impresora Multifuncional Epson EcoTank L3350 Wi-Fi",
        "category": "Impresoras",
        "brand": "Epson",
        "fingerprint": {
            "brand": "epson",
            "family_tokens": [
                "ecotank",
                "l3350"
            ],
            "screen_inches": None,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "l3310",
                "l3250",
                "l4260"
            ]
        },
        "description": "Multifuncional inalámbrica EcoTank para familias activas con conectividad Wi-Fi, Wi-Fi Direct y soporte para Epson Smart Panel.",
        "features": [
            "Tipo: Multifuncional Tinta Continua EcoTank",
            "Conectividad: Wi-Fi, Wi-Fi Direct, USB",
            "Funciones: Impresión, Copia, Escaneo",
            "Tecnología: MicroPiezo Heat-Free",
            "Rendimiento: 4500 páginas negro / 7500 páginas color"
        ],
        "tech_specs": {
            "Tipo": "Multifuncional Tinta Continua EcoTank",
            "Conectividad": "Wi-Fi, Wi-Fi Direct, USB",
            "Funciones": "Impresión, Copia, Escaneo",
            "Marca": "Epson",
            "Resolución": "5760 x 1440 dpi"
        },
        "store_urls": {
            "metro": "https://www.metro.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p",
            "wong": "https://www.wong.pe/impresora-multifuncional-epson-l3350-wifi-1069770/p"
        }
    },
    {
        "id": "prod_lg_oled_tv",
        "title": "Televisor LG 55\" OLED evo AI C6 4K Smart TV 2026",
        "category": "TVs",
        "brand": "LG",
        "fingerprint": {
            "brand": "lg",
            "family_tokens": [
                "oled",
                "c6"
            ],
            "screen_inches": 55,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "42",
                "48",
                "65",
                "77",
                "83"
            ]
        },
        "description": "Televisor LG OLED evo serie C6 con panel autoemisivo 4K, procesador inteligente alpha 9 Gen7, tasa de refresco nativa de 144Hz y Dolby Vision / Atmos.",
        "features": [
            "Pantalla: 55\" OLED evo 4K 144Hz",
            "Resolución: 3840 x 2160 (4K UHD)",
            "Procesador: alpha 9 Gen7 AI Processor 4K",
            "Sistema Operativo: webOS 26 con actualizaciones garantizadas",
            "Gaming: 4 puertos HDMI 2.1 con VRR, G-Sync y FreeSync"
        ],
        "tech_specs": {
            "Resolución": "3840 x 2160 (4K UHD)",
            "Pantalla": "55\" OLED evo 144Hz",
            "Sistema Operativo": "webOS 26",
            "Marca": "LG",
            "Tasa de Refresco": "144 Hz",
            "Conectividad": "Wi-Fi, Bluetooth 5.2, HDMI 2.1"
        },
        "store_urls": {
            "falabella": "https://www.falabella.com.pe/falabella-pe/product/80046493/55-lg-oled-evo-ai-c6-4k-smart-tv-2026/80046493",
            "ripley": "https://simple.ripley.com.pe/televisor-smart-tv-lg-55-oled-evo-ai-c6-4k-2026-2018371874913p",
            "hiraoka": "https://hiraoka.com.pe/televisor-lg-55-oled-evo-ai-c6-4k-smart-tv-2026",
            "efe": "https://www.efe.com.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html",
            "curacao": "https://www.lacuracao.pe/55-lg-oled-evo-ai-c6-4k-smart-tv-2026-oled55c6psaotb.html"
        }
    },
    {
        "id": "prod_iphone_16",
        "title": "Apple iPhone 16 128GB",
        "category": "Smartphones",
        "brand": "Apple",
        "fingerprint": {
            "brand": "apple",
            "family_tokens": [
                "iphone",
                "16",
                "128gb"
            ],
            "screen_inches": None,
            "storage_gb": 128,
            "ram_gb": 8,
            "network": "5G",
            "forbidden_tokens": [
                "pro",
                "plus",
                "max",
                "256gb",
                "512gb"
            ]
        },
        "description": "Apple iPhone 16 con chip A18 ultrapotente, Control de la Cámara táctil, sistema de dos cámaras de 48 MP con Fusion y botón de Acción personalizable.",
        "features": [
            "Procesador: Apple A18",
            "Memoria RAM: 8 GB",
            "Almacenamiento: 128 GB",
            "Pantalla: 6.1\" Super Retina XDR OLED",
            "Resolución: 2556 x 1179 píxeles",
            "Cámara Principal: 48 MP Fusion + 12 MP Ultra gran angular"
        ],
        "tech_specs": {
            "Procesador": "Apple A18",
            "Memoria RAM": "8 GB",
            "Almacenamiento": "128 GB",
            "Pantalla": "6.1\" Super Retina XDR OLED",
            "Resolución": "2556 x 1179",
            "Sistema Operativo": "iOS 18",
            "Conectividad": "5G",
            "Marca": "Apple"
        },
        "store_urls": {
            "falabella": "https://www.falabella.com.pe/falabella-pe/product/prod18120095/iPhone-16-128GB/20687062",
            "ripley": "https://simple.ripley.com.pe/iphone-16-128gb-2065365819351",
            "hiraoka": "https://hiraoka.com.pe/iphone-16-6-1-128gb-negro",
            "efe": "https://www.efe.com.pe/iphone-16-blk-128gb-bes-mye73be-a.html"
        }
    },
    {
        "id": "prod_xiaomi_redmi_note",
        "title": "Xiaomi Redmi Note 15 Pro 5G 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Xiaomi",
        "fingerprint": {
            "brand": "xiaomi",
            "family_tokens": [
                "redmi",
                "note",
                "15",
                "pro"
            ],
            "screen_inches": None,
            "storage_gb": 512,
            "ram_gb": 12,
            "network": "5G",
            "forbidden_tokens": [
                "256gb",
                "128gb",
                "a7",
                "a3"
            ]
        },
        "description": "Xiaomi Redmi Note 15 Pro 5G con cámara insignia de 200MP con OIS, carga ultra rápida de 120W HyperCharge y pantalla AMOLED CrystalRes 1.5K.",
        "features": [
            "Procesador: Snapdragon 7s Gen 3",
            "Memoria RAM: 12 GB",
            "Almacenamiento: 512 GB",
            "Pantalla: 6.67\" AMOLED CrystalRes 120Hz",
            "Resolución: 2712 x 1220 píxeles",
            "Batería: 5000 mAh con carga de 120W"
        ],
        "tech_specs": {
            "Procesador": "Snapdragon 7s Gen 3",
            "Memoria RAM": "12 GB",
            "Almacenamiento": "512 GB",
            "Pantalla": "6.67\" AMOLED CrystalRes 120Hz",
            "Resolución": "2712 x 1220",
            "Sistema Operativo": "Android / HyperOS",
            "Conectividad": "5G",
            "Marca": "Xiaomi"
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/celular-libre-xiaomi-redmi-note-15-pro-5g-6-8-512gb-12gb-ram-blue",
            "efe": "https://www.efe.com.pe/redmi-note15pro-5g-12gb-512gb-brown-15pro-5gbrown.html"
        }
    },
    {
        "id": "prod_ipad_11",
        "title": "Apple iPad 11\" Chip A16 Wi-Fi 128GB",
        "category": "Tablets",
        "brand": "Apple",
        "fingerprint": {
            "brand": "apple",
            "family_tokens": [
                "ipad",
                "11",
                "a16"
            ],
            "screen_inches": 11,
            "storage_gb": 128,
            "ram_gb": 6,
            "network": "Wi-Fi",
            "forbidden_tokens": [
                "pro",
                "air",
                "mini"
            ]
        },
        "description": "Nueva tableta Apple iPad de 11 pulgadas con chip A16 Bionic, pantalla Liquid Retina envolvente, conectividad Wi-Fi 6 de alta velocidad y compatibilidad con Apple Pencil.",
        "features": [
            "Procesador: Apple A16 Bionic",
            "Memoria RAM: 6 GB",
            "Almacenamiento: 128 GB",
            "Pantalla: 11\" Liquid Retina True Tone",
            "Resolución: 2360 x 1640 píxeles",
            "Conectividad: Wi-Fi 6, Bluetooth 5.3"
        ],
        "tech_specs": {
            "Procesador": "Apple A16 Bionic",
            "Memoria RAM": "6 GB",
            "Almacenamiento": "128 GB",
            "Pantalla": "11\" Liquid Retina",
            "Resolución": "2360 x 1640",
            "Sistema Operativo": "iPadOS",
            "Conectividad": "Wi-Fi 6",
            "Marca": "Apple"
        },
        "store_urls": {
            "falabella": "https://www.falabella.com.pe/falabella-pe/product/prod18440041/iPad-Apple-11-Chip-A16-Wi-Fi/21014911",
            "tottus": "https://www.tottus.com.pe/tottus-pe/articulo/150930380/ipad-a16-wifi-128gb-azul/150930381",
            "hiraoka": "https://hiraoka.com.pe/ipad-11-11ma-gen-a16-wifi-128gb-plata",
            "efe": "https://www.efe.com.pe/ipad-a16-wi-fi-md4e4ll-a-11-128gb-6gb-p26513743.html"
        }
    },
    {
        "id": "prod_macbook_air_m1",
        "title": "Apple MacBook Air 13\" Chip M1 512GB SSD 8GB RAM",
        "category": "Laptops",
        "brand": "Apple",
        "fingerprint": {
            "brand": "apple",
            "family_tokens": [
                "macbook",
                "air",
                "13",
                "m1"
            ],
            "screen_inches": 13,
            "storage_gb": 512,
            "ram_gb": 8,
            "network": None,
            "forbidden_tokens": [
                "pro",
                "m2",
                "m3",
                "m4",
                "m5"
            ]
        },
        "description": "La laptop más delgada y liviana de Apple con revolucionario chip M1, CPU de 8 núcleos, diseño silencioso sin ventilador y hasta 18 horas de batería.",
        "features": [
            "Procesador: Apple M1 (8 núcleos)",
            "Memoria RAM: 8 GB unificada",
            "Almacenamiento: 512 GB SSD ultra rápido",
            "Pantalla: 13.3\" Retina retroiluminada por LED",
            "Resolución: 2560 x 1600 píxeles",
            "Batería: Hasta 18 horas de reproducción"
        ],
        "tech_specs": {
            "Procesador": "Apple M1",
            "Memoria RAM": "8 GB",
            "Almacenamiento": "512 GB SSD",
            "Pantalla": "13.3\" Retina LED",
            "Resolución": "2560 x 1600",
            "Sistema Operativo": "macOS",
            "Marca": "Apple"
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/macbook-air-13-m1-512gb-ssd-8gb-ram-gris-espacial"
        }
    },
    {
        "id": "prod_samsung_s25_ultra",
        "title": "Samsung Galaxy S25 Ultra 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Samsung",
        "fingerprint": {
            "brand": "samsung",
            "family_tokens": [
                "galaxy",
                "s25",
                "ultra"
            ],
            "screen_inches": None,
            "storage_gb": 512,
            "ram_gb": 12,
            "network": "5G",
            "forbidden_tokens": [
                "s24",
                "s23",
                "s22",
                "s26",
                "plus"
            ]
        },
        "description": "El estandarte de Samsung con Galaxy AI integrada, procesador Snapdragon 8 Elite for Galaxy, chasis de titanio con S-Pen y cámara cuádruple de 200MP.",
        "features": [
            "Procesador: Snapdragon 8 Elite",
            "Memoria RAM: 12 GB",
            "Almacenamiento: 512 GB",
            "Pantalla: 6.9\" Dynamic AMOLED 2X",
            "Resolución: 3120 x 1440 píxeles",
            "Cámara Principal: 200 MP + 50 MP + 12 MP + 10 MP"
        ],
        "tech_specs": {
            "Procesador": "Snapdragon 8 Elite",
            "Memoria RAM": "12 GB",
            "Almacenamiento": "512 GB",
            "Pantalla": "6.9\" Dynamic AMOLED 2X",
            "Resolución": "3120 x 1440",
            "Sistema Operativo": "Android 15",
            "Conectividad": "5G",
            "Marca": "Samsung"
        },
        "store_urls": {
            "efe": "https://www.efe.com.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html",
            "curacao": "https://www.lacuracao.pe/samsung-galaxy-s25-ultra-512gb-12gb-200m-s25ul-512gray.html"
        }
    },
    {
        "id": "prod_samsung_s24_ultra",
        "title": "Samsung Galaxy S24 Ultra 5G 512GB 12GB RAM",
        "category": "Smartphones",
        "brand": "Samsung",
        "fingerprint": {
            "brand": "samsung",
            "family_tokens": [
                "galaxy",
                "s24",
                "ultra"
            ],
            "screen_inches": None,
            "storage_gb": 512,
            "ram_gb": 12,
            "network": "5G",
            "forbidden_tokens": [
                "s25",
                "s23",
                "s22",
                "plus"
            ]
        },
        "description": "Samsung Galaxy S24 Ultra con chip Snapdragon 8 Gen 3 for Galaxy, marco de titanio, Corning Gorilla Armor y funciones completas de Galaxy AI.",
        "features": [
            "Procesador: Snapdragon 8 Gen 3",
            "Memoria RAM: 12 GB",
            "Almacenamiento: 512 GB",
            "Pantalla: 6.8\" Dynamic AMOLED 2X 120Hz",
            "Resolución: 3120 x 1440 píxeles",
            "Cámara: 200 MP + 50 MP + 12 MP + 10 MP"
        ],
        "tech_specs": {
            "Procesador": "Snapdragon 8 Gen 3",
            "Memoria RAM": "12 GB",
            "Almacenamiento": "512 GB",
            "Pantalla": "6.8\" Dynamic AMOLED 2X",
            "Resolución": "3120 x 1440",
            "Sistema Operativo": "Android 14",
            "Conectividad": "5G",
            "Marca": "Samsung"
        },
        "store_urls": {
            "falabella": "https://www.falabella.com.pe/falabella-pe/product/155039506/samsung-galaxy-s24-ultra-5g-512gb-12gb-ram-negro"
        }
    },
    {
        "id": "prod_samsung_a55",
        "title": "Samsung Galaxy A55 5G 8GB RAM 256GB",
        "category": "Smartphones",
        "brand": "Samsung",
        "fingerprint": {
            "brand": "samsung",
            "family_tokens": [
                "galaxy",
                "a55"
            ],
            "screen_inches": None,
            "storage_gb": 256,
            "ram_gb": 8,
            "network": "5G",
            "forbidden_tokens": [
                "a35",
                "a15",
                "a25",
                "a54",
                "128gb"
            ]
        },
        "description": "Gama media premium con procesador Exynos 1480 con GPU Xclipse 530 de arquitectura AMD RDNA2, diseño en cristal y marco metálico con resistencia IP67.",
        "features": [
            "Procesador: Exynos 1480",
            "Memoria RAM: 8 GB",
            "Almacenamiento: 256 GB",
            "Pantalla: 6.6\" Super AMOLED FHD+ 120Hz",
            "Resolución: 2340 x 1080 píxeles",
            "Cámara Principal: 50 MP con OIS + 12 MP + 5 MP"
        ],
        "tech_specs": {
            "Procesador": "Exynos 1480",
            "Memoria RAM": "8 GB",
            "Almacenamiento": "256 GB",
            "Pantalla": "6.6\" Super AMOLED 120Hz",
            "Resolución": "2340 x 1080",
            "Sistema Operativo": "Android 14",
            "Conectividad": "5G",
            "Marca": "Samsung"
        },
        "store_urls": {
            "falabella": "https://www.falabella.com.pe/falabella-pe/product/158309351/samsung-galaxy-a55-5g-8gb-ram-256gb"
        }
    },
    {
        "id": "prod_samsung_a35",
        "title": "Samsung Galaxy A35 5G 6.6\" 8GB RAM 256GB",
        "category": "Smartphones",
        "brand": "Samsung",
        "fingerprint": {
            "brand": "samsung",
            "family_tokens": [
                "galaxy",
                "a35"
            ],
            "screen_inches": None,
            "storage_gb": 256,
            "ram_gb": 8,
            "network": "5G",
            "forbidden_tokens": [
                "a55",
                "a15",
                "a25",
                "128gb"
            ]
        },
        "description": "Excelente balance calidad-precio con pantalla Infinity-O Super AMOLED a 120Hz, procesador Exynos 1380 octa-core y batería de 5000 mAh para 2 días.",
        "features": [
            "Procesador: Exynos 1380",
            "Memoria RAM: 8 GB",
            "Almacenamiento: 256 GB",
            "Pantalla: 6.6\" Super AMOLED FHD+ 120Hz",
            "Resolución: 2340 x 1080 píxeles",
            "Batería: 5000 mAh con carga de 25W"
        ],
        "tech_specs": {
            "Procesador": "Exynos 1380",
            "Memoria RAM": "8 GB",
            "Almacenamiento": "256 GB",
            "Pantalla": "6.6\" Super AMOLED 120Hz",
            "Resolución": "2340 x 1080",
            "Sistema Operativo": "Android 14",
            "Conectividad": "5G",
            "Marca": "Samsung"
        },
        "store_urls": {
            "falabella": "https://www.falabella.com.pe/falabella-pe/product/158509217/celular-samsung-galaxy-a35-5g-6-6-pulg-8gb-ram-256gb-android-14-negro"
        }
    },
    {
        "id": "prod_lenovo_ideapad_slim",
        "title": "Laptop IA Lenovo IdeaPad Slim 5i de 14\", Intel Core Ultra 9 185H, 16GB RAM, 512GB SSD",
        "category": "Laptops",
        "brand": "Lenovo",
        "fingerprint": {
            "brand": "lenovo",
            "family_tokens": [
                "ideapad",
                "slim",
                "5i",
                "14"
            ],
            "screen_inches": 14,
            "storage_gb": 512,
            "ram_gb": 16,
            "network": None,
            "forbidden_tokens": [
                "ryzen",
                "slim 3"
            ]
        },
        "description": "Laptop impulsada por Inteligencia Artificial con potente procesador Intel Core Ultra 9 185H con NPU dedicada, pantalla OLED de 14 pulgadas y chasis ultradelgado de aluminio militar.",
        "features": [
            "Procesador: Intel Core Ultra 9 185H",
            "Memoria RAM: 16 GB LPDDR5X",
            "Almacenamiento: 512 GB SSD M.2 PCIe",
            "Pantalla: 14\" WUXGA OLED 100% DCI-P3",
            "Resolución: 1920 x 1200 píxeles",
            "Sistema Operativo: Windows 11 Home"
        ],
        "tech_specs": {
            "Procesador": "Intel Core Ultra 9 185H",
            "Memoria RAM": "16 GB",
            "Almacenamiento": "512 GB SSD",
            "Pantalla": "14\" OLED WUXGA",
            "Resolución": "1920 x 1200",
            "Sistema Operativo": "Windows 11 Home",
            "Marca": "Lenovo"
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/laptop-ia-lenovo-ideapad-slim-5i-de-14-intel-core-ultra-9-185h-16gb-ram-disco-solido-de-512gb-modelo-83v6004elm"
        }
    },
    {
        "id": "prod_asus_zenbook_14",
        "title": "Laptop Asus Zenbook A14 de 14\", Copilot+ PC, Qualcomm Snapdragon X, 16GB RAM, 512GB SSD + Funda",
        "category": "Laptops",
        "brand": "Asus",
        "fingerprint": {
            "brand": "asus",
            "family_tokens": [
                "zenbook",
                "a14",
                "14"
            ],
            "screen_inches": 14,
            "storage_gb": 512,
            "ram_gb": 16,
            "network": None,
            "forbidden_tokens": [
                "vivobook",
                "tuf",
                "rog"
            ]
        },
        "description": "Copilot+ PC de última generación con procesador Snapdragon X, 45 TOPS de NPU para IA local, pantalla Asus Lumina OLED 2.8K y hasta 22 horas de autonomía extrema.",
        "features": [
            "Procesador: Snapdragon X Plus",
            "Memoria RAM: 16 GB LPDDR5X",
            "Almacenamiento: 512 GB SSD NVMe PCIe 4.0",
            "Pantalla: 14\" 2.8K (2880 x 1800) OLED 120Hz",
            "Resolución: 2880 x 1800 píxeles",
            "IA: NPU Qualcomm Hexagon de 45 TOPS"
        ],
        "tech_specs": {
            "Procesador": "Snapdragon X Plus",
            "Memoria RAM": "16 GB",
            "Almacenamiento": "512 GB SSD",
            "Pantalla": "14\" OLED 2.8K",
            "Resolución": "2880 x 1800",
            "Sistema Operativo": "Windows 11 Home",
            "Marca": "Asus"
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/laptop-asus-zenbook-a14-de-14-copilot-pc-qualcomm-snapdragon-x-16gb-ram-disco-solido-de-512gb-modelo-ux3407qa-qd289w-funda"
        }
    },
    {
        "id": "prod_samsung_tab_s10",
        "title": "Tablet Samsung Galaxy Tab A11 8.7\" 64GB 4GB RAM",
        "category": "Tablets",
        "brand": "Samsung",
        "fingerprint": {
            "brand": "samsung",
            "family_tokens": [
                "galaxy",
                "tab",
                "a11"
            ],
            "screen_inches": None,
            "storage_gb": 64,
            "ram_gb": 4,
            "network": "Wi-Fi",
            "forbidden_tokens": [
                "s9",
                "s10",
                "ultra",
                "plus"
            ]
        },
        "description": "Tableta portátil de 8.7 pulgadas con marco metálico ligero, altavoces duales con sonido Dolby Atmos, procesador Octa-Core y batería de larga duración.",
        "features": [
            "Procesador: MediaTek Helio G99 Octa-Core",
            "Memoria RAM: 4 GB",
            "Almacenamiento: 64 GB ampliable hasta 1TB con microSD",
            "Pantalla: 8.7\" TFT LCD WXGA+",
            "Resolución: 1340 x 800 píxeles",
            "Audio: Altavoces duales Dolby Atmos"
        ],
        "tech_specs": {
            "Procesador": "MediaTek Helio G99",
            "Memoria RAM": "4 GB",
            "Almacenamiento": "64 GB",
            "Pantalla": "8.7\" TFT LCD",
            "Resolución": "1340 x 800",
            "Sistema Operativo": "Android 14",
            "Conectividad": "Wi-Fi",
            "Marca": "Samsung"
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/tablet-samsung-galaxy-tab-a11-8-7-64gb-4gb-ram-gray"
        }
    },
    {
        "id": "prod_samsung_neo_qled_65",
        "title": "Televisor Samsung Smart TV 85\" Neo QLED 4K QN85QN70HAGXPE",
        "category": "TVs",
        "brand": "Samsung",
        "fingerprint": {
            "brand": "samsung",
            "family_tokens": [
                "neo",
                "qled",
                "85"
            ],
            "screen_inches": 85,
            "storage_gb": None,
            "ram_gb": None,
            "network": None,
            "forbidden_tokens": [
                "55",
                "65",
                "75"
            ]
        },
        "description": "Gigantesco televisor Samsung Neo QLED de 85 pulgadas con Quantum Matrix Technology, procesador NQ4 AI Gen2 con escalado a 4K por redes neuronales y Motion Xcelerator 120Hz.",
        "features": [
            "Pantalla: 85\" Neo QLED 4K con Mini LED",
            "Resolución: 3840 x 2160 (4K UHD)",
            "Procesador: NQ4 AI Gen2 Processor",
            "Tasa de Refresco: 120 Hz nativo",
            "Sonido: OTS Lite y Dolby Atmos con Q-Symphony"
        ],
        "tech_specs": {
            "Resolución": "3840 x 2160 (4K UHD)",
            "Pantalla": "85\" Neo QLED 120Hz",
            "Sistema Operativo": "Tizen OS",
            "Marca": "Samsung",
            "Tasa de Refresco": "120 Hz",
            "Conectividad": "Wi-Fi 5, Bluetooth 5.2, 4 x HDMI"
        },
        "store_urls": {
            "hiraoka": "https://hiraoka.com.pe/televisor-samsung-smart-tv-85-neo-qled-4k-qn85qn70hagxpe"
        }
    }
]

VERIFIED_URL_CACHE: Dict[str, Dict[str, str]] = {}


def get_catalog_product(product_id: str) -> Optional[Dict[str, Any]]:
    """Retorna la especificación canónica de un producto por su identificador."""
    for item in CATALOG_PRODUCTS:
        if item.get("id") == product_id:
            return item
    return None


def get_all_catalog_products() -> List[Dict[str, Any]]:
    """Retorna la lista completa de productos canónicos oficiales."""
    return list(CATALOG_PRODUCTS)


def get_verified_store_urls(
    product_id: str,
    extra_seed_urls: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Retorna el mapa consolidado de {store_id: url} verificadas para un producto.
    Combina la caché en memoria, las URLs semilla estáticas de CATALOG_PRODUCTS
    y opcionalmente URLs adicionales provistas externamente.
    """
    merged: Dict[str, str] = {}
    cached = VERIFIED_URL_CACHE.get(product_id) or {}
    for s_id, raw_u in cached.items():
        _, clean_u = canonicalize_store_url(raw_u)
        if clean_u:
            merged[s_id] = clean_u

    for item in CATALOG_PRODUCTS:
        if item.get("id") == product_id:
            for s_id, raw_u in (item.get("store_urls") or {}).items():
                _, clean_u = canonicalize_store_url(raw_u)
                if clean_u:
                    merged[s_id] = clean_u
            break

    if extra_seed_urls:
        for s_id, raw_u in extra_seed_urls.items():
            _, clean_u = canonicalize_store_url(raw_u)
            if clean_u:
                merged[s_id] = clean_u

    return merged


get_verified_store_urls_for_product = get_verified_store_urls


def register_verified_store_url(product_id: str, store_id: str, offer_url: str) -> None:
    """
    Registra una URL real verificada en la caché en memoria para acelerar
    futuras ejecuciones del grafo.
    """
    if not product_id or not store_id or not offer_url:
        return
    detected_store, clean_u = canonicalize_store_url(offer_url)
    if not clean_u or (detected_store != "unknown" and detected_store != store_id):
        return
    VERIFIED_URL_CACHE.setdefault(product_id, {})[store_id] = clean_u


async def load_persisted_urls_from_db(
    session: Any,
    product_id: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    """
    Sincroniza la caché de URLs verificadas leyendo las StoreOfferEntity reales
    persistidas en la base de datos SQLite/PostgreSQL.
    """
    from sqlalchemy import select
    from app.models.entities import StoreOfferEntity

    stmt = select(StoreOfferEntity)
    if product_id:
        stmt = stmt.where(StoreOfferEntity.product_id == product_id)

    res = await session.execute(stmt)
    offers = res.scalars().all()
    for off in offers:
        if off.product_id and off.store_id and off.offer_url:
            register_verified_store_url(off.product_id, off.store_id, off.offer_url)

    return VERIFIED_URL_CACHE
