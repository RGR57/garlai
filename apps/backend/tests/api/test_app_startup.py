from fastapi.testclient import TestClient

from src.main import app


def test_fastapi_app_imports_and_serves_root_endpoint():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "GARL Backend is running",
    }
