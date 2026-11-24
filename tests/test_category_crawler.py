"""
Pruebas unitarias e integración en SQLite temporal para Fase 2A:
1. Registro declarativo de categorías tech (`category_registry.py`) en las 8 tiendas 1P.
2. Clasificador genérico `infer_tech_category`.
3. Parseo en bloque de listados por tienda con filtro estricto 1P (rechazo de marketplace).
4. Upsert idempotente en `store_listings` sin duplicados ni alteración de tablas previas.
5. Modo CLI `--discover-categories` (incluyendo `--dry-run`) en `app/worker.py`.
"""
import json
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.collectors.category_crawler import (
    build_listing_signature,
    crawl_categories,
    parse_category_listing_page,
    upsert_store_listings,
)
from app.collectors.category_registry import (
    ALL_TECH_CATEGORIES,
    ALL_TECH_STORES,
    CATEGORY_REGISTRY,
    StoreCategorySource,
    build_paginated_category_url,
    get_category_spec,
    get_store_category_sources,
    infer_tech_category,
)
from app.core.database import Base
from app.models.entities import (
    PriceHistoryEntity,
    ProductEntity,
    StoreListing,
    StoreOfferEntity,
)


def test_category_registry_covers_all_14_categories_and_8_stores():
    expected_categories = {
        "celulares",
        "laptops",
        "tablets",
        "televisores",
        "impresoras",
        "consolas",
        "monitores",
        "audifonos",
        "smartwatches",
        "audio",
        "camaras",
        "almacenamiento_redes",
        "accesorios_pc",
        "smart_home",
    }
    assert set(ALL_TECH_CATEGORIES) == expected_categories
    assert set(CATEGORY_REGISTRY.keys()) == expected_categories

    for cat_slug in expected_categories:
        spec = get_category_spec(cat_slug)
        assert spec is not None
        assert set(spec.store_sources.keys()) == set(ALL_TECH_STORES)
        for store_id in ALL_TECH_STORES:
            sources = spec.store_sources[store_id]
            assert len(sources) >= 1
            for src in sources:
                assert src.store == store_id
                assert src.category == cat_slug
                assert src.url.startswith("https://")

    filtered = get_store_category_sources(
        stores=["falabella", "hiraoka"],
        categories=["consolas", "monitores"],
    )
    assert [(s.store, s.category) for s in filtered] == [
        ("falabella", "consolas"),
        ("hiraoka", "consolas"),
        ("falabella", "monitores"),
        ("hiraoka", "monitores"),
    ]


def test_build_paginated_category_url_strategies():
    src_fala = StoreCategorySource(
        store="falabella",
        category="monitores",
        url="https://www.falabella.com.pe/falabella-pe/category/cat40695/Monitores?f.derived.variant.sellerId=FALABELLA",
        pagination="query_page",
    )
    u_fala_p2 = build_paginated_category_url(src_fala, 2)
    assert "f.derived.variant.sellerId=FALABELLA" in u_fala_p2
    assert "page=2" in u_fala_p2

    src_efe = StoreCategorySource(
        store="efe",
        category="consolas",
        url="https://www.efe.com.pe/catalogsearch/result/?q=consolas",
        pagination="query_p",
    )
    assert build_paginated_category_url(src_efe, 1) == "https://www.efe.com.pe/catalogsearch/result/?q=consolas"
    u_efe_p2 = build_paginated_category_url(src_efe, 2)
    assert "q=consolas" in u_efe_p2
    assert "p=2" in u_efe_p2

    src_vtex = StoreCategorySource(
        store="metro",
        category="consolas",
        url="https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/zona-gamer/consolas",
        pagination="vtex_range",
        page_size=24,
    )
    assert "_from=0" in build_paginated_category_url(src_vtex, 1)
    assert "_to=23" in build_paginated_category_url(src_vtex, 1)
    assert "_from=24" in build_paginated_category_url(src_vtex, 2)
    assert "_to=47" in build_paginated_category_url(src_vtex, 2)

    with pytest.raises(ValueError):
        build_paginated_category_url(src_fala, 0)


@pytest.mark.parametrize(
    "title,url,expected",
    [
        ("Consola Sony PlayStation 5 Slim Digital 1TB", "", "consolas"),
        ("Consola Nintendo Switch 2 + Mario Kart Bundle", "", "consolas"),
        ("Juego PS5 Spider-Man 2 Edición Estándar", "", "otros_tech"),
        ('Monitor Gaming LG UltraGear 27" QHD 180Hz', "", "monitores"),
        ('Monitor Acer 15.6" Full HD con Parlantes', "", "monitores"),
        ("Audífonos Bluetooth Sony WH-1000XM5 Negro", "", "audifonos"),
        ("Apple AirPods Pro 2da Generación USB-C", "", "audifonos"),
        ("Samsung Galaxy Watch 7 44mm Bluetooth", "", "smartwatches"),
        ('Laptop Lenovo IdeaPad Slim 3 15.6" Ryzen 5 16GB 512GB', "", "laptops"),
        ('Laptop Asus VivoBook 15" con Parlantes SonicMaster', "", "laptops"),
        ('Tablet Samsung Galaxy Tab S10 FE 11" 128GB', "", "tablets"),
        ('iPad Apple 11" Chip A16 Wi-Fi 128GB', "", "tablets"),
        ('Televisor LG OLED 55" 4K Smart TV C6', "", "televisores"),
        ("Impresora Multifuncional Epson EcoTank L3250 Wi-Fi", "", "impresoras"),
        ("Botella de Tinta Original Epson EcoTank T504 Negro", "", "otros_tech"),
        ("Parlante Bluetooth JBL Charge 5 Portátil", "", "audio"),
        ("Cámara Mirrorless Sony Alpha A7 IV", "", "camaras"),
        ("Cámara de Seguridad Wi-Fi TP-Link Tapo C200", "", "smart_home"),
        ("Parlante Inteligente Amazon Echo Dot 5ta Gen Alexa", "", "smart_home"),
        ("Disco SSD Externo Samsung T7 1TB USB 3.2", "", "almacenamiento_redes"),
        ("Router Wi-Fi 6 TP-Link Archer AX55 Dual Band", "", "almacenamiento_redes"),
        ("Mouse Inalámbrico Logitech MX Master 3S", "", "accesorios_pc"),
        ("Teclado Mecánico Gamer HyperX Alloy Origins", "", "accesorios_pc"),
        ("Celular Xiaomi Redmi Note 14 Pro 5G 256GB + Audífonos", "", "celulares"),
        ("Mochila Ejecutiva para Laptop 15.6 Pulgadas", "", "otros_tech"),
        ("Termo de Acero Inoxidable 1 Litro", "", "otros_tech"),
    ],
)
def test_infer_tech_category_generic(title, url, expected):
    assert infer_tech_category(title=title, url=url) == expected


def test_parse_falabella_and_tottus_strict_1p_and_prices():
    fala_payload = {
        "props": {
            "pageProps": {
                "results": [
                    {
                        "productId": "80146897",
                        "skuId": "80146897",
                        "displayName": 'Monitor Gaming Odyssey G7 27" UHD',
                        "brand": "SAMSUNG",
                        "sellerId": "FALABELLA_PERU",
                        "sellerName": "Falabella",
                        "url": "https://www.falabella.com.pe/falabella-pe/product/80146897/monitor-gaming-odyssey-g7",
                        "prices": [
                            {"type": "cmrPrice", "price": ["1,899"], "crossed": False},
                            {"type": "internetPrice", "price": ["1,999"], "crossed": False},
                            {"type": "normalPrice", "price": ["2,599"], "crossed": True},
                        ],
                        "mediaUrls": ["https://media.falabella.com.pe/falabellaPE/80146897_1/public"],
                    },
                    {
                        "productId": "99000111",
                        "skuId": "99000111",
                        "displayName": "Monitor Teros 24 Full HD",
                        "brand": "TEROS",
                        "sellerId": "SC919A7",
                        "sellerName": "Grupo Adratec S.A.C.",
                        "isMarketplace": True,
                        "url": "https://www.falabella.com.pe/falabella-pe/product/99000111/monitor-teros",
                        "prices": [{"type": "internetPrice", "price": ["299"], "crossed": False}],
                    },
                ]
            }
        }
    }
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(fala_payload)}</script></html>'
    spec = get_category_spec("monitores")
    assert spec is not None

    parsed = parse_category_listing_page(
        store="falabella",
        html_or_json=html,
        page_url="https://www.falabella.com.pe/falabella-pe/category/cat40695/Monitores",
        category_spec=spec,
    )
    assert parsed.raw_cards_seen == 2
    assert parsed.discarded_marketplace == 1
    assert len(parsed.listings) == 1

    item = parsed.listings[0]
    assert item.store == "falabella"
    assert item.store_sku == "80146897"
    assert item.category == "monitores"
    assert item.brand == "Samsung"
    assert item.price == 1899.0
    assert item.original_price == 2599.0
    assert item.seller_name == "Falabella"
    assert item.url == "https://www.falabella.com.pe/falabella-pe/product/80146897/monitor-gaming-odyssey-g7/80146897"
    assert item.image_url == "https://media.falabella.com.pe/falabellaPE/80146897_1/w=800,h=800,fit=pad"
    assert "odyssey" in item.normalized_signature


def test_parse_ripley_strict_1p_rejects_marketplace_and_pmp():
    ripley_payload = {
        "props": {
            "pageProps": {
                "findabilityProps": {
                    "data": {
                        "products": [
                            {
                                "sku": "2031378938822",
                                "parentProductID": "2031378938822P",
                                "name": "CONSOLA NINTENDO SWITCH 2 + EA SPORTS FC 27 BUNDLE",
                                "brand": "NINTENDO",
                                "priceNumber": 2099,
                                "masterPriceNumber": 2589,
                                "inStock": True,
                                "seller": "RIPLEY",
                                "images": ["https://rimage.ripley.com.pe/home.ripley/Attachment/WOP/1/2031378938822/full_image-2031378938822.webp"],
                            },
                            {
                                "sku": "9169674",
                                "parentProductID": "PMP20001534044",
                                "name": "CONSOLA PLAYSTATION 5 SLIM DIGITAL",
                                "brand": "SONY",
                                "priceNumber": 2999,
                                "masterPriceNumber": 3499,
                                "inStock": True,
                                "seller": "MARKETPLACE",
                                "isMarketplaceProduct": True,
                            },
                            {
                                "sku": "2031370000111",
                                "parentProductID": "2031370000111P",
                                "name": "Juego EA Sports FC 26 PS5",
                                "brand": "EA",
                                "priceNumber": 389,
                                "masterPriceNumber": 389,
                                "inStock": True,
                                "seller": "RIPLEY",
                            },
                        ]
                    }
                }
            }
        }
    }
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(ripley_payload)}</script></html>'
    spec = get_category_spec("consolas")
    assert spec is not None

    parsed = parse_category_listing_page(
        store="ripley",
        html_or_json=html,
        page_url="https://simple.ripley.com.pe/tecnologia/videojuegos/consolas?s=mdco",
        category_spec=spec,
    )
    assert parsed.raw_cards_seen == 3
    assert parsed.discarded_marketplace == 1
    assert parsed.discarded_filtered == 1
    assert len(parsed.listings) == 1
    assert parsed.listings[0].store_sku == "2031378938822P"
    assert parsed.listings[0].price == 2099.0
    assert parsed.listings[0].original_price == 2589.0


def test_parse_magento_strict_1p_efe_and_hiraoka():
    efe_html = """
    <html><body><main><div class="products wrapper">
      <ol class="products list items product-items">
        <li class="item product product-item">
          <div class="product-item-info">
            <img class="product-image-photo" src="https://www.efe.com.pe/media/catalog/product/a/1/a17.jpg" />
            <a class="product-item-link" href="https://www.efe.com.pe/galaxy-a17-256gb-negro-sm-a175fzkkltp.html">
              Celular Samsung Galaxy A17 256GB 8GB 6.7" Negro
            </a>
            <div class="label-sold-by">Por Tiendas EFE</div>
            <div class="price-box" data-product-id="375560">
              <span data-price-type="finalPrice" data-price-amount="1099"><span class="price">S/ 1,099.00</span></span>
              <span data-price-type="oldPrice" data-price-amount="1595"><span class="price">S/ 1,595.00</span></span>
            </div>
          </div>
        </li>
        <li class="item product product-item">
          <div class="product-item-info">
            <a class="product-item-link" href="https://www.efe.com.pe/celular-tercero-128gb.html">
              Celular Xiaomi Redmi 14C 128GB
            </a>
            <div class="label-sold-by">Por Coolbox</div>
            <div class="price-box" data-product-id="999001">
              <span data-price-type="finalPrice" data-price-amount="499"><span class="price">S/ 499.00</span></span>
            </div>
          </div>
        </li>
      </ol>
    </div></main></body></html>
    """
    spec_cel = get_category_spec("celulares")
    assert spec_cel is not None
    parsed_efe = parse_category_listing_page(
        store="efe",
        html_or_json=efe_html,
        page_url="https://www.efe.com.pe/tecnologia/celulares.html",
        category_spec=spec_cel,
    )
    assert parsed_efe.raw_cards_seen == 2
    assert parsed_efe.discarded_marketplace == 1
    assert len(parsed_efe.listings) == 1
    assert parsed_efe.listings[0].store_sku == "375560"
    assert parsed_efe.listings[0].mpn == "sma175fzkkltp"
    assert parsed_efe.listings[0].price == 1099.0
    assert parsed_efe.listings[0].original_price == 1595.0

    hiraoka_html = """
    <html><body><main><div class="column main"><div class="products wrapper">
      <ol class="products list items product-items">
        <li class="item product product-item">
          <div class="product-item-info">
            <img class="product-image-photo" src="https://hiraoka.com.pe/media/catalog/product/m/o/mon.jpg" />
            <a class="product-item-link" href="https://hiraoka.com.pe/monitor-lg-u4-27-full-hd-27u411b">LG</a>
            <a class="product-item-link" href="https://hiraoka.com.pe/monitor-lg-u4-27-full-hd-27u411b">Monitor LG U4 27" Full HD 27U411B</a>
            <span>Código 140764</span>
            <div class="price-box" data-product-id="111677">
              <span data-price-type="finalPrice" data-price-amount="399"><span class="price">S/ 399.00</span></span>
              <span data-price-type="oldPrice" data-price-amount="469"><span class="price">S/ 469.00</span></span>
            </div>
          </div>
        </li>
      </ol>
    </div></div></main></body></html>
    """
    spec_mon = get_category_spec("monitores")
    assert spec_mon is not None
    parsed_hira = parse_category_listing_page(
        store="hiraoka",
        html_or_json=hiraoka_html,
        page_url="https://hiraoka.com.pe/computo-y-tablets/monitores",
        category_spec=spec_mon,
    )
    assert len(parsed_hira.listings) == 1
    assert parsed_hira.listings[0].brand == "LG"
    assert parsed_hira.listings[0].store_sku == "140764"
    assert parsed_hira.listings[0].price == 399.0


def test_parse_vtex_strict_1p_and_accessory_category_behavior():
    vtex_payload = [
        {
            "productId": "1082705",
            "productName": "Consola PS5 Slim Standard",
            "brand": "Sony",
            "productReference": "CFI-2015A",
            "link": "https://www.metro.pe/consola-ps5-slim-1082705/p",
            "items": [
                {
                    "itemId": "108270501",
                    "ean": "711719570974",
                    "images": [{"imageUrl": "https://metroio.vtexassets.com/arquivos/ids/123/ps5.jpg"}],
                    "sellers": [
                        {
                            "sellerId": "2045",
                            "sellerName": "Seller Tercero",
                            "commertialOffer": {"Price": 1899.0, "ListPrice": 2199.0, "AvailableQuantity": 5},
                        },
                        {
                            "sellerId": "1",
                            "sellerName": "CENCOSUD RETAIL PERU S.A.",
                            "commertialOffer": {
                                "Price": 2399.0,
                                "ListPrice": 2799.0,
                                "AvailableQuantity": 8,
                                "PromotionTeasers": [
                                    {
                                        "Name": "A 2249 Con TC",
                                        "Effects": {
                                            "Parameters": [{"Name": "MaximumUnitPriceDiscount", "Value": "224900"}]
                                        },
                                    }
                                ],
                            },
                        },
                    ],
                }
            ],
        },
        {
            "productId": "999999",
            "productName": "Consola Xbox Series X 1TB",
            "brand": "Microsoft",
            "link": "https://www.metro.pe/consola-xbox-999999/p",
            "items": [
                {
                    "itemId": "99999901",
                    "sellers": [
                        {
                            "sellerId": "3333",
                            "sellerName": "Tercero Mkp",
                            "commertialOffer": {"Price": 2499.0, "AvailableQuantity": 3},
                        }
                    ],
                }
            ],
        },
    ]
    spec_con = get_category_spec("consolas")
    assert spec_con is not None
    parsed = parse_category_listing_page(
        store="metro",
        html_or_json=json.dumps(vtex_payload),
        page_url="https://www.metro.pe/api/catalog_system/pub/products/search/tecnologia/zona-gamer/consolas",
        category_spec=spec_con,
    )
    assert parsed.raw_cards_seen == 2
    assert parsed.discarded_marketplace == 1
    assert len(parsed.listings) == 1
    item = parsed.listings[0]
    assert item.price == 2249.0
    assert item.original_price == 2799.0
    assert item.ean == "711719570974"
    assert item.mpn == "cfi2015a"

    # En categoría de accesorios (`accesorios_pc`), los mouses y teclados SÍ deben aceptarse
    spec_acc = get_category_spec("accesorios_pc")
    assert spec_acc is not None
    vtex_acc = [
        {
            "productId": "5001",
            "productName": "Mouse Gamer Inalámbrico G305",
            "brand": "Logitech",
            "link": "https://www.wong.pe/mouse-logitech-g305-5001/p",
            "items": [
                {
                    "itemId": "500101",
                    "sellers": [
                        {
                            "sellerId": "1",
                            "sellerName": "WongIO",
                            "commertialOffer": {"Price": 179.0, "ListPrice": 219.0, "AvailableQuantity": 4},
                        }
                    ],
                }
            ],
        }
    ]
    parsed_acc = parse_category_listing_page(
        store="wong",
        html_or_json=json.dumps(vtex_acc),
        page_url="https://www.wong.pe/api/catalog_system/pub/products/search/tecnologia/computo/accesorios-de-computo",
        category_spec=spec_acc,
    )
    assert len(parsed_acc.listings) == 1
    assert parsed_acc.listings[0].category == "accesorios_pc"


def test_build_listing_signature_normalizes_specs_and_strips_colors():
    sig1 = build_listing_signature("Celular Samsung Galaxy S25 Ultra 12 GB 512 GB Negro Titanio 5G", "Samsung")
    sig2 = build_listing_signature("Smartphone Galaxy S25 Ultra 12/512GB Titanium Silver", "Samsung")
    assert "negro" not in sig1
    assert "titanio" not in sig1
    assert "12gb" in sig1 and "512gb" in sig1
    assert sig1 == sig2


@pytest.mark.asyncio
async def test_idempotent_upsert_and_crawl_categories_on_temp_sqlite(tmp_path):
    db_file = tmp_path / "phase2a_test.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Sembrar filas en products, store_offers y price_history para comprobar retrocompatibilidad total
    async with SessionMaker() as session:
        session.add(
            ProductEntity(
                id="prod_keep_intact",
                title="Apple iPhone 16 128GB",
                category="Smartphones",
                brand="Apple",
                best_price=3299.0,
                original_price=3999.0,
                best_store_name="Falabella",
                best_store_url="https://www.falabella.com.pe/falabella-pe/product/1/iphone/1",
            )
        )
        session.add(
            StoreOfferEntity(
                product_id="prod_keep_intact",
                store_id="falabella",
                store_name="Falabella",
                price=3299.0,
                original_price=3999.0,
                offer_url="https://www.falabella.com.pe/falabella-pe/product/1/iphone/1",
                is_best_price=True,
            )
        )
        session.add(
            PriceHistoryEntity(
                product_id="prod_keep_intact",
                day_offset=0,
                date_label="24 Nov",
                recorded_date="2026-11-24",
                price=3299.0,
            )
        )
        await session.commit()

    page1_data = {
        "props": {
            "pageProps": {
                "results": [
                    {
                        "productId": "1001",
                        "skuId": "1001",
                        "displayName": "Consola PlayStation 5 Slim 1TB",
                        "brand": "SONY",
                        "sellerName": "Falabella",
                        "url": "https://www.falabella.com.pe/falabella-pe/product/1001/ps5-slim",
                        "prices": [
                            {"type": "cmrPrice", "price": ["2,199"], "crossed": False},
                            {"type": "normalPrice", "price": ["2,699"], "crossed": True},
                        ],
                    },
                    {
                        "productId": "1002",
                        "skuId": "1002",
                        "displayName": "Consola Switch Oled Tercero",
                        "brand": "NINTENDO",
                        "sellerName": "Marketplace X",
                        "isMarketplace": True,
                        "url": "https://www.falabella.com.pe/falabella-pe/product/1002/switch-oled",
                        "prices": [{"type": "internetPrice", "price": ["1,299"], "crossed": False}],
                    },
                ]
            }
        }
    }
    page2_empty = {"props": {"pageProps": {"results": []}}}

    current_price = ["2,199"]
    current_oos = False

    async def fake_fetch(url: str):
        if "page=2" in url:
            return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(page2_empty)}</script></html>'
        payload = json.loads(json.dumps(page1_data))
        payload["props"]["pageProps"]["results"][0]["prices"][0]["price"] = list(current_price)
        payload["props"]["pageProps"]["results"][0]["isOutOfStock"] = current_oos
        return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'

    # 1. Dry-run NO debe escribir nada en store_listings
    dry_summary = await crawl_categories(
        stores=["falabella"],
        categories=["consolas"],
        max_pages=2,
        dry_run=True,
        session_factory=SessionMaker,
        fetch_fn=fake_fetch,
    )
    assert dry_summary.dry_run is True
    assert dry_summary.extracted_1p == 1
    assert dry_summary.inserted == 0
    assert dry_summary.discarded_marketplace == 1
    async with SessionMaker() as session:
        assert (await session.execute(select(func.count(StoreListing.id)))).scalar() == 0

    # 2. Primera corrida real -> inserta 1 fila
    summary1 = await crawl_categories(
        stores=["falabella"],
        categories=["consolas"],
        max_pages=2,
        dry_run=False,
        session_factory=SessionMaker,
        fetch_fn=fake_fetch,
    )
    assert summary1.extracted_1p == 1
    assert summary1.inserted == 1
    assert summary1.updated == 0
    assert summary1.discarded_marketplace == 1

    async with SessionMaker() as session:
        row1 = (await session.execute(select(StoreListing))).scalar_one()
        first_seen_orig = row1.first_seen_at
        row1.canonical_product_id = "prod_ps5_slim"
        await session.commit()

    # 3. Segunda corrida con nuevo precio y stock=False -> actualiza sin duplicar
    current_price = ["2,049"]
    current_oos = True
    summary2 = await crawl_categories(
        stores=["falabella"],
        categories=["consolas"],
        max_pages=2,
        dry_run=False,
        session_factory=SessionMaker,
        fetch_fn=fake_fetch,
    )
    assert summary2.extracted_1p == 1
    assert summary2.inserted == 0
    assert summary2.updated == 1

    async with SessionMaker() as session:
        rows = list((await session.execute(select(StoreListing))).scalars().all())
        assert len(rows) == 1
        assert rows[0].price == 2049.0
        assert rows[0].in_stock is False
        assert rows[0].first_seen_at == first_seen_orig
        assert rows[0].canonical_product_id == "prod_ps5_slim"
        assert rows[0].last_seen_at >= first_seen_orig

        # Verificar que las tablas existentes quedaron intactas
        assert (await session.execute(select(func.count(ProductEntity.id)))).scalar() == 1
        assert (await session.execute(select(func.count(StoreOfferEntity.id)))).scalar() == 1
        assert (await session.execute(select(func.count(PriceHistoryEntity.id)))).scalar() == 1

        # Verificar también deduplicación en memoria cuando upsert_store_listings recibe repetidos
        ins_dup, upd_dup = await upsert_store_listings(session, [summary2.listings[0], summary2.listings[0]])
        assert ins_dup == 0 and upd_dup == 1
        assert (await session.execute(select(func.count(StoreListing.id)))).scalar() == 1

    await test_engine.dispose()


def test_worker_cli_discover_categories_dry_run(monkeypatch, capsys):
    from app import worker as worker_mod

    with pytest.raises(SystemExit):
        worker_mod.main(["--discover-categories", "--categories", "categoria_inexistente"])

    fala_html = """
    <html><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"results":[
      {"productId":"111","skuId":"111","displayName":"Consola PS5 Slim Digital","brand":"SONY","sellerName":"Falabella","url":"https://www.falabella.com.pe/falabella-pe/product/111/ps5","prices":[{"type":"internetPrice","price":["2,199"],"crossed":false}]},
      {"productId":"222","skuId":"222","displayName":"Consola Switch","brand":"NINTENDO","sellerName":"Marketplace","isMarketplace":true,"url":"https://www.falabella.com.pe/falabella-pe/product/222/sw","prices":[{"type":"internetPrice","price":["1,399"],"crossed":false}]}
    ]}}}
    </script></html>
    """
    hira_html = """
    <html><body><main><div class="column main"><div class="products wrapper">
      <ol class="products list items">
        <li class="item product product-item">
          <div class="product-item-info">
            <a class="product-item-link" href="https://hiraoka.com.pe/monitor-lg-27">LG</a>
            <a class="product-item-link" href="https://hiraoka.com.pe/monitor-lg-27">Monitor LG 27" Full HD</a>
            <div class="price-box" data-product-id="5551">
              <span data-price-type="finalPrice" data-price-amount="499"><span class="price">S/ 499.00</span></span>
            </div>
          </div>
        </li>
      </ol>
    </div></div></main></body></html>
    """

    async def fake_fetch(url: str, *args, **kwargs):
        if "falabella" in url:
            return fala_html if "consolas" in url else "<html></html>"
        if "hiraoka" in url:
            return hira_html if "monitores" in url else "<html></html>"
        return "<html></html>"

    async def forbid_db(*args, **kwargs):
        raise AssertionError("--dry-run no debe inicializar ni escribir en Neon/BD")

    monkeypatch.setattr("app.collectors.category_crawler.fetch_page", fake_fetch)
    monkeypatch.setattr(worker_mod, "init_db", forbid_db)
    monkeypatch.setattr(worker_mod, "bootstrap_worker_db", forbid_db)

    exit_code = worker_mod.main(
        [
            "--discover-categories",
            "--stores",
            "falabella,hiraoka",
            "--categories",
            "consolas,monitores",
            "--max-pages",
            "1",
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "DRY-RUN" in out
    assert "falabella" in out
    assert "hiraoka" in out
    assert "extraídos_1p=2" in out
    assert "descartados_marketplace=1" in out
