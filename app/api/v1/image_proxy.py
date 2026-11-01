"""
Endpoint de Proxy de Imágenes para clientes móviles y web.
Resuelve bloqueos 403 / 404 causados por restricciones de User-Agent o Referer
en servidores de retailers peruanos (Hiraoka, Falabella, Coolbox, etc.).
Incluye caché LRU en memoria con límite de tamaño para mantener el consumo de RAM bajo (< 15 MB).
"""
import collections
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.logging import get_logger

logger = get_logger("api.v1.image_proxy")

router = APIRouter(tags=["Proxy de Imágenes"])

# Caché LRU en memoria: (content, content_type) limitado a 80 elementos (~10-15 MB RAM)
MAX_CACHE_ITEMS = 80
_IMAGE_CACHE = collections.OrderedDict()


@router.get(
    "/image-proxy",
    summary="Proxy de imágenes con cabeceras de navegador reales y caché LRU",
)
async def proxy_image(
    url: str = Query(..., description="URL absoluta de la imagen a obtener vía proxy"),
):
    """
    Obtiene una imagen de tienda retail usando cabeceras de navegador estándar (User-Agent, Referer)
    para evitar respuestas 403 Forbidden en clientes Android / iOS.
    """
    clean_url = url.strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL de imagen inválida. Debe comenzar con http:// o https://",
        )

    # Prevenir SSRF bloqueando localhost e IPs internas
    netloc_lower = parsed.netloc.lower()
    if any(blocked in netloc_lower for blocked in ["localhost", "127.0.0.1", "0.0.0.0", "169.254."]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Destino de imagen no permitido.",
        )

    # 1. Verificar si está en caché
    if clean_url in _IMAGE_CACHE:
        content, ctype = _IMAGE_CACHE[clean_url]
        _IMAGE_CACHE.move_to_end(clean_url)
        return Response(
            content=content,
            media_type=ctype,
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Proxy-Cache": "HIT",
            },
        )

    # 2. Descargar con cabeceras reales de navegador
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": f"{parsed.scheme}://{parsed.netloc}/",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(clean_url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Error descargando imagen {clean_url}: HTTP {resp.status_code}")
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"No se pudo descargar la imagen (HTTP {resp.status_code})",
                )

            ctype = resp.headers.get("content-type", "image/jpeg")
            if "image" not in ctype and "application/octet-stream" not in ctype:
                ctype = "image/jpeg"

            img_bytes = resp.content

            # Almacenar en caché LRU
            if len(_IMAGE_CACHE) >= MAX_CACHE_ITEMS:
                _IMAGE_CACHE.popitem(last=False)
            _IMAGE_CACHE[clean_url] = (img_bytes, ctype)

            return Response(
                content=img_bytes,
                media_type=ctype,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "X-Proxy-Cache": "MISS",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Excepción al proxyficar imagen {clean_url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fallo de conexión al descargar la imagen: {str(e)}",
        )
