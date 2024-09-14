from fastapi.testclient import TestClient
from rcapi.main import app
import pytest
from importlib.resources import open_text
from rcapi.services.solr_query import SOLR_VECTOR 
from numcompress import  decompress

client = TestClient(app)

TEST_ENDPOINT = "/query"

@pytest.fixture
def knnquery4test():
    # Load the file content from resources
    with open_text('resources.api', 'pdf2knnquery.txt') as file_stream:
        knnQuery = file_stream.read()
    return knnQuery

def test_query_metadata():
    params = { "query_type" : "metadata" }
    response = client.get(TEST_ENDPOINT,params=params)
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, list), "Response is not a list"
    for item in result:
        assert isinstance(item, dict), "Items in the list should be dictionaries"
        assert "value" in item, "'value' key missing"
        assert "text" in item, "'text' key missing"
        assert "imageLink" in item, "'imageLink' key missing"

def test_query_metadata_embeddedimages():
    params = { "query_type" : "metadata" , "img" : "embedded"}
    response = client.get(TEST_ENDPOINT,params=params)
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
    params = { "query_type" : "knnquery" , "ann" : knnquery4test}
    response = client.get(TEST_ENDPOINT,params=params)
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, list), "Response is not a list"
    for item in result:
        assert isinstance(item, dict), "Items in the list should be dictionaries"
        assert "score" in item, "'value' key missing"        
        assert "value" in item, "'value' key missing"
        assert "text" in item, "'text' key missing"
        assert "imageLink" in item, "'imageLink' key missing"
        assert SOLR_VECTOR in item, "vector field key missing"

def test_fixture(knnquery4test):
    _knnquery = decompress(knnquery4test)
    assert len(_knnquery) == 2048