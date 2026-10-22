from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="FinPrice API", description="Servicio en la nube para comparar precios")

# Permitir que tu app móvil consulte la API sin bloqueos de red
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estructura de datos
class StoreOffer(BaseModel):
    store_name: str
    price: float
    currency: str = "PEN"
    product_url: str

class ProductResponse(BaseModel):
    id: int
    name: str
    category: str
    lowest_price: float
    best_store: str
    offers: List[StoreOffer]

# Catálogo de prueba
CATALOG = [
    {
        "id": 1,
        "name": "MacBook Air M2 256GB",
        "category": "Laptops",
        "offers": [
            {"store_name": "Tienda A", "price": 4199.0, "currency": "PEN", "product_url": "https://ejemplo.com/a"},
            {"store_name": "Tienda B", "price": 3899.0, "currency": "PEN", "product_url": "https://ejemplo.com/b"},
        ]
    },
    {
        "id": 2,
        "name": "POCO X6 Pro 5G",
        "category": "Smartphones",
        "offers": [
            {"store_name": "Tienda A", "price": 1450.0, "currency": "PEN", "product_url": "https://ejemplo.com/c"},
            {"store_name": "Tienda B", "price": 1380.0, "currency": "PEN", "product_url": "https://ejemplo.com/d"},
        ]
    }
]

@app.get("/")
def home():
    return {"message": "FinPrice API está activa en la nube"}

@app.get("/products", response_model=List[ProductResponse])
def get_products(search: Optional[str] = Query(None)):
    results = []
    for item in CATALOG:
        if search and search.lower() not in item["name"].lower():
            continue
        
        best_offer = min(item["offers"], key=lambda x: x["price"])
        
        results.append(ProductResponse(
            id=item["id"],
            name=item["name"],
            category=item["category"],
            lowest_price=best_offer["price"],
            best_store=best_offer["store_name"],
            offers=sorted(item["offers"], key=lambda x: x["price"])
        ))
    return results
