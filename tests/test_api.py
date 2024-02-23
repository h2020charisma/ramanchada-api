from fastapi.testclient import TestClient
import re
from rcapi.main import app

client = TestClient(app)

def test_dataset():
    response = client.get("/dataset")
    assert response.status_code == 200
    assert response.json() == {"datasets": {}}

def test_docs():
    response = client.get("/docs")
    assert response.status_code == 200
    assert "<title>Ramanchada API - Swagger UI</title>" in response.text

def test_info():
    response = client.get("/info")
    assert response.status_code == 200
    content = response.json()
    assert "build_number" in content
    # Check if the build_number looks like a SHA1 hash.
    assert re.match(r"^[a-f0-9]{40}$", content["build_number"])

def test_process():
    response = client.get("/process")
    assert response.status_code == 200
    assert response.json() == ["test", "calibrate", "peaks"]

def test_task():
    response = client.get("/task")
    assert response.status_code == 200
    assert response.json() == []
