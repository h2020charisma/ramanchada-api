from fastapi.testclient import TestClient
from rcapi.main import app
import pytest
from importlib.resources import files
from numcompress import decompress

client = TestClient(app)

TEST_ENDPOINT = "/db/query"

@pytest.fixture
def knnquery4test():
    resource_path = files('resources.api',).joinpath('pdf2knnquery.txt')
    with resource_path.open('r') as file_stream:
        knnQuery = file_stream.read()
    return knnQuery


def test_query_metadata():
    params = { "query_type": "metadata" }
    response = client.get(TEST_ENDPOINT, params=params)
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, list), "Response is not a list"
    for item in result:
        assert isinstance(item, dict), "Items in the list should be dictionaries"
        assert "value" in item, "'value' key missing"
        assert "text" in item, "'text' key missing"
        assert "imageLink" in item, "'imageLink' key missing"


def test_query_metadata_embeddedimages():
    params = { "query_type": "metadata" , "img": "embedded"}
    response = client.get(TEST_ENDPOINT, params=params)
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, list), "Response is not a list"
    for item in result:
        assert isinstance(item, dict), "Items in the list should be dictionaries"
        assert "value" in item, "'value' key missing"
        assert "text" in item, "'text' key missing"
        assert "imageLink" in item, "'imageLink' key missing"
        #assert "spectrum_p1024" in item, "vector field key missing"


def test_knnquery(knnquery4test):
    params = { "query_type": "knnquery" , "ann": knnquery4test}
    response = client.get(TEST_ENDPOINT, params=params)
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, list), "Response is not a list"
    for item in result:
        assert isinstance(item, dict), "Items in the list should be dictionaries"
        assert "score" in item, "'score' key missing"        
        assert "value" in item, "'value' key missing"
        assert "text" in item, "'text' key missing"
        assert "imageLink" in item, "'imageLink' key missing"
        #assert SOLR_VECTOR in item, "vector field key missing"


def test_fixture(knnquery4test):
    _knnquery = decompress(knnquery4test)
    assert len(_knnquery) == 2048