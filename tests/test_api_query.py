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
    # Whichever collection this deployment defaults to -- naming one here ties
    # the test to a particular config, and an unserved name is now refused
    # rather than quietly swapped for the default.
    default_source = client.get("/db/query/sources").json()["default"]
    payload = {
        "query_type": "metadata",
        "qdynamic": {"name_s": "Anatase"},
        "data_source": default_source,
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
# Whatever collection this deployment defaults to, the suggestion list has to
# match inside a value and not only at its start: these are string fields
# holding phrases ("ATR-FTIR spectroscopy", "Py-GC-MS"), so a left-anchored
# match -- what the previous TermsComponent implementation did -- can never
# find "FTIR" or "GC". The values are read from the running index rather than
# hard-coded, so the tests hold for any configured collection.

TERMS_ENDPOINT = "/db/query/field/terms"
TERMS_FIELD = "publicname_s"


def _a_value_with_an_interior_substring():
    """A real indexed value long enough to probe by a non-leading substring."""
    response = client.get("/db/query/field", params={"name": TERMS_FIELD})
    assert response.status_code == 200
    for entry in response.json()["response"]:
        value = entry["value"]
        # need >=3 chars after the first so the probe is unambiguously interior
        if isinstance(value, str) and len(value.strip()) >= 4:
            return value.strip()
    pytest.skip(f"no {TERMS_FIELD} value long enough in the default collection")


def test_field_terms_matches_inside_a_value():
    value = _a_value_with_an_interior_substring()
    interior = value[1:4]  # deliberately skips the first character

    response = client.get(
        TERMS_ENDPOINT, params={"name": TERMS_FIELD, "prefix": interior, "limit": 500}
    )
    assert response.status_code == 200
    values = response.json()["response"]

    assert value in values, (
        f"{value!r} not found by its interior substring {interior!r} -- "
        "left-anchored prefix semantics are back"
    )


def test_field_terms_ignores_case():
    value = _a_value_with_an_interior_substring()
    interior = value[1:4]

    lower = client.get(
        TERMS_ENDPOINT, params={"name": TERMS_FIELD, "prefix": interior.lower(), "limit": 500}
    )
    upper = client.get(
        TERMS_ENDPOINT, params={"name": TERMS_FIELD, "prefix": interior.upper(), "limit": 500}
    )
    assert lower.status_code == upper.status_code == 200
    assert value in lower.json()["response"]
    assert value in upper.json()["response"]


def test_field_terms_without_prefix_lists_values():
    response = client.get(TERMS_ENDPOINT, params={"name": TERMS_FIELD, "limit": 3})
    assert response.status_code == 200
    values = response.json()["response"]
    assert 0 < len(values) <= 3
    assert all(isinstance(v, str) for v in values)


def test_field_terms_unmatched_prefix_is_empty():
    response = client.get(
        TERMS_ENDPOINT, params={"name": TERMS_FIELD, "prefix": "zzz-no-such-value-zzz"}
    )
    assert response.status_code == 200
    assert response.json()["response"] == []
