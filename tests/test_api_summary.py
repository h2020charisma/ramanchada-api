"""/db/query/summary -- group a data source by its import provenance.

Config-agnostic by construction: the deployed config varies per instance, so every
test reads the collection to use from /db/query/sources and probes real values out of
the running index rather than naming a collection or a field value.
"""

import pytest
from fastapi.testclient import TestClient

from rcapi.main import app
from rcapi.api.query import (
    SUMMARY_GROUP_FIELDS,
    SUMMARY_METRICS,
    _summary_facet,
    _summary_rows,
)
from rcapi.services.standard_response import StandardResponse

client = TestClient(app)
TEST_ENDPOINT = "/db/query/summary"


@pytest.fixture
def default_source():
    response = client.get("/db/query/sources")
    assert response.status_code == 200
    return response.json()["default"]


# --------------------------------------------------------------------
# The facet builder and the response flattener -- no network
# --------------------------------------------------------------------

def test_facet_asks_for_the_missing_bucket():
    """The bucket of documents with NO value for the grouping field is the whole
    point of the report: it is "this import recorded no provenance". Solr omits it
    unless asked, so if this ever flips to False the defect stops being visible.
    """
    facet = _summary_facet(["__input_file_s"], ["studies"])
    assert facet["group"]["missing"] is True
    assert facet["group"]["field"] == "__input_file_s"
    assert facet["group"]["facet"]["studies"] == SUMMARY_METRICS["studies"]


def test_facet_nests_several_group_fields_outermost_first():
    facet = _summary_facet(["a_s", "b_s"], ["studies"])
    assert facet["group"]["field"] == "a_s"
    inner = facet["group"]["facet"]["group"]
    assert inner["field"] == "b_s"
    assert inner["facet"]["studies"] == SUMMARY_METRICS["studies"]


def test_missing_bucket_flattens_to_a_null_group_value():
    """Reported as null, not dropped and not renamed to a sentinel string -- a
    caller has to be able to tell "no value recorded" apart from a document whose
    value happens to be the word "missing".
    """
    response = {
        "group": {
            "buckets": [
                {
                    "val": "a.xlsx",
                    "count": 3,
                    "studies": 3,
                    "investigation": {"buckets": [{"val": "T1"}, {"val": "T2"}]},
                    "uuid": {"buckets": [{"val": "U1"}]},
                    "substance_uuid": {"buckets": [{"val": "S1"}]},
                    "value": {"buckets": [{"val": "/x.nxs#/entry/RAW"}]},
                }
            ],
            "missing": {
                "count": 7,
                "studies": 7,
                "investigation": {"buckets": []},
                "uuid": {"buckets": []},
                "substance_uuid": {"buckets": []},
                "value": {"buckets": []},
            },
        }
    }
    rows = _summary_rows(response, ["__input_file_s"], ["studies"])

    missing = [r for r in rows if r["__input_file_s"] is None]
    assert len(missing) == 1
    assert missing[0]["count"] == 7

    named = [r for r in rows if r["__input_file_s"] == "a.xlsx"][0]
    # the values, not just a count: the "several investigations for one file" and
    # "title reused across files" checks are made from these
    assert named["investigation"] == ["T1", "T2"]
    # a representative document to open, resolved by the frontend viewers registry
    assert named["uuid"] == "U1"
    assert named["substance_uuid"] == "S1"
    assert named["value"] == "/x.nxs#/entry/RAW"


def test_missing_bucket_is_omitted_when_empty():
    response = {"group": {"buckets": [], "missing": {"count": 0}}}
    assert _summary_rows(response, ["f_s"], []) == []


# --------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------

def test_summary_returns_one_entry_per_source(default_source):
    response = client.get(TEST_ENDPOINT, params={"data_source": default_source})
    assert response.status_code == 200
    parsed = StandardDictList(response.json())

    assert len(parsed) == 1
    entry = parsed[0]
    assert entry["data_source"] == default_source
    assert "error" not in entry, entry.get("error")
    assert isinstance(entry["rows"], list)


def test_grouping_field_is_derived_from_the_index(default_source):
    """Which provenance field to group by is read off the collection, never
    configured -- that is what lets the same report cover a collection nobody
    anticipated. The chosen field must be the first one the probe found populated.
    """
    response = client.get(TEST_ENDPOINT, params={"data_source": default_source})
    entry = StandardDictList(response.json())[0]

    provenance = entry["provenance"]
    assert set(provenance) == set(SUMMARY_GROUP_FIELDS)

    expected = next(
        (f for f in SUMMARY_GROUP_FIELDS if provenance.get(f)), SUMMARY_GROUP_FIELDS[0]
    )
    assert entry["group_by"] == [expected]


def test_rows_never_claim_more_documents_than_the_collection_holds(default_source):
    response = client.get(TEST_ENDPOINT, params={"data_source": default_source})
    entry = StandardDictList(response.json())[0]

    total = sum(row["count"] for row in entry["rows"])
    # equal when the grouping field is single-valued, less only if mincount hid
    # something; more would mean documents were double counted across buckets
    assert total <= entry["numFound"]


def test_explicit_group_by_is_honoured(default_source):
    response = client.get(
        TEST_ENDPOINT,
        params={"data_source": default_source, "group_by": "topcategory_s"},
    )
    assert response.status_code == 200
    entry = StandardDictList(response.json())[0]
    assert entry["group_by"] == ["topcategory_s"]
    assert all("topcategory_s" in row for row in entry["rows"])


def test_metrics_are_whitelisted(default_source):
    """A caller supplies metric NAMES, never Solr expressions -- nothing a caller
    sends is interpolated into json.facet.
    """
    response = client.get(
        TEST_ENDPOINT,
        params={"data_source": default_source, "metrics": "hll(secret_s)"},
    )
    assert response.status_code == 400
    assert "Unknown metric" in response.json()["detail"]


def test_selected_metrics_are_the_ones_returned(default_source):
    response = client.get(
        TEST_ENDPOINT,
        params={"data_source": default_source, "metrics": ["studies", "materials"]},
    )
    assert response.status_code == 200
    rows = StandardDictList(response.json())[0]["rows"]
    if not rows:
        pytest.skip("default collection has no rows to inspect")
    assert "studies" in rows[0] and "materials" in rows[0]
    assert "endpoints" not in rows[0]


def test_group_by_is_capped(default_source):
    response = client.get(
        TEST_ENDPOINT,
        params={
            "data_source": default_source,
            "group_by": ["a_s", "b_s", "c_s", "d_s"],
        },
    )
    assert response.status_code == 400
    assert "At most 3" in response.json()["detail"]


def test_anonymous_is_refused_an_inaccessible_source():
    """Same gating as every other route: no data leaks through the summary because
    it is a different endpoint.
    """
    response = client.get(TEST_ENDPOINT, params={"data_source": "no-such-collection"})
    assert response.status_code == 401


def StandardDictList(payload):
    parsed = StandardResponse[list].model_validate(payload)
    assert isinstance(parsed.response, list)
    return parsed.response
