"""
Motor automático genérico de agrupación y promoción de catálogo (`store_listings` -> `products` + `store_offers` + `price_history`).

Fase 2B:
1. Lee `store_listings` activos (`in_stock=True`, `price > 0`) descartando marketplace y outliers.
2. Paso 1: Enlaza estrictamente listings coincidentes con productos existentes (`prod_*` semilla) sin
   corromper sus IDs, títulos históricos ni `price_history` previo.
3. Paso 2: Agrupa los listings restantes en clústeres multi-tienda (2-8 tiendas) y de 1 sola tienda
   mediante Union-Find por EAN, MPN o `(categoría, marca, firma normalizada)`, validando cero contradicciones
   de variante (`Slim` vs `Pro`, `24"` vs `27"`, `40mm` vs `44mm`, `MK470` vs `MK270`, `Pack 1` vs `Pack 3`, etc.).
4. Paso 3: Promueve de forma idempotente hacia `products` (ID determinístico `auto_<slug>_<hash8>`),
   `store_offers` y el punto diario en `price_history`, con soporte completo de `dry_run=True` sin escrituras.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import re
import statistics
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.collectors.category_registry import (
    ALL_TECH_CATEGORIES,
    CATEGORY_REGISTRY,
    get_category_spec,
    infer_tech_category,
    resolve_category_display_name,
)
from app.collectors.color_stripper import strip_color_tokens
from app.collectors.orchestrator import format_peru_date_label, get_today_peru, utc_now
from app.collectors.spec_extractor import (
    generate_product_features,
    merge_product_specs,
    normalize_brand,
)
from app.collectors.tech_normalizer import (
    _normalize_gtin,
    _normalize_mpn,
    _strip_bundles_and_colors,
    are_listings_variant_compatible,
    build_canonical_product_signature,
    evaluate_strict_guardrails,
    extract_product_codes,
    extract_variant_profile,
    is_signature_specific_enough,
    is_strict_tech_product,
    strip_accents_lower,
)
from app.collectors.url_utils import (
    canonicalize_store_url,
    ensure_https_image_url,
    is_marketplace_url,
    is_valid_product_image_url,
)
from app.collectors.validators import (
    select_best_canonical_image,
    validate_cross_store_prices,
    validate_product_identity,
)
from app.core.database import ReaderSessionLocal, WriterSessionLocal
from app.core.logging import get_logger
from app.models.entities import (
    PriceHistoryEntity,
    ProductEntity,
    StoreListing,
    StoreOfferEntity,
)

logger = get_logger("collectors.catalog_promoter")

_STORE_DISPLAY_NAMES: Dict[str, str] = {
    "falabella": "Falabella",
    "ripley": "Ripley",
    "tottus": "Tottus",
    "efe": "Tiendas Efe",
    "curacao": "La Curacao",
    "hiraoka": "Hiraoka",
    "metro": "Metro",
    "wong": "Wong",
}

_DISPLAY_TO_SLUG_MAP: Dict[str, str] = {
    strip_accents_lower(resolve_category_display_name(slug)): slug
    for slug in ALL_TECH_CATEGORIES
}

_PRESERVE_UPPER_WORDS: Set[str] = {
    "OLED", "QLED", "QNED", "QHD", "WQHD", "UWQHD", "FHD", "UHD", "HD", "4K", "8K",
    "IPS", "VA", "TN", "LED", "LCD", "HDR", "HDR10", "5G", "4G", "LTE", "GPS", "NFC",
    "USB", "USB-C", "USBC", "HDMI", "NVME", "SATA", "SSD", "HDD", "RAM", "ROM", "DPI",
    "RGB", "ANC", "TWS", "RMS", "BT", "PC", "TV", "DJ", "AI", "SE", "FE", "GT", "XT",
    "LG", "HP", "MSI", "TCL", "AOC", "JBL", "DJI", "WD", "TP-LINK", "PS5", "PS4", "EOS",
}

_NON_HARDWARE_SOFTWARE_RE = re.compile(
    r"^(?:antivirus|bitdefender|kaspersky|mcafee|norton|microsoft\s+365|office\s+365|licencia|suscripcion|gift\s+card|membresia|tarjeta\s+de\s+regalo)\b"
    r"|\b(?:antivirus|bitdefender|kaspersky|mcafee|norton|gift\s+card|membresia|tarjeta\s+de\s+regalo)\b",
    flags=re.IGNORECASE,
)


@dataclass
class _EnrichedListing:
    entity: Optional[StoreListing]
    idx: int
    store: str
    store_name: str
    store_sku: str
    effective_category: str
    display_category: str
    title: str
    clean_title: str
    brand: str
    price: float
    original_price: float
    offer_url: str
    image_url: str
    eans: Set[str]
    mpns: Set[str]
    canonical_signature: str
    is_specific_sig: bool
    variant_profile: Dict[str, Any]
    existing_canonical_product_id: Optional[str]


@dataclass
class ExistingLinkSummary:
    listing_id: Optional[int]
    store: str
    product_id: str
    product_title: str
    price: float
    match_reason: str


@dataclass
class PromotedGroupPreview:
    product_id: str
    title: str
    category: str
    brand: str
    stores_count: int
    best_price: float
    original_price: float
    savings_amount: float
    discount_percentage: int
    canonical_signature: str
    store_prices: Dict[str, float] = field(default_factory=dict)


@dataclass
class CatalogPromotionSummary:
    active_listings_scanned: int = 0
    discarded_invalid_or_outliers: int = 0
    discarded_non_tech: int = 0
    discarded_no_image: int = 0
    linked_to_existing_products: int = 0
    existing_offers_upserted: int = 0
    new_multi_store_groups: int = 0
    new_single_store_products: int = 0
    total_promoted_products: int = 0
    offers_promoted: int = 0
    history_points_upserted: int = 0
    pruned_auto_products_total: int = 0
    pruned_non_tech_listings: int = 0
    pruned_by_reason: Dict[str, int] = field(default_factory=dict)
    dry_run: bool = False
    by_category: Dict[str, Dict[str, int]] = field(default_factory=dict)
    existing_links: List[ExistingLinkSummary] = field(default_factory=list)
    multi_store_examples: List[PromotedGroupPreview] = field(default_factory=list)


def _display_to_category_slug(display_or_slug: str) -> str:
    low = strip_accents_lower(str(display_or_slug or "").strip())
    if low in CATEGORY_REGISTRY:
        return low
    return _DISPLAY_TO_SLUG_MAP.get(low, low)


def _min_valid_price_for_category(cat_slug: str) -> float:
    spec = get_category_spec(cat_slug)
    return float(spec.min_valid_price_pen) if spec else 15.0


def _prettify_title_casing(text: str) -> str:
    """Convierte títulos retail totalmente en mayúsculas a capitalización limpia preservando siglas tech."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip(" |-•")
    if not clean:
        return ""

    alpha_chars = [c for c in clean if c.isalpha()]
    upper_ratio = (sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)) if alpha_chars else 0.0
    if upper_ratio < 0.78:
        return clean[:255]

    words: List[str] = []
    lower_connectors = {"de", "del", "la", "las", "el", "los", "y", "con", "para", "en", "a"}
    for i, raw_w in enumerate(clean.split()):
        w_up = raw_w.upper()
        stripped_up = w_up.strip(",.()[]\"")
        if stripped_up in _PRESERVE_UPPER_WORDS:
            words.append(w_up)
        elif re.match(r"^\d+(?:GB|TB|MB|HZ|MM|MP|MAH|W)$", stripped_up):
            words.append(stripped_up)
        elif re.match(r"^[A-Z0-9\-/]*\d[A-Z0-9\-/]*$", stripped_up) and len(stripped_up) >= 3:
            words.append(w_up)
        elif i > 0 and stripped_up.lower() in lower_connectors:
            words.append(raw_w.lower())
        else:
            words.append(raw_w.capitalize())
    return " ".join(words)[:255]


def _select_clean_canonical_title(candidates: Sequence[_EnrichedListing]) -> str:
    """Elige el título más limpio, descriptivo y sin colores ni ruido promocional del grupo."""
    best_score = -9999.0
    best_title = ""

    for c in candidates:
        raw = str(c.title or "").strip()
        stripped = strip_color_tokens(_strip_bundles_and_colors(raw, category=c.effective_category) or raw)
        stripped = re.sub(r"\s+", " ", stripped).strip(" |-•,+")
        if not stripped:
            stripped = raw

        pretty = _prettify_title_casing(stripped)
        if not pretty:
            continue

        score = 0.0
        alpha_chars = [ch for ch in raw if ch.isalpha()]
        if alpha_chars:
            up_ratio = sum(1 for ch in alpha_chars if ch.isupper()) / len(alpha_chars)
            if 0.05 <= up_ratio <= 0.55:
                score += 18.0
            elif up_ratio > 0.85:
                score -= 10.0

        if c.brand and c.brand.lower() in pretty.lower():
            score += 10.0

        length = len(pretty)
        if 18 <= length <= 95:
            score += 14.0
        elif 95 < length <= 145:
            score += 6.0
        elif length < 12:
            score -= 20.0
        else:
            score -= 8.0

        low_pretty = pretty.lower()
        for noisy in ("envio gratis", "oferta", "cuotas", "sin interes", "stock limitado", "descuento"):
            if noisy in low_pretty:
                score -= 18.0

        # Desempate determinístico favoreciendo fichas mejor curadas
        store_bonus = {
            "hiraoka": 4.0,
            "falabella": 3.5,
            "ripley": 3.0,
            "efe": 2.0,
            "curacao": 2.0,
            "tottus": 1.5,
            "wong": 1.0,
            "metro": 1.0,
        }.get(c.store, 0.0)
        score += store_bonus

        if score > best_score:
            best_score = score
            best_title = pretty

    return (best_title or candidates[0].title)[:255]


def _select_best_https_image(offers: Sequence[_EnrichedListing]) -> str:
    """Selecciona la mejor imagen HTTPS válida priorizando retailers oficiales; rechaza HTTP plano o placeholders."""
    https_candidates: List[Dict[str, str]] = []
    for o in offers:
        norm_img = ensure_https_image_url(o.image_url)
        if norm_img and norm_img.lower().startswith("https://") and is_valid_product_image_url(norm_img):
            https_candidates.append({"store_id": o.store, "image_url": norm_img})
    if https_candidates:
        chosen = select_best_canonical_image(https_candidates)
        if chosen and chosen.lower().startswith("https://") and is_valid_product_image_url(chosen):
            return chosen[:500]
    return ""


def _build_deterministic_auto_id(
    rep: _EnrichedListing,
    members: Sequence[_EnrichedListing],
    used_ids: Set[str],
) -> str:
    """
    Construye un ID canónico determinístico `auto_<slug_corto>_<hash8>` (<= 80 chars).
    Reutiliza un `auto_*` previo si el grupo ya estuvo enlazado de manera consistente.
    """
    prev_auto_ids = {
        m.existing_canonical_product_id
        for m in members
        if m.existing_canonical_product_id and m.existing_canonical_product_id.startswith("auto_")
    }
    if len(prev_auto_ids) == 1:
        reused = next(iter(prev_auto_ids))
        if reused not in used_ids and len(reused) <= 80:
            return reused

    has_multi_or_specific = len({m.store for m in members}) >= 2 or rep.is_specific_sig or bool(rep.eans or rep.mpns)
    if has_multi_or_specific:
        anchor = rep.canonical_signature or (
            sorted(rep.eans)[0] if rep.eans else sorted(rep.mpns)[0]
        )
        seed_key = f"{rep.effective_category}|{rep.brand.lower()}|{anchor}"
        slug_source = rep.canonical_signature or rep.clean_title
    else:
        seed_key = f"{rep.effective_category}|{rep.store}|{rep.store_sku}"
        slug_source = rep.clean_title or rep.store_sku

    raw_slug = re.sub(r"[^a-z0-9]+", "_", strip_accents_lower(slug_source)).strip("_")
    raw_slug = re.sub(r"_+", "_", raw_slug) or rep.effective_category
    if len(raw_slug) > 36:
        cut = raw_slug[:36]
        if "_" in cut and cut.rfind("_") >= 12:
            cut = cut[: cut.rfind("_")]
        raw_slug = cut.strip("_") or raw_slug[:36]

    hash8 = hashlib.sha1(seed_key.encode("utf-8")).hexdigest()[:8]
    cand_id = f"auto_{raw_slug}_{hash8}"[:80]

    suffix = 2
    while cand_id in used_ids:
        hash8_alt = hashlib.sha1(f"{seed_key}#{suffix}".encode("utf-8")).hexdigest()[:8]
        cand_id = f"auto_{raw_slug[:30]}_{hash8_alt}"[:80]
        suffix += 1
    return cand_id


def _enrich_raw_listing(
    row: Any,
    idx: int,
) -> Optional[_EnrichedListing]:
    """Valida y enriquece un `StoreListing` (o `ScrapedListing`) recalculando la firma Fase 2B."""
    store = str(getattr(row, "store", "") or "").strip().lower()
    title = re.sub(r"\s+", " ", str(getattr(row, "title", "") or "")).strip()
    raw_url = str(getattr(row, "url", "") or "").strip()
    price = float(getattr(row, "price", 0.0) or 0.0)
    in_stock = bool(getattr(row, "in_stock", True))

    if not store or not title or not raw_url or not in_stock or price <= 0.0:
        return None
    if _NON_HARDWARE_SOFTWARE_RE.search(strip_accents_lower(title)):
        return None

    _, clean_u = canonicalize_store_url(raw_url)
    eff_url = (clean_u or raw_url).strip()
    if is_marketplace_url(store, eff_url):
        return None

    raw_cat = str(getattr(row, "category", "") or "").strip().lower() or "otros_tech"
    inferred_cat = infer_tech_category(title=title, url=eff_url, default_category="otros_tech")
    if inferred_cat != "otros_tech":
        effective_category = inferred_cat
    elif raw_cat in CATEGORY_REGISTRY:
        effective_category = raw_cat
    else:
        return None

    raw_brand = str(getattr(row, "brand", "") or "").strip()
    if not is_strict_tech_product(
        title=title,
        category=effective_category,
        url=eff_url,
        brand=raw_brand,
    ):
        return None

    if price < _min_valid_price_for_category(effective_category):
        return None

    brand = normalize_brand(raw_brand, title)

    raw_orig = getattr(row, "original_price", None)
    orig_val = round(float(raw_orig), 2) if (raw_orig and float(raw_orig) > price) else round(price, 2)

    img = ensure_https_image_url(str(getattr(row, "image_url", "") or "").strip()) or ""

    codes = extract_product_codes(title=title, url=eff_url)
    eans: Set[str] = set()
    db_ean = _normalize_gtin(getattr(row, "ean", None))
    if db_ean:
        eans.add(db_ean)
    for g in codes.get("gtin") or []:
        ng = _normalize_gtin(g)
        if ng:
            eans.add(ng)

    mpns: Set[str] = set()
    db_mpn = _normalize_mpn(getattr(row, "mpn", None))
    if db_mpn:
        mpns.add(db_mpn)
    for m in codes.get("mpn") or []:
        nm = _normalize_mpn(m)
        if nm:
            mpns.add(nm)

    sig = build_canonical_product_signature(
        title=title,
        brand=brand,
        url=eff_url,
        category=effective_category,
    )
    if not sig:
        return None

    is_spec = is_signature_specific_enough(sig, brand=brand, category=effective_category)
    profile = extract_variant_profile(
        title=title,
        url=eff_url,
        category=effective_category,
        brand=brand,
    )
    clean_title = _prettify_title_casing(
        strip_color_tokens(_strip_bundles_and_colors(title, category=effective_category) or title)
    )

    entity_ref = row if isinstance(row, StoreListing) else None
    sku_val = str(getattr(row, "store_sku", "") or "").strip()
    existing_canon = getattr(row, "canonical_product_id", None)

    return _EnrichedListing(
        entity=entity_ref,
        idx=idx,
        store=store,
        store_name=_STORE_DISPLAY_NAMES.get(store, store.title()),
        store_sku=sku_val,
        effective_category=effective_category,
        display_category=resolve_category_display_name(effective_category),
        title=title,
        clean_title=clean_title or title,
        brand=brand,
        price=round(price, 2),
        original_price=orig_val,
        offer_url=eff_url,
        image_url=img,
        eans=eans,
        mpns=mpns,
        canonical_signature=sig,
        is_specific_sig=is_spec,
        variant_profile=profile,
        existing_canonical_product_id=existing_canon,
    )


def _match_existing_product(
    cand: _EnrichedListing,
    base_products_meta: Sequence[Dict[str, Any]],
) -> Optional[Tuple[ProductEntity, str]]:
    """
    Paso 1: Verifica si un listing coincide estrictamente con algún producto existente (`prod_*`)
    por EAN/MPN exacto o por firma normalizada + identidad/guardrails + cordura de precio.
    """
    for meta in base_products_meta:
        prod: ProductEntity = meta["entity"]
        if cand.display_category.lower() != meta["display_category"].lower():
            continue

        if cand.brand and meta["brand_low"] and cand.brand.lower() != meta["brand_low"]:
            continue

        ref_price = meta["ref_price"]
        if ref_price > 0 and not ((ref_price * 0.55) <= cand.price <= (ref_price * 1.85)):
            continue

        exact_ean = bool(cand.eans & meta["eans"])
        exact_mpn = bool(cand.mpns & meta["mpns"])
        if exact_ean or exact_mpn:
            if are_listings_variant_compatible(meta["profile"], cand.variant_profile) and evaluate_strict_guardrails(
                canonical_title=prod.title,
                scraped_title=cand.title,
                scraped_url=cand.offer_url,
                target_specs=meta["tech_specs"],
                exact_code_matched=True,
            ):
                return (prod, "ean" if exact_ean else "mpn")

        if (
            are_listings_variant_compatible(meta["profile"], cand.variant_profile)
            and validate_product_identity(
                canonical_title=prod.title,
                scraped_title=cand.title,
                scraped_url=cand.offer_url,
                store_id=cand.store,
                target_tech_specs=meta["tech_specs"],
            )
        ):
            reason = (
                "signature"
                if (cand.is_specific_sig and meta["canonical_signature"] and cand.canonical_signature == meta["canonical_signature"])
                else "identity"
            )
            return (prod, reason)

    return None


def _cluster_remaining_listings(
    items: Sequence[_EnrichedListing],
) -> Tuple[List[List[_EnrichedListing]], int]:
    """
    Paso 2: Agrupa los listings restantes mediante Union-Find validando compatibilidad mutua de
    variantes y coherencia de precios inter-tienda en cada fusión.
    """
    n = len(items)
    if n == 0:
        return ([], 0)

    parent = list(range(n))
    comp_members: Dict[int, List[int]] = {i: [i] for i in range(n)}

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _try_union(a_idx: int, b_idx: int) -> None:
        ra = _find(a_idx)
        rb = _find(b_idx)
        if ra == rb:
            return

        members_a = comp_members[ra]
        members_b = comp_members[rb]

        for ma in members_a:
            prof_a = items[ma].variant_profile
            for mb in members_b:
                if not are_listings_variant_compatible(prof_a, items[mb].variant_profile):
                    return

        combined_prices = [items[k].price for k in members_a] + [items[k].price for k in members_b]
        ref_p = max(combined_prices) if len(combined_prices) == 2 else float(statistics.median(combined_prices))
        if ref_p > 0 and min(combined_prices) < (ref_p * 0.50):
            return

        if len(members_a) < len(members_b):
            ra, rb = rb, ra
            members_a, members_b = members_b, members_a

        parent[rb] = ra
        members_a.extend(members_b)
        del comp_members[rb]

    ean_buckets: Dict[Tuple[str, str], List[int]] = {}
    mpn_buckets: Dict[Tuple[str, str], List[int]] = {}
    sig_buckets: Dict[Tuple[str, str], List[int]] = {}

    for idx, item in enumerate(items):
        for g in sorted(item.eans):
            ean_buckets.setdefault((item.effective_category, g), []).append(idx)
        for m in sorted(item.mpns):
            mpn_buckets.setdefault((item.effective_category, m), []).append(idx)
        if item.is_specific_sig and item.canonical_signature:
            sig_buckets.setdefault((item.effective_category, item.canonical_signature), []).append(idx)

    for bucket_map in (ean_buckets, mpn_buckets, sig_buckets):
        for bucket in bucket_map.values():
            if len(bucket) < 2:
                continue
            anchor = bucket[0]
            for other in bucket[1:]:
                _try_union(anchor, other)

    clusters: List[List[_EnrichedListing]] = []
    outliers_discarded = 0

    for idx_list in comp_members.values():
        raw_group = [items[k] for k in idx_list]
        if len(raw_group) >= 2:
            clean_group = validate_cross_store_prices(raw_group)
            outliers_discarded += len(raw_group) - len(clean_group)
            if not clean_group:
                continue
            clusters.append(clean_group)
        else:
            clusters.append(raw_group)

    return (clusters, outliers_discarded)


def _consolidate_cluster_offers(members: Sequence[_EnrichedListing]) -> List[_EnrichedListing]:
    """Consolida como máximo 1 oferta activa por tienda manteniendo el menor precio 1P disponible."""
    by_store: Dict[str, List[_EnrichedListing]] = {}
    for m in members:
        by_store.setdefault(m.store, []).append(m)

    consolidated: List[_EnrichedListing] = []
    for store_items in by_store.values():
        store_items.sort(
            key=lambda x: (
                x.price,
                0 if (x.image_url and x.image_url.startswith("https://")) else 1,
                -x.original_price,
                x.store_sku,
            )
        )
        consolidated.append(store_items[0])

    consolidated.sort(key=lambda x: (x.price, x.store))
    return consolidated


def _bump_category_stat(
    bucket: Dict[str, Dict[str, int]],
    display_category: str,
    *,
    multi_store: int = 0,
    single_store: int = 0,
    linked_existing: int = 0,
) -> None:
    if display_category not in bucket:
        bucket[display_category] = {
            "multi_store": 0,
            "single_store": 0,
            "total": 0,
            "linked_existing": 0,
        }
    row = bucket[display_category]
    row["multi_store"] += multi_store
    row["single_store"] += single_store
    row["total"] += multi_store + single_store
    row["linked_existing"] += linked_existing


async def _upsert_today_price_history(
    session: AsyncSession,
    product: ProductEntity,
    best_price: float,
    orig_price: float,
    today_peru: date,
    existing_history: Sequence[PriceHistoryEntity],
    now_dt: datetime,
) -> Tuple[float, bool, float, float, int]:
    """
    Mantiene historial diario idempotente para `product` sin modificar ni inventar días pasados.
    Retorna `(historical_min_price, is_historical_min, previous_best_price, price_drop_amount, days_tracked)`.
    """
    t_iso = today_peru.isoformat()
    t_label = format_peru_date_label(today_peru)

    today_row: Optional[PriceHistoryEntity] = None
    past_prices: List[float] = []
    sorted_rows = sorted(existing_history, key=lambda h: h.day_offset)

    for h_row in sorted_rows:
        r_date = str(getattr(h_row, "recorded_date", "") or "").strip()
        if r_date == t_iso or (not r_date and h_row.day_offset == 0):
            if today_row is None:
                today_row = h_row
            else:
                today_row.price = round(min(float(today_row.price), float(h_row.price)), 2)
                await session.delete(h_row)
        elif float(h_row.price or 0.0) > 0:
            past_prices.append(float(h_row.price))

    if today_row is not None:
        today_row.price = round(min(float(today_row.price), best_price), 2)
        today_row.day_offset = 0
        today_row.date_label = t_label
        today_row.recorded_date = t_iso
        today_row.recorded_at = now_dt
    else:
        today_row = PriceHistoryEntity(
            product_id=product.id,
            day_offset=0,
            date_label=t_label,
            recorded_date=t_iso,
            price=best_price,
            recorded_at=now_dt,
        )
        session.add(today_row)

    all_prices = past_prices + [float(today_row.price), best_price]
    prev_hist_min = (
        float(product.historical_min_price)
        if product.historical_min_price and float(product.historical_min_price) > 0
        else best_price
    )
    hist_min = round(min(all_prices + [prev_hist_min]), 2)
    is_hist_min = bool(best_price <= hist_min)
    prev_best = round(past_prices[-1], 2) if past_prices else round(orig_price, 2)
    drop_amt = round(max(0.0, orig_price - best_price), 2)
    if past_prices and past_prices[-1] > best_price:
        drop_amt = round(max(drop_amt, past_prices[-1] - best_price), 2)
    days_tracked = max(1, len(past_prices) + 1)

    return (hist_min, is_hist_min, prev_best, drop_amt, days_tracked)


async def promote_store_listings(
    session: Optional[AsyncSession] = None,
    dry_run: bool = False,
    in_memory_listings: Optional[Sequence[Any]] = None,
    today_peru: Optional[date] = None,
) -> CatalogPromotionSummary:
    """
    Orquesta el agrupamiento y promoción automática de `store_listings` hacia
    `products`, `store_offers` y `price_history`.

    - Cuando `dry_run=True`, NO realiza escrituras en base de datos y retorna las métricas reales
      y ejemplos multi-tienda listos para inspección.
    - Preserva intactos los productos semilla `prod_*` y sus historiales previos.
    """
    if session is None:
        session_cm = ReaderSessionLocal() if dry_run else WriterSessionLocal()
        async with session_cm as owned_session:
            return await promote_store_listings(
                session=owned_session,
                dry_run=dry_run,
                in_memory_listings=in_memory_listings,
                today_peru=today_peru,
            )

    summary = CatalogPromotionSummary(dry_run=dry_run)
    t_peru = today_peru or get_today_peru()
    now_dt = utc_now()

    # 1. Cargar productos actuales con ofertas, historial y relaciones comunitarias
    prod_res = await session.execute(
        select(ProductEntity)
        .options(
            selectinload(ProductEntity.store_offers),
            selectinload(ProductEntity.price_history),
            selectinload(ProductEntity.community_offers),
            selectinload(ProductEntity.community_posts),
        )
        .execution_options(populate_existing=True)
    )
    existing_products: List[ProductEntity] = list(prod_res.scalars().all())
    products_by_id: Dict[str, ProductEntity] = {p.id: p for p in existing_products}

    base_products_meta: List[Dict[str, Any]] = []
    for p in existing_products:
        if str(p.id).startswith("auto_"):
            continue
        raw_specs = json.loads(p.tech_specs_json) if p.tech_specs_json else {}
        disp_cat = resolve_category_display_name(p.category)
        cat_slug = _display_to_category_slug(disp_cat)
        brand = raw_specs.get("Marca") or normalize_brand(p.brand, p.title)
        codes = extract_product_codes(tech_specs=raw_specs, title=p.title)
        active_prices = [
            float(o.price)
            for o in (p.store_offers or [])
            if o.price and float(o.price) > 0
        ]
        ref_price = (
            float(statistics.median(active_prices))
            if active_prices
            else float(p.best_price or 0.0)
        )
        base_products_meta.append(
            {
                "entity": p,
                "display_category": disp_cat,
                "cat_slug": cat_slug,
                "brand_low": strip_accents_lower(brand),
                "tech_specs": raw_specs,
                "eans": {_normalize_gtin(g) for g in (codes.get("gtin") or []) if _normalize_gtin(g)},
                "mpns": {_normalize_mpn(m) for m in (codes.get("mpn") or []) if _normalize_mpn(m)},
                "canonical_signature": build_canonical_product_signature(
                    title=p.title,
                    brand=brand,
                    url="",
                    category=cat_slug,
                ),
                "profile": extract_variant_profile(
                    title=p.title,
                    url="",
                    category=cat_slug,
                    brand=brand,
                ),
                "ref_price": ref_price,
            }
        )

    # 2. Cargar listings (en modo BD auditamos todos para detectar no-tech y desactualizados)
    all_db_listings: List[StoreListing] = []
    if in_memory_listings is not None:
        raw_rows: List[Any] = [
            r for r in in_memory_listings
            if bool(getattr(r, "in_stock", True)) and float(getattr(r, "price", 0.0) or 0.0) > 0.0
        ]
    else:
        listing_res = await session.execute(select(StoreListing))
        all_db_listings = list(listing_res.scalars().all())
        raw_rows = []
        for db_row in all_db_listings:
            row_title = re.sub(r"\s+", " ", str(db_row.title or "")).strip()
            row_cat = str(db_row.category or "").strip().lower() or "otros_tech"
            row_brand = str(db_row.brand or "").strip()
            is_tech_row = (
                bool(row_title)
                and not _NON_HARDWARE_SOFTWARE_RE.search(strip_accents_lower(row_title))
                and is_strict_tech_product(
                    title=row_title,
                    category=row_cat,
                    url=str(db_row.url or ""),
                    brand=row_brand,
                )
            )
            if not is_tech_row:
                summary.pruned_non_tech_listings += 1
                if not dry_run:
                    await session.delete(db_row)
                if bool(db_row.in_stock) and float(db_row.price or 0.0) > 0.0:
                    raw_rows.append(db_row)
                continue
            if bool(db_row.in_stock) and float(db_row.price or 0.0) > 0.0:
                raw_rows.append(db_row)

    enriched: List[_EnrichedListing] = []
    for idx, row in enumerate(raw_rows):
        item = _enrich_raw_listing(row, idx=idx)
        if item is None:
            summary.discarded_invalid_or_outliers += 1
            row_title = str(getattr(row, "title", "") or "")
            if row_title and (
                _NON_HARDWARE_SOFTWARE_RE.search(strip_accents_lower(row_title))
                or not is_strict_tech_product(
                    title=row_title,
                    category=str(getattr(row, "category", "") or ""),
                    url=str(getattr(row, "url", "") or ""),
                    brand=str(getattr(row, "brand", "") or ""),
                )
            ):
                summary.discarded_non_tech += 1
            continue
        enriched.append(item)

    summary.active_listings_scanned = len(raw_rows)

    # 3. Paso 1: Match estricto contra catálogo base existente (`prod_*`)
    remaining: List[_EnrichedListing] = []
    matched_by_base_prod: Dict[str, List[Tuple[_EnrichedListing, str]]] = {}

    for cand in enriched:
        match_res = _match_existing_product(cand, base_products_meta)
        if match_res is not None:
            base_prod, match_reason = match_res
            matched_by_base_prod.setdefault(base_prod.id, []).append((cand, match_reason))
        else:
            remaining.append(cand)

    for prod_id, paired_list in matched_by_base_prod.items():
        base_prod = products_by_id[prod_id]
        # Si hay varios colores en la misma tienda para el mismo prod_*, elegir el menor precio activo
        best_by_store: Dict[str, Tuple[_EnrichedListing, str]] = {}
        for cand, reason in paired_list:
            if not dry_run and cand.entity is not None:
                cand.entity.canonical_product_id = prod_id
                cand.entity.normalized_signature = cand.canonical_signature
            summary.linked_to_existing_products += 1
            summary.existing_links.append(
                ExistingLinkSummary(
                    listing_id=cand.entity.id if cand.entity is not None else None,
                    store=cand.store,
                    product_id=prod_id,
                    product_title=base_prod.title,
                    price=cand.price,
                    match_reason=reason,
                )
            )
            _bump_category_stat(
                summary.by_category,
                resolve_category_display_name(base_prod.category),
                linked_existing=1,
            )

            prev_pair = best_by_store.get(cand.store)
            if prev_pair is None or cand.price < prev_pair[0].price:
                best_by_store[cand.store] = (cand, reason)

        if dry_run:
            continue

        existing_offers_map: Dict[str, StoreOfferEntity] = {
            off.store_id.lower(): off for off in (base_prod.store_offers or [])
        }
        all_offer_prices_ref = [
            float(off.price)
            for off in existing_offers_map.values()
            if off.price and float(off.price) > 0
        ]
        ref_med = (
            float(statistics.median(all_offer_prices_ref))
            if all_offer_prices_ref
            else float(base_prod.best_price or 0.0)
        )

        offers_changed = False
        for store_id, (cand, _reason) in best_by_store.items():
            if ref_med > 0 and cand.price < (ref_med * 0.55):
                continue

            existing_off = existing_offers_map.get(store_id)
            if existing_off is not None:
                if (
                    float(existing_off.price or 0.0) <= 0.0
                    or abs(float(existing_off.price) - cand.price) >= 0.01
                ):
                    existing_off.price = cand.price
                    existing_off.original_price = cand.original_price
                    existing_off.offer_url = cand.offer_url[:600]
                    existing_off.last_scraped_at = now_dt
                    summary.existing_offers_upserted += 1
                    offers_changed = True
            else:
                new_off = StoreOfferEntity(
                    product_id=base_prod.id,
                    store_id=store_id,
                    store_name=cand.store_name,
                    price=cand.price,
                    original_price=cand.original_price,
                    offer_url=cand.offer_url[:600],
                    is_best_price=False,
                    last_scraped_at=now_dt,
                )
                session.add(new_off)
                existing_offers_map[store_id] = new_off
                summary.existing_offers_upserted += 1
                offers_changed = True

        if offers_changed:
            active_offs = [
                o for o in existing_offers_map.values() if o.price and float(o.price) > 0
            ]
            active_offs.sort(key=lambda o: float(o.price))
            for idx_o, o in enumerate(active_offs):
                o.is_best_price = idx_o == 0
            if active_offs:
                b_off = active_offs[0]
                b_price = round(float(b_off.price), 2)
                o_price = round(float(b_off.original_price or b_price), 2)
                if o_price < b_price:
                    o_price = b_price
                base_prod.best_price = b_price
                base_prod.original_price = o_price
                base_prod.best_store_name = b_off.store_name
                base_prod.best_store_url = b_off.offer_url
                base_prod.discount_percentage = (
                    round(((o_price - b_price) / o_price) * 100)
                    if o_price > b_price
                    else 0
                )
                base_prod.available_stores_count = len(active_offs)
                base_prod.updated_at = now_dt

    # 4. Paso 2: Agrupar los listings restantes
    clusters, cluster_outliers = _cluster_remaining_listings(remaining)
    summary.discarded_invalid_or_outliers += cluster_outliers

    # 5. Paso 3: Promover grupos multi-tienda y 1-tienda de forma idempotente (exigiendo imagen HTTPS válida)
    used_auto_ids: Set[str] = set()
    promoted_signatures: Set[Tuple[str, str, str]] = set()
    reassigned_old_auto_ids: Set[str] = {
        str(cand.existing_canonical_product_id)
        for paired_list in matched_by_base_prod.values()
        for cand, _ in paired_list
        if cand.existing_canonical_product_id
        and str(cand.existing_canonical_product_id).startswith("auto_")
    }
    multi_previews: List[PromotedGroupPreview] = []

    for cluster_members in clusters:
        consolidated_offers = _consolidate_cluster_offers(cluster_members)
        if not consolidated_offers:
            continue

        image_url = _select_best_https_image(consolidated_offers)
        if not image_url or not is_valid_product_image_url(image_url):
            summary.discarded_no_image += 1
            summary.discarded_invalid_or_outliers += len(cluster_members)
            continue

        best_offer = consolidated_offers[0]
        canonical_title = _select_clean_canonical_title(cluster_members)
        rep = best_offer
        canonical_id = _build_deterministic_auto_id(rep, cluster_members, used_auto_ids)
        used_auto_ids.add(canonical_id)
        promoted_signatures.add(
            (
                rep.display_category.lower(),
                strip_accents_lower(rep.brand or ""),
                rep.canonical_signature,
            )
        )
        for member in cluster_members:
            old_c = member.existing_canonical_product_id
            if old_c and str(old_c).startswith("auto_") and old_c != canonical_id:
                reassigned_old_auto_ids.add(str(old_c))

        best_price = round(float(best_offer.price), 2)
        orig_price = round(float(best_offer.original_price or best_price), 2)
        if orig_price < best_price:
            orig_price = best_price
        savings_amt = round(max(0.0, orig_price - best_price), 2)
        discount_pct = (
            round(((orig_price - best_price) / orig_price) * 100)
            if orig_price > best_price
            else 0
        )

        stores_count = len(consolidated_offers)
        is_multi = stores_count >= 2
        if is_multi:
            summary.new_multi_store_groups += 1
            _bump_category_stat(summary.by_category, rep.display_category, multi_store=1)
        else:
            summary.new_single_store_products += 1
            _bump_category_stat(summary.by_category, rep.display_category, single_store=1)
        summary.total_promoted_products += 1
        summary.offers_promoted += stores_count

        if is_multi:
            multi_previews.append(
                PromotedGroupPreview(
                    product_id=canonical_id,
                    title=canonical_title,
                    category=rep.display_category,
                    brand=rep.brand or "Genérico",
                    stores_count=stores_count,
                    best_price=best_price,
                    original_price=orig_price,
                    savings_amount=savings_amt,
                    discount_percentage=discount_pct,
                    canonical_signature=rep.canonical_signature,
                    store_prices={off.store: off.price for off in consolidated_offers},
                )
            )

        if dry_run:
            continue

        # Enlazar todos los `store_listings` del clúster al `canonical_id` y refrescar firma
        for member in cluster_members:
            if member.entity is not None:
                member.entity.canonical_product_id = canonical_id
                member.entity.normalized_signature = member.canonical_signature

        # Construir ficha técnica + imagen + descripción limpia
        seed_specs: Dict[str, str] = {}
        if rep.brand:
            seed_specs["Marca"] = rep.brand
        all_eans = sorted({g for m in cluster_members for g in m.eans})
        all_mpns = sorted({m_code for m in cluster_members for m_code in m.mpns})
        if all_eans:
            seed_specs["EAN"] = all_eans[0]
        if all_mpns:
            seed_specs["MPN"] = all_mpns[0].upper()

        tech_specs = merge_product_specs(
            specs_list=[seed_specs],
            base_specs=seed_specs,
            title=canonical_title,
        )
        brand_final = tech_specs.get("Marca") or rep.brand or "Genérico"
        tech_specs["Marca"] = brand_final

        features = generate_product_features(
            soup=None,
            tech_specs=tech_specs,
            title=canonical_title,
        )
        description = (
            f"{canonical_title} ({rep.display_category}). "
            f"Comparativa verificada en {stores_count} "
            f"{'tiendas oficiales del Perú' if stores_count > 1 else 'tienda oficial del Perú'}."
        )

        existing_prod = products_by_id.get(canonical_id)
        if existing_prod is not None:
            hist_min, is_hist_min, prev_best, drop_amt, days_tracked = await _upsert_today_price_history(
                session=session,
                product=existing_prod,
                best_price=best_price,
                orig_price=orig_price,
                today_peru=t_peru,
                existing_history=list(existing_prod.price_history or []),
                now_dt=now_dt,
            )
            summary.history_points_upserted += 1

            existing_prod.title = canonical_title
            existing_prod.category = rep.display_category
            existing_prod.brand = brand_final[:80]
            existing_prod.best_price = best_price
            existing_prod.original_price = orig_price
            existing_prod.best_store_name = best_offer.store_name[:100]
            existing_prod.best_store_url = best_offer.offer_url[:600]
            existing_prod.previous_best_price = prev_best
            existing_prod.price_drop_amount = drop_amt
            existing_prod.days_tracked = days_tracked
            existing_prod.discount_percentage = discount_pct
            existing_prod.available_stores_count = stores_count
            if image_url:
                existing_prod.image_url = image_url
            existing_prod.description = description
            existing_prod.features_json = json.dumps(features, ensure_ascii=False)
            existing_prod.tech_specs_json = json.dumps(tech_specs, ensure_ascii=False)
            existing_prod.historical_min_price = hist_min
            existing_prod.is_historical_min = is_hist_min
            existing_prod.updated_at = now_dt

            existing_offs = {o.store_id.lower(): o for o in (existing_prod.store_offers or [])}
            target_stores_set = {off.store for off in consolidated_offers}
            for s_id_old, old_off in list(existing_offs.items()):
                if s_id_old not in target_stores_set:
                    await session.delete(old_off)

            for idx_o, off in enumerate(consolidated_offers):
                cur_off = existing_offs.get(off.store)
                if cur_off is not None:
                    cur_off.store_name = off.store_name[:100]
                    cur_off.price = off.price
                    cur_off.original_price = off.original_price
                    cur_off.offer_url = off.offer_url[:600]
                    cur_off.is_best_price = idx_o == 0
                    cur_off.last_scraped_at = now_dt
                else:
                    session.add(
                        StoreOfferEntity(
                            product_id=canonical_id,
                            store_id=off.store[:50],
                            store_name=off.store_name[:100],
                            price=off.price,
                            original_price=off.original_price,
                            offer_url=off.offer_url[:600],
                            is_best_price=idx_o == 0,
                            last_scraped_at=now_dt,
                        )
                    )
        else:
            new_prod = ProductEntity(
                id=canonical_id,
                title=canonical_title,
                category=rep.display_category,
                brand=brand_final[:80],
                best_price=best_price,
                original_price=orig_price,
                best_store_name=best_offer.store_name[:100],
                best_store_url=best_offer.offer_url[:600],
                previous_best_price=orig_price,
                price_drop_amount=savings_amt,
                days_tracked=1,
                discount_percentage=discount_pct,
                available_stores_count=stores_count,
                image_url=image_url,
                description=description,
                features_json=json.dumps(features, ensure_ascii=False),
                tech_specs_json=json.dumps(tech_specs, ensure_ascii=False),
                is_favorite=False,
                historical_min_price=best_price,
                is_historical_min=True,
                created_at=now_dt,
                updated_at=now_dt,
            )
            session.add(new_prod)
            products_by_id[canonical_id] = new_prod

            for idx_o, off in enumerate(consolidated_offers):
                session.add(
                    StoreOfferEntity(
                        product_id=canonical_id,
                        store_id=off.store[:50],
                        store_name=off.store_name[:100],
                        price=off.price,
                        original_price=off.original_price,
                        offer_url=off.offer_url[:600],
                        is_best_price=idx_o == 0,
                        last_scraped_at=now_dt,
                    )
                )

            session.add(
                PriceHistoryEntity(
                    product_id=canonical_id,
                    day_offset=0,
                    date_label=format_peru_date_label(t_peru),
                    recorded_date=t_peru.isoformat(),
                    price=best_price,
                    recorded_at=now_dt,
                )
            )
            summary.history_points_upserted += 1

    # 6. Paso 4: Auto-poda (prune) de `auto_*` inválidos, sin imagen HTTPS, sin stock o ya fusionados
    #    Preserva 100% intactos los productos semilla (`prod_*`), su historial y registros comunitarios.
    if in_memory_listings is None:
        base_sig_keys: Set[Tuple[str, str, str]] = {
            (
                str(m["display_category"]).lower(),
                str(m["brand_low"]),
                str(m["canonical_signature"]),
            )
            for m in base_products_meta
            if m.get("canonical_signature")
        }
        pruned_ids: Set[str] = set()
        for p in list(existing_products):
            pid = str(p.id)
            if not pid.startswith("auto_") or pid in used_auto_ids:
                continue
            if getattr(p, "community_offers", None) or getattr(p, "community_posts", None):
                continue

            p_slug = _display_to_category_slug(p.category)
            p_title = str(p.title or "").strip()
            p_brand = str(p.brand or "").strip()
            p_url = str(p.best_store_url or "").strip()

            if (
                _NON_HARDWARE_SOFTWARE_RE.search(strip_accents_lower(p_title))
                or not is_strict_tech_product(
                    title=p_title,
                    category=p_slug,
                    url=p_url,
                    brand=p_brand,
                )
            ):
                reason = "no_tech"
            elif not is_valid_product_image_url(p.image_url):
                reason = "sin_imagen_https"
            else:
                p_sig = build_canonical_product_signature(
                    title=p_title,
                    brand=p_brand,
                    url=p_url,
                    category=p_slug,
                )
                sig_key = (
                    resolve_category_display_name(p.category).lower(),
                    strip_accents_lower(normalize_brand(p_brand, p_title)),
                    p_sig,
                )
                if pid in reassigned_old_auto_ids or sig_key in base_sig_keys or sig_key in promoted_signatures:
                    reason = "duplicado_o_reemplazado"
                else:
                    reason = "sin_stock_u_obsoleto"

            summary.pruned_auto_products_total += 1
            summary.pruned_by_reason[reason] = summary.pruned_by_reason.get(reason, 0) + 1
            pruned_ids.add(pid)
            if not dry_run:
                products_by_id.pop(pid, None)
                await session.delete(p)

        if not dry_run and pruned_ids:
            for db_row in all_db_listings:
                if db_row.canonical_product_id in pruned_ids:
                    db_row.canonical_product_id = None

    multi_previews.sort(
        key=lambda g: (
            -g.stores_count,
            -g.discount_percentage,
            -g.savings_amount,
            g.best_price,
            g.title.lower(),
        )
    )
    summary.multi_store_examples = multi_previews[:10]

    if not dry_run:
        await session.commit()
        try:
            from app.services.catalog_service import catalog_service

            catalog_service.invalidate_cache()
        except Exception:
            pass

    logger.info(
        f"Promoción de catálogo ({'DRY-RUN' if dry_run else 'LIVE'}): "
        f"listings={summary.active_listings_scanned}, enlazados={summary.linked_to_existing_products}, "
        f"multi_tienda={summary.new_multi_store_groups}, 1_tienda={summary.new_single_store_products}, "
        f"total_auto={summary.total_promoted_products}"
    )
    return summary
