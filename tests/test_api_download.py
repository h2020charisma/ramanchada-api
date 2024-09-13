from fastapi.testclient import TestClient
from rcapi.main import app
import pytest
import h5pyd

client = TestClient(app)

@pytest.fixture(scope="module")
def domain():
    params = { "query_type" : "metadata" , "pagesize" : 1} 
    response = client.get("/query",params=params)
    assert response.status_code == 200
    _domain = response.json()[0]["value"]
    return _domain


def test_download_domain(domain):
    print(domain)
    params = { "domain" : domain , "what" : "h5"} 
    response = client.get("/download",params=params)
    assert response.status_code == 200
    print(response)


def test_access_domain(domain):
    print(h5pyd.__version__)
    print(domain)
    with h5pyd.File(domain) as top_group:
        for index,key in enumerate(top_group):
            print(index,key)