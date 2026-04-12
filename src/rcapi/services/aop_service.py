"""
aop_service.py — material → AOP plausibility chain

Given a substance name in the eNanoMapper Solr index, finds:
  1. All study endpoints measured on that substance  (type_s:study, publicname_s match)
  2. Key Events in AOP-Wiki that share ontology terms with those endpoints
  3. AOPs that contain those Key Events, with coverage scoring

Ontology join
-------------
Both Solr indices carry ontology term annotations:
  - eNanoMapper study documents: E.method_synonym_ss
  - AOP Solr assay documents:    name_clean_t  (type_s:assay)

The join is two-hop:
  study endpoint ontology terms
    → AOP assay records (type_s:assay, name_clean_t)
      → KEs that reference those assays (attr_assays)
        → AOPs containing those KEs

Substance lookup
----------------
publicname_s on type_s:study is searchable and carries the substance public name.
name_hs is stored-only (non-searchable by design, used for Solr joins).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional
import traceback

from rcapi.services.solr_query import solr_query_get, solr_escape

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field name configuration
# ---------------------------------------------------------------------------

# Ontology/synonym field in eNanoMapper type_s:study records
ENM_ONTOLOGY_FIELD = "E.method_synonym_ss"

# Matching field in AOP Solr type_s:assay records
AOP_ASSAY_MATCH_FIELD = "name_clean_t"

# AOP Solr — public, no auth
AOP_SOLR_URL = "https://api.ideaconsult.net/enanomapper/aop"

# Fields to retrieve from AOP KE records
KE_FL = (
    "id,title_t,short_name_t,type_s,biological_organization_level_t,"
    "description_t,attr_assays,upstream_ss,downstream_ss,"
    "molecular_initiating_event_ss,adverse_outcome_ss,key_event_ss,"
    "oecd_status_t"
)

# Fields to retrieve from AOP assay records
ASSAY_FL = f"id,name_t,{AOP_ASSAY_MATCH_FIELD},attr_assays"

TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class StudyEndpoint:
    study_uuid: str
    name: str              # name_s
    publicname: str        # publicname_s — the substance name
    guidance: str          # guidance_s
    method: str            # E.method_s
    ontology_terms: list[str]   # values from ENM_ONTOLOGY_FIELD
    has_data: bool         # True when textValue_s present (HSDS path exists)


@dataclass
class AssayMatch:
    assay_id: str
    assay_name: str
    matched_terms: list[str]   # terms shared between endpoint and AOP assay


@dataclass
class KeyEventMatch:
    ke_id: str
    ke_title: str
    ke_level: str
    matched_assays: list[str]  # attr_assays values that triggered this KE
    triggered_by: list[str]    # endpoint names


@dataclass
class AOPResult:
    aop_id: str
    aop_title: str
    oecd_status: str
    mie_ids: list[str]
    ao_ids: list[str]
    ke_ids: list[str]
    matched_ke_ids: list[str]
    coverage: float


@dataclass
class MaterialToAOPResult:
    substance_name: str
    endpoints: list[StudyEndpoint] = field(default_factory=list)
    ontology_terms_union: list[str] = field(default_factory=list)
    assay_matches: list[AssayMatch] = field(default_factory=list)
    key_event_matches: list[KeyEventMatch] = field(default_factory=list)
    aops: list[AOPResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# eNanoMapper Solr
# ---------------------------------------------------------------------------

async def _enm_get(
    solr_url: str,
    params: dict,
    token: Optional[str],
    collection_param: Optional[str] = None,
) -> dict:
    """GET from eNanoMapper Solr. Delegates to existing solr_query_get."""
    if collection_param:
        params = {**params, "collection": collection_param}
    r = await solr_query_get(solr_url, params, token)
    return r.json()


async def _find_studies_by_name(
    name: str,
    solr_url: str,
    token: Optional[str],
    collection_param: Optional[str] = None,
) -> list[dict]:
    """
    Find type_s:study records by publicname_s.
    Returns all matching docs — may span multiple investigations/projects.
    """
    escaped = solr_escape(name)
    params = {
        "q": f"publicname_s:{escaped}",
        "fq": "type_s:study",
        "fl": f"id,s_uuid_s,name_s,publicname_s,guidance_s,"
              f"document_uuid_s,textValue_s,E.method_s,{ENM_ONTOLOGY_FIELD}",
        "rows": 500,
        "wt": "json",
    }
    data = await _enm_get(solr_url, params, token, collection_param)
    return data.get("response", {}).get("docs", [])


async def _get_study_endpoints(
    substance_name: str,
    solr_url: str,
    token: Optional[str],
    collection_param: Optional[str] = None,
) -> list[StudyEndpoint]:
    docs = await _find_studies_by_name(substance_name, solr_url, token, collection_param)
    endpoints = []
    for doc in docs:
        terms = doc.get(ENM_ONTOLOGY_FIELD, [])
        if isinstance(terms, str):
            terms = [terms]
        endpoints.append(StudyEndpoint(
            study_uuid=doc.get("document_uuid_s", ""),
            name=doc.get("name_s", ""),
            publicname=doc.get("publicname_s", ""),
            guidance=doc.get("guidance_s", ""),
            method=doc.get("E.method_s", ""),
            ontology_terms=terms,
            has_data=bool(doc.get("textValue_s")),
        ))
    return endpoints


# ---------------------------------------------------------------------------
# AOP Solr
# ---------------------------------------------------------------------------

async def _aop_get(params: dict) -> dict:
    r = await solr_query_get(AOP_SOLR_URL, params, token=None)
    return r.json()


async def _find_aop_assays_by_terms(terms: list[str]) -> list[dict]:
    """
    Find type_s:assay records in AOP Solr whose AOP_ASSAY_MATCH_FIELD
    contains any of the given terms.
    """
    if not terms:
        return []
    term_clause = " OR ".join(f'"{t}"' for t in terms)
    params = {
        "q": f"{AOP_ASSAY_MATCH_FIELD}:({term_clause})",
        "fq": "type_s:assay",
        "fl": ASSAY_FL,
        "rows": 200,
        "wt": "json",
    }
    data = await _aop_get(params)
    return data.get("response", {}).get("docs", [])


async def _find_ke_by_assay_names(assay_names: list[str]) -> list[dict]:
    """
    Find type_s:key_event records whose attr_assays field contains
    any of the given assay name tokens.
    """
    if not assay_names:
        return []
    name_clause = " OR ".join(f'"{a}"' for a in assay_names)
    params = {
        "q": f"attr_assays:({name_clause})",
        "fq": "type_s:key_event",
        "fl": KE_FL,
        "rows": 200,
        "wt": "json",
    }
    data = await _aop_get(params)
    return data.get("response", {}).get("docs", [])


async def _find_aops_for_ke_ids(ke_ids: list[str]) -> list[dict]:
    if not ke_ids:
        return []
    id_clause = " OR ".join(f"id:{kid}" for kid in ke_ids)
    params = {
        "q": f"{{!join from=key_event_ss to=id}}({id_clause})",
        "fq": "type_s:aop",
        "fl": "id,title_t,oecd_status_t,molecular_initiating_event_ss,"
              "adverse_outcome_ss,key_event_ss",
        "rows": 100,
        "wt": "json",
    }
    data = await _aop_get(params)
    return data.get("response", {}).get("docs", [])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def material_to_aop(
    substance_name: str,
    solr_url: str,
    token: Optional[str],
    collection_param: Optional[str] = None,
    min_coverage: float = 0.0,
) -> MaterialToAOPResult:
    """
    Full chain:
      substance name
        → study endpoints (publicname_s on type_s:study)
        → ontology terms (E.method_synonym_ss)
        → AOP assay records (name_clean_t on type_s:assay)
        → Key Events (attr_assays)
        → AOPs (key_event_ss join), ranked by coverage
    """
    result = MaterialToAOPResult(substance_name=substance_name)

    # Step 1 — study endpoints
    try:
        endpoints = await _get_study_endpoints(substance_name, solr_url, token, collection_param)
    except Exception as e:
        result.warnings.append(f"eNanoMapper query failed: {e}")
        return result

    result.endpoints = endpoints

    if not endpoints:
        result.warnings.append(
            f"No study records found for '{substance_name}' in accessible collections."
        )
        return result

    # Step 2 — ontology term union
    all_terms: set[str] = set()
    for ep in endpoints:
        all_terms.update(ep.ontology_terms)
    result.ontology_terms_union = sorted(all_terms)

    if not all_terms:
        result.warnings.append(
            f"Found {len(endpoints)} study endpoint(s) but none carry "
            f"ontology annotations in '{ENM_ONTOLOGY_FIELD}'."
        )
        return result

    # Step 3 — match AOP assay records by term
    try:
        aop_assay_docs = await _find_aop_assays_by_terms(list(all_terms))
    except Exception as e:
        result.warnings.append(f"AOP assay query failed: {e}")
        return result

    if not aop_assay_docs:
        result.warnings.append(
            f"No AOP assay records match ontology terms for '{substance_name}'."
        )
        return result

    # Collect matched assay names and record which terms triggered each
    assay_matches: list[AssayMatch] = []
    matched_assay_names: set[str] = set()
    for doc in aop_assay_docs:
        doc_terms = doc.get(AOP_ASSAY_MATCH_FIELD, [])
        if isinstance(doc_terms, str):
            doc_terms = [doc_terms]
        shared = sorted(all_terms.intersection(doc_terms))
        if not shared:
            continue
        attr = doc.get("attr_assays", [])
        if isinstance(attr, str):
            attr = [attr]
        assay_matches.append(AssayMatch(
            assay_id=doc.get("id", ""),
            assay_name=doc.get("name_t", ""),
            matched_terms=shared,
        ))
        matched_assay_names.update(attr)

    result.assay_matches = assay_matches

    if not matched_assay_names:
        result.warnings.append(
            "AOP assay records matched but none had attr_assays tokens."
        )
        return result

    # Step 4 — KEs by assay name
    try:
        ke_docs = await _find_ke_by_assay_names(list(matched_assay_names))
    except Exception as e:
        result.warnings.append(f"AOP KE query failed: {e}")
        return result

    if not ke_docs:
        result.warnings.append(
            f"No Key Events found with assays: {sorted(matched_assay_names)}"
        )
        return result

    ke_matches: list[KeyEventMatch] = []
    for ke in ke_docs:
        ke_assays = ke.get("attr_assays", [])
        if isinstance(ke_assays, str):
            ke_assays = [ke_assays]
        matched_assays = [a for a in ke_assays if a in matched_assay_names]
        if not matched_assays:
            continue

        # Which endpoint names contributed to these assays?
        triggered_by = list(dict.fromkeys(
            ep.name for ep in endpoints
            if any(t in ep.ontology_terms
                   for am in assay_matches
                   if a in am.assay_name or True   # all endpoints contributed via union
                   for t in am.matched_terms)
        ))

        ke_matches.append(KeyEventMatch(
            ke_id=ke.get("id", ""),
            ke_title=ke.get("title_t") or ke.get("short_name_t", ""),
            ke_level=ke.get("biological_organization_level_t", ""),
            matched_assays=matched_assays,
            triggered_by=list(dict.fromkeys(ep.name for ep in endpoints)),
        ))

    result.key_event_matches = ke_matches

    if not ke_matches:
        result.warnings.append("No KE matches survived the assay filter.")
        return result

    # Step 5 — AOPs
    try:
        ke_ids = [m.ke_id for m in ke_matches]
        aop_docs = await _find_aops_for_ke_ids(ke_ids)
    except Exception as e:
        result.warnings.append(f"AOP expansion query failed: {e}")
        return result

    matched_ke_set = set(ke_ids)
    aop_results: list[AOPResult] = []
    for aop in aop_docs:
        all_ke_in_aop = aop.get("key_event_ss", [])
        matched_in_aop = [k for k in all_ke_in_aop if k in matched_ke_set]
        total = len(all_ke_in_aop)
        coverage = len(matched_in_aop) / total if total > 0 else 0.0
        if coverage < min_coverage:
            continue
        aop_results.append(AOPResult(
            aop_id=aop.get("id", ""),
            aop_title=aop.get("title_t", ""),
            oecd_status=aop.get("oecd_status_t", ""),
            mie_ids=aop.get("molecular_initiating_event_ss", []),
            ao_ids=aop.get("adverse_outcome_ss", []),
            ke_ids=all_ke_in_aop,
            matched_ke_ids=matched_in_aop,
            coverage=round(coverage, 3),
        ))

    aop_results.sort(key=lambda a: a.coverage, reverse=True)
    result.aops = aop_results
    return result
