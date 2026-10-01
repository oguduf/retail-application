import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


app = FastAPI(title="Coffee Catalog Service")


class Product(BaseModel):
    sku: str
    name: str
    price: float
    description: str
    roast: str


PRODUCTS_FILE = Path(__file__).parent.parent / "data" / "products.json"
PRODUCTS = [Product(**item) for item in json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))]


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "product-catalog"}


@app.get("/products", response_model=list[Product])
def list_products() -> list[Product]:
    return PRODUCTS


@app.get("/products/{sku}", response_model=Product)
def get_product(sku: str) -> Product:
    for product in PRODUCTS:
        if product.sku == sku:
            return product
    raise HTTPException(status_code=404, detail="Product not found")
