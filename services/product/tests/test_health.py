from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "product-catalog"}


def test_list_products() -> None:
    response = client.get("/products")

    assert response.status_code == 200
    assert len(response.json()) == 4
    assert response.json()[0]["sku"] == "ETHIOPIA-YIRGACHEFFE"
