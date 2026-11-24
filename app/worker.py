"""
Worker independiente de recolección de precios reales para FinPrice API.
========================================================================
Ejecutable vía:
  python -m app.worker --once
  python -m app.worker --once --stores ripley,efe,curacao
  python -m app.worker

Inicializa la base de datos (Neon PostgreSQL / SQLite) igual que el backend y ejecuta
directamente el flujo real de `app.collectors.orchestrator` preservando la regla
`[RETENCIÓN TOLERANTE A FALLOS]` y los UPSERT granulares hacia Neon.
"""
import argparse
import asyncio
import signal
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.collectors.catalog_urls import STORES_INFO
from app.collectors.category_crawler import CategoryCrawlSummary, crawl_categories
from app.collectors.category_registry import CATEGORY_REGISTRY, list_registered_categories
from app.collectors.graph.smart_multi_graph import ALL_8_PERU_STORES
from app.collectors.http_client import (
    close_shared_client,
    get_configured_proxy_stores,
    log_proxy_status_once,
    mask_proxy_url,
    probe_store_connection,
)
from app.collectors.orchestrator import (
    SCHEDULE_WINDOWS_LABELS,
    calculate_seconds_until_next_window,
    orchestrator,
)
from app.core.config import settings
from app.core.database import (
    ReaderSessionLocal,
    WriterSessionLocal,
    engine,
    init_db,
    reader_engine,
)
from app.core.logging import get_logger
from app.core.seed_data import sync_and_upsert_catalog
from app.models.entities import ProductEntity
from app.services.catalog_service import catalog_service

logger = get_logger("worker")


def parse_stores_arg(raw_stores: Optional[str]) -> Optional[List[str]]:
    """Valida y normaliza la lista separada por comas de tiendas en `--stores`."""
    if raw_stores is None:
        return None

    parsed: List[str] = []
    invalid: List[str] = []
    seen = set()

    for token in raw_stores.split(","):
        store_id = token.strip().lower()
        if not store_id:
            continue
        if store_id not in STORES_INFO:
            invalid.append(store_id)
            continue
        if store_id not in seen:
            seen.add(store_id)
            parsed.append(store_id)

    if invalid:
        valid_list = ", ".join(ALL_8_PERU_STORES)
        raise argparse.ArgumentTypeError(
            f"Tienda(s) inválida(s): {', '.join(invalid)}. Tiendas válidas: {valid_list}"
        )

    if not parsed:
        valid_list = ", ".join(ALL_8_PERU_STORES)
        raise argparse.ArgumentTypeError(
            f"Debe indicar al menos una tienda válida en --stores. Opciones: {valid_list}"
        )

    return parsed


def parse_categories_arg(raw_categories: Optional[str]) -> Optional[List[str]]:
    """Valida y normaliza la lista separada por comas de categorías en `--categories`."""
    if raw_categories is None:
        return None

    parsed: List[str] = []
    invalid: List[str] = []
    seen = set()

    for token in raw_categories.split(","):
        cat_slug = token.strip().lower()
        if not cat_slug:
            continue
        if cat_slug not in CATEGORY_REGISTRY:
            invalid.append(cat_slug)
            continue
        if cat_slug not in seen:
            seen.add(cat_slug)
            parsed.append(cat_slug)

    valid_list = ", ".join(list_registered_categories())
    if invalid:
        raise argparse.ArgumentTypeError(
            f"Categoría(s) inválida(s): {', '.join(invalid)}. Categorías válidas: {valid_list}"
        )

    if not parsed:
        raise argparse.ArgumentTypeError(
            f"Debe indicar al menos una categoría válida en --categories. Opciones: {valid_list}"
        )

    return parsed


def parse_max_pages_arg(raw_val: str) -> int:
    """Valida que `--max-pages` sea un entero positivo >= 1."""
    try:
        val = int(raw_val)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"--max-pages inválido: {raw_val!r}") from exc
    if val < 1:
        raise argparse.ArgumentTypeError("--max-pages debe ser >= 1.")
    return val


def build_arg_parser() -> argparse.ArgumentParser:
    """Construye el parser CLI para el worker independiente de FinPrice."""
    valid_stores_text = ", ".join(ALL_8_PERU_STORES)
    valid_categories_text = ", ".join(list_registered_categories())
    parser = argparse.ArgumentParser(
        prog="python -m app.worker",
        description=(
            "Worker independiente de scraping real de FinPrice hacia Neon PostgreSQL. "
            "Respeta la retención tolerante a fallos y los UPSERT granulares por tienda."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Ejecuta un solo barrido completo (o filtrado con --stores) y termina con "
            "código de salida 0. Ideal para Cron Jobs o pruebas manuales."
        ),
    )
    parser.add_argument(
        "--stores",
        type=parse_stores_arg,
        default=None,
        metavar="TIENDAS",
        help=(
            "Lista opcional separada por comas de tiendas a consultar "
            f"(ej. ripley,efe,curacao) sin tocar el resto. Tiendas válidas: {valid_stores_text}."
        ),
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help=(
            "Solo lectura contra Neon/DB (sin scrapear ni escribir): imprime una tabla compacta "
            "ordenada de menor a mayor cobertura mostrando precios activos y tiendas oficiales faltantes."
        ),
    )
    parser.add_argument(
        "--check-proxy",
        action="store_true",
        help=(
            "Solo lectura HTTP (sin tocar Neon): realiza 1 petición ligera a ripley, efe, curacao "
            "y falabella mostrando si usó PERU_PROXY_URL (enmascarado) o DIRECT y el código HTTP."
        ),
    )
    parser.add_argument(
        "--discover-categories",
        action="store_true",
        help=(
            "Fase 2A: barre listados por categorías tech en las tiendas oficiales 1P "
            "y realiza upsert idempotente en store_listings (sin modificar products ni store_offers)."
        ),
    )
    parser.add_argument(
        "--categories",
        type=parse_categories_arg,
        default=None,
        metavar="CATEGORIAS",
        help=(
            "Lista opcional separada por comas de categorías tech para --discover-categories "
            f"(ej. consolas,monitores,celulares). Categorías válidas: {valid_categories_text}."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=parse_max_pages_arg,
        default=2,
        metavar="N",
        help="Número máximo de páginas a barrer por tienda y categoría en --discover-categories (default: 2).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecuta --discover-categories en modo lectura sin escribir ni inicializar tablas en Neon/DB.",
    )
    return parser


async def bootstrap_worker_db() -> int:
    """Inicializa esquema y sincroniza el catálogo oficial en base de datos igual que el backend."""
    await init_db()
    async with WriterSessionLocal() as session:
        await catalog_service.purge_ghost_community_data(session)
        synced_count = await sync_and_upsert_catalog(session=session)
    logger.info(
        f"Base de datos inicializada para worker ({synced_count} productos oficiales listos).",
        extra={"env": settings.ENVIRONMENT},
    )
    return synced_count


async def run_single_sweep(only_stores: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Ejecuta un barrido de recolección y actualización programada contra Neon PostgreSQL."""
    async with WriterSessionLocal() as session:
        return await orchestrator.run_scheduled_price_update(
            session=session,
            only_stores=only_stores,
        )


def _truncate_label(text: str, width: int) -> str:
    s = str(text or "").strip()
    if len(s) <= width:
        return s
    return f"{s[: max(1, width - 3)].rstrip()}..."


def build_coverage_audit_rows(
    products: Sequence[ProductEntity],
    target_stores: Sequence[str],
) -> List[Dict[str, Any]]:
    """Construye y ordena de menor a mayor cobertura las filas de auditoría solo lectura."""
    target_set = set(target_stores)
    rows: List[Dict[str, Any]] = []

    for prod in products:
        active_prices: Dict[str, float] = {}
        for off in prod.store_offers or []:
            s_id = str(off.store_id or "").strip().lower()
            p_val = float(off.price or 0.0)
            if s_id in target_set and p_val > 0.0:
                if s_id not in active_prices or p_val < active_prices[s_id]:
                    active_prices[s_id] = p_val

        missing_stores = [s for s in target_stores if s not in active_prices]
        best_price = min(active_prices.values()) if active_prices else 0.0
        rows.append(
            {
                "product_id": str(prod.id),
                "title": str(prod.title or prod.id),
                "active_stores": [s for s in target_stores if s in active_prices],
                "active_count": len(active_prices),
                "total_stores": len(target_stores),
                "missing_stores": missing_stores,
                "best_price": best_price,
            }
        )

    rows.sort(key=lambda r: (r["active_count"], r["title"].lower(), r["product_id"]))
    return rows


def format_coverage_audit_table(
    rows: Sequence[Dict[str, Any]],
    target_stores: Sequence[str],
) -> str:
    """Formatea una tabla ASCII compacta ordenada de menor a mayor cobertura."""
    prod_w = 46
    cov_w = 7
    best_w = 11
    miss_w = 44

    header = (
        f"{'Producto':<{prod_w}} | "
        f"{'Activas':>{cov_w}} | "
        f"{'Mejor S/':>{best_w}} | "
        f"{'Tiendas oficiales faltantes':<{miss_w}}"
    )
    sep = f"{'-' * prod_w}-+-{'-' * cov_w}-+-{'-' * best_w}-+-{'-' * miss_w}"
    lines: List[str] = [
        "=== AUDITORÍA DE COBERTURA FINPRICE (SOLO LECTURA) ===",
        header,
        sep,
    ]

    store_counts: Dict[str, int] = {s: 0 for s in target_stores}
    total_active = 0
    total_slots = len(rows) * len(target_stores)

    for row in rows:
        for s_id in row["active_stores"]:
            if s_id in store_counts:
                store_counts[s_id] += 1
        total_active += row["active_count"]

        cov_str = f"{row['active_count']}/{row['total_stores']}"
        best_str = f"S/ {row['best_price']:,.0f}" if row["best_price"] > 0 else "—"
        miss_str = ", ".join(row["missing_stores"]) if row["missing_stores"] else "(cobertura completa)"
        lines.append(
            f"{_truncate_label(row['title'], prod_w):<{prod_w}} | "
            f"{cov_str:>{cov_w}} | "
            f"{best_str:>{best_w}} | "
            f"{miss_str}"
        )

    avg_cov = (total_active / len(rows)) if rows else 0.0
    pct_cov = (100.0 * total_active / total_slots) if total_slots else 0.0
    per_store_summary = ", ".join(f"{s}:{store_counts[s]}" for s in target_stores)
    lines.extend(
        [
            sep,
            (
                f"Productos: {len(rows)} | Ofertas activas: {total_active}/{total_slots} "
                f"({pct_cov:.1f}%, promedio {avg_cov:.2f} tiendas/producto)"
            ),
            f"Cobertura por tienda: {per_store_summary}",
        ]
    )
    return "\n".join(lines)


async def run_coverage_audit(only_stores: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """
    Consulta Neon/DB en modo estrictamente solo lectura (ReaderSessionLocal, sin scrapear ni escribir),
    imprime la tabla compacta ordenada de menor a mayor cobertura y retorna las filas calculadas.
    """
    target_stores = list(only_stores) if only_stores is not None else list(ALL_8_PERU_STORES)
    async with ReaderSessionLocal() as session:
        result = await session.execute(
            select(ProductEntity).options(selectinload(ProductEntity.store_offers))
        )
        products = list(result.scalars().all())

    rows = build_coverage_audit_rows(products=products, target_stores=target_stores)
    print(format_coverage_audit_table(rows=rows, target_stores=target_stores))
    return rows


PROXY_CHECK_TARGETS: Tuple[Tuple[str, str], ...] = (
    ("ripley", "https://simple.ripley.com.pe/"),
    ("efe", "https://www.efe.com.pe/"),
    ("curacao", "https://www.lacuracao.pe/"),
    ("falabella", "https://www.falabella.com.pe/falabella-pe"),
)


async def run_proxy_check() -> List[Dict[str, Any]]:
    """
    Realiza una comprobación ligera en vivo (solo lectura HTTP, sin tocar Neon)
    sobre ripley, efe, curacao y falabella mostrando ruta (proxy enmascarado vs DIRECT) y HTTP status.
    """
    log_proxy_status_once()
    masked_proxy = mask_proxy_url(settings.PERU_PROXY_URL)
    proxy_stores = ",".join(get_configured_proxy_stores()) or "ninguna"
    print(f"=== VERIFICACIÓN DE PROXY SELECTIVO (PERU_PROXY_URL={masked_proxy} | tiendas={proxy_stores}) ===")

    results: List[Dict[str, Any]] = []
    try:
        for store_id, url in PROXY_CHECK_TARGETS:
            res = await probe_store_connection(store_id=store_id, url=url)
            results.append(res)
            http_label = str(res["status_code"]) if res["status_code"] is not None else "ERR"
            mode_label = f"PROXY ({res['route']})" if res["used_proxy"] else "DIRECT"
            err_suffix = f" | err={res['error']}" if res.get("error") else ""
            print(
                f"  - {store_id:<10} | {mode_label:<36} | HTTP {http_label:<4} | "
                f"{res['elapsed_ms']:>7.1f} ms | {url}{err_suffix}"
            )
    finally:
        await close_shared_client()

    return results


def format_category_discovery_summary(summary: CategoryCrawlSummary) -> str:
    """Formatea el resumen por tienda, categoría y totales de `--discover-categories`."""
    mode_tag = "DRY-RUN (sin escritura en BD)" if summary.dry_run else "PERSISTIDO EN store_listings"
    lines: List[str] = [
        f"=== DESCUBRIMIENTO DE CATEGORÍAS TECH — FASE 2A ({mode_tag}) ===",
    ]

    store_w = 12
    cat_w = 22
    header = (
        f"{'Tienda':<{store_w}} | "
        f"{'Categoría':<{cat_w}} | "
        f"{'Págs':>4} | "
        f"{'1P':>5} | "
        f"{'Nuevos':>6} | "
        f"{'Actual.':>7} | "
        f"{'Mkp Desc':>8} | "
        f"{'Filtro':>6}"
    )
    sep = (
        f"{'-' * store_w}-+-{'-' * cat_w}-+-{'-' * 4}-+-{'-' * 5}-+-"
        f"{'-' * 6}-+-{'-' * 7}-+-{'-' * 8}-+-{'-' * 6}"
    )
    lines.extend([header, sep])

    for st in summary.by_source:
        lines.append(
            f"{st.store:<{store_w}} | "
            f"{st.category:<{cat_w}} | "
            f"{st.pages_fetched:>4} | "
            f"{st.extracted_1p:>5} | "
            f"{st.inserted:>6} | "
            f"{st.updated:>7} | "
            f"{st.discarded_marketplace:>8} | "
            f"{st.discarded_filtered:>6}"
        )

    lines.append(sep)
    if summary.by_store:
        lines.append("Desglose por tienda:")
        for store_id, m in summary.by_store.items():
            lines.append(
                f"  - {store_id:<11}: extraídos_1p={m['extracted_1p']} | "
                f"nuevos={m['inserted']} | actualizados={m['updated']} | "
                f"descartados_marketplace={m['discarded_marketplace']}"
            )

    if summary.by_category:
        lines.append("Desglose por categoría:")
        for cat_slug, m in summary.by_category.items():
            lines.append(
                f"  - {cat_slug:<21}: extraídos_1p={m['extracted_1p']} | "
                f"nuevos={m['inserted']} | actualizados={m['updated']} | "
                f"descartados_marketplace={m['discarded_marketplace']}"
            )

    persisted_label = (
        "0 nuevos / 0 actualizados (dry-run)"
        if summary.dry_run
        else f"{summary.inserted} nuevos / {summary.updated} actualizados"
    )
    lines.append(
        f"RESUMEN TOTAL: páginas={summary.pages_fetched} | extraídos_1p={summary.extracted_1p} | "
        f"{persisted_label} | descartados_marketplace={summary.discarded_marketplace} | "
        f"descartados_filtro={summary.discarded_filtered}"
    )
    return "\n".join(lines)


async def run_category_discovery(
    only_stores: Optional[Sequence[str]] = None,
    only_categories: Optional[Sequence[str]] = None,
    max_pages: int = 2,
    dry_run: bool = False,
) -> CategoryCrawlSummary:
    """Ejecuta el barrido de categorías tech y muestra el resumen completo por tienda y categoría."""
    try:
        summary = await crawl_categories(
            stores=only_stores,
            categories=only_categories,
            max_pages=max_pages,
            dry_run=dry_run,
        )
        print(format_category_discovery_summary(summary))
        return summary
    finally:
        await close_shared_client()


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Registra manejadores limpios para SIGINT/SIGTERM en modo daemon."""
    loop = asyncio.get_running_loop()

    def _trigger_stop() -> None:
        if not stop_event.is_set():
            logger.info("Señal de parada recibida; finalizando worker de forma ordenada...")
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _trigger_stop)
        except NotImplementedError:
            signal.signal(sig, lambda _s, _f: loop.call_soon_threadsafe(_trigger_stop))


async def _wait_interruptible(stop_event: asyncio.Event, timeout_seconds: float) -> bool:
    """Espera hasta `timeout_seconds` o hasta que se solicite parada. Retorna True si debe detenerse."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(0.1, float(timeout_seconds)))
        return True
    except asyncio.TimeoutError:
        return stop_event.is_set()


async def run_worker_async(
    once: bool = False,
    only_stores: Optional[List[str]] = None,
    audit: bool = False,
    check_proxy: bool = False,
    discover_categories: bool = False,
    only_categories: Optional[List[str]] = None,
    max_pages: int = 2,
    dry_run: bool = False,
) -> int:
    """Ciclo principal asíncrono del worker independiente (`--check-proxy`, `--audit`, `--discover-categories`, `--once` o daemon)."""
    target_stores = only_stores if only_stores is not None else list(ALL_8_PERU_STORES)
    if check_proxy:
        await run_proxy_check()
        return 0

    if discover_categories:
        log_proxy_status_once()
        try:
            if not dry_run:
                await init_db()
            await run_category_discovery(
                only_stores=only_stores,
                only_categories=only_categories,
                max_pages=max_pages,
                dry_run=dry_run,
            )
            return 0
        finally:
            if not dry_run:
                await engine.dispose()
                await reader_engine.dispose()

    try:
        if audit:
            await run_coverage_audit(only_stores=only_stores)
            return 0

        log_proxy_status_once()
        await bootstrap_worker_db()

        if once:
            logger.info(
                f"Worker iniciado en modo --once (tiendas={','.join(target_stores)})."
            )
            result = await run_single_sweep(only_stores=only_stores)
            logger.info(
                f"Worker --once completado exitosamente: {result}"
            )
            return 0

        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        logger.info(
            f"Worker daemon activo ({', '.join(SCHEDULE_WINDOWS_LABELS)} America/Lima | "
            f"tiendas={','.join(target_stores)})."
        )

        async with WriterSessionLocal() as session:
            if await orchestrator.needs_scheduled_catchup(session):
                logger.info("Worker Catch-Up on Wakeup: ejecutando corte programado pendiente...")
                await orchestrator.run_scheduled_price_update(
                    session=session,
                    only_stores=only_stores,
                )

        while not stop_event.is_set():
            try:
                sleep_seconds, window_label = calculate_seconds_until_next_window(
                    tz_name="America/Lima"
                )
                hours = int(sleep_seconds // 3600)
                minutes = int((sleep_seconds % 3600) // 60)
                seconds = int(sleep_seconds % 60)
                logger.info(
                    f"Worker en reposo. Siguiente corte programado ({window_label} Lima) "
                    f"en {hours}h {minutes}m {seconds}s."
                )

                if await _wait_interruptible(stop_event, sleep_seconds):
                    break

                logger.info(
                    f"¡Ventana programada alcanzada ({window_label} America/Lima)! "
                    "Ejecutando actualización de precios desde worker..."
                )
                await run_single_sweep(only_stores=only_stores)

                if await _wait_interruptible(stop_event, 65.0):
                    break
            except asyncio.CancelledError:
                logger.info("Worker daemon cancelado.")
                break
            except Exception as exc:
                logger.error(f"Error imprevisto en ciclo del worker daemon: {exc}")
                if await _wait_interruptible(stop_event, 60.0):
                    break

        logger.info("Worker daemon apagado correctamente.")
        return 0
    finally:
        await engine.dispose()
        await reader_engine.dispose()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto de entrada síncrono del CLI `python -m app.worker`."""
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return asyncio.run(
        run_worker_async(
            once=bool(args.once),
            only_stores=args.stores,
            audit=bool(args.audit),
            check_proxy=bool(args.check_proxy),
            discover_categories=bool(args.discover_categories),
            only_categories=args.categories,
            max_pages=int(args.max_pages),
            dry_run=bool(args.dry_run),
        )
    )


if __name__ == "__main__":
    sys.exit(main())
