"""
Pruebas integrales de endpoints de FinPrice API conectados a Neon PostgreSQL:
- Keep-Alive /ping (GET y HEAD)
- Diagnóstico /api/v1/health
- Catálogo /api/v1/products, /api/v1/products/search y /api/v1/products/{id}/history
- Comunidad /api/v1/community/posts (GET, POST, PUT) y /api/v1/community-offers
- Libro de Reclamaciones /api/v1/complaints y /api/v1/cancellations
- Retrocompatibilidad /products
"""
import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from app.core.database import engine


@pytest.mark.asyncio
async def test_ping_endpoints():
    """Valida que /ping responda instantáneamente en GET y HEAD con status alive."""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_get = await client.get("/ping")
            assert res_get.status_code == 200
            assert res_get.json() == {"status": "alive", "service": "FinPrice-api"}

            res_head = await client.head("/ping")
            assert res_head.status_code == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_health_endpoint():
    """Valida diagnóstico de salud y conexión a Neon PostgreSQL."""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/health")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "healthy"
            assert "Neon PostgreSQL" in data["database"]
            assert data["totalProducts"] >= 6
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_products_catalog_and_search():
    """Valida listado, búsqueda y detalle de productos."""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/products")
            assert res.status_code == 200
            prods = res.json()
            assert len(prods) >= 6

            search_res = await client.get("/api/v1/products/search?q=iPhone")
            assert search_res.status_code == 200
            search_data = search_res.json()
            assert len(search_data) >= 1
            assert "iPhone" in search_data[0]["title"]

            prod_id = prods[0]["id"]
            detail_res = await client.get(f"/api/v1/products/{prod_id}")
            assert detail_res.status_code == 200
            assert detail_res.json()["id"] == prod_id

            hist_res = await client.get(f"/api/v1/products/{prod_id}/history")
            assert hist_res.status_code == 200
            hist_data = hist_res.json()
            assert isinstance(hist_data, list)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_community_posts_lifecycle():
    """Valida ciclo de vida completo de publicaciones comunitarias (GET, POST, PUT)."""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            list_res = await client.get("/api/v1/community/posts")
            assert list_res.status_code == 200
            posts = list_res.json()
            assert isinstance(posts, list)

            new_post_payload = {
                "title": "Oferta relámpago en Falabella Jockey",
                "content": "iPhone 16 a precio de locura en vitrina",
                "productId": "prod_iphone_16",
                "productName": "Apple iPhone 16 128GB",
                "physicalStoreName": "Falabella Jockey Plaza",
                "price": 3199.0,
                "department": "Lima",
                "province": "Lima",
                "district": "Santiago de Surco",
                "authorName": "Tester Senior",
            }
            create_res = await client.post("/api/v1/community/posts", json=new_post_payload)
            assert create_res.status_code == 201
            created_post = create_res.json()
            post_id = created_post["id"]
            assert created_post["title"] == new_post_payload["title"]
            assert created_post["price"] == 3199.0

            update_payload = {
                "title": "Oferta relámpago ACTUALIZADA Falabella Jockey",
                "price": 3149.0,
                "content": "Bajó aún más de precio en tienda",
            }
            put_res = await client.put(f"/api/v1/community/posts/{post_id}", json=update_payload)
            assert put_res.status_code == 200
            updated = put_res.json()
            assert updated["title"] == update_payload["title"]
            assert updated["price"] == 3149.0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_complaints_and_cancellations():
    """Valida registro en Libro de Reclamaciones y sugerencias de cancelación."""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            complaint_payload = {
                "fullName": "Juan Carlos Pérez",
                "documentType": "DNI",
                "documentNumber": "74839201",
                "email": "juan.perez@example.pe",
                "phone": "987654321",
                "address": "Av. Javier Prado Este 2450",
                "department": "Lima",
                "province": "Lima",
                "district": "San Borja",
                "complaintType": "Reclamo",
                "contractedGood": "Servicio",
                "claimedAmount": 150.0,
                "description": "El precio listado en tienda no coincidía con el precio de caja en la sucursal.",
                "consumerRequest": "Reembolso de la diferencia cobrada indebidamente.",
            }
            res_comp = await client.post("/api/v1/complaints", json=complaint_payload)
            assert res_comp.status_code == 201
            comp_data = res_comp.json()
            assert "REC-" in comp_data["claimNumber"]
            assert comp_data["fullName"] == "Juan Carlos Pérez"

            get_comp = await client.get(f"/api/v1/complaints/{comp_data['claimNumber']}")
            assert get_comp.status_code == 200
            assert get_comp.json()["claimNumber"] == comp_data["claimNumber"]

            cancel_payload = {
                "email": "usuario.despedida@example.pe",
                "reason": "Ya encontré el producto que buscaba al mejor precio",
                "feedback": "Excelente servicio, volveré para la campaña navideña.",
            }
            res_cancel = await client.post("/api/v1/cancellations", json=cancel_payload)
            assert res_cancel.status_code == 201
            assert res_cancel.json()["email"] == cancel_payload["email"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_products():
    """Valida retrocompatibilidad de GET /products."""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/products")
            assert res.status_code == 200
            data = res.json()
            assert len(data) >= 6
            assert "offers" in data[0]
            assert "lowest_price" in data[0]
    finally:
        await engine.dispose()
