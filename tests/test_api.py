import re

from fastapi.testclient import TestClient
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
    # Check if build_number looks like what we expect.
    regex = r"^[a-f0-9]{7} \(.*, \d{4}-\d{2}-\d{2}\)$"
    assert re.match(regex, content["build_number"])


def test_process():
    response = client.get("/process")
    assert response.status_code == 200
    assert response.json() == ["test", "calibrate", "peaks"]


def test_task():
    response = client.get("/task")
    assert response.status_code == 200
    assert response.json() == []
