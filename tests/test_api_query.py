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
        "qdynamic.name_s": "Fluorapatite"
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
        "qdynamic": {"name_s": "Anatase"},
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


# --------------------------------------------------------------------
# Field type-ahead (/db/query/field/terms)
# --------------------------------------------------------------------
# These run against the public `plastic` collection, whose E.method_s values are
# full phrases ("ATR-FTIR spectroscopy", "Raman spectroscopy") -- the shape that
# made the previous TermsComponent implementation unusable as a type-ahead.

TERMS_ENDPOINT = "/db/query/field/terms"


def test_field_terms_matches_inside_a_value():
    """A type-ahead must match within a value, not only at its start.

    terms.prefix is left-anchored over the whole indexed string, so typing
    "FTIR" could never find "ATR-FTIR spectroscopy". Regression guard for that.
    """
    params = {"name": "qdynamic.E.method_s", "prefix": "FTIR",
              "data_source": "plastic"}
    response = client.get(TERMS_ENDPOINT, params=params)
    assert response.status_code == 200
    values = response.json()["response"]

    assert values, "no match for a substring present in the data"
    assert all("FTIR" in v for v in values)
    assert any(not v.startswith("FTIR") for v in values), (
        "only start-of-string matches returned -- prefix semantics are back"
    )


def test_field_terms_ignores_case():
    params = {"name": "qdynamic.E.method_s", "prefix": "ftir",
              "data_source": "plastic"}
    response = client.get(TERMS_ENDPOINT, params=params)
    assert response.status_code == 200
    assert response.json()["response"]


def test_field_terms_without_prefix_lists_values():
    params = {"name": "publicname_s", "limit": 3, "data_source": "plastic"}
    response = client.get(TERMS_ENDPOINT, params=params)
    assert response.status_code == 200
    values = response.json()["response"]
    assert 0 < len(values) <= 3
    assert all(isinstance(v, str) for v in values)


def test_field_terms_unmatched_prefix_is_empty():
    params = {"name": "qdynamic.E.method_s", "prefix": "zzz-no-such-method",
              "data_source": "plastic"}
    response = client.get(TERMS_ENDPOINT, params=params)
    assert response.status_code == 200
    assert response.json()["response"] == []
