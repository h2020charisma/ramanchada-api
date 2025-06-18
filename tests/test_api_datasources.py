import pytest
from fastapi.testclient import TestClient
from rcapi.main import app
from rcapi.services.kc import get_token


@pytest.fixture
def client():
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()  # ensure no side effects after each test


def test_sources_no_token(client):
    # Mock get_token to return None (unauthenticated)
    app.dependency_overrides[get_token] = lambda: None

    response = client.get("/db/query/sources")
    assert response.status_code == 200

    data = response.json()
    names = {item['name'] for item in data.get("data_sources", [])}

    assert "charisma" in names  # Public source should be visible
    assert "charisma_protected" not in names  # Private source should be hidden


def test_sources_with_token(client):
    # Mock get_token to simulate an authenticated request
    app.dependency_overrides[get_token] = lambda: "fake_token"

    response = client.get("/db/query/sources")
    assert response.status_code == 200

    data = response.json()
    names = {item['name'] for item in data.get("data_sources", [])}

    assert "charisma" in names
    assert "charisma_protected" in names  # Private source should be visible
