import pytest
from fastapi.testclient import TestClient
from rcapi.api.hsds_dataset import read_cha
from rcapi.main import app


TEST_ENDPOINT = "/db/dataset"
client = TestClient(app)


@pytest.fixture(scope="module")
def domain():
    params = {
        "pagesize": 1,
        "query_type": "metadata",
    }
    response = client.get("/db/query", params=params)
    assert response.status_code == 200
    domain_url = response.json()[0]["value"]
    return domain_url.partition("#")[0]


def test_get_dataset(domain):
    response = client.get(TEST_ENDPOINT, params={"domain": domain})
    assert response.status_code == 200
    print(response.json())
    expected_response = {
        "annotation": [],
        "datasets": [],
        "domain": domain,
        "subdomains": [],
    }
    assert response.json() == expected_response
