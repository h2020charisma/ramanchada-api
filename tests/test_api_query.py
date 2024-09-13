from fastapi.testclient import TestClient
from rcapi.main import app

client = TestClient(app)

def test_query_metadata():
    params = { "query_type" : "metadata" }
    response = client.get("/query",params=params)
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
    response = client.get("/query",params=params)
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, list), "Response is not a list"
    for item in result:
        assert isinstance(item, dict), "Items in the list should be dictionaries"
        assert "value" in item, "'value' key missing"
        assert "text" in item, "'text' key missing"
        assert "imageLink" in item, "'imageLink' key missing"
        #assert "spectrum_p1024" in item, "vector field key missing"