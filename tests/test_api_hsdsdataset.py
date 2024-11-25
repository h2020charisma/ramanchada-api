from fastapi.testclient import TestClient
from rcapi.api.hsds_dataset import read_cha
from rcapi.main import app
import pytest

client = TestClient(app)

TEST_ENDPOINT = "/db/dataset"


@pytest.fixture(scope="module")
def domain():
    params = {"query_type": "metadata", "pagesize": 1}
    response = client.get("/db/query", params=params)
    assert response.status_code == 200
    _domain = response.json()[0]["value"]
    return _domain


def test_get_dataset(domain):
    # Test case where the domain ends with '.cha'
    response = client.get(TEST_ENDPOINT, params={"domain": domain})
    assert response.status_code == 200
    print(response.json())
    result = {"subdomains": [], "domain": domain, "annotation": [], "datasets": []}
    _content = read_cha(domain, result)
    # print(_content)
    # assert response.json() == _content # Ensure that the result is as expected

