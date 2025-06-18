import unittest
from fastapi.testclient import TestClient
from rcapi.main import app
from rcapi.services.kc import get_token 


class TestRealConfigWithMockedToken(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        # Always clear overrides after each test to avoid side effects
        app.dependency_overrides.clear()

    def test_sources_no_token(self):
        # Override get_token to return None
        app.dependency_overrides[get_token] = lambda: None

        response = self.client.get("/db/query/sources")
        assert response.status_code == 200
        data = response.json()

        names = {item['name'] for item in data.get("data_sources", [])}

        # default and public expected
        assert "charisma" in names  # example value from your real config
        # Private should NOT be present when no token
        assert "charisma_protected" not in names

    def test_sources_with_token(self):
        # Override get_token to return a fake token string
        app.dependency_overrides[get_token] = lambda: "fake_token"

        response = self.client.get("/db/query/sources")
        assert response.status_code == 200
        data = response.json()

        names = {item['name'] for item in data.get("data_sources", [])}

        # With token, default, public, private all expected
        assert "charisma" in names
        assert "charisma_protected" in names


if __name__ == "__main__":
    unittest.main()
