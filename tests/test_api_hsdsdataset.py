from fastapi.testclient import TestClient
from rcapi.api.hsds_dataset import read_cha
from rcapi.main import app
import pytest

client = TestClient(app)

@pytest.fixture(scope="module")
def domain():
    params = { "query_type" : "metadata" , "pagesize" : 1} 
    response = client.get("/query",params=params)
    assert response.status_code == 200
    _domain = response.json()[0]["value"]
    return _domain

def test_get_dataset(domain):
    # Test case where the domain ends with '.cha'
    response = client.get("/hsds/dataset", params={"domain": domain})
    assert response.status_code == 200
    print(response.json())
    result = {"subdomains": [], "domain": domain, "annotation": [], "datasets": []}
    assert response.json() == read_cha(domain,result)  # Ensure that the result is as expected

