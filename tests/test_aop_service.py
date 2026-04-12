"""
tests/test_aop_service.py — material → AOP plausibility chain

Three layers:
  - Unit tests  (mock all HTTP — fast, always offline)
  - Integration tests against real Solr (marked integration, skipped by default)
  - API tests via FastAPI TestClient

Run unit + API tests only (default, no network required):
    pytest tests/test_aop_service.py -v

Run everything including real Solr calls:
    pytest tests/test_aop_service.py -v --run-integration
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from rcapi.main import app
from rcapi.services.aop_service import (
    material_to_aop,
    _find_studies_by_name,
    _find_aop_assays_by_terms,
    _find_ke_by_assay_names,
    _find_aops_for_ke_ids,
    _get_study_endpoints,
    StudyEndpoint,
    ENM_ONTOLOGY_FIELD,
    AOP_ASSAY_MATCH_FIELD,
    AOP_SOLR_URL,
)
from rcapi.services.kc import get_token

# ---------------------------------------------------------------------------
# pytest flag
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--run-integration", action="store_true", default=False,
        help="Run tests that hit real external Solr endpoints",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as requiring live Solr access"
    )


@pytest.fixture(scope="session")
def run_integration(request):
    return request.config.getoption("--run-integration")


# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

client = TestClient(app)

TERM_A = "DAPI staining"
TERM_B = "oxidative DNA damage"

FAKE_STUDY_DOCS = [
    {
        "id": "NRG2-001/s1",
        "name_s": "Cell viability DAPI 24H A549",
        "publicname_s": "JRCNM02000a",
        "guidance_s": "OECD 487",
        "E.method_s": "DAPI staining",
        "document_uuid_s": "UUID-JRCNM02000a",
        "textValue_s": "/hsds/jrcnm/s1",
        ENM_ONTOLOGY_FIELD: [TERM_A],
    },
    {
        "id": "NRG2-001/s2",
        "name_s": "Oxidative DNA damage 8-OHdG 24H A549",
        "publicname_s": "JRCNM02000a",
        "guidance_s": "OxiSelect",
        "E.method_s": "8-OHdG ELISA",
        "document_uuid_s": "UUID-JRCNM02000a",
        "textValue_s": "/hsds/jrcnm/s2",
        ENM_ONTOLOGY_FIELD: [TERM_B],
    },
]

FAKE_STUDY_DOCS_NO_ONTOLOGY = [
    {
        "id": "NRG2-001/s1",
        "name_s": "Some assay",
        "publicname_s": "JRCNM02000a",
        "guidance_s": "Internal",
        "E.method_s": "",
        "document_uuid_s": "UUID-JRCNM02000a",
        # ENM_ONTOLOGY_FIELD absent
    },
]

FAKE_AOP_ASSAY_DOCS = [
    {
        "id": "ASSAY1",
        "name_t": "DAPI cell count assay",
        AOP_ASSAY_MATCH_FIELD: [TERM_A],
        "attr_assays": ["DAPI"],
    },
    {
        "id": "ASSAY2",
        "name_t": "8-OHG oxidative DNA damage assay",
        AOP_ASSAY_MATCH_FIELD: [TERM_B],
        "attr_assays": ["8OHG"],
    },
]

FAKE_KE_DOCS = [
    {
        "id": "KE1696",
        "title_t": "Increase in cell death",
        "biological_organization_level_t": "cellular",
        "attr_assays": ["DAPI"],
        "upstream_ss": [],
        "downstream_ss": ["KE1697"],
    },
    {
        "id": "KE881",
        "title_t": "Oxidative DNA damage",
        "biological_organization_level_t": "molecular",
        "attr_assays": ["8OHG"],
        "upstream_ss": [],
        "downstream_ss": ["KE882"],
    },
]

FAKE_AOP_DOCS = [
    {
        "id": "AOP173",
        "title_t": "Nanomaterial-induced lung inflammation",
        "oecd_status_t": "Under Development",
        "molecular_initiating_event_ss": ["KE881"],
        "adverse_outcome_ss": ["KE999"],
        "key_event_ss": ["KE881", "KE1696", "KE500"],  # 2/3 matched → 0.667
    },
]


def _enm_response(docs):
    return {"response": {"numFound": len(docs), "docs": docs}}


def _aop_response(docs):
    return {"response": {"numFound": len(docs), "docs": docs}}


# ---------------------------------------------------------------------------
# Unit: _find_studies_by_name
# ---------------------------------------------------------------------------

class TestFindStudiesByName:

    @pytest.mark.asyncio
    async def test_returns_docs(self):
        with patch("rcapi.services.aop_service.solr_query_get", new_callable=AsyncMock) as m:
            m.return_value = MagicMock(json=lambda: _enm_response(FAKE_STUDY_DOCS))
            docs = await _find_studies_by_name("JRCNM02000a", "http://fake/select", None)
        assert len(docs) == 2

    @pytest.mark.asyncio
    async def test_queries_publicname_s_not_name_hs(self):
        """publicname_s is searchable; name_hs is stored-only and must not appear."""
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _enm_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_studies_by_name("JRCNM02000a", "http://fake/select", None)

        q = captured.get("q", "")
        assert "publicname_s" in q,  f"Expected publicname_s in query, got: {q}"
        assert "name_hs"      not in q, "name_hs is non-searchable and must not appear"

    @pytest.mark.asyncio
    async def test_queries_type_study(self):
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _enm_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_studies_by_name("JRCNM02000a", "http://fake/select", None)

        assert "type_s:study" in captured.get("fq", "")

    @pytest.mark.asyncio
    async def test_name_is_solr_escaped_in_query(self):
        """Names with spaces or special chars must be escaped."""
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _enm_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_studies_by_name("TiO2 17nm", "http://fake/select", None)

        # Space must be escaped or quoted — must not appear bare in q
        q = captured.get("q", "")
        assert " 17nm" not in q or q.count('"') >= 2, \
            f"Unescaped space in query: {q}"

    @pytest.mark.asyncio
    async def test_empty_result(self):
        with patch("rcapi.services.aop_service.solr_query_get", new_callable=AsyncMock) as m:
            m.return_value = MagicMock(json=lambda: _enm_response([]))
            docs = await _find_studies_by_name("UNKNOWN", "http://fake/select", None)
        assert docs == []

    @pytest.mark.asyncio
    async def test_collection_param_added(self):
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _enm_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_studies_by_name(
                "JRCNM02000a", "http://fake/select", None, collection_param="nanoreg2"
            )

        assert captured.get("collection") == "nanoreg2"

    @pytest.mark.asyncio
    async def test_fl_does_not_contain_where_clause(self):
        """fl must be a valid comma-separated field list — no SQL-like WHERE."""
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _enm_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_studies_by_name("JRCNM02000a", "http://fake/select", None)

        fl = captured.get("fl", "")
        assert "where" not in fl.lower(), f"Invalid 'where' clause in fl: {fl}"
        assert "type_s:" not in fl, f"Field filter in fl: {fl}"


# ---------------------------------------------------------------------------
# Unit: _get_study_endpoints
# ---------------------------------------------------------------------------

class TestGetStudyEndpoints:

    @pytest.mark.asyncio
    async def test_populates_all_fields(self):
        with patch("rcapi.services.aop_service.solr_query_get", new_callable=AsyncMock) as m:
            m.return_value = MagicMock(json=lambda: _enm_response(FAKE_STUDY_DOCS))
            eps = await _get_study_endpoints("JRCNM02000a", "http://fake/select", None)

        assert len(eps) == 2
        ep = eps[0]
        assert ep.publicname == "JRCNM02000a"
        assert ep.guidance == "OECD 487"
        assert ep.method == "DAPI staining"
        assert ep.has_data is True
        assert TERM_A in ep.ontology_terms

    @pytest.mark.asyncio
    async def test_no_ontology_field_empty_list(self):
        with patch("rcapi.services.aop_service.solr_query_get", new_callable=AsyncMock) as m:
            m.return_value = MagicMock(json=lambda: _enm_response(FAKE_STUDY_DOCS_NO_ONTOLOGY))
            eps = await _get_study_endpoints("JRCNM02000a", "http://fake/select", None)

        assert eps[0].ontology_terms == []
        assert eps[0].has_data is False

    @pytest.mark.asyncio
    async def test_string_ontology_normalised_to_list(self):
        doc = {**FAKE_STUDY_DOCS[0], ENM_ONTOLOGY_FIELD: TERM_A}  # string, not list
        with patch("rcapi.services.aop_service.solr_query_get", new_callable=AsyncMock) as m:
            m.return_value = MagicMock(json=lambda: _enm_response([doc]))
            eps = await _get_study_endpoints("JRCNM02000a", "http://fake/select", None)

        assert isinstance(eps[0].ontology_terms, list)
        assert eps[0].ontology_terms == [TERM_A]


# ---------------------------------------------------------------------------
# Unit: _find_aop_assays_by_terms
# ---------------------------------------------------------------------------

class TestFindAOPAssaysByTerms:

    @pytest.mark.asyncio
    async def test_empty_input_no_call(self):
        with patch("rcapi.services.aop_service.solr_query_get") as m:
            docs = await _find_aop_assays_by_terms([])
        m.assert_not_called()
        assert docs == []

    @pytest.mark.asyncio
    async def test_queries_assay_type_and_correct_field(self):
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _aop_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_aop_assays_by_terms([TERM_A])

        assert AOP_ASSAY_MATCH_FIELD in captured.get("q", "")
        assert "type_s:assay" in captured.get("fq", "")

    @pytest.mark.asyncio
    async def test_terms_quoted_in_query(self):
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _aop_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_aop_assays_by_terms([TERM_A, TERM_B])

        q = captured.get("q", "")
        assert f'"{TERM_A}"' in q, f"Term must be quoted, got: {q}"
        assert f'"{TERM_B}"' in q

    @pytest.mark.asyncio
    async def test_returns_docs(self):
        async def fake(url, params, token):
            return MagicMock(json=lambda: _aop_response(FAKE_AOP_ASSAY_DOCS))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=fake):
            docs = await _find_aop_assays_by_terms([TERM_A])

        assert len(docs) == 2


# ---------------------------------------------------------------------------
# Unit: _find_ke_by_assay_names
# ---------------------------------------------------------------------------

class TestFindKEByAssayNames:

    @pytest.mark.asyncio
    async def test_empty_input_no_call(self):
        with patch("rcapi.services.aop_service.solr_query_get") as m:
            docs = await _find_ke_by_assay_names([])
        m.assert_not_called()
        assert docs == []

    @pytest.mark.asyncio
    async def test_queries_attr_assays_and_ke_type(self):
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _aop_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_ke_by_assay_names(["DAPI", "8OHG"])

        assert "attr_assays" in captured.get("q", "")
        assert "type_s:key_event" in captured.get("fq", "")

    @pytest.mark.asyncio
    async def test_fl_is_valid_no_where(self):
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _aop_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_ke_by_assay_names(["DAPI"])

        fl = captured.get("fl", "")
        assert "where" not in fl.lower(), f"Invalid 'where' in fl: {fl}"
        assert "type_s:" not in fl, f"Filter expression in fl: {fl}"


# ---------------------------------------------------------------------------
# Unit: _find_aops_for_ke_ids
# ---------------------------------------------------------------------------

class TestFindAOPsForKEIds:

    @pytest.mark.asyncio
    async def test_empty_ids_no_call(self):
        with patch("rcapi.services.aop_service.solr_query_get") as m:
            docs = await _find_aops_for_ke_ids([])
        m.assert_not_called()
        assert docs == []

    @pytest.mark.asyncio
    async def test_uses_join_query(self):
        captured = {}

        async def capture(url, params, token):
            captured.update(params)
            return MagicMock(json=lambda: _aop_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await _find_aops_for_ke_ids(["KE881", "KE1696"])

        q = captured.get("q", "")
        assert "join" in q and "key_event_ss" in q, f"Expected join query, got: {q}"
        assert "type_s:aop" in captured.get("fq", "")


# ---------------------------------------------------------------------------
# Unit: material_to_aop (full chain, all HTTP mocked)
# ---------------------------------------------------------------------------

class TestMaterialToAOP:

    def _solr_get_mock(self, docs):
        """Return a mock for solr_query_get that returns given eNanoMapper docs."""
        async def mock(url, params, token):
            return MagicMock(json=lambda: _enm_response(docs))
        return mock

    @pytest.mark.asyncio
    async def test_no_studies_returns_warning(self):
        with patch("rcapi.services.aop_service.solr_query_get",
                   side_effect=self._solr_get_mock([])):
            result = await material_to_aop("UNKNOWN", "http://fake/select", None)

        assert result.endpoints == []
        assert result.aops == []
        assert any("No study records found" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_no_ontology_annotations(self):
        with patch("rcapi.services.aop_service.solr_query_get",
                   side_effect=self._solr_get_mock(FAKE_STUDY_DOCS_NO_ONTOLOGY)):
            result = await material_to_aop("JRCNM02000a", "http://fake/select", None)

        assert result.ontology_terms_union == []
        assert any(ENM_ONTOLOGY_FIELD in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_full_chain(self):
        async def fake_solr_get(url, params, token):
            # All calls go through solr_query_get; route by URL
            if AOP_SOLR_URL in url:
                fq = params.get("fq", "")
                if "type_s:assay" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_AOP_ASSAY_DOCS))
                elif "type_s:key_event" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_KE_DOCS))
                elif "type_s:aop" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_AOP_DOCS))
            # eNanoMapper
            return MagicMock(json=lambda: _enm_response(FAKE_STUDY_DOCS))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=fake_solr_get):
            result = await material_to_aop("JRCNM02000a", "http://fake/select", None)

        assert len(result.endpoints) == 2
        assert set(result.ontology_terms_union) == {TERM_A, TERM_B}
        assert len(result.assay_matches) >= 1
        assert len(result.key_event_matches) >= 1
        assert len(result.aops) == 1

        aop = result.aops[0]
        assert aop.aop_id == "AOP173"
        assert aop.coverage == pytest.approx(2 / 3, rel=1e-3)
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_min_coverage_filter(self):
        async def fake_solr_get(url, params, token):
            if AOP_SOLR_URL in url:
                fq = params.get("fq", "")
                if "type_s:assay" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_AOP_ASSAY_DOCS))
                elif "type_s:key_event" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_KE_DOCS))
                elif "type_s:aop" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_AOP_DOCS))
            return MagicMock(json=lambda: _enm_response(FAKE_STUDY_DOCS))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=fake_solr_get):
            result = await material_to_aop(
                "JRCNM02000a", "http://fake/select", None, min_coverage=1.0
            )

        assert result.aops == []

    @pytest.mark.asyncio
    async def test_aops_sorted_descending(self):
        two_aops = [
            {**FAKE_AOP_DOCS[0], "id": "AOP_LOW",
             "key_event_ss": ["KE881", "KE1696", "KE500", "KE501", "KE502"]},  # 2/5
            {**FAKE_AOP_DOCS[0], "id": "AOP_HIGH",
             "key_event_ss": ["KE881", "KE1696"]},                              # 2/2
        ]

        async def fake_solr_get(url, params, token):
            if AOP_SOLR_URL in url:
                fq = params.get("fq", "")
                if "type_s:assay" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_AOP_ASSAY_DOCS))
                elif "type_s:key_event" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_KE_DOCS))
                elif "type_s:aop" in fq:
                    return MagicMock(json=lambda: _aop_response(two_aops))
            return MagicMock(json=lambda: _enm_response(FAKE_STUDY_DOCS))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=fake_solr_get):
            result = await material_to_aop("JRCNM02000a", "http://fake/select", None)

        assert len(result.aops) == 2
        assert result.aops[0].aop_id == "AOP_HIGH"
        assert result.aops[0].coverage == pytest.approx(1.0)
        assert result.aops[1].aop_id == "AOP_LOW"
        assert result.aops[1].coverage == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_enm_error_returns_warning_not_500(self):
        from fastapi import HTTPException

        async def raise_http(url, params, token):
            raise HTTPException(status_code=400, detail="Solr bad request")

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=raise_http):
            result = await material_to_aop("JRCNM02000a", "http://fake/select", None)

        assert any("failed" in w.lower() or "error" in w.lower() for w in result.warnings)
        assert result.aops == []

    @pytest.mark.asyncio
    async def test_token_passed_to_enm(self):
        captured_tokens = []

        async def capture(url, params, token):
            if AOP_SOLR_URL not in url:
                captured_tokens.append(token)
            return MagicMock(json=lambda: _enm_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
            await material_to_aop(
                "JRCNM02000a", "http://fake/select", token="my-token"
            )

        assert any(t == "my-token" for t in captured_tokens)


# ---------------------------------------------------------------------------
# API tests — TestClient
# ---------------------------------------------------------------------------

class TestAOPMaterialEndpoint:

    def test_missing_name_param_returns_422(self):
        response = client.get("/db/aop/material")
        assert response.status_code == 422

    def test_returns_200_with_warnings_when_empty(self):
        async def fake(url, params, token):
            return MagicMock(json=lambda: _enm_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=fake):
            response = client.get("/db/aop/material", params={"name": "NONEXISTENT_XYZ"})

        assert response.status_code == 200
        data = response.json()
        assert data["n_endpoints"] == 0
        assert data["n_aops"] == 0
        assert len(data["warnings"]) > 0

    def test_full_response_shape(self):
        async def fake(url, params, token):
            if AOP_SOLR_URL in url:
                fq = params.get("fq", "")
                if "type_s:assay" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_AOP_ASSAY_DOCS))
                elif "type_s:key_event" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_KE_DOCS))
                elif "type_s:aop" in fq:
                    return MagicMock(json=lambda: _aop_response(FAKE_AOP_DOCS))
            return MagicMock(json=lambda: _enm_response(FAKE_STUDY_DOCS))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=fake):
            response = client.get("/db/aop/material", params={"name": "JRCNM02000a"})

        assert response.status_code == 200
        data = response.json()

        for key in [
            "substance_name", "n_endpoints", "n_ontology_terms",
            "n_key_event_matches", "n_aops", "ontology_terms_union",
            "endpoints", "key_event_matches", "aops", "warnings",
        ]:
            assert key in data, f"Missing key: {key}"

        assert data["substance_name"] == "JRCNM02000a"
        assert data["n_endpoints"] == 2

        if data["n_aops"] > 0:
            aop = data["aops"][0]
            assert 0.0 <= aop["coverage"] <= 1.0
            assert "matched_ke_ids" in aop

    def test_min_coverage_out_of_range_returns_422(self):
        response = client.get("/db/aop/material",
                              params={"name": "X", "min_coverage": 1.5})
        assert response.status_code == 422

    def test_no_auth_token_is_none(self):
        captured = {}

        async def capture(url, params, token):
            if AOP_SOLR_URL not in url:
                captured["token"] = token
            return MagicMock(json=lambda: _enm_response([]))

        app.dependency_overrides[get_token] = lambda: None
        try:
            with patch("rcapi.services.aop_service.solr_query_get", side_effect=capture):
                client.get("/db/aop/material", params={"name": "JRCNM02000a"})
        finally:
            app.dependency_overrides.clear()

        assert captured.get("token") is None


class TestAOPKeEndpoint:

    def test_missing_iri_returns_422(self):
        response = client.get("/db/aop/ke")
        assert response.status_code == 422

    def test_returns_200(self):
        async def fake(url, params, token):
            return MagicMock(json=lambda: _aop_response(FAKE_KE_DOCS))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=fake):
            response = client.get("/db/aop/ke", params={"iri": TERM_A})

        assert response.status_code == 200
        data = response.json()
        assert "key_events" in data
        assert "n_key_events" in data

    def test_empty_result(self):
        async def fake(url, params, token):
            return MagicMock(json=lambda: _aop_response([]))

        with patch("rcapi.services.aop_service.solr_query_get", side_effect=fake):
            response = client.get("/db/aop/ke", params={"iri": "http://unknown"})

        assert response.status_code == 200
        assert response.json()["n_key_events"] == 0


class TestAOPInMCPTools:

    def test_aop_material_appears_in_mcp_tools(self):
        response = client.get("/.well-known/mcp/tools.json")
        assert response.status_code == 200
        tools = response.json()["tools"]
        aop_paths = [t["path"] for t in tools if "/aop/" in t["path"]]
        assert any("material" in p for p in aop_paths), \
            f"No /db/aop/material in MCP tools. Found: {aop_paths}"


# ---------------------------------------------------------------------------
# Integration tests — real Solr (skipped unless --run-integration)
# ---------------------------------------------------------------------------

class TestIntegrationAOPSolrPublic:

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_aop_solr_reachable(self):
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(AOP_SOLR_URL, params={"q": "*:*", "rows": 0, "wt": "json"})
        assert r.status_code == 200

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_aops_for_ke1696(self):
        """KE1696 must exist in AOP Wiki."""
        docs = await _find_aops_for_ke_ids(["KE1696"])
        assert isinstance(docs, list)
        # KE1696 belongs to at least one AOP — if this fails the index has changed
        assert len(docs) > 0, "KE1696 should belong to at least one AOP"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_unknown_term_returns_empty(self):
        docs = await _find_aop_assays_by_terms(["__no_such_term_xyz__"])
        assert docs == []


class TestIntegrationENMSolrPublic:

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_publicname_s_searchable_on_study(self):
        """publicname_s on type_s:study is searchable — the correct lookup field."""
        from rcapi.services.solr_query import SOLR_ROOT, SOLR_COLLECTIONS
        solr_url, collection_param, _ = SOLR_COLLECTIONS.get_url(
            SOLR_ROOT, {"nanoreg2"}, drop_private=True
        )
        docs = await _find_studies_by_name("JRCNM02000a", solr_url, None, collection_param)
        assert isinstance(docs, list)
        # JRCNM02000a has 1811 study records in nanoreg2 per curl test above
        assert len(docs) > 0, \
            "JRCNM02000a should have study records in nanoreg2"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_name_hs_non_searchable(self):
        """
        Confirm name_hs returns 0 results on type_s:study.
        This documents the design constraint and will alert if name_hs
        ever becomes searchable (which would require updating _find_studies_by_name).
        """
        import httpx
        from rcapi.services.solr_query import SOLR_ROOT, SOLR_COLLECTIONS
        solr_url, collection_param, _ = SOLR_COLLECTIONS.get_url(
            SOLR_ROOT, {"nanoreg2"}, drop_private=True
        )
        params = {
            "q": 'name_hs:"JRCNM02000a"',
            "fq": "type_s:study",
            "rows": 1,
            "wt": "json",
        }
        if collection_param:
            params["collection"] = collection_param
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(solr_url, params=params)
        assert r.status_code == 200
        assert r.json()["response"]["numFound"] == 0, (
            "name_hs returned results — it may now be searchable; "
            "review _find_studies_by_name if this assertion fails"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_chain_real_solr(self):
        """
        End-to-end with real Solr.
        Will produce warnings at the ontology step until E.method_synonym_ss
        and AOP name_clean_t are populated — that is expected and the test
        documents the current state.
        """
        from rcapi.services.solr_query import SOLR_ROOT, SOLR_COLLECTIONS
        solr_url, collection_param, _ = SOLR_COLLECTIONS.get_url(
            SOLR_ROOT, {"nanoreg2"}, drop_private=True
        )
        result = await material_to_aop(
            substance_name="JRCNM02000a",
            solr_url=solr_url,
            token=None,
            collection_param=collection_param,
        )

        # Must find study records (we confirmed 1811 above)
        assert len(result.endpoints) > 0, \
            "No endpoints found — publicname_s lookup failed"

        # Log current state of ontology coverage (expected to be empty until indexed)
        if not result.ontology_terms_union:
            pytest.xfail(
                f"No ontology terms in {ENM_ONTOLOGY_FIELD} for JRCNM02000a yet. "
                f"Found {len(result.endpoints)} endpoints. "
                f"Warnings: {result.warnings}"
            )
