"""
Servicio asíncrono de catálogo:
- Caché en memoria TTL de alto rendimiento (< 50ms)
- Generación dinámica de facetas de filtrado (GET /api/v1/filters)
- Filtrado avanzado en memoria (búsqueda, categoría, marca, specs dinámicos y resolución)
- Recálculo dinámico de ofertas cuando el usuario filtra por 'enabled_stores'
- Manejo real de ofertas comunitarias en base de datos
- Compatibilidad retroactiva con GET /products
"""
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import sanitize_input_text
from app.collectors.catalog_urls import PERU_DEPARTMENTS
from app.collectors.color_stripper import strip_color_tokens
from app.collectors.orchestrator import orchestrator
from app.collectors.spec_extractor import (
    generate_product_features,
    merge_product_specs,
    normalize_brand,
)
from app.collectors.validators import (
    validate_cross_store_prices,
    validate_product_identity,
)
from app.models.entities import (
    CommunityOfferEntity,
    ProductEntity,
)
from app.models.schemas import (
    CommunityOfferCreateSchema,
    CommunityPhysicalOfferSchema,
    DynamicFiltersSchema,
    PricePointSchema,
    ProductResponse,
    ProductSchema,
    StoreOffer,
    StorePriceSchema,
    StoreSchema,
)

logger = get_logger("services.catalog")

FEMININE_SPEC_KEYS = {
    "Memoria RAM",
    "Conectividad",
    "Pantalla",
    "Resolución",
    "Batería",
    "Cámara Principal",
}

FACET_SPEC_KEYS_ORDER = (
    "Memoria RAM",
    "Almacenamiento",
    "Procesador",
    "Conectividad",
    "Pantalla",
    "Resolución",
    "Cámara Principal",
    "Batería",
    "Sistema Operativo",
)

STANDARD_CATEGORY_ORDER = ("Smartphones", "Laptops", "Tablets", "TVs")


def _capacity_sort_key(val: str) -> float:
    """Ordena capacidades numéricamente (ej. '8 GB' < '12 GB' < '128 GB' < '1 TB')."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(TB|GB|MB)?", str(val), flags=re.IGNORECASE)
    if not m:
        return 999999.0
    num = float(m.group(1))
    unit = (m.group(2) or "GB").upper()
    if unit == "TB":
        return num * 1024.0
    if unit == "MB":
        return num / 1024.0
    return num


class CatalogService:
    def __init__(self):
        self._cached_products: Optional[List[ProductSchema]] = None
        self._cache_timestamp: float = 0.0

    def invalidate_cache(self) -> None:
        """Invalida la caché en memoria para forzar lectura fresca de BD."""
        self._cached_products = None
        self._cache_timestamp = 0.0

    async def _get_base_products(self, session: AsyncSession) -> List[ProductSchema]:
        """Retorna la lista de productos base desde la caché en memoria o desde la base de datos."""
        now = time.time()
        if (
            self._cached_products is not None
            and (now - self._cache_timestamp) < settings.CACHE_TTL_SECONDS
        ):
            return self._cached_products

        stmt = select(ProductEntity)
        result = await session.execute(stmt)
        entities = result.scalars().all()

        schemas: List[ProductSchema] = []
        for p in entities:
            clean_title = strip_color_tokens(p.title) or p.title
            raw_features = json.loads(p.features_json) if p.features_json else []
            raw_specs = json.loads(p.tech_specs_json) if p.tech_specs_json else {}

            # Normalizar y asegurar specs completos y estandarizados
            tech_specs = merge_product_specs(
                specs_list=[raw_specs],
                base_specs=raw_specs,
                title=clean_title,
            )
            brand = tech_specs.get("Marca") or normalize_brand(p.brand, clean_title)
            if brand:
                tech_specs["Marca"] = brand

            features = generate_product_features(
                soup=None,
                tech_specs=tech_specs,
                title=clean_title,
                existing_features=raw_features,
            )

            raw_store_prices: List[StorePriceSchema] = [
                StorePriceSchema(
                    store_id=sp.store_id,
                    store_name=sp.store_name,
                    price=sp.price,
                    original_price=sp.original_price,
                    offer_url=sp.offer_url,
                    is_best_price=sp.is_best_price,
                )
                for sp in p.store_offers
                if validate_product_identity(
                    canonical_title=clean_title,
                    scraped_title="",
                    scraped_url=sp.offer_url,
                    store_id=sp.store_id,
                    tech_specs=tech_specs,
                )
            ]
            store_prices = validate_cross_store_prices(raw_store_prices)
            store_prices.sort(key=lambda x: x.price)
            for idx, sp_item in enumerate(store_prices):
                sp_item.is_best_price = idx == 0

            if store_prices:
                eff_best_price = store_prices[0].price
                eff_best_store = store_prices[0].store_name
                eff_orig_price = store_prices[0].original_price or eff_best_price
                if eff_orig_price < eff_best_price:
                    eff_orig_price = eff_best_price
                eff_discount = (
                    round(((eff_orig_price - eff_best_price) / eff_orig_price) * 100)
                    if eff_orig_price > eff_best_price
                    else 0
                )
                eff_count = len(store_prices)
            else:
                eff_best_price = p.best_price
                eff_best_store = p.best_store_name
                eff_orig_price = p.original_price
                eff_discount = p.discount_percentage
                eff_count = p.available_stores_count

            price_history: List[PricePointSchema] = [
                PricePointSchema(
                    day_offset=hp.day_offset,
                    date_label=hp.date_label,
                    price=hp.price,
                )
                for hp in p.price_history
                if hp.price >= (eff_best_price * 0.55)
            ]
            price_history.sort(key=lambda x: x.day_offset)

            schemas.append(
                ProductSchema(
                    id=p.id,
                    title=clean_title,
                    category=p.category,
                    brand=brand,
                    best_price=eff_best_price,
                    original_price=eff_orig_price,
                    best_store_name=eff_best_store,
                    discount_percentage=eff_discount,
                    available_stores_count=eff_count,
                    image_url=p.image_url,
                    description=p.description,
                    features=features,
                    is_favorite=p.is_favorite,
                    store_prices=store_prices,
                    historical_min_price=(
                        min(hp.price for hp in price_history)
                        if price_history
                        else eff_best_price
                    ),
                    tech_specs=tech_specs,
                    is_historical_min=p.is_historical_min,
                    price_history_30_days=price_history,
                )
            )

        self._cached_products = schemas
        self._cache_timestamp = now
        return schemas

    async def get_dynamic_filters(self, session: AsyncSession) -> DynamicFiltersSchema:
        """
        Calcula dinámicamente las categorías, marcas por categoría y facetas de
        especificaciones técnicas por categoría a partir de los productos activos en BD.
        """
        products = await self._get_base_products(session)

        # 1. Categorías activas ordenadas
        present_cats = {p.category for p in products if p.category}
        ordered_cats = [c for c in STANDARD_CATEGORY_ORDER if c in present_cats]
        for extra_cat in sorted(present_cats - set(ordered_cats)):
            ordered_cats.append(extra_cat)

        categories = ["Todos"] + ordered_cats

        # 2. Marcas por categoría
        all_brands = sorted(
            {
                (p.brand or p.tech_specs.get("Marca", "")).strip()
                for p in products
                if (p.brand or p.tech_specs.get("Marca", "")).strip()
            }
        )
        brands_by_category: Dict[str, List[str]] = {
            "Todos": ["Todas"] + all_brands,
        }
        for cat in ordered_cats:
            cat_brands = sorted(
                {
                    (p.brand or p.tech_specs.get("Marca", "")).strip()
                    for p in products
                    if p.category == cat and (p.brand or p.tech_specs.get("Marca", "")).strip()
                }
            )
            brands_by_category[cat] = ["Todas"] + cat_brands

        # 3. Especificaciones técnicas por categoría
        specs_by_category: Dict[str, Dict[str, List[str]]] = {}

        for cat in ordered_cats:
            cat_products = [p for p in products if p.category == cat]
            cat_specs_map: Dict[str, List[str]] = {}

            for spec_key in FACET_SPEC_KEYS_ORDER:
                values_set = {
                    p.tech_specs[spec_key].strip()
                    for p in cat_products
                    if spec_key in p.tech_specs and p.tech_specs[spec_key].strip()
                }
                if not values_set:
                    continue

                if spec_key in {"Memoria RAM", "Almacenamiento"}:
                    sorted_vals = sorted(values_set, key=lambda v: (_capacity_sort_key(v), v))
                else:
                    sorted_vals = sorted(values_set)

                default_prefix = "Todas" if spec_key in FEMININE_SPEC_KEYS else "Todos"
                cat_specs_map[spec_key] = [default_prefix] + sorted_vals

            specs_by_category[cat] = cat_specs_map

        return DynamicFiltersSchema(
            categories=categories,
            brands_by_category=brands_by_category,
            specs_by_category=specs_by_category,
            brandsByCategory=brands_by_category,
            specsByCategory=specs_by_category,
        )

    async def get_products(
        self,
        session: AsyncSession,
        search: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        processor: Optional[str] = None,
        ram: Optional[str] = None,
        storage: Optional[str] = None,
        tv_resolution: Optional[str] = None,
        connectivity: Optional[str] = None,
        screen: Optional[str] = None,
        os_filter: Optional[str] = None,
        dynamic_specs: Optional[Dict[str, str]] = None,
        enabled_stores: Optional[str] = None,
        sort_order: Literal["LOW_TO_HIGH", "HIGH_TO_LOW"] = "LOW_TO_HIGH",
    ) -> List[ProductSchema]:
        """Filtra y ordena el catálogo en memoria respondiendo en < 50ms."""
        products = await self._get_base_products(session)
        results: List[ProductSchema] = []

        allowed_store_ids = set()
        if enabled_stores:
            allowed_store_ids = {
                s.strip().lower() for s in enabled_stores.split(",") if s.strip()
            }

        def _is_active_filter(val: Optional[str]) -> bool:
            if not val:
                return False
            return val.strip().lower() not in {"", "todos", "todas", "all"}

        search_term = search.lower().strip() if search and search.strip() else None
        category_term = category.strip() if _is_active_filter(category) else None
        brand_term = brand.strip().lower() if _is_active_filter(brand) else None

        for prod in products:
            if category_term and prod.category.lower() != category_term.lower():
                continue

            if search_term:
                match_search = (
                    search_term in prod.title.lower()
                    or search_term in prod.category.lower()
                    or search_term in prod.best_store_name.lower()
                    or search_term in prod.brand.lower()
                )
                if not match_search:
                    continue

            if brand_term:
                prod_brand = (prod.brand or prod.tech_specs.get("Marca", "")).lower()
                if brand_term not in prod.title.lower() and brand_term != prod_brand:
                    continue

            if _is_active_filter(processor):
                p_query = processor.lower().strip()  # type: ignore[union-attr]
                p_spec = prod.tech_specs.get("Procesador", "").lower()
                if p_query not in prod.title.lower() and p_query not in p_spec:
                    continue

            if _is_active_filter(ram):
                r_query = ram.lower().replace(" ", "")  # type: ignore[union-attr]
                r_spec = prod.tech_specs.get("Memoria RAM", "").lower().replace(" ", "")
                if r_query not in prod.title.lower().replace(" ", "") and r_query != r_spec and r_query not in r_spec:
                    continue

            if _is_active_filter(storage):
                s_query = storage.lower().replace(" ", "")  # type: ignore[union-attr]
                s_spec = prod.tech_specs.get("Almacenamiento", "").lower().replace(" ", "")
                if s_query not in prod.title.lower().replace(" ", "") and s_query != s_spec and s_query not in s_spec:
                    continue

            if _is_active_filter(tv_resolution):
                t_query = tv_resolution.lower().strip()  # type: ignore[union-attr]
                t_spec = prod.tech_specs.get("Resolución", "").lower()
                feats = " ".join(prod.features).lower()
                if (
                    t_query not in prod.title.lower()
                    and t_query not in t_spec
                    and t_query not in feats
                ):
                    continue

            if _is_active_filter(connectivity):
                c_query = connectivity.lower().strip()  # type: ignore[union-attr]
                c_spec = prod.tech_specs.get("Conectividad", "").lower()
                if c_query not in prod.title.lower() and c_query not in c_spec:
                    continue

            if _is_active_filter(screen):
                sc_query = screen.lower().strip()  # type: ignore[union-attr]
                sc_spec = prod.tech_specs.get("Pantalla", "").lower()
                if sc_query not in prod.title.lower() and sc_query not in sc_spec:
                    continue

            if _is_active_filter(os_filter):
                os_query = os_filter.lower().strip()  # type: ignore[union-attr]
                os_spec = prod.tech_specs.get("Sistema Operativo", "").lower()
                if os_query not in prod.title.lower() and os_query not in os_spec:
                    continue

            # Filtros dinámicos arbitrarios sobre tech_specs (ej. ?Memoria RAM=12 GB o ?Conectividad=5G)
            if dynamic_specs:
                matched_dynamic = True
                for d_key, d_val in dynamic_specs.items():
                    if not _is_active_filter(d_val):
                        continue
                    q_norm = d_val.lower().replace(" ", "")
                    spec_val_norm = prod.tech_specs.get(d_key, "").lower().replace(" ", "")
                    if q_norm not in spec_val_norm and q_norm not in prod.title.lower().replace(" ", ""):
                        matched_dynamic = False
                        break
                if not matched_dynamic:
                    continue

            # Recálculo dinámico si se enviaron enabled_stores
            effective_store_prices = prod.store_prices
            if allowed_store_ids:
                effective_store_prices = [
                    sp for sp in prod.store_prices if sp.store_id.lower() in allowed_store_ids
                ]
                if not effective_store_prices:
                    continue

            sorted_stores = sorted(effective_store_prices, key=lambda x: x.price)
            adjusted_stores = [
                StorePriceSchema(
                    store_id=sp.store_id,
                    store_name=sp.store_name,
                    price=sp.price,
                    original_price=sp.original_price,
                    offer_url=sp.offer_url,
                    is_best_price=(idx == 0),
                )
                for idx, sp in enumerate(sorted_stores)
            ]

            effective_best_price = adjusted_stores[0].price
            effective_best_store = adjusted_stores[0].store_name
            effective_orig_price = adjusted_stores[0].original_price or effective_best_price
            effective_discount = (
                round(((effective_orig_price - effective_best_price) / effective_orig_price) * 100)
                if effective_orig_price > effective_best_price
                else 0
            )

            result_item = ProductSchema(
                id=prod.id,
                title=prod.title,
                category=prod.category,
                brand=prod.brand,
                best_price=effective_best_price,
                original_price=effective_orig_price,
                best_store_name=effective_best_store,
                discount_percentage=effective_discount,
                available_stores_count=len(adjusted_stores),
                image_url=prod.image_url,
                description=prod.description,
                features=prod.features,
                is_favorite=prod.is_favorite,
                store_prices=adjusted_stores,
                historical_min_price=prod.historical_min_price,
                tech_specs=prod.tech_specs,
                is_historical_min=(
                    effective_best_price <= prod.historical_min_price
                    if prod.historical_min_price
                    else True
                ),
                price_history_30_days=prod.price_history_30_days,
            )
            results.append(result_item)

        if sort_order == "HIGH_TO_LOW":
            results.sort(key=lambda x: x.best_price, reverse=True)
        else:
            results.sort(key=lambda x: x.best_price, reverse=False)

        return results

    async def get_product_by_id(
        self, product_id: str, session: AsyncSession
    ) -> Optional[ProductSchema]:
        """Retorna el detalle completo de un producto por su ID."""
        products = await self._get_base_products(session)
        for p in products:
            if p.id == product_id:
                return p
        return None

    def get_stores(self) -> List[StoreSchema]:
        """Retorna el listado de las tiendas oficiales y el estado de su Circuit Breaker."""
        statuses = orchestrator.get_stores_status()
        return [
            StoreSchema(
                id=s["id"],
                name=s["name"],
                code=s["code"],
                is_enabled=s["is_enabled"],
                circuit_status=s["circuit_status"],
            )
            for s in statuses
        ]

    async def get_community_offers(
        self,
        session: AsyncSession,
        department: Optional[str] = None,
        province: Optional[str] = None,
        district: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> List[CommunityPhysicalOfferSchema]:
        """Lee ofertas comunitarias reales guardadas en la base de datos."""
        stmt = select(CommunityOfferEntity)
        if department:
            stmt = stmt.where(CommunityOfferEntity.department.ilike(f"%{department.strip()}%"))
        if province:
            stmt = stmt.where(CommunityOfferEntity.province.ilike(f"%{province.strip()}%"))
        if district:
            stmt = stmt.where(CommunityOfferEntity.district.ilike(f"%{district.strip()}%"))
        if product_id:
            stmt = stmt.where(CommunityOfferEntity.product_id == product_id.strip())

        stmt = stmt.order_by(CommunityOfferEntity.timestamp_millis.desc())
        res = await session.execute(stmt)
        items = res.scalars().all()

        return [
            CommunityPhysicalOfferSchema(
                id=o.id,
                product_id=o.product_id,
                product_name=o.product_name,
                physical_store_name=o.physical_store_name,
                department=o.department,
                province=o.province,
                district=o.district,
                price_found=o.price_found,
                photo_uri=o.photo_uri or "",
                comment=o.comment or "",
                timestamp_millis=o.timestamp_millis,
                formatted_date=o.formatted_date,
                author_name=o.author_name or "Usuario FinPrice",
            )
            for o in items
        ]

    async def create_community_offer(
        self, session: AsyncSession, offer_in: CommunityOfferCreateSchema
    ) -> CommunityPhysicalOfferSchema:
        """Registra una oferta física real en la base de datos validando ubigeo."""
        norm_dept = offer_in.department.strip()
        matched = next((d for d in PERU_DEPARTMENTS if d.lower() == norm_dept.lower()), None)
        if not matched:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Departamento inválido: '{offer_in.department}'. Debe ser un departamento oficial de Perú.",
            )

        prod_q = await session.execute(
            select(ProductEntity).where(ProductEntity.id == offer_in.product_id)
        )
        prod = prod_q.scalar_one_or_none()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con ID '{offer_in.product_id}' no encontrado.",
            )

        now_utc = datetime.now(timezone.utc)
        new_entity = CommunityOfferEntity(
            id=f"comm_off_{uuid.uuid4().hex[:8]}",
            product_id=prod.id,
            product_name=sanitize_input_text(offer_in.product_name or prod.title, max_length=150),
            physical_store_name=sanitize_input_text(offer_in.physical_store_name, max_length=120),
            department=matched,
            province=sanitize_input_text(offer_in.province, max_length=100),
            district=sanitize_input_text(offer_in.district, max_length=100),
            price_found=round(offer_in.price_found, 2),
            photo_uri=offer_in.photo_uri or "",
            comment=sanitize_input_text(offer_in.comment or "", max_length=500),
            timestamp_millis=int(now_utc.timestamp() * 1000),
            formatted_date=now_utc.strftime("%d %b %Y, %H:%M"),
            author_name=sanitize_input_text(offer_in.author_name or "Usuario FinPrice", max_length=80),
        )

        session.add(new_entity)
        await session.commit()
        await session.refresh(new_entity)

        return CommunityPhysicalOfferSchema(
            id=new_entity.id,
            product_id=new_entity.product_id,
            product_name=new_entity.product_name,
            physical_store_name=new_entity.physical_store_name,
            department=new_entity.department,
            province=new_entity.province,
            district=new_entity.district,
            price_found=new_entity.price_found,
            photo_uri=new_entity.photo_uri or "",
            comment=new_entity.comment or "",
            timestamp_millis=new_entity.timestamp_millis,
            formatted_date=new_entity.formatted_date,
            author_name=new_entity.author_name,
        )

    async def get_legacy_products(
        self, session: AsyncSession, search: Optional[str] = None
    ) -> List[ProductResponse]:
        """Retrocompatibilidad exacta con GET /products."""
        products = await self._get_base_products(session)
        results: List[ProductResponse] = []
        search_lower = search.lower().strip() if search else None

        for prod in products:
            if search_lower and search_lower not in prod.title.lower():
                continue

            int_id = abs(hash(prod.id)) % 10000
            offers = [
                StoreOffer(
                    store_name=sp.store_name,
                    price=sp.price,
                    currency="PEN",
                    product_url=sp.offer_url,
                )
                for sp in prod.store_prices
            ]
            results.append(
                ProductResponse(
                    id=int_id,
                    name=prod.title,
                    category=prod.category,
                    lowest_price=prod.best_price,
                    best_store=prod.best_store_name,
                    offers=offers,
                )
            )

        return results


catalog_service = CatalogService()
