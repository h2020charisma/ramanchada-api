from fastapi.testclient import TestClient
from rcapi.main import app
import pytest
from importlib.resources import files
from numcompress import decompress
from rcapi.services.standard_response import StandardDictListResponse

client = TestClient(app)
TEST_ENDPOINT = "/db/query"


@pytest.fixture
def knnquery4test():
    resource_path = files("resources.api").joinpath("pdf2knnquery.txt")
    with resource_path.open("r") as file_stream:
        knnQuery = file_stream.read()
    return knnQuery


# --------------------------------------------------------------------
# GET tests
# --------------------------------------------------------------------

def test_query_metadata():
    params = {"query_type": "metadata"}
    response = client.get(TEST_ENDPOINT, params=params)
    assert response.status_code == 200
    parsed = StandardDictListResponse.model_validate(response.json())
    assert isinstance(parsed.response, list)
    for item in parsed.response:
        assert isinstance(item, dict)
        assert "value" in item
        assert "text" in item
        assert "imageLink" in item


def test_query_metadata_embeddedimages():
    params = {"query_type": "metadata", "img": "embedded"}
    response = client.get(TEST_ENDPOINT, params=params)
    assert response.status_code == 200
    parsed = StandardDictListResponse.model_validate(response.json())
    assert isinstance(parsed.response, list)
    for item in parsed.response:
        assert isinstance(item, dict)
        assert "value" in item
        assert "text" in item
        assert "imageLink" in item


def test_query_metadata_with_filters_get():
    params = {
        "query_type": "metadata",
        "filters.name_s": "Fluorapatite"
    }
    response = client.get(TEST_ENDPOINT, params=params)
    assert response.status_code == 200
    parsed = StandardDictListResponse.model_validate(response.json())
    assert isinstance(parsed.response, list)
    for item in parsed.response:
        assert isinstance(item, dict)
        assert "value" in item
        assert "text" in item
        assert "imageLink" in item


def test_knnquery(knnquery4test):
    params = {"query_type": "knnquery", "ann": knnquery4test}
    response = client.get(TEST_ENDPOINT, params=params)
    assert response.status_code == 200
    parsed = StandardDictListResponse.model_validate(response.json())
    assert isinstance(parsed.response, list)
    for item in parsed.response:
        assert isinstance(item, dict)
        assert "score" in item
        assert "value" in item
        assert "text" in item
        assert "imageLink" in item


# --------------------------------------------------------------------
# POST tests
# --------------------------------------------------------------------

def test_post_query_metadata():
    payload = {"query_type": "metadata"}
    response = client.post(TEST_ENDPOINT, json=payload)
    assert response.status_code == 200
    parsed = StandardDictListResponse.model_validate(response.json())
    assert isinstance(parsed.response, list)
    for item in parsed.response:
        assert "value" in item
        assert "text" in item
        assert "imageLink" in item


def test_post_query_metadata_with_filters():
    payload = {
        "query_type": "metadata",
        "filters": {"name_s": "Anatase"},
        "data_source": "charisma",
    }
    response = client.post(TEST_ENDPOINT, json=payload)
    assert response.status_code == 200
    parsed = StandardDictListResponse.model_validate(response.json())
    assert isinstance(parsed.response, list)
    for item in parsed.response:
        assert isinstance(item, dict)
        assert "value" in item
        assert "text" in item
        assert "imageLink" in item


def test_post_knnquery(knnquery4test):
    payload = {"query_type": "knnquery", "ann": knnquery4test}
    response = client.post(TEST_ENDPOINT, json=payload)
    assert response.status_code == 200
    parsed = StandardDictListResponse.model_validate(response.json())
    assert isinstance(parsed.response, list)
    for item in parsed.response:
        assert "score" in item
        assert "value" in item
        assert "text" in item
        assert "imageLink" in item


# --------------------------------------------------------------------
# Fixtures / sanity checks
# --------------------------------------------------------------------

def test_fixture(knnquery4test):
    _knnquery = decompress(knnquery4test)
    assert len(_knnquery) == 2048
