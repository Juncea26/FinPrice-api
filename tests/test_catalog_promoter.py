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
