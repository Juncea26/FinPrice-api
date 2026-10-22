"""
Servicio central de catálogo de FinPrice:
- Inicialización con catálogo semilla si la base de datos está vacía
- Caché en memoria de alto rendimiento con TTL (respuestas < 50ms)
- Lógica de búsqueda, filtros avanzados por hardware y recálculo dinámico por tiendas activas
- Endpoints de tiendas, ofertas comunitarias y retrocompatibilidad legada
"""
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import sanitize_input_text
from app.data.seed_catalog import (
    OFFICIAL_STORES,
    PERU_DEPARTMENTS,
    SEED_COMMUNITY_OFFERS,
    SEED_PRODUCTS,
)
from app.models.domain import (
    CommunityOfferModel,
    PriceHistoryModel,
    ProductModel,
    StorePriceModel,
)
from app.models.schemas import (
    CommunityOfferCreateSchema,
    CommunityPhysicalOfferSchema,
    PricePointSchema,
    ProductResponse,
    ProductSchema,
    StoreOffer,
    StorePriceSchema,
    StoreSchema,
)
from app.collectors.normalizer import calculate_discount_percentage
from app.collectors.registry import collector_registry

logger = get_logger("services.catalog")


class CatalogService:
    def __init__(self):
        self._cached_products: Optional[List[ProductSchema]] = None
        self._cache_timestamp: float = 0.0

    def invalidate_cache(self) -> None:
        """Invalida la caché en memoria para forzar recarga desde BD."""
        self._cached_products = None
        self._cache_timestamp = 0.0
        logger.info("Caché en memoria de catálogo invalidada.")

    # ==========================================================================
    # 1. SEMILLA E INICIALIZACIÓN
    # ==========================================================================

    def ensure_seed_data(self, db: Session) -> None:
        """
        Verifica si la base de datos está vacía al iniciar la aplicación.
        Si está vacía, la inicializa con el catálogo semilla oficial.
        """
        try:
            product_count = db.query(ProductModel).count()
            if product_count > 0:
                logger.info(f"Base de datos operativa con {product_count} productos cargados.")
                return

            logger.info("Base de datos vacía. Inicializando catálogo semilla oficial...")

            for item in SEED_PRODUCTS:
                prod = ProductModel(
                    id=item["id"],
                    title=item["title"],
                    category=item["category"],
                    brand=item["brand"],
                    original_price=item["original_price"],
                    image_url=item["image_url"],
                    description=item["description"],
                    features_json=json.dumps(item["features"], ensure_ascii=False),
                    tech_specs_json=json.dumps(item["tech_specs"], ensure_ascii=False),
                    is_favorite=False,
                )
                db.add(prod)
                db.flush()

                # Precios por tienda
                for sp in item["store_prices"]:
                    store_price = StorePriceModel(
                        product_id=prod.id,
                        store_id=sp["store_id"],
                        store_name=sp["store_name"],
                        price=sp["price"],
                        original_price=sp.get("original_price"),
                        offer_url=sp["offer_url"],
                        last_checked=datetime.now(timezone.utc),
                    )
                    db.add(store_price)

                # Histórico de 30 días
                for hp in item["price_history_30_days"]:
                    hist = PriceHistoryModel(
                        product_id=prod.id,
                        day_offset=hp["day_offset"],
                        date_label=hp["date_label"],
                        price=hp["price"],
                        recorded_date=datetime.now(timezone.utc),
                    )
                    db.add(hist)

            # Ofertas comunitarias semilla
            for comm in SEED_COMMUNITY_OFFERS:
                comm_model = CommunityOfferModel(
                    id=comm["id"],
                    product_id=comm["product_id"],
                    product_name=comm["product_name"],
                    physical_store_name=comm["physical_store_name"],
                    department=comm["department"],
                    province=comm["province"],
                    district=comm["district"],
                    price_found=comm["price_found"],
                    photo_uri=comm.get("photo_uri", ""),
                    comment=comm.get("comment", ""),
                    timestamp_millis=comm["timestamp_millis"],
                    formatted_date=comm["formatted_date"],
                    author_name=comm.get("author_name", "Usuario FinPrice"),
                )
                db.add(comm_model)

            db.commit()
            logger.info("Catálogo semilla inicializado con éxito.")
        except Exception as e:
            db.rollback()
            logger.error(f"Error inicializando catálogo semilla: {e}")
            raise e

    # ==========================================================================
    # 2. CARGA Y CACHÉ DE PRODUCTOS
    # ==========================================================================

    def _get_base_products(self, db: Session) -> List[ProductSchema]:
        """Obtiene la lista de productos base desde la caché o desde la base de datos."""
        now = time.time()
        if (
            self._cached_products is not None
            and (now - self._cache_timestamp) < settings.CACHE_TTL_SECONDS
        ):
            return self._cached_products

        # Consultar base de datos
        db_products = db.query(ProductModel).all()
        schemas: List[ProductSchema] = []

        for p in db_products:
            # Parsear JSON fields
            features = json.loads(p.features_json) if p.features_json else []
            tech_specs = json.loads(p.tech_specs_json) if p.tech_specs_json else {}

            # Construir StorePriceSchemas
            store_prices: List[StorePriceSchema] = []
            for sp in p.store_prices:
                store_prices.append(
                    StorePriceSchema(
                        store_id=sp.store_id,
                        store_name=sp.store_name,
                        price=sp.price,
                        original_price=sp.original_price,
                        offer_url=sp.offer_url,
                        is_best_price=False,
                    )
                )

            # Ordenar store_prices por precio ascendente
            store_prices.sort(key=lambda x: x.price)

            # Construir PricePointSchemas ordenados por day_offset
            history_points: List[PricePointSchema] = []
            for hp in p.price_history:
                history_points.append(
                    PricePointSchema(
                        day_offset=hp.day_offset,
                        date_label=hp.date_label,
                        price=hp.price,
                    )
                )
            history_points.sort(key=lambda x: x.day_offset)

            # Mínimo histórico registrado en el historial
            historical_min_price = (
                min(hp.price for hp in history_points) if history_points else None
            )

            # Cálculo de mejor precio
            best_price = store_prices[0].price if store_prices else p.original_price
            best_store_name = store_prices[0].store_name if store_prices else "Sin ofertas"

            # Marcar is_best_price en la tienda ganadora
            if store_prices:
                store_prices[0].is_best_price = True

            discount_pct = calculate_discount_percentage(p.original_price, best_price)
            is_historical_min = (
                best_price <= historical_min_price if historical_min_price else True
            )

            product_schema = ProductSchema(
                id=p.id,
                title=p.title,
                category=p.category,
                best_price=best_price,
                original_price=p.original_price,
                best_store_name=best_store_name,
                discount_percentage=discount_pct,
                available_stores_count=len(store_prices),
                image_url=p.image_url,
                description=p.description,
                features=features,
                is_favorite=p.is_favorite or False,
                store_prices=store_prices,
                historical_min_price=historical_min_price,
                tech_specs=tech_specs,
                is_historical_min=is_historical_min,
                price_history_30_days=history_points,
            )
            schemas.append(product_schema)

        self._cached_products = schemas
        self._cache_timestamp = now
        return schemas

    # ==========================================================================
    # 3. FILTRADO AVANZADO Y RECÁLCULO DINÁMICO
    # ==========================================================================

    def get_products(
        self,
        db: Session,
        search: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        processor: Optional[str] = None,
        ram: Optional[str] = None,
        storage: Optional[str] = None,
        tv_resolution: Optional[str] = None,
        enabled_stores: Optional[str] = None,
        sort_order: Literal["LOW_TO_HIGH", "HIGH_TO_LOW"] = "LOW_TO_HIGH",
    ) -> List[ProductSchema]:
        """
        Ejecuta el filtrado ultra rápido en memoria (< 50ms) y recalcula
        los mejores precios dinámicamente si se filtran tiendas habilitadas.
        """
        products = self._get_base_products(db)
        results: List[ProductSchema] = []

        # Preparar tiendas habilitadas si se enviaron
        allowed_store_ids = set()
        if enabled_stores:
            allowed_store_ids = {
                s.strip().lower() for s in enabled_stores.split(",") if s.strip()
            }

        search_term = search.lower().strip() if search else None
        category_term = category.strip() if category and category.lower() != "todos" else None
        brand_term = brand.strip().lower() if brand and brand.lower() != "todas" else None

        for prod in products:
            # 1. Filtro por categoría
            if category_term and prod.category.lower() != category_term.lower():
                continue

            # 2. Filtro por búsqueda general (title, category, bestStoreName)
            if search_term:
                match_search = (
                    search_term in prod.title.lower()
                    or search_term in prod.category.lower()
                    or search_term in prod.best_store_name.lower()
                )
                if not match_search:
                    continue

            # 3. Filtro por marca
            if brand_term:
                title_lower = prod.title.lower()
                brand_in_specs = prod.tech_specs.get("Marca", "").lower()
                if brand_term not in title_lower and brand_term != brand_in_specs:
                    continue

            # 4. Filtro por procesador
            if processor:
                proc_query = processor.lower().strip()
                proc_spec = prod.tech_specs.get("Procesador", "").lower()
                if proc_query not in prod.title.lower() and proc_query not in proc_spec:
                    continue

            # 5. Filtro por RAM
            if ram:
                ram_query = ram.lower().replace(" ", "")
                ram_spec = prod.tech_specs.get("Memoria RAM", "").lower().replace(" ", "")
                title_ram = prod.title.lower().replace(" ", "")
                if ram_query not in ram_spec and ram_query not in title_ram:
                    continue

            # 6. Filtro por almacenamiento
            if storage:
                storage_query = storage.lower().replace(" ", "")
                storage_spec = prod.tech_specs.get("Almacenamiento", "").lower().replace(" ", "")
                title_storage = prod.title.lower().replace(" ", "")
                if storage_query not in storage_spec and storage_query not in title_storage:
                    continue

            # 7. Filtro por resolución de TV
            if tv_resolution:
                res_query = tv_resolution.lower().strip()
                res_spec = prod.tech_specs.get("Resolución", "").lower()
                features_str = " ".join(prod.features).lower()
                if (
                    res_query not in prod.title.lower()
                    and res_query not in res_spec
                    and res_query not in features_str
                ):
                    continue

            # 8. Recálculo dinámico por tiendas habilitadas
            effective_store_prices = prod.store_prices
            if allowed_store_ids:
                effective_store_prices = [
                    sp for sp in prod.store_prices if sp.store_id.lower() in allowed_store_ids
                ]
                if not effective_store_prices:
                    # Producto no disponible en las tiendas habilitadas
                    continue

            # Clonar o recalcular datos con base en tiendas activas
            sorted_stores = sorted(effective_store_prices, key=lambda x: x.price)
            # Reasignar bandera is_best_price
            adjusted_stores: List[StorePriceSchema] = []
            for idx, sp in enumerate(sorted_stores):
                adjusted_stores.append(
                    StorePriceSchema(
                        store_id=sp.store_id,
                        store_name=sp.store_name,
                        price=sp.price,
                        original_price=sp.original_price,
                        offer_url=sp.offer_url,
                        is_best_price=(idx == 0),
                    )
                )

            effective_best_price = adjusted_stores[0].price
            effective_best_store = adjusted_stores[0].store_name
            effective_discount = calculate_discount_percentage(
                prod.original_price, effective_best_price
            )
            effective_hist_min = (
                effective_best_price <= prod.historical_min_price
                if prod.historical_min_price
                else True
            )

            result_item = ProductSchema(
                id=prod.id,
                title=prod.title,
                category=prod.category,
                best_price=effective_best_price,
                original_price=prod.original_price,
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
                is_historical_min=effective_hist_min,
                price_history_30_days=prod.price_history_30_days,
            )
            results.append(result_item)

        # 9. Ordenamiento por precio
        if sort_order == "HIGH_TO_LOW":
            results.sort(key=lambda x: x.best_price, reverse=True)
        else:
            results.sort(key=lambda x: x.best_price, reverse=False)

        return results

    def get_product_by_id(self, product_id: str, db: Session) -> Optional[ProductSchema]:
        """Retorna el detalle completo de un producto por su identificador."""
        all_prods = self._get_base_products(db)
        for p in all_prods:
            if p.id == product_id:
                return p
        return None

    # ==========================================================================
    # 4. TIENDAS OFICIALES Y ESTADO
    # ==========================================================================

    def get_stores(self) -> List[StoreSchema]:
        """Retorna las 8 tiendas retail soportadas con el estado de su Circuit Breaker."""
        statuses = collector_registry.get_all_stores_status()
        result: List[StoreSchema] = []
        for s in statuses:
            result.append(
                StoreSchema(
                    id=s["id"],
                    name=s["name"],
                    code=s["code"],
                    is_enabled=s["is_enabled"],
                    circuit_status=s["circuit_status"],
                )
            )
        return result

    # ==========================================================================
    # 5. OFERTAS FÍSICAS COMUNITARIAS
    # ==========================================================================

    def get_community_offers(
        self,
        db: Session,
        department: Optional[str] = None,
        province: Optional[str] = None,
        district: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> List[CommunityPhysicalOfferSchema]:
        """Lista ofertas físicas reportadas por usuarios con filtros de ubigeo."""
        query = db.query(CommunityOfferModel)

        if department:
            query = query.filter(CommunityOfferModel.department.ilike(f"%{department.strip()}%"))
        if province:
            query = query.filter(CommunityOfferModel.province.ilike(f"%{province.strip()}%"))
        if district:
            query = query.filter(CommunityOfferModel.district.ilike(f"%{district.strip()}%"))
        if product_id:
            query = query.filter(CommunityOfferModel.product_id == product_id.strip())

        query = query.order_by(CommunityOfferModel.timestamp_millis.desc())
        items = query.all()

        schemas = []
        for o in items:
            schemas.append(
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
            )
        return schemas

    def create_community_offer(
        self, db: Session, offer_in: CommunityOfferCreateSchema
    ) -> CommunityPhysicalOfferSchema:
        """Valida y crea una nueva oferta física reportada."""
        # Validar departamento contra lista oficial de Perú
        norm_dept = offer_in.department.strip()
        matched_dept = next((d for d in PERU_DEPARTMENTS if d.lower() == norm_dept.lower()), None)
        if not matched_dept:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Departamento inválido: '{offer_in.department}'. Debe ser un departamento oficial del Perú.",
            )

        # Verificar existencia del producto
        product = db.query(ProductModel).filter(ProductModel.id == offer_in.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con ID '{offer_in.product_id}' no encontrado en el catálogo.",
            )

        product_name = offer_in.product_name or product.title
        now_utc = datetime.now(timezone.utc)
        timestamp_ms = int(now_utc.timestamp() * 1000)
        formatted_date = now_utc.strftime("%d %b %Y, %H:%M")

        new_offer = CommunityOfferModel(
            id=f"comm_off_{uuid.uuid4().hex[:8]}",
            product_id=product.id,
            product_name=sanitize_input_text(product_name, max_length=150),
            physical_store_name=sanitize_input_text(offer_in.physical_store_name, max_length=120),
            department=matched_dept,
            province=sanitize_input_text(offer_in.province, max_length=100),
            district=sanitize_input_text(offer_in.district, max_length=100),
            price_found=round(offer_in.price_found, 2),
            photo_uri=offer_in.photo_uri or "",
            comment=sanitize_input_text(offer_in.comment or "", max_length=500),
            timestamp_millis=timestamp_ms,
            formatted_date=formatted_date,
            author_name=sanitize_input_text(offer_in.author_name or "Usuario FinPrice", max_length=80),
        )

        db.add(new_offer)
        db.commit()
        db.refresh(new_offer)

        logger.info(
            f"Nueva oferta comunitaria registrada: {new_offer.id} para {product.id} en {matched_dept}"
        )

        return CommunityPhysicalOfferSchema(
            id=new_offer.id,
            product_id=new_offer.product_id,
            product_name=new_offer.product_name,
            physical_store_name=new_offer.physical_store_name,
            department=new_offer.department,
            province=new_offer.province,
            district=new_offer.district,
            price_found=new_offer.price_found,
            photo_uri=new_offer.photo_uri or "",
            comment=new_offer.comment or "",
            timestamp_millis=new_offer.timestamp_millis,
            formatted_date=new_offer.formatted_date,
            author_name=new_offer.author_name,
        )

    # ==========================================================================
    # 6. RETROCOMPATIBILIDAD CON /products ORIGINAL
    # ==========================================================================

    def get_legacy_products(
        self, db: Session, search: Optional[str] = None
    ) -> List[ProductResponse]:
        """
        Retorna la lista de productos en el formato del contrato anterior GET /products
        para garantizar retrocompatibilidad total con pruebas y clientes previos.
        """
        products = self._get_base_products(db)
        results: List[ProductResponse] = []

        search_lower = search.lower().strip() if search else None

        for prod in products:
            if search_lower and search_lower not in prod.title.lower():
                continue

            # Mapear 'prod_1' a int 1, o hash si no tiene sufijo entero
            int_id = 1
            if prod.id.startswith("prod_"):
                suffix = prod.id.replace("prod_", "")
                if suffix.isdigit():
                    int_id = int(suffix)
                else:
                    int_id = abs(hash(prod.id)) % 10000
            elif prod.id.isdigit():
                int_id = int(prod.id)

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
