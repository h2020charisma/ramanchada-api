import pytest
from fastapi.testclient import TestClient
from rcapi.main import app
from rcapi.services.kc import get_token, get_roles_from_token
from pathlib import Path


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


def test_sources_with_token(client, monkeypatch):
    TEST_TOKEN = Path(__file__).parent / "resources/api/test-token.txt"
    token = TEST_TOKEN.read_text()
    TEST_KEY = Path(__file__).parent / "resources/api/test-jwt-key.pem"
    key = TEST_KEY.read_text()
    app.dependency_overrides[get_token] = lambda: token

    # Define patched version of get_roles_from_token
    def mock_get_roles_from_token(token, key=key):
        print("----> mock_get_roles_from_token (key=key)")
        return get_roles_from_token(token, key=key)
    monkeypatch.setattr("rcapi.api.query.get_roles_from_token",
                        mock_get_roles_from_token)

    # Call the endpoint
    response = client.get("/db/query/sources")
    assert response.status_code == 200

    data = response.json()
    print(data)
    names = {item['name'] for item in data.get("data_sources", [])}
    assert "charisma" in names
    assert "charisma_protected" in names
