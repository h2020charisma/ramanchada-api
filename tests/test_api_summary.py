"""/db/query/summary -- group a data source by its import provenance.

Config-agnostic by construction: the deployed config varies per instance, so every
test reads the collection to use from /db/query/sources and probes real values out of
the running index rather than naming a collection or a field value.
"""

import pytest
from fastapi.testclient import TestClient

from rcapi.main import app
from rcapi.api.query import (
    SUMMARY_DEFAULT_GROUPS,
    SUMMARY_INPUT_FILE_FIELD,
    SUMMARY_METRICS,
    SUMMARY_PROVENANCE_FIELDS,
    _grouping_doc_types,
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
    detail = facet["group"]["facet"]["detail"]
    assert detail["facet"]["studies"] == SUMMARY_METRICS["studies"]
    # the measures are reached through a join, because the grouped documents
    # are the params children and the measures live on the study records
    assert detail["domain"]["join"] == {
        "from": "document_uuid_s",
        "to": "document_uuid_s",
    }


def test_facet_nests_several_group_fields_outermost_first():
    facet = _summary_facet(["a_s", "b_s"], ["studies"])
    assert facet["group"]["field"] == "a_s"
    inner = facet["group"]["facet"]["group"]
    assert inner["field"] == "b_s"
    assert inner["facet"]["detail"]["facet"]["studies"] == SUMMARY_METRICS["studies"]


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
                    "detail": {
                        "studies": 3,
                        "investigation": {
                            "buckets": [{"val": "T1"}, {"val": "T2"}]
                        },
                        "documents": {
                            "buckets": [
                                {
                                    "val": "U1",
                                    "count": 1,
                                    "substance_uuid": {"buckets": [{"val": "S1"}]},
                                    "value": {
                                        "buckets": [{"val": "/x.nxs#/entry/RAW"}]
                                    },
                                }
                            ]
                        },
                    },
                }
            ],
            "missing": {
                "count": 7,
                "detail": {
                    "studies": 7,
                    "investigation": {"buckets": []},
                    "documents": {"buckets": []},
                },
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
    # and it stands for the whole group, so a caller can say "one of 3"
    assert named["represents"] == 3


def test_representative_fields_describe_one_document():
    """The uuid and the fields describing it must come from the SAME document.

    Regression: they were three sibling top-1 facets, so each picked its own
    winner independently. On a real collection one row came back with a
    document_uuid from one study, an s_uuid from a second and a textValue from a
    third -- the study viewer would then get a studyId and a substanceId that do
    not belong together. Nesting them inside the chosen document's bucket is what
    makes them coherent, and this asserts the flattener reads them from there.
    """
    response = {
        "group": {
            "buckets": [
                {
                    "val": "a.xlsx",
                    "count": 3,
                    "detail": {
                        "investigation": {"buckets": []},
                        "documents": {
                            "buckets": [
                                {
                                    "val": "CHOSEN-uuid",
                                    "count": 1,
                                    "substance_uuid": {
                                        "buckets": [{"val": "ITS-substance"}]
                                    },
                                    "value": {"buckets": [{"val": "ITS-value"}]},
                                }
                            ]
                        },
                    },
                }
            ],
            "missing": {"count": 0},
        }
    }
    row = _summary_rows(response, ["__input_file_s"], [])[0]
    assert row["uuid"] == "CHOSEN-uuid"
    assert row["substance_uuid"] == "ITS-substance"
    assert row["value"] == "ITS-value"


def test_representative_is_nested_not_sibling():
    """The facet itself must nest, or the flattener above can never be coherent."""
    facet = _summary_facet(["__input_file_s"], [])
    rep = facet["group"]["facet"]["detail"]["facet"]["documents"]
    assert rep["field"] == "document_uuid_s"
    assert rep["limit"] > 1  # a list to choose from, not one pick
    # deterministic pick, not count-then-arbitrary-tiebreak
    assert rep["sort"] == "index"
    assert {"substance_uuid", "value", "material", "method"} <= set(
        rep["facet"]
    )
    # and NOT sitting beside the group's other measures
    assert "substance_uuid" not in facet["group"]["facet"]
    assert "substance_uuid" not in facet["group"]["facet"]["detail"]["facet"]


def test_grouping_prefers_params_one_document_per_study():
    """A provenance field can sit on the params child AND on the study record at
    once (the NeXus index writes both), so exactly one type is chosen -- grouping
    over both counts every protocol application twice.

    params wins. It is one document per protocol application, whereas the AMBIT
    index duplicates the study document per effect: grouping study documents would
    make a bucket's count the number of measurements, so an import of 3 studies
    with 200 measurements each would report 600 instead of 3. The measures that
    live only on the study record are still reached, through the join.
    """
    assert _grouping_doc_types(["params", "study"]) == ["params"]
    assert _grouping_doc_types(["study", "params"]) == ["params"]


def test_grouping_uses_the_study_record_when_there_is_no_params_child():
    assert _grouping_doc_types(["study"]) == ["study"]


def test_studies_counts_entries_not_effects():
    """"Studies" must mean protocol applications (NXentries), not measurements.

    The AMBIT index writes one study document per effect, so a plain document
    count would report an import of 3 entries with 200 measurements each as 600.
    hll(document_uuid_s) is distinct-by-entry -- document_uuid_s is the protocol
    application uuid, repeated across every effect of one entry -- so the
    duplication collapses.
    """
    assert SUMMARY_METRICS["studies"] == "hll(document_uuid_s)"
    facet = _summary_facet(["__input_file_s"], ["studies"])
    assert (
        facet["group"]["facet"]["detail"]["facet"]["studies"]
        == "hll(document_uuid_s)"
    )


def test_grouping_over_nothing_when_the_field_is_absent():
    assert _grouping_doc_types([]) == []
    assert _grouping_doc_types([None]) == []


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


def test_groups_by_input_file_and_never_substitutes(default_source):
    """The question is "which files were imported", so the grouping is the input
    file whether or not the collection records one.

    Substituting nexus_file_ss (the *transformed* file) or reference_s (a dataset
    citation) would answer a different question with a table that looks complete --
    a work package grouping 1000 studies reads exactly like a file grouping 1000
    studies. The caller could not tell that its question went unanswered, and the
    import-pipeline defect would be hidden rather than reported.
    """
    response = client.get(TEST_ENDPOINT, params={"data_source": default_source})
    entry = StandardDictList(response.json())[0]

    # grouped under the data provider, because that is how people look for their
    # own submissions -- but the row is still the input file
    assert entry["group_by"] == list(SUMMARY_DEFAULT_GROUPS)
    assert entry["group_by"][0] == SUMMARY_INPUT_FILE_FIELD
    assert set(entry["provenance"]) == set(SUMMARY_PROVENANCE_FIELDS)
    # reported, so a caller can say "this collection records no input files"
    # instead of rendering an empty table with no explanation
    assert entry["records_input_files"] == bool(
        entry["provenance"][SUMMARY_INPUT_FILE_FIELD]
    )


def test_a_collection_without_input_files_says_so(default_source):
    """It must be possible to tell "nothing imported" from "provenance not
    recorded". A collection with no input files reports every document in the
    missing bucket, not an empty row list.
    """
    response = client.get(TEST_ENDPOINT, params={"data_source": default_source})
    entry = StandardDictList(response.json())[0]
    if entry["records_input_files"]:
        pytest.skip("this collection does record input files")

    assert entry["records_input_files"] is False
    missing = [r for r in entry["rows"] if r[SUMMARY_INPUT_FILE_FIELD] is None]
    assert missing, "documents with no input file must still be reported"
    # every document lands in a no-input-file bucket, whatever provider it
    # is grouped under
    assert sum(r["entries"] or 0 for r in missing) == entry["entries"]


def test_rows_never_claim_more_documents_than_the_collection_holds(default_source):
    response = client.get(TEST_ENDPOINT, params={"data_source": default_source})
    entry = StandardDictList(response.json())[0]

    # in protocol applications, the unit every row is in -- NOT raw documents,
    # which are effect-level and inflated by the params duplication
    total = sum(row["entries"] or 0 for row in entry["rows"])
    assert total <= entry["entries"]
    # and the raw document count is reported separately, never as studies
    assert entry["documents_matched"] >= entry["entries"]


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


# --------------------------------------------------------------------
# Token forwarding
# --------------------------------------------------------------------

def test_every_solr_call_forwards_the_caller_token(monkeypatch):
    """Each Solr request this endpoint makes must carry the caller's token.

    A private collection answers 401 without one, which surfaces as "no input
    files recorded" -- indistinguishable from a collection that genuinely has
    none. The equivalent bug has already happened once in this stack, in the
    type-ahead's bare fetch, and was invisible for exactly the same reason.
    """
    seen = []

    async def fake_get(url, params=None, token=None):
        seen.append(token)

        class R:
            @staticmethod
            def json():
                return {
                    "response": {"numFound": 0},
                    "facet_counts": {"facet_fields": {"type_s": []}},
                    "facets": {},
                }

        return R()

    monkeypatch.setattr("rcapi.api.query.solr_query_get", fake_get)
    # Override the dependency rather than sending a header: get_token validates
    # the JWT against Keycloak, and this test is about what the route does with
    # a token it has already accepted, not about validation.
    from rcapi.services.kc import get_token

    app.dependency_overrides[get_token] = lambda: "test-token-123"
    try:
        response = client.get(TEST_ENDPOINT)
    finally:
        app.dependency_overrides.pop(get_token, None)
    assert response.status_code == 200
    assert seen, "no Solr request was made at all"
    assert all(t == "test-token-123" for t in seen), (
        "these Solr calls dropped the token: "
        f"{[i for i, t in enumerate(seen) if t != 'test-token-123']}"
    )


def test_solr_query_get_sets_the_bearer_header():
    """The layer below: the token has to become an Authorization header."""
    import asyncio

    import httpx

    from rcapi.services.solr_query import solr_query_get

    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            captured["headers"] = headers or {}

            class R:
                status_code = 200

                @staticmethod
                def raise_for_status():
                    return None

            return R()

    original = httpx.AsyncClient
    httpx.AsyncClient = lambda *a, **k: FakeClient()
    try:
        asyncio.run(solr_query_get("http://solr/x/select", {"q": "*:*"}, "tok-9"))
    finally:
        httpx.AsyncClient = original

    assert captured["headers"].get("Authorization") == "Bearer tok-9"


def test_group_fields_are_located_before_grouping(monkeypatch):
    """The grouping must run over documents that carry the grouping field.

    Two ways this silently produced an empty report: the probe only located the
    fixed provenance fields, so the default group fields were never looked up;
    and the lookup used the LAST group level rather than the first. Either way
    `carriers` came out empty, the grouping fell back to the study-only filter,
    and every row reported "no input file" directly underneath a probe saying
    there were 9974 of them.
    """
    calls = []

    async def fake_get(url, params=None, token=None):
        calls.append(params or {})

        class R:
            @staticmethod
            def json():
                return {
                    "response": {"numFound": 1},
                    # the probe's fq names the field being located; claim it
                    # lives on params, as an AMBIT collection's does
                    "facet_counts": {"facet_fields": {"type_s": ["params", 1]}},
                    "facets": {"entries": 0},
                }

        return R()

    monkeypatch.setattr("rcapi.api.query.solr_query_get", fake_get)
    assert client.get(TEST_ENDPOINT).status_code == 200

    located = {
        c["fq"].split(":")[0] for c in calls if "fq" in c and c["fq"].endswith(":*")
    }
    # the row-identity field, and the levels that break it down, are all probed
    for field in SUMMARY_DEFAULT_GROUPS:
        assert field in located, f"{field} was never located before grouping"

    # and the grouping query runs over the type the identity field lives on,
    # not the default study-only filter
    grouping = [c for c in calls if "json.facet" in c]
    assert grouping, "no grouping query was issued"
    assert grouping[-1]["fq"] == 'type_s:("params")'
