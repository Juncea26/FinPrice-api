"""
Pruebas automatizadas en SQLite temporal para Fase 2B y 2C:
1. Corrección de rutas de Ripley en `category_registry.py` (`accesorios_pc`, `almacenamiento_redes`).
2. Normalización y guardrails estrictos para las 14 categorías tecnológicas.
3. Agrupación y promoción idempotente (`store_listings` -> `products` + `store_offers` + `price_history`),
   incluyendo enlace a semilla `prod_*`, grupos multi-tienda, productos de 1 sola tienda y preservación
   de `auto_*` en `sync_and_upsert_catalog(overwrite_live=False)` y `sanitize_database_offers`.
4. CLI `--promote-catalog --dry-run` y `--sync-categories-and-promote` sin tocar BD en dry-run.
5. Paginación y filtros retrocompatibles en `GET /api/v1/products`.
"""
from datetime import date, timedelta
import json
import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.collectors.catalog_promoter import promote_store_listings
from app.collectors.category_registry import (
    get_category_spec,
    matches_category_filter,
    resolve_category_display_name,
)
from app.collectors.orchestrator import orchestrator
from app.collectors.tech_normalizer import (
    are_listings_variant_compatible,
    build_canonical_product_signature,
    evaluate_strict_guardrails,
    extract_variant_profile,
)
from app.core.database import Base, get_read_db
from app.core.seed_data import SEED_PRODUCTS, sync_and_upsert_catalog
from app.models.entities import (
    PriceHistoryEntity,
    ProductEntity,
    StoreListing,
    StoreOfferEntity,
)
from app.services.catalog_service import catalog_service
from main import app


def test_ripley_routes_fixed_and_category_aliases():
    acc_spec = get_category_spec("accesorios_pc")
    assert acc_spec is not None
    ripley_acc_urls = [s.url for s in acc_spec.store_sources["ripley"]]
    assert all("accesorios-computacion" not in u for u in ripley_acc_urls)
    assert any("/tecnologia/computacion/mouse" in u for u in ripley_acc_urls)
    assert any("/tecnologia/computacion/teclados" in u for u in ripley_acc_urls)

    net_spec = get_category_spec("almacenamiento_redes")
    assert net_spec is not None
    ripley_net_urls = [s.url for s in net_spec.store_sources["ripley"]]
    assert any("disco-duro-y-memorias" in u for u in ripley_net_urls)
    assert any("routers-y-modems" in u for u in ripley_net_urls)

    assert resolve_category_display_name("celulares") == "Smartphones"
    assert resolve_category_display_name("consolas") == "Consolas"
    assert matches_category_filter("Smartphones", "celulares") is True
    assert matches_category_filter("Consolas", "consolas") is True
    assert matches_category_filter("TVs", "televisores") is True


def test_14_category_signatures_and_strict_variant_separation():
    # Coincidencia multi-tienda correcta en consolas, monitores, audífonos, smartwatches y accesorios
    s_ps5_a = build_canonical_product_signature("Consola Sony PlayStation 5 Slim 1TB", "Sony", category="consolas")
    s_ps5_b = build_canonical_product_signature("Consola PS5 Slim 1 TB Con Lectora", "Sony", category="consolas")
    assert s_ps5_a == s_ps5_b

    s_mon_a = build_canonical_product_signature('Monitor Gaming LG UltraGear 27" QHD 180Hz IPS 27GS75Q-B', "LG", category="monitores")
    s_mon_b = build_canonical_product_signature("Monitor LG 27'' IPS 180Hz QHD UltraGear 27GS75Q", "LG", category="monitores")
    assert s_mon_a == s_mon_b

    s_aud_a = build_canonical_product_signature("Apple AirPods Pro 3ra Generación USB-C", "Apple", category="audifonos")
    s_aud_b = build_canonical_product_signature("Audífonos Apple AirPods Pro 3", "Apple", category="audifonos")
    assert s_aud_a == s_aud_b

    s_w_a = build_canonical_product_signature("Samsung Galaxy Watch 7 44mm Bluetooth", "Samsung", category="smartwatches")
    s_w_b = build_canonical_product_signature("Smartwatch Samsung Galaxy Watch7 BT 44 mm Verde", "Samsung", category="smartwatches")
    assert s_w_a == s_w_b

    # Teclado Logitech + Mouse MK470 NO debe perder "+ Mouse MK470"
    s_mk470 = build_canonical_product_signature("Teclado Logitech + Mouse MK470", "Logitech", category="accesorios_pc")
    s_mk270 = build_canonical_product_signature("Teclado Logitech + Mouse MK270", "Logitech", category="accesorios_pc")
    assert "mk470" in s_mk470 and "mouse" in s_mk470
    assert s_mk470 != s_mk270

    # Pares estrictamente incompatibles
    incompatible_pairs = [
        ("consolas", "Consola PlayStation 5 Slim 1TB", "Consola PlayStation 5 Pro 2TB"),
        ("consolas", "Consola PlayStation 5 Slim 1TB Con Lectora", "Consola PlayStation 5 Slim Digital 1TB"),
        ("consolas", "Consola Nintendo Switch 64GB", "Consola Nintendo Switch OLED 64GB"),
        ("consolas", "Consola Nintendo Switch OLED 64GB", "Consola Nintendo Switch 2 256GB"),
        ("consolas", "Consola Nintendo Switch 2", "Consola Nintendo Switch 2 + Mario Kart World Bundle"),
        ("monitores", 'Monitor LG UltraGear 24" FHD 180Hz IPS', 'Monitor LG UltraGear 27" FHD 180Hz IPS'),
        ("monitores", 'Monitor LG UltraGear 27" QHD 100Hz IPS', 'Monitor LG UltraGear 27" QHD 180Hz IPS'),
        ("monitores", 'Monitor Samsung Odyssey 27" QHD IPS', 'Monitor Samsung Odyssey 27" QHD OLED'),
        ("smartwatches", "Samsung Galaxy Watch 7 40mm Bluetooth", "Samsung Galaxy Watch 7 44mm Bluetooth"),
        ("smartwatches", "Apple Watch Series 10 46mm GPS", "Apple Watch Series 10 46mm GPS + Cellular"),
        ("audifonos", "Audífonos JBL Tune 530 C Negro", "Audífonos Inalámbricos JBL Tune 530"),
        ("audifonos", "Apple AirPods 4", "Apple AirPods 4 con Cancelación Activa de Ruido ANC"),
        ("almacenamiento_redes", "Router Mesh TP-Link Deco X50 Wi-Fi 6", "Router Mesh TP-Link Deco X50 Wi-Fi 6 Pack 3"),
    ]
    for cat, t_a, t_b in incompatible_pairs:
        p_a = extract_variant_profile(t_a, category=cat)
        p_b = extract_variant_profile(t_b, category=cat)
        assert are_listings_variant_compatible(p_a, p_b) is False, f"Se esperaba rechazo entre {t_a!r} y {t_b!r}"
        assert evaluate_strict_guardrails(t_a, t_b) is False


@pytest.mark.asyncio
async def test_catalog_promoter_end_to_end_and_idempotent_on_sqlite(tmp_path):
    db_file = tmp_path / "phase2bc_promoter.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Sembrar los 25 productos semilla reales (`prod_*`)
    async with SessionMaker() as session:
        await sync_and_upsert_catalog(session=session, overwrite_live=True)
        seed_count = (await session.execute(select(func.count(ProductEntity.id)))).scalar()
        assert seed_count == len(SEED_PRODUCTS)

        # Insertar listings variados en `store_listings`:
        # 1) Match contra producto semilla existente (`prod_samsung_galaxy_tab_a11` en ripley faltante)
        # 2) Grupo multi-tienda por EAN en `consolas` (PS5 Slim 1TB en falabella + ripley + hiraoka)
        # 3) Variante distinta de consola (PS5 Slim Digital 1TB en efe -> NO debe mezclarse con la de disco)
        # 4) Grupo multi-tienda por firma en `monitores` (LG 27" QHD 180Hz IPS) y variante incompatible (24")
        # 5) Combo accesorios_pc (Teclado Logitech + Mouse MK470 en 2 tiendas vs MK270 en 1 tienda)
        # 6) Smartwatch 44mm (2 tiendas) vs 40mm (1 tienda) -> ambos deben promoverse separados
        # 7) Licencia antivirus no-hardware -> debe descartarse
        session.add_all(
            [
                StoreListing(
                    store="ripley",
                    store_sku="2000111",
                    category="tablets",
                    title='TABLET SAMSUNG GALAXY TAB A11 8.7" 4GB 64GB GRIS',
                    brand="Samsung",
                    price=429.0,
                    original_price=699.0,
                    url="https://simple.ripley.com.pe/tablet-samsung-galaxy-tab-a11-64gb-2000111p",
                    image_url="https://rimage.ripley.com.pe/tab-a11.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="falabella",
                    store_sku="F_PS5_DISC",
                    category="consolas",
                    title="Consola Sony PlayStation 5 Slim 1TB",
                    brand="Sony",
                    price=2299.0,
                    original_price=2799.0,
                    url="https://www.falabella.com.pe/falabella-pe/product/100/ps5-slim/100",
                    image_url="https://media.falabella.com.pe/ps5.jpg",
                    ean="0711719577294",
                    in_stock=True,
                ),
                StoreListing(
                    store="hiraoka",
                    store_sku="H_PS5_DISC",
                    category="consolas",
                    title="PS5 PlayStation 5 Slim Con Lectora 1 TB",
                    brand="Sony",
                    price=2399.0,
                    original_price=2799.0,
                    url="https://hiraoka.com.pe/consola-ps5-slim-1tb",
                    image_url="https://hiraoka.com.pe/media/ps5.jpg",
                    ean="0711719577294",
                    in_stock=True,
                ),
                StoreListing(
                    store="efe",
                    store_sku="E_PS5_DIG",
                    category="consolas",
                    title="Consola PlayStation 5 Slim Digital 1TB",
                    brand="Sony",
                    price=2049.0,
                    original_price=2499.0,
                    url="https://www.efe.com.pe/hw-ps5-slim-digital.html",
                    image_url="https://www.efe.com.pe/media/ps5d.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="falabella",
                    store_sku="F_MON_27",
                    category="monitores",
                    title='Monitor Gaming LG UltraGear 27" QHD 180Hz IPS 27GS75Q-B',
                    brand="LG",
                    price=999.0,
                    original_price=1299.0,
                    url="https://www.falabella.com.pe/falabella-pe/product/201/lg-27gs75q/201",
                    image_url="https://media.falabella.com.pe/lg27.jpg",
                    mpn="27GS75Q-B",
                    in_stock=True,
                ),
                StoreListing(
                    store="curacao",
                    store_sku="C_MON_27",
                    category="monitores",
                    title="Monitor LG 27'' IPS QHD 180Hz UltraGear 27GS75Q",
                    brand="LG",
                    price=1049.0,
                    original_price=1349.0,
                    url="https://www.lacuracao.pe/mon-lg-27gs75q.html",
                    image_url="https://www.lacuracao.pe/media/lg27.jpg",
                    mpn="27GS75Q-B",
                    in_stock=True,
                ),
                StoreListing(
                    store="hiraoka",
                    store_sku="H_MON_24",
                    category="monitores",
                    title='Monitor LG UltraGear 24" FHD 180Hz IPS 24GS60F',
                    brand="LG",
                    price=549.0,
                    original_price=699.0,
                    url="https://hiraoka.com.pe/monitor-lg-24gs60f",
                    image_url="https://hiraoka.com.pe/media/lg24.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="falabella",
                    store_sku="F_MK470",
                    category="accesorios_pc",
                    title="Teclado Logitech + Mouse MK470",
                    brand="Logitech",
                    price=199.0,
                    original_price=249.0,
                    url="https://www.falabella.com.pe/falabella-pe/product/301/mk470/301",
                    image_url="https://media.falabella.com.pe/mk470.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="tottus",
                    store_sku="T_MK470",
                    category="accesorios_pc",
                    title="Combo Teclado y Mouse Inalámbrico Logitech MK470 Blanco",
                    brand="Logitech",
                    price=189.0,
                    original_price=239.0,
                    url="https://www.tottus.com.pe/tottus-pe/articulo/302/mk470/302",
                    image_url="https://media.falabella.com.pe/tottus_mk470.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="wong",
                    store_sku="W_MK270",
                    category="accesorios_pc",
                    title="Teclado Logitech + Mouse MK270",
                    brand="Logitech",
                    price=119.0,
                    original_price=149.0,
                    url="https://www.wong.pe/teclado-mouse-logitech-mk270-303/p",
                    image_url="https://www.wong.pe/media/mk270.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="falabella",
                    store_sku="F_GW7_44",
                    category="smartwatches",
                    title="Samsung Galaxy Watch 7 44mm Bluetooth",
                    brand="Samsung",
                    price=899.0,
                    original_price=1199.0,
                    url="https://www.falabella.com.pe/falabella-pe/product/401/watch7-44/401",
                    image_url="https://media.falabella.com.pe/gw7_44.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="efe",
                    store_sku="E_GW7_44",
                    category="smartwatches",
                    title="Smartwatch Samsung Galaxy Watch7 BT 44 mm Verde",
                    brand="Samsung",
                    price=929.0,
                    original_price=1199.0,
                    url="https://www.efe.com.pe/watch7-44mm.html",
                    image_url="https://www.efe.com.pe/media/gw7_44.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="efe",
                    store_sku="E_GW7_40",
                    category="smartwatches",
                    title="Smartwatch Samsung Galaxy Watch 7 40mm Bluetooth",
                    brand="Samsung",
                    price=799.0,
                    original_price=1099.0,
                    url="https://www.efe.com.pe/watch7-40mm.html",
                    image_url="https://www.efe.com.pe/media/gw7_40.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="wong",
                    store_sku="W_AV",
                    category="accesorios_pc",
                    title="Antivirus Plus Bitdefender 1Pieza 12Meses",
                    brand="Bitdefender",
                    price=29.0,
                    original_price=49.0,
                    url="https://www.wong.pe/antivirus-bitdefender-1/p",
                    image_url="https://www.wong.pe/media/av.jpg",
                    in_stock=True,
                ),
            ]
        )
        await session.commit()

        # 1. Dry-Run NO escribe en BD
        dry_summary = await promote_store_listings(session=session, dry_run=True)
        assert dry_summary.dry_run is True
        assert dry_summary.linked_to_existing_products == 1
        assert dry_summary.new_multi_store_groups == 4  # PS5 disc, Mon 27", MK470, GW7 44mm
        assert dry_summary.new_single_store_products == 4  # PS5 digital, Mon 24", MK270, GW7 40mm
        assert dry_summary.total_promoted_products == 8
        assert dry_summary.discarded_invalid_or_outliers == 1  # Bitdefender antivirus
        assert (await session.execute(select(func.count(ProductEntity.id)))).scalar() == len(SEED_PRODUCTS)

        # 2. Promoción real
        fixed_today = date(2026, 11, 24)
        real_summary = await promote_store_listings(session=session, dry_run=False, today_peru=fixed_today)
        assert real_summary.linked_to_existing_products == 1
        assert real_summary.new_multi_store_groups == 4
        assert real_summary.new_single_store_products == 4
        assert real_summary.total_promoted_products == 8

        all_prods = list((await session.execute(select(ProductEntity))).scalars().all())
        assert len(all_prods) == len(SEED_PRODUCTS) + 8
        seed_ids = {p["id"] for p in SEED_PRODUCTS}
        assert seed_ids.issubset({p.id for p in all_prods})

        auto_prods = [p for p in all_prods if p.id.startswith("auto_")]
        assert len(auto_prods) == 8

        # Confirmar que existe el de 1 sola tienda (ej. PS5 Slim Digital) y que los grupos no se mezclaron
        ps5_prods = [p for p in auto_prods if "playstation" in p.title.lower() or "ps5" in p.title.lower()]
        assert len(ps5_prods) == 2
        ps5_disc = next(p for p in ps5_prods if "digital" not in p.title.lower())
        ps5_dig = next(p for p in ps5_prods if "digital" in p.title.lower())
        assert ps5_disc.available_stores_count == 2
        assert ps5_disc.best_price == 2299.0
        assert ps5_dig.available_stores_count == 1
        assert ps5_dig.best_price == 2049.0

        # Verificar enlace de `prod_samsung_galaxy_tab_a11` con la nueva oferta de ripley
        tab_prod = await session.get(ProductEntity, "prod_samsung_galaxy_tab_a11")
        assert tab_prod is not None
        assert any(o.store_id == "ripley" and o.price == 429.0 for o in tab_prod.store_offers)

        # Añadir punto histórico del día anterior en un `auto_*` y re-promover -> idempotente + preserva historial
        session.add(
            PriceHistoryEntity(
                product_id=ps5_disc.id,
                day_offset=-1,
                date_label="23 Nov",
                recorded_date=(fixed_today - timedelta(days=1)).isoformat(),
                price=2450.0,
            )
        )
        await session.commit()

        second_summary = await promote_store_listings(session=session, dry_run=False, today_peru=fixed_today)
        assert second_summary.total_promoted_products == 8
        assert (await session.execute(select(func.count(ProductEntity.id)))).scalar() == len(SEED_PRODUCTS) + 8

        ps5_disc_reloaded = (
            await session.execute(
                select(ProductEntity)
                .where(ProductEntity.id == ps5_disc.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert len(ps5_disc_reloaded.price_history) == 2
        assert any(h.recorded_date == (fixed_today - timedelta(days=1)).isoformat() for h in ps5_disc_reloaded.price_history)

        # 3. `sync_and_upsert_catalog(overwrite_live=False)` y `sanitize_database_offers` NO deben borrar `auto_*`
        await sync_and_upsert_catalog(session=session, overwrite_live=False)
        await orchestrator.sanitize_database_offers(session=session)
        assert (await session.execute(select(func.count(ProductEntity.id)))).scalar() == len(SEED_PRODUCTS) + 8
        ps5_after_sync = await session.get(ProductEntity, ps5_dig.id)
        assert ps5_after_sync is not None and ps5_after_sync.available_stores_count == 1

    # 4. Verificar paginación y filtros retrocompatibles en GET /api/v1/products
    async def override_get_read_db():
        async with SessionMaker() as read_session:
            yield read_session

    app.dependency_overrides[get_read_db] = override_get_read_db
    catalog_service.invalidate_cache()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as api_client:
            # Llamada sin parámetros -> lista completa, multi-tienda priorizados, estructura intacta
            r_all = await api_client.get("/api/v1/products")
            assert r_all.status_code == 200
            data_all = r_all.json()
            assert isinstance(data_all, list)
            assert len(data_all) == len(SEED_PRODUCTS) + 8
            first_single_idx = next(
                (i for i, item in enumerate(data_all) if item["availableStoresCount"] < 2),
                len(data_all),
            )
            assert all(item["availableStoresCount"] >= 2 for item in data_all[:first_single_idx])

            # Paginación limit + offset
            r_page = await api_client.get("/api/v1/products?limit=4&offset=2")
            assert r_page.status_code == 200
            data_page = r_page.json()
            assert len(data_page) == 4
            assert [p["id"] for p in data_page] == [p["id"] for p in data_all[2:6]]

            # Filtro por categoría usando slug y display name
            r_con_slug = await api_client.get("/api/v1/products?category=consolas")
            r_con_name = await api_client.get("/api/v1/products?category=Consolas")
            assert r_con_slug.status_code == 200 and r_con_name.status_code == 200
            assert len(r_con_slug.json()) == 2
            assert r_con_slug.json() == r_con_name.json()

            # Filtro por tienda + min_stores
            r_store_min = await api_client.get("/api/v1/products?store=hiraoka&min_stores=2")
            assert r_store_min.status_code == 200
            for prod in r_store_min.json():
                assert prod["availableStoresCount"] >= 2
                assert any(sp["storeId"] == "hiraoka" for sp in prod["storePrices"])

            # Ordenamiento por descuento y precio ascendente
            r_disc = await api_client.get("/api/v1/products?sort=discount&limit=10")
            assert r_disc.status_code == 200
            discs = [p["discountPercentage"] for p in r_disc.json()]
            assert discs == sorted(discs, reverse=True)

            r_asc = await api_client.get("/api/v1/products?sort=price_asc")
            assert r_asc.status_code == 200
            prices_asc = [p["bestPrice"] for p in r_asc.json()]
            assert prices_asc == sorted(prices_asc)

            # Retrocompatibilidad con sort_order=LOW_TO_HIGH
            r_legacy_sort = await api_client.get("/api/v1/products?sort_order=LOW_TO_HIGH")
            assert r_legacy_sort.status_code == 200
            assert [p["bestPrice"] for p in r_legacy_sort.json()] == prices_asc
    finally:
        app.dependency_overrides.pop(get_read_db, None)
        catalog_service.invalidate_cache()
        await test_engine.dispose()


def test_worker_cli_promote_catalog_dry_run_never_touches_writer(tmp_path, monkeypatch, capsys):
    import asyncio
    from app import worker as worker_mod

    db_file = tmp_path / "cli_dry_run.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    TestSession = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def _prep():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with TestSession() as s:
            s.add_all(
                [
                    StoreListing(
                        store="falabella",
                        store_sku="CLI_1",
                        category="consolas",
                        title="Consola Nintendo Switch 2 256GB",
                        brand="Nintendo",
                        price=2399.0,
                        original_price=2599.0,
                        url="https://www.falabella.com.pe/falabella-pe/product/999/switch-2/999",
                        image_url="https://media.falabella.com.pe/switch2.jpg",
                        in_stock=True,
                    ),
                    StoreListing(
                        store="hiraoka",
                        store_sku="CLI_2",
                        category="consolas",
                        title="Consola Nintendo Switch 2 256GB",
                        brand="Nintendo",
                        price=2449.0,
                        original_price=2649.0,
                        url="https://hiraoka.com.pe/consola-nintendo-switch-2",
                        image_url="https://hiraoka.com.pe/media/switch2.jpg",
                        in_stock=True,
                    ),
                ]
            )
            await s.commit()

    asyncio.run(_prep())

    async def forbid_write(*args, **kwargs):
        raise AssertionError("--promote-catalog --dry-run no debe inicializar ni escribir en Neon/BD")

    monkeypatch.setattr(worker_mod, "init_db", forbid_write)
    monkeypatch.setattr(worker_mod, "bootstrap_worker_db", forbid_write)
    monkeypatch.setattr("app.collectors.catalog_promoter.ReaderSessionLocal", TestSession)

    exit_code = worker_mod.main(["--promote-catalog", "--dry-run"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "DRY-RUN" in out
    assert "Grupos nuevos multi-tienda  : 1" in out
    assert "Nintendo Switch 2" in out

    asyncio.run(test_engine.dispose())


@pytest.mark.asyncio
async def test_promoter_rejects_out_of_stock_missing_https_image_and_non_tech(tmp_path):
    from app.collectors.category_crawler import ScrapedListing

    db_file = tmp_path / "hardening_filters.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    items = [
        ScrapedListing(
            store="falabella",
            store_sku="NT_1",
            category="accesorios_pc",
            title='Maleta Dura Bazy 28" Cabina',
            brand="Bazy",
            price=199.0,
            original_price=249.0,
            currency="PEN",
            url="https://www.falabella.com.pe/falabella-pe/product/1/maleta/1",
            image_url="https://media.falabella.com.pe/maleta.jpg",
            in_stock=True,
        ),
        ScrapedListing(
            store="ripley",
            store_sku="OOS_1",
            category="monitores",
            title='Monitor Gamer LG UltraGear 27" 180Hz IPS QHD 27GS75Q',
            brand="LG",
            price=1199.0,
            original_price=1399.0,
            currency="PEN",
            url="https://simple.ripley.com.pe/monitor-lg-2004123456p",
            image_url="https://home.ripley.com.pe/monitor.webp",
            in_stock=False,
        ),
        ScrapedListing(
            store="efe",
            store_sku="NOIMG_1",
            category="monitores",
            title='Monitor Gamer AOC 24" 180Hz IPS 24G4',
            brand="AOC",
            price=649.0,
            original_price=799.0,
            currency="PEN",
            url="https://www.efe.com.pe/monitor-aoc-24g4.html",
            image_url="https://www.efe.com.pe/media/catalog/product/placeholder/websites/1/IMG_PRODUCTO-EFE_1__1.jpg",
            in_stock=True,
        ),
        ScrapedListing(
            store="hiraoka",
            store_sku="OK_1",
            category="monitores",
            title='Monitor Gamer LG UltraGear 27" 180Hz IPS QHD 27GS75Q',
            brand="LG",
            price=1229.0,
            original_price=1499.0,
            currency="PEN",
            url="https://hiraoka.com.pe/monitor-lg-27gs75q",
            image_url="https://hiraoka.com.pe/media/27gs75q.jpg",
            in_stock=True,
        ),
    ]

    async with SessionMaker() as session:
        summary = await promote_store_listings(
            session=session,
            dry_run=False,
            in_memory_listings=items,
            today_peru=date(2026, 4, 21),
        )
        assert summary.total_promoted_products == 1
        assert summary.discarded_non_tech >= 1

        prods = list((await session.execute(select(ProductEntity))).scalars().all())
        assert len(prods) == 1
        assert prods[0].image_url == "https://hiraoka.com.pe/media/27gs75q.jpg"
        assert prods[0].available_stores_count == 1

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_promoter_seed_linking_and_marketing_filler_signatures(tmp_path):
    from app.collectors.category_crawler import ScrapedListing

    db_file = tmp_path / "seed_and_sony.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionMaker() as session:
        session.add(
            ProductEntity(
                id="prod_hp_smart_tank_580",
                title="Impresora Multifuncional HP Smart Tank 580 Wi-Fi",
                category="Impresoras",
                brand="HP",
                best_price=679.0,
                original_price=799.0,
                best_store_name="Hiraoka",
                best_store_url="https://hiraoka.com.pe/impresora-hp-smart-tank-580",
                available_stores_count=1,
                image_url="https://hiraoka.com.pe/media/hp580.jpg",
                tech_specs_json=json.dumps({"Marca": "HP", "Modelo": "Smart Tank 580"}),
            )
        )
        session.add(
            StoreOfferEntity(
                product_id="prod_hp_smart_tank_580",
                store_id="hiraoka",
                store_name="Hiraoka",
                price=679.0,
                original_price=799.0,
                offer_url="https://hiraoka.com.pe/impresora-hp-smart-tank-580",
                is_best_price=True,
            )
        )
        await session.commit()

    listings = [
        ScrapedListing(
            store="falabella",
            store_sku="HP580_FAL",
            category="impresoras",
            title="Impresora Multifuncional HP Smart Tank 580 Sistema Continuo, Wi-Fi, Color, HP App",
            brand="HP",
            price=649.0,
            original_price=799.0,
            currency="PEN",
            url="https://www.falabella.com.pe/falabella-pe/product/12/hp-580/12",
            image_url="https://media.falabella.com.pe/hp580.jpg",
            in_stock=True,
        ),
        ScrapedListing(
            store="falabella",
            store_sku="SONY_B",
            category="audifonos",
            title="Audífonos Bluetooth Sony WH-CH520B On-Ear Negro",
            brand="Sony",
            price=159.0,
            original_price=199.0,
            currency="PEN",
            url="https://www.falabella.com.pe/falabella-pe/product/52/whch520b/52",
            image_url="https://media.falabella.com.pe/ch520b.jpg",
            in_stock=True,
        ),
        ScrapedListing(
            store="hiraoka",
            store_sku="SONY_L",
            category="audifonos",
            title="Audífonos Inalámbricos Sony WH-CH520L Azul",
            brand="Sony",
            price=169.0,
            original_price=199.0,
            currency="PEN",
            url="https://hiraoka.com.pe/audifonos-sony-wh-ch520l",
            image_url="https://hiraoka.com.pe/media/ch520l.jpg",
            in_stock=True,
        ),
    ]

    async with SessionMaker() as session:
        summary = await promote_store_listings(
            session=session,
            dry_run=False,
            in_memory_listings=listings,
            today_peru=date(2026, 4, 21),
        )
        assert summary.linked_to_existing_products == 1
        assert summary.new_multi_store_groups == 1
        assert summary.new_single_store_products == 0

        hp_prod = (
            await session.execute(select(ProductEntity).where(ProductEntity.id == "prod_hp_smart_tank_580"))
        ).scalar_one()
        assert hp_prod.best_price == 649.0
        assert hp_prod.available_stores_count == 2

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_promoter_auto_pruning_preserves_seed_products_and_cleans_invalid_auto(tmp_path):
    db_file = tmp_path / "pruning_test.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionMaker() as session:
        session.add_all(
            [
                # Semilla prod_* SIEMPRE intacta
                ProductEntity(
                    id="prod_seed_intact",
                    title="Impresora Multifuncional HP Smart Tank 580 Wi-Fi",
                    category="Impresoras",
                    brand="HP",
                    best_price=679.0,
                    original_price=799.0,
                    best_store_name="Hiraoka",
                    best_store_url="https://hiraoka.com.pe/hp580",
                    available_stores_count=1,
                    image_url="https://hiraoka.com.pe/media/hp580.jpg",
                    tech_specs_json=json.dumps({"Marca": "HP", "Modelo": "Smart Tank 580"}),
                ),
                # auto_* contaminado no-tech -> podar (no_tech)
                ProductEntity(
                    id="auto_bad_nontech",
                    title="Huntington Gorro Fleece",
                    category="Almacenamiento y Redes",
                    brand="Huntington",
                    best_price=39.9,
                    original_price=59.9,
                    best_store_name="Falabella",
                    best_store_url="https://www.falabella.com.pe/falabella-pe/product/1/gorro/1",
                    available_stores_count=1,
                    image_url="https://media.falabella.com.pe/gorro.jpg",
                ),
                # auto_* sin imagen HTTPS -> podar (sin_imagen_https)
                ProductEntity(
                    id="auto_bad_noimg",
                    title='Monitor LG UltraGear 27" 180Hz',
                    category="Monitores",
                    brand="LG",
                    best_price=999.0,
                    original_price=1199.0,
                    best_store_name="Tiendas Efe",
                    best_store_url="https://www.efe.com.pe/monitor.html",
                    available_stores_count=1,
                    image_url="",
                ),
                # auto_* sin stock / obsoleto -> podar (sin_stock_u_obsoleto)
                ProductEntity(
                    id="auto_bad_oos",
                    title="Mouse Gamer Logitech G502 Hero",
                    category="Accesorios PC",
                    brand="Logitech",
                    best_price=199.0,
                    original_price=249.0,
                    best_store_name="Ripley",
                    best_store_url="https://simple.ripley.com.pe/mouse-g502-2004p",
                    available_stores_count=1,
                    image_url="https://home.ripley.com.pe/g502.webp",
                ),
                # StoreListing no-tech -> eliminar en live
                StoreListing(
                    store="metro",
                    store_sku="BAD_MOCHILA",
                    category="accesorios_pc",
                    title="Mochila Kuzler Ligera de Viaje",
                    brand="Kuzler",
                    price=89.0,
                    original_price=119.0,
                    url="https://www.metro.pe/mochila-kuzler/p",
                    image_url="https://metroio.vtexassets.com/mochila.jpg",
                    in_stock=True,
                ),
                # StoreListing tech válido
                StoreListing(
                    store="hiraoka",
                    store_sku="GOOD_SONOS",
                    category="audio",
                    title="Parlante Bluetooth JBL Flip 6 Portátil",
                    brand="JBL",
                    price=449.0,
                    original_price=549.0,
                    url="https://hiraoka.com.pe/parlante-jbl-flip-6",
                    image_url="https://hiraoka.com.pe/media/flip6.jpg",
                    in_stock=True,
                ),
            ]
        )
        await session.commit()

        # Dry-run reporta todo lo que se va a podar SIN borrar nada
        dry_summary = await promote_store_listings(
            session=session,
            dry_run=True,
            in_memory_listings=None,
            today_peru=date(2026, 4, 21),
        )
        assert dry_summary.pruned_auto_products_total == 3
        assert dry_summary.pruned_by_reason["no_tech"] == 1
        assert dry_summary.pruned_by_reason["sin_imagen_https"] == 1
        assert dry_summary.pruned_by_reason["sin_stock_u_obsoleto"] == 1
        assert dry_summary.pruned_non_tech_listings == 1
        assert len(list((await session.execute(select(ProductEntity))).scalars().all())) == 4

        # Live ejecuta la poda manteniendo prod_* y el auto_* válido
        live_summary = await promote_store_listings(
            session=session,
            dry_run=False,
            in_memory_listings=None,
            today_peru=date(2026, 4, 21),
        )
        assert live_summary.pruned_auto_products_total == 3
        assert live_summary.pruned_non_tech_listings == 1

        remaining_prods = list((await session.execute(select(ProductEntity))).scalars().all())
        rem_ids = {p.id for p in remaining_prods}
        assert "prod_seed_intact" in rem_ids
        assert "auto_bad_nontech" not in rem_ids
        assert "auto_bad_noimg" not in rem_ids
        assert "auto_bad_oos" not in rem_ids
        assert len(remaining_prods) == 2

        remaining_listings = list((await session.execute(select(StoreListing))).scalars().all())
        assert len(remaining_listings) == 1
        assert remaining_listings[0].store_sku == "GOOD_SONOS"

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_api_products_gzip_and_1800s_cache_prewarm_invalidation(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from main import app
    from app.core.database import get_read_db
    from app.services.catalog_service import (
        _PRODUCTS_RESPONSE_CACHE_TTL_SECONDS,
        catalog_service,
    )

    assert _PRODUCTS_RESPONSE_CACHE_TTL_SECONDS == 1800.0

    db_file = tmp_path / "api_cache_gzip.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionMaker() as s:
        s.add(
            ProductEntity(
                id="prod_cache_test",
                title="Laptop ASUS VivoBook 15" + (" Intel Core i5 16GB 512GB" * 5),
                category="Laptops",
                brand="ASUS",
                best_price=2499.0,
                original_price=2899.0,
                best_store_name="Hiraoka",
                best_store_url="https://hiraoka.com.pe/asus-vivobook-15",
                available_stores_count=1,
                image_url="https://hiraoka.com.pe/media/vivobook.jpg",
                description="Laptop ASUS de alto rendimiento para testing de GZip " * 25,
                tech_specs_json=json.dumps({"Marca": "ASUS"}),
            )
        )
        await s.commit()

        catalog_service.invalidate_cache()
        warmed_bytes = await catalog_service.prewarm_default_products_cache(session=s)
        assert warmed_bytes > 100
        default_key = catalog_service._build_products_cache_key(
            search=None, category=None, brand=None, processor=None, ram=None,
            storage=None, tv_resolution=None, connectivity=None, screen=None,
            os_filter=None, dynamic_specs=None, enabled_stores=None,
            sort_order=None, limit=None, offset=0, store=None, min_stores=None, sort=None,
        )
        assert default_key in catalog_service._products_json_cache

    async def _override_read_db():
        async with SessionMaker() as s:
            yield s

    catalog_service.invalidate_cache()
    app.dependency_overrides[get_read_db] = _override_read_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as api_client:
            r1 = await api_client.get(
                "/api/v1/products?limit=10",
                headers={"Accept-Encoding": "gzip"},
            )
            assert r1.status_code == 200
            assert isinstance(r1.json(), list)
            assert len(r1.json()) == 1
            assert r1.json()[0]["id"] == "prod_cache_test"
            assert r1.headers.get("content-encoding") == "gzip"
            assert len(catalog_service._products_json_cache) >= 1

            # Mutación en BD seguida de hit en caché (antes de invalidar sigue 1) y luego invalidación
            async with SessionMaker() as s2:
                s2.add(
                    ProductEntity(
                        id="prod_cache_test_2",
                        title="Tablet Apple iPad 11 A16 128GB",
                        category="Tablets",
                        brand="Apple",
                        best_price=1699.0,
                        original_price=1899.0,
                        best_store_name="Falabella",
                        best_store_url="https://www.falabella.com.pe/falabella-pe/product/9/ipad/9",
                        available_stores_count=1,
                        image_url="https://media.falabella.com.pe/ipad.jpg",
                        tech_specs_json=json.dumps({"Marca": "Apple"}),
                    )
                )
                await s2.commit()

            r_cached = await api_client.get("/api/v1/products?limit=10")
            assert len(r_cached.json()) == 1

            catalog_service.invalidate_cache()
            r_fresh = await api_client.get("/api/v1/products?limit=10")
            assert len(r_fresh.json()) == 2
    finally:
        app.dependency_overrides.pop(get_read_db, None)
        catalog_service.invalidate_cache()
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_structured_laptop_matching_and_variant_protection(tmp_path):
    from app.collectors.category_crawler import ScrapedListing
    from app.collectors.tech_normalizer import build_structured_match_key, extract_inline_manufacturer_mpns

    assert "x1504vabq523w" in extract_inline_manufacturer_mpns(
        'Laptop Asus Vivobook 15 de 15.6", Intel Core 3 304, 8GB RAM, disco sólido de 256GB, modelo X1504VA-BQ523W'
    )
    k_fal = build_structured_match_key('Acer Laptop Aspire Lite AMD Ryzen 5 8GB 512GB 15.6" FHD', "Acer", category="laptops")
    k_rip = build_structured_match_key("LAPTOP ACER ASPIRE LITE AMD RYZEN 5 8GB RAM 512GB SSD 15.6”", "Acer", category="laptops")
    assert k_fal is not None and k_fal == k_rip

    db_file = tmp_path / "structured_laptops.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    listings = [
        # Par 1: Acer Aspire Lite R5 8GB 512GB 15.6" (Falabella + Ripley) -> DEBE FUSIONAR
        ScrapedListing(
            store="falabella",
            store_sku="AC_FAL",
            category="laptops",
            title='Acer Laptop Aspire Lite AMD Ryzen 5 8GB 512GB 15.6" FHD',
            brand="Acer",
            price=1949.0,
            original_price=2299.0,
            currency="PEN",
            url="https://www.falabella.com.pe/falabella-pe/product/11/acer-lite/11",
            image_url="https://media.falabella.com.pe/acer1.jpg",
            in_stock=True,
        ),
        ScrapedListing(
            store="ripley",
            store_sku="AC_RIP",
            category="laptops",
            title="LAPTOP ACER ASPIRE LITE AMD RYZEN 5 8GB RAM 512GB SSD 15.6”",
            brand="Acer",
            price=1799.0,
            original_price=2199.0,
            currency="PEN",
            url="https://simple.ripley.com.pe/laptop-acer-aspire-lite-r5-2004111p",
            image_url="https://home.ripley.com.pe/acer1.webp",
            in_stock=True,
        ),
        # Par 2: Asus Vivobook 15 Core 3 304 8GB 256GB 15.6" (Falabella + Hiraoka con MPN largo) -> DEBE FUSIONAR
        ScrapedListing(
            store="falabella",
            store_sku="VV_FAL",
            category="laptops",
            title='Asus Vivobook 15 Intel Core 3 304 8GB 256SSD 15.6" FHD',
            brand="Asus",
            price=1899.0,
            original_price=2199.0,
            currency="PEN",
            url="https://www.falabella.com.pe/falabella-pe/product/22/vv-c3/22",
            image_url="https://media.falabella.com.pe/vv1.jpg",
            in_stock=True,
        ),
        ScrapedListing(
            store="hiraoka",
            store_sku="VV_HIR",
            category="laptops",
            title='Laptop Asus Vivobook 15 de 15.6", Intel Core 3 304, 8GB RAM, disco sólido de 256GB, modelo X1504VA-BQ523W',
            brand="Asus",
            price=1949.0,
            original_price=2249.0,
            currency="PEN",
            url="https://hiraoka.com.pe/laptop-asus-vivobook-15-core-3-304-x1504va-bq523w",
            image_url="https://hiraoka.com.pe/media/vv1.jpg",
            in_stock=True,
        ),
        # Variantes distintas que NUNCA deben mezclarse: 16GB RAM, 512GB SSD, Core 5, RTX 4050
        ScrapedListing(
            store="tottus",
            store_sku="VV_16_512",
            category="laptops",
            title='Asus Vivobook 15 Intel Core 3 304 16RAM 512SSD 15.6" FHD',
            brand="Asus",
            price=2199.0,
            original_price=2499.0,
            currency="PEN",
            url="https://www.tottus.com.pe/tottus-pe/articulo/33/vv-16/33",
            image_url="https://media.falabella.com.pe/vv16.jpg",
            in_stock=True,
        ),
        ScrapedListing(
            store="efe",
            store_sku="VV_C5_RTX",
            category="laptops",
            title='Laptop Gamer Asus Vivobook 15 Intel Core 5 8GB 512GB RTX 4050 15.6"',
            brand="Asus",
            price=3299.0,
            original_price=3699.0,
            currency="PEN",
            url="https://www.efe.com.pe/vv-c5-rtx4050.html",
            image_url="https://www.efe.com.pe/media/vvrtx.jpg",
            in_stock=True,
        ),
    ]

    async with SessionMaker() as session:
        summary = await promote_store_listings(
            session=session,
            dry_run=False,
            in_memory_listings=listings,
            today_peru=date(2026, 4, 21),
        )
        assert summary.new_multi_store_groups == 2
        assert summary.new_single_store_products == 2
        assert summary.total_promoted_products == 4

        multi_titles = {ex.title: ex for ex in summary.multi_store_examples}
        assert any("Aspire Lite" in t and ex.stores_count == 2 for t, ex in multi_titles.items())
        assert any("Vivobook 15" in t and ex.stores_count == 2 for t, ex in multi_titles.items())

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_toy_karaoke_rejection_and_strict_category_reclassification(tmp_path):
    db_file = tmp_path / "reclass_toys.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionMaker() as session:
        session.add_all(
            [
                # Juguetes infantiles -> DEBEN rechazarse/podarse
                StoreListing(
                    store="tottus",
                    store_sku="TOY_WOODY",
                    category="almacenamiento_redes",
                    title="Disney Micrófono Karaoke Woody",
                    brand="Disney",
                    price=39.9,
                    original_price=49.9,
                    url="https://www.tottus.com.pe/tottus-pe/articulo/151402787/microfono-karaoke-woody/151402789",
                    image_url="https://media.falabella.com.pe/woody.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="tottus",
                    store_sku="TOY_JESSIE",
                    category="almacenamiento_redes",
                    title="Disney Micrófono Karaoke Jessie",
                    brand="Disney",
                    price=39.9,
                    original_price=49.9,
                    url="https://www.tottus.com.pe/tottus-pe/articulo/151402869/microfono-karaoke-jessie/151402871",
                    image_url="https://media.falabella.com.pe/jessie.jpg",
                    in_stock=True,
                ),
                # Smartphone que cayó en almacenamiento_redes -> DEBE reclasificarse a celulares (Smartphones)
                StoreListing(
                    store="falabella",
                    store_sku="OPPO_X10",
                    category="almacenamiento_redes",
                    title="Oppo Find X10 5G 12GB + 512GB",
                    brand="Oppo",
                    price=5999.0,
                    original_price=6499.0,
                    url="https://www.falabella.com.pe/falabella-pe/product/80226828/oppo-find-x10-5g-12gb-512gb/80226830",
                    image_url="https://media.falabella.com.pe/oppo.jpg",
                    in_stock=True,
                ),
                # Equipo de audio real con palabra Karaoke -> DEBE conservarse en Audio
                StoreListing(
                    store="ripley",
                    store_sku="LG_XBOOM",
                    category="audio",
                    title="TORRE DE SONIDO LG XBOOM RNC9 MULTI-BLUETOOTH KARAOKE STAR",
                    brand="LG",
                    price=1099.0,
                    original_price=1499.0,
                    url="https://simple.ripley.com.pe/torre-de-sonido-lg-xboom-rnc9-20041234p",
                    image_url="https://home.ripley.com.pe/xboom.webp",
                    in_stock=True,
                ),
            ]
        )
        await session.commit()

        summary = await promote_store_listings(
            session=session,
            dry_run=False,
            in_memory_listings=None,
            today_peru=date(2026, 4, 21),
        )
        assert summary.pruned_non_tech_listings == 2
        assert summary.reclassified_listings >= 1
        assert summary.total_promoted_products == 2

        prods = list((await session.execute(select(ProductEntity))).scalars().all())
        by_title = {p.title: p for p in prods}
        assert len(prods) == 2
        oppo_prod = next(p for t, p in by_title.items() if "Oppo" in t)
        lg_prod = next(p for t, p in by_title.items() if "XBOOM" in t or "Xboom" in t)
        assert oppo_prod.category == "Smartphones"
        assert lg_prod.category == "Audio"

    await test_engine.dispose()


def test_expanded_color_dictionary_and_generic_signature_guard():
    from app.collectors.color_stripper import strip_color_tokens
    from app.collectors.tech_normalizer import is_signature_specific_enough

    commercial_samples = [
        ("Audífonos In Ear Skullcandy Jib Usb C Bone", "Audífonos In Ear Skullcandy Jib Usb C"),
        ("Mouse Gaming Logitech G305 Mint", "Mouse Gaming Logitech G305"),
        ("Garmin Venu 3S GPS Wi‑Fi Sage Gray", "Garmin Venu 3S GPS Wi‑Fi"),
        ("Samsung Galaxy A56 256GB Olive", "Samsung Galaxy A56 256GB"),
        ("Teclado Logitech MK470 Rose", "Teclado Logitech MK470"),
        ("Nokia 5G Indigo Slate Burgundy Champagne", "Nokia 5G"),
        ("Laptop Asus Zenbook 14 Obsidian Sand Cream", "Laptop Asus Zenbook 14"),
        ("Audífonos Buds Hueso Marfil Durazno Blush Lavender", "Audífonos Buds"),
        ("Smartwatch Oliva Cobalto Turquesa Guinda Vino Mostaza Fucsia", "Smartwatch"),
        ("Tablet Cobre Copper Bronce Bronze Plomo Marrón Púrpura Cyan Aqua Turquoise", "Tablet"),
        ("Apple MacBook Neo 13, color Índigo, 256GB", "Apple MacBook Neo 13, 256GB"),
    ]
    for raw_t, expected_t in commercial_samples:
        assert strip_color_tokens(raw_t) == expected_t

    # Nunca romper tokens reales de hardware ni "Impresora a Color"
    assert strip_color_tokens("SSD Externo SanDisk Extreme 1TB") == "SSD Externo SanDisk Extreme 1TB"
    assert strip_color_tokens("Impresora Multifuncional Epson a Color Wi-Fi") == "Impresora Multifuncional Epson a Color Wi-Fi"

    # Firmas sin dígitos pero con marca + tokens descriptivos sí son válidas
    sig_jib = build_canonical_product_signature(
        "Audífonos In Ear Skullcandy Jib Usb C Bone", "Skullcandy", category="audifonos"
    )
    assert sig_jib == "skullcandy jib inear"
    assert is_signature_specific_enough(sig_jib, brand="Skullcandy", category="audifonos") is True

    sig_fiddler = build_canonical_product_signature(
        "Fiddler Mouse Inalámbrico Blanco con Pilas", "Fiddler", category="accesorios_pc"
    )
    assert sig_fiddler == "fiddler mouse pilas"
    assert is_signature_specific_enough(sig_fiddler, brand="Fiddler", category="accesorios_pc") is True

    # Firmas ultra-genéricas siguen estrictamente bloqueadas
    assert is_signature_specific_enough("samsung", brand="Samsung", category="celulares") is False
    assert is_signature_specific_enough("hp", brand="HP", category="laptops") is False
    assert is_signature_specific_enough("logitech mouse", brand="Logitech", category="accesorios_pc") is False
    assert is_signature_specific_enough("sony overear", brand="Sony", category="audifonos") is False
    assert is_signature_specific_enough("lg 27 fhd ips", brand="LG", category="monitores") is False
    assert is_signature_specific_enough("kuzler teclado mouse", brand="Kuzler", category="accesorios_pc") is False


@pytest.mark.asyncio
async def test_color_variant_collapse_and_no_digit_deduplication(tmp_path):
    db_file = tmp_path / "color_nodigit_dedup.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionMaker() as session:
        session.add_all(
            [
                # Duplicados auto_* obsoletos por color para comprobar poda automática
                ProductEntity(
                    id="auto_skullcandy_jib_black_old",
                    title="Audífonos In Ear Skullcandy Jib Usb C",
                    category="Audífonos",
                    brand="Skullcandy",
                    best_price=24.9,
                    original_price=39.9,
                    best_store_name="La Curacao",
                    best_store_url="https://www.lacuracao.pe/audifonos-skullcandy-jib-usb-c.html",
                    available_stores_count=1,
                    image_url="https://www.lacuracao.pe/media/jib-blk.jpg",
                ),
                ProductEntity(
                    id="auto_skullcandy_jib_bone_old",
                    title="Audífonos In Ear Skullcandy Jib Usb C Bone",
                    category="Audífonos",
                    brand="Skullcandy",
                    best_price=26.9,
                    original_price=39.9,
                    best_store_name="La Curacao",
                    best_store_url="https://www.lacuracao.pe/audifonos-skullcandy-jib-usb-c-bone.html",
                    available_stores_count=1,
                    image_url="https://www.lacuracao.pe/media/jib-bone.jpg",
                ),
                # 1) Skullcandy Jib Usb C en Curacao (2 colores) + Efe -> 1 producto, 2 tiendas
                StoreListing(
                    store="curacao",
                    store_sku="JIB_CUR_BLK",
                    category="audifonos",
                    title="Audífonos In Ear Skullcandy Jib Usb C",
                    brand="Skullcandy",
                    price=24.9,
                    original_price=39.9,
                    url="https://www.lacuracao.pe/audifonos-skullcandy-jib-usb-c.html",
                    image_url="https://www.lacuracao.pe/media/jib-blk.jpg",
                    in_stock=True,
                    canonical_product_id="auto_skullcandy_jib_black_old",
                ),
                StoreListing(
                    store="curacao",
                    store_sku="JIB_CUR_BONE",
                    category="audifonos",
                    title="Audífonos In Ear Skullcandy Jib Usb C Bone",
                    brand="Skullcandy",
                    price=26.9,
                    original_price=39.9,
                    url="https://www.lacuracao.pe/audifonos-skullcandy-jib-usb-c-bone.html",
                    image_url="https://www.lacuracao.pe/media/jib-bone.jpg",
                    in_stock=True,
                    canonical_product_id="auto_skullcandy_jib_bone_old",
                ),
                StoreListing(
                    store="efe",
                    store_sku="JIB_EFE_BLK",
                    category="audifonos",
                    title="Audífonos In Ear Skullcandy Jib Usb C",
                    brand="Skullcandy",
                    price=24.9,
                    original_price=39.9,
                    url="https://www.efe.com.pe/audifonos-skullcandy-jib-usb-c.html",
                    image_url="https://www.efe.com.pe/media/jib-blk.jpg",
                    in_stock=True,
                ),
                # 2) Fiddler Mouse Inalámbrico con Pilas en Tottus + Wong (menta y blanco con EANs distintos) -> 1 producto, 2 tiendas
                StoreListing(
                    store="tottus",
                    store_sku="FID_TOT_BLK",
                    category="accesorios_pc",
                    title="Fiddler Mouse Inalámbrico con Pilas Negro",
                    brand="Fiddler",
                    price=24.9,
                    original_price=29.9,
                    url="https://www.tottus.com.pe/tottus-pe/articulo/10/fiddler-mouse/10",
                    image_url="https://media.falabella.com.pe/fiddler-blk.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="wong",
                    store_sku="FID_WONG_MINT",
                    category="accesorios_pc",
                    title="Fiddler Mouse Inalámbrico con Pilas Menta",
                    brand="Fiddler",
                    price=24.9,
                    original_price=29.9,
                    url="https://www.wong.pe/fiddler-mouse-pilas-menta/p?utm_source=test",
                    image_url="https://wongfood.vtexassets.com/fiddler-mint.jpg",
                    ean="7809601112661",
                    in_stock=True,
                ),
                StoreListing(
                    store="wong",
                    store_sku="FID_WONG_WHT",
                    category="accesorios_pc",
                    title="Fiddler Mouse Inalámbrico Blanco con Pilas",
                    brand="Fiddler",
                    price=24.9,
                    original_price=29.9,
                    url="https://www.wong.pe/fiddler-mouse-pilas-blanco/p",
                    image_url="https://wongfood.vtexassets.com/fiddler-wht.jpg",
                    ean="7809601112685",
                    in_stock=True,
                ),
                # 3) Protección ultra-genérica: Logitech Mouse NO debe fusionar con G305 ni M170
                StoreListing(
                    store="tottus",
                    store_sku="LOGI_GEN",
                    category="accesorios_pc",
                    title="Mouse Logitech",
                    brand="Logitech",
                    price=39.9,
                    original_price=49.9,
                    url="https://www.tottus.com.pe/tottus-pe/articulo/11/mouse-logitech/11",
                    image_url="https://media.falabella.com.pe/logi-gen.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="falabella",
                    store_sku="LOGI_G305",
                    category="accesorios_pc",
                    title="Mouse Gamer Logitech G305 Lightspeed Mint",
                    brand="Logitech",
                    price=169.9,
                    original_price=199.9,
                    url="https://www.falabella.com.pe/falabella-pe/product/12/logi-g305/12",
                    image_url="https://media.falabella.com.pe/logi-g305.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="hiraoka",
                    store_sku="LOGI_M170",
                    category="accesorios_pc",
                    title="Mouse Inalámbrico Logitech M170 Rose",
                    brand="Logitech",
                    price=49.9,
                    original_price=59.9,
                    url="https://hiraoka.com.pe/mouse-logitech-m170-rose",
                    image_url="https://hiraoka.com.pe/media/m170.jpg",
                    in_stock=True,
                ),
            ]
        )
        await session.commit()

        summary = await promote_store_listings(
            session=session,
            dry_run=False,
            in_memory_listings=None,
            today_peru=date(2026, 4, 21),
        )
        assert summary.new_multi_store_groups == 2
        assert summary.new_single_store_products == 3
        assert summary.total_promoted_products == 5
        assert summary.pruned_auto_products_total == 2
        assert summary.pruned_by_reason.get("duplicado_o_reemplazado") == 2

        prods = list(
            (
                await session.execute(
                    select(ProductEntity).options(selectinload(ProductEntity.store_offers))
                )
            ).scalars().all()
        )
        assert len(prods) == 5

        jib_prods = [p for p in prods if "skullcandy" in p.title.lower()]
        assert len(jib_prods) == 1
        jib = jib_prods[0]
        assert jib.available_stores_count == 2
        assert len(jib.store_offers) == 2
        assert {o.store_id for o in jib.store_offers} == {"curacao", "efe"}
        assert jib.best_price == 24.9
        assert "bone" not in jib.title.lower()

        fiddler_prods = [p for p in prods if "fiddler" in p.title.lower()]
        assert len(fiddler_prods) == 1
        fid = fiddler_prods[0]
        assert fid.available_stores_count == 2
        assert len(fid.store_offers) == 2
        assert {o.store_id for o in fid.store_offers} == {"tottus", "wong"}
        wong_offer = next(o for o in fid.store_offers if o.store_id == "wong")
        assert "?" not in wong_offer.offer_url

        logi_prods = [p for p in prods if "logitech" in p.title.lower()]
        assert len(logi_prods) == 3
        assert all(p.available_stores_count == 1 for p in logi_prods)

    await test_engine.dispose()


def test_enable_auto_category_discovery_default_and_standalone_mousepad_rejection():
    from app.collectors.tech_normalizer import is_strict_tech_product
    from app.core.config import Settings

    assert Settings().ENABLE_AUTO_CATEGORY_DISCOVERY is True
    assert Settings(ENABLE_AUTO_CATEGORY_DISCOVERY="false").ENABLE_AUTO_CATEGORY_DISCOVERY is False

    # Mousepads sueltos deben rechazarse
    assert is_strict_tech_product("Mouse Pad Fiddler Gel Negro Fd-Mp01", category="accesorios_pc", brand="Fiddler") is False
    assert is_strict_tech_product("Mousepad Logitech G840 XL", category="accesorios_pc", brand="Logitech") is False
    assert is_strict_tech_product("Pad Mouse Gamer RGB Antideslizante", category="accesorios_pc") is False
    assert is_strict_tech_product("Alfombrilla Ergonómica con Reposamuñecas", category="accesorios_pc") is False

    # Combos con hardware electrónico real SÍ se permiten
    assert is_strict_tech_product("Combo Xtech Mousepad + Audífonos + Teclado + Mouse", category="accesorios_pc", brand="Xtech") is True
    assert is_strict_tech_product("Kit gamer Xtrike Me 3 en 1 Teclado + Mouse + Mouse pad", category="accesorios_pc", brand="Xtrike Me") is True
    assert is_strict_tech_product("Pack Xtech Ghost Spider: Audífonos + Mouse + Mouse PAD", category="audifonos", brand="Xtech") is True


def test_structured_key_smartphone_4g_5g_and_tv_resolution_panels():
    from app.collectors.tech_normalizer import (
        are_listings_variant_compatible,
        build_structured_match_key,
        evaluate_strict_guardrails,
        extract_variant_profile,
    )

    # Smartphones: color ignorado, 4G vs 5G estrictamente separado
    k_s5g_a = build_structured_match_key("Samsung Galaxy A57 5G 256GB 8GB RAM Negro", "Samsung", category="celulares")
    k_s5g_b = build_structured_match_key("Celular Samsung Galaxy A57 5G 8GB 256GB Azul", "Samsung", category="celulares")
    k_s4g = build_structured_match_key("Samsung Galaxy A57 4G 256GB 8GB RAM Negro", "Samsung", category="celulares")
    assert k_s5g_a is not None and k_s5g_a == k_s5g_b
    assert k_s4g is not None and k_s5g_a != k_s4g
    assert are_listings_variant_compatible(
        extract_variant_profile("Samsung Galaxy A57 5G 256GB 8GB", category="celulares", brand="Samsung"),
        extract_variant_profile("Samsung Galaxy A57 4G 256GB 8GB", category="celulares", brand="Samsung"),
    ) is False
    assert evaluate_strict_guardrails("Samsung Galaxy A57 4G 256GB 8GB RAM", "Samsung Galaxy A57 5G 256GB 8GB RAM") is False
    assert evaluate_strict_guardrails("Samsung Galaxy A57 5G 256GB 8GB RAM", "Samsung Galaxy A57 4G 256GB 8GB RAM") is False

    # Televisores: HD vs Full HD vs 4K y OLED vs QLED vs MiniLED estrictamente separados (omitiendo color)
    k_tv_hd = build_structured_match_key('Televisor JVC 32" QLED HD LT-32KM1584 Smart TV Negro', "JVC", category="televisores")
    k_tv_fhd = build_structured_match_key('Televisor JVC 32" QLED Full HD LT-32KM1584 Smart TV Blanco', "JVC", category="televisores")
    k_tv_4k = build_structured_match_key('Televisor JVC 32" QLED 4K LT-32KM1584 Smart TV Negro', "JVC", category="televisores")
    assert k_tv_hd is not None and k_tv_fhd is not None and k_tv_4k is not None
    assert k_tv_hd != k_tv_fhd and k_tv_fhd != k_tv_4k and k_tv_hd != k_tv_4k

    k_oled_a = build_structured_match_key('LG Televisor 65" OLED evo AI C6 4K Smart TV 2026', "LG", category="televisores")
    k_oled_b = build_structured_match_key("Televisor Smart TV LG OLED 65 OLED65C6PSA", "LG", category="televisores")
    assert k_oled_a is not None and k_oled_a == k_oled_b

    assert are_listings_variant_compatible(
        extract_variant_profile('Televisor JVC 43" QLED FHD', category="televisores", brand="JVC"),
        extract_variant_profile('Televisor JVC 43" QLED 4K', category="televisores", brand="JVC"),
    ) is False
    assert evaluate_strict_guardrails('Televisor JVC 43" QLED FHD', 'Televisor JVC 43" QLED 4K') is False
    assert evaluate_strict_guardrails('Televisor Samsung 55" QLED 4K', 'Televisor Samsung 55" OLED 4K') is False


@pytest.mark.asyncio
async def test_incomplete_a57_absorption_and_scheduled_full_auto_update(tmp_path, monkeypatch):
    from app.services.catalog_service import catalog_service

    db_file = tmp_path / "phase2d_absorption.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    SessionMaker = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionMaker() as session:
        await sync_and_upsert_catalog(session=session, overwrite_live=True)

        # Simular estado legado de producción:
        # 1) prod_samsung_galaxy_a57 tiene oferta Falabella a S/ 1,499 en URL /product/80007794/...
        # 2) Se había creado un auto_* duplicado con S/ 1,799 y título incompleto "Samsung Celular Galaxy A57 5G"
        # 3) Otro listing incompleto en tienda distinta (sin URL coincidente) y caso ambiguo iPhone 16 sin GB
        # 4) Un Mousepad suelto debe podarse y un combo con Mousepad debe mantenerse
        a57_prod = await session.get(ProductEntity, "prod_samsung_galaxy_a57")
        assert a57_prod is not None
        fal_offer = next((o for o in a57_prod.store_offers if o.store_id == "falabella"), None)
        assert fal_offer is not None
        fal_offer.price = 1499.0
        fal_offer.offer_url = "https://www.falabella.com.pe/falabella-pe/product/80007794/celular-samsung-galaxy-a57-5g/80007798"

        # Agregar una segunda variante de iPhone 16 para verificar bloqueo ante ambigüedad
        session.add(
            ProductEntity(
                id="prod_apple_iphone_16_256gb_test",
                title="Apple iPhone 16 5G 256GB",
                category="Smartphones",
                brand="Apple",
                best_price=3699.0,
                original_price=4199.0,
                best_store_name="Hiraoka",
                best_store_url="https://hiraoka.com.pe/iphone-16-256gb",
                available_stores_count=1,
                image_url="https://hiraoka.com.pe/media/ip16_256.jpg",
                tech_specs_json=json.dumps({"Marca": "Apple", "Almacenamiento": "256 GB"}),
            )
        )
        session.add(
            ProductEntity(
                id="auto_samsung_galaxy_a57_dup",
                title="Samsung Celular Galaxy A57 5G",
                category="Smartphones",
                brand="Samsung",
                best_price=1799.0,
                original_price=1999.0,
                best_store_name="Falabella",
                best_store_url="https://www.falabella.com.pe/falabella-pe/product/80007794/celular-samsung-galaxy-a57-5g/80007798",
                available_stores_count=1,
                image_url="https://media.falabella.com.pe/a57.jpg",
            )
        )
        session.add_all(
            [
                StoreListing(
                    store="falabella",
                    store_sku="80007798",
                    category="celulares",
                    title="Samsung Celular Galaxy A57 5G",
                    brand="Samsung",
                    price=1799.0,
                    original_price=1999.0,
                    url="https://www.falabella.com.pe/falabella-pe/product/80007794/celular-samsung-galaxy-a57-5g/80007798",
                    image_url="https://media.falabella.com.pe/a57.jpg",
                    in_stock=True,
                    canonical_product_id="auto_samsung_galaxy_a57_dup",
                ),
                StoreListing(
                    store="metro",
                    store_sku="M_A57_INC",
                    category="celulares",
                    title="Celular Samsung Galaxy A57 5G Negro",
                    brand="Samsung",
                    price=1549.0,
                    original_price=1799.0,
                    url="https://www.metro.pe/celular-samsung-galaxy-a57-5g/p",
                    image_url="https://metroio.vtexassets.com/a57.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="wong",
                    store_sku="W_IP16_AMB",
                    category="celulares",
                    title="Apple Celular iPhone 16 5G Blanco",
                    brand="Apple",
                    price=3499.0,
                    original_price=3899.0,
                    url="https://www.wong.pe/apple-iphone-16-5g/p",
                    image_url="https://wongfood.vtexassets.com/ip16.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="metro",
                    store_sku="MP_GEL_BAD",
                    category="accesorios_pc",
                    title="Mouse Pad Fiddler Gel Negro Fd-Mp01",
                    brand="Fiddler",
                    price=39.9,
                    original_price=49.9,
                    url="https://www.metro.pe/mousepad-fiddler-gel/p",
                    image_url="https://metroio.vtexassets.com/mp.jpg",
                    in_stock=True,
                ),
                StoreListing(
                    store="efe",
                    store_sku="COMBO_MP_OK",
                    category="accesorios_pc",
                    title="Combo Xtech Mousepad + Audífonos + Teclado + Mouse",
                    brand="Xtech",
                    price=99.0,
                    original_price=129.0,
                    url="https://www.efe.com.pe/combo-xtech-mousepad.html",
                    image_url="https://www.efe.com.pe/media/combo-xtech.jpg",
                    in_stock=True,
                ),
            ]
        )
        await session.commit()

        from app.collectors.orchestrator import get_today_peru
        yesterday_peru = get_today_peru() - timedelta(days=1)

        summary = await promote_store_listings(
            session=session,
            dry_run=False,
            in_memory_listings=None,
            today_peru=yesterday_peru,
        )
        # Ambos A57 incompletos se absorben en prod_samsung_galaxy_a57; iPhone 16 ambiguo no se adivina; mousepad se poda
        assert summary.linked_to_existing_products == 2
        assert summary.pruned_non_tech_listings == 1
        assert summary.pruned_auto_products_total == 1
        assert summary.pruned_by_reason.get("duplicado_o_reemplazado") == 1

        # Verificar que no existe ningún auto_* duplicado de A57 y que prod_samsung_galaxy_a57 conserva S/ 1,499 en Falabella
        a57_autos = [
            p
            for p in (await session.execute(select(ProductEntity))).scalars().all()
            if p.id.startswith("auto_") and "a57" in (p.title or "").lower()
        ]
        assert a57_autos == []
        a57_reloaded = (
            await session.execute(
                select(ProductEntity)
                .options(selectinload(ProductEntity.store_offers))
                .where(ProductEntity.id == "prod_samsung_galaxy_a57")
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        fal_after = next(o for o in a57_reloaded.store_offers if o.store_id == "falabella")
        assert fal_after.price == 1499.0
        assert any(o.store_id == "metro" and o.price == 1549.0 for o in a57_reloaded.store_offers)

        # Combo con mousepad sí promovido, Mousepad suelto no
        combo_prods = [
            p
            for p in (await session.execute(select(ProductEntity))).scalars().all()
            if p.id.startswith("auto_") and "combo xtech" in (p.title or "").lower()
        ]
        assert len(combo_prods) == 1

        # Verificar flujo de run_scheduled_price_update: actualiza prod_* + crawl + promote (auto_*) + invalida y precalienta caché
        calls_order = []

        async def fake_sync_all_catalog_products(session, on_cache_invalidate=None, **kwargs):
            calls_order.append("sync_prod")
            return {"status": "success", "updated_products": 25}

        async def fake_crawl_categories(stores=None, max_pages=1, dry_run=False, session=None):
            from app.collectors.category_crawler import CategoryCrawlSummary
            calls_order.append("crawl_categories")
            # Simular caída de precio en Combo Xtech (99 -> 79) para validar refresco completo de auto_*
            res_l = (
                await session.execute(
                    select(StoreListing).where(StoreListing.store_sku == "COMBO_MP_OK")
                )
            ).scalar_one()
            res_l.price = 79.0
            await session.flush()
            return CategoryCrawlSummary(extracted_1p=1, updated=1)

        catalog_service.invalidate_cache()
        monkeypatch.setattr(orchestrator, "sync_all_catalog_products", fake_sync_all_catalog_products)
        monkeypatch.setattr("app.collectors.category_crawler.crawl_categories", fake_crawl_categories)

        run_res = await orchestrator.run_scheduled_price_update(
            session=session,
            on_cache_invalidate=catalog_service.invalidate_cache,
        )
        assert calls_order == ["sync_prod", "crawl_categories"]
        assert "auto_category_discovery" in run_res
        assert run_res["auto_category_discovery"]["updated_listings"] == 1
        assert run_res["cache_prewarmed_bytes"] > 100
        assert len(catalog_service._products_json_cache) >= 1

        # Verificar que el auto_* reflejó nuevo best_price=79.0, ahorro, descuento e historial
        combo_updated = await session.get(ProductEntity, combo_prods[0].id)
        assert combo_updated is not None
        assert combo_updated.best_price == 79.0
        assert combo_updated.original_price == 129.0
        assert combo_updated.price_drop_amount == 50.0
        assert combo_updated.discount_percentage == 39
        assert len(combo_updated.price_history) >= 1

    catalog_service.invalidate_cache()
    await test_engine.dispose()
