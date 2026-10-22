"""
Módulo de normalización de precios en Soles (PEN), cálculo de descuentos
y filtros de cordura (sanity check) para evitar anomalías en el scraping.
"""
import re
from typing import Optional, Tuple, Union

from app.core.logging import get_logger

logger = get_logger("normalizer")

# Expresiones regulares para extracción de moneda y números
PRICE_CLEAN_REGEX = re.compile(r"[^\d.,]")


def clean_pen_price(raw_val: Union[str, float, int, None]) -> Optional[float]:
    """
    Normaliza y extrae un valor de precio numérico en Soles (PEN).
    Limpia símbolos comunes en retail peruano ('S/', 'S/.', 'PEN', comas de miles y espacios).
    Soporta formatos estándar ('1,450.90' o '1.450,90' o '1450').
    """
    if raw_val is None:
        return None

    if isinstance(raw_val, (int, float)):
        val = float(raw_val)
        return round(val, 2) if val > 0 else None

    text = str(raw_val).strip()
    if not text:
        return None

    # Quitar prefijos de moneda conocidos: 'S/.', 'S/', 'PEN', etc.
    text = re.sub(r"(?i)\b(s/\.|s/|pen|usd|\$)\b", "", text)
    text = re.sub(r"[sS]/\.?", "", text)

    # Eliminar cualquier carácter que no sea dígito, coma o punto
    cleaned = re.sub(r"[^\d.,]", "", text).strip()
    cleaned = cleaned.strip(".,")
    if not cleaned:
        return None

    try:
        # Detectar separadores decimales vs de miles:
        # Formato '1,450.50' (coma miles, punto decimal)
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(".") > cleaned.rfind(","):
                # Coma es miles, punto es decimal
                cleaned = cleaned.replace(",", "")
            else:
                # Punto es miles, coma es decimal (formato latino/europeo '1.450,50')
                cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned and "." not in cleaned:
            parts = cleaned.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                # Es coma decimal
                cleaned = cleaned.replace(",", ".")
            else:
                # Es coma de miles
                cleaned = cleaned.replace(",", "")
        elif "." in cleaned and "," not in cleaned:
            parts = cleaned.split(".")
            if len(parts) > 2:
                cleaned = cleaned.replace(".", "")

        val = float(cleaned)
        return round(val, 2) if val > 0 else None
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parseando precio raw '{raw_val}': {e}")
        return None


def sanity_check_price(
    price: Optional[float],
    original_price: Optional[float] = None,
    min_threshold: float = 20.0,
    max_drop_pct: float = 0.90,
    max_markup_ratio: float = 3.0,
) -> bool:
    """
    Filtro de cordura para descartar anomalías de scraping:
    - Precios <= 0 o menores a `min_threshold` (elimina accesorios/fundas parseados por error).
    - Descuentos anómalos mayores a `max_drop_pct` (caída > 90% comparado a precio original).
    - Inflaciones absurdas mayores a `max_markup_ratio` (precio > 3x precio original).
    """
    if price is None or price <= 0:
        return False

    if price < min_threshold:
        logger.warning(
            f"Precio sospechosamente bajo descartado por sanity check: S/. {price} < {min_threshold}"
        )
        return False

    if original_price and original_price > 0:
        # Si cae más del 90% respecto al original
        lowest_allowed = original_price * (1.0 - max_drop_pct)
        if price < lowest_allowed:
            logger.warning(
                f"Caída anómala de precio detectada: S/. {price} frente a original S/. {original_price} (caída > 90%)"
            )
            return False

        # Si sube más del triple
        if price > original_price * max_markup_ratio:
            logger.warning(
                f"Inflación anómala detectada: S/. {price} frente a original S/. {original_price}"
            )
            return False

    return True


def calculate_discount_percentage(original_price: float, best_price: float) -> int:
    """Calcula el porcentaje de descuento redondeado entre 0 y 100."""
    if original_price <= 0 or best_price <= 0:
        return 0
    if original_price <= best_price:
        return 0
    pct = round(((original_price - best_price) / original_price) * 100)
    return max(0, min(100, pct))


def evaluate_historical_min(
    best_price: float, historical_min_price: Optional[float]
) -> Tuple[bool, float]:
    """
    Evalúa si el precio actual es un mínimo histórico.
    Retorna (is_historical_min, effective_min_price).
    """
    if historical_min_price is None or historical_min_price <= 0:
        return True, best_price

    if best_price <= historical_min_price:
        return True, best_price

    return False, historical_min_price
