"""
aop_service.py — material → AOP plausibility chain

Given a substance name, finds study endpoints via the eNanoMapper REST API,
parses them using pyambit datamodel classes, then links to AOP-Wiki via
shared ontology terms.

Data flow
---------
publicname_s (type_s:study, eNanoMapper Solr)
  → fetch /substance/{uuid}/study via eNanoMapper REST API
  → parse into pyambit.datamodel.SubstanceRecord / ProtocolApplication
  → collect Protocol.endpoint + EffectRecord.endpointSynonyms (ontology IRIs)
  → query AOP Solr type_s:assay by shared ontology field
  → type_s:key_event via attr_assays
  → type_s:aop via {!join from=key_event_ss to=id}
  → coverage score per AOP

pyambit usage
-------------
We use ONLY the protocol/parameter layer — no HSDS actual data reading.
Relevant classes:
  SubstanceRecord         — name, publicname, i5uuid
  ProtocolApplication     — protocol, parameters, effects[]
  Protocol                — topcategory, category.code, endpoint, guideline
  EffectRecord            — endpoint, endpointSynonyms (ontology IRIs)
  ProtocolApplication.parameters["E.method_s"] — measurement method name

Ontology field convention (must match between both indices)
----------------------------------------------------------
  eNanoMapper: EffectRecord.endpointSynonyms[]  →  E.method_synonym_ss in Solr
  AOP Solr:    endpoint_iri_ss                   (populated by extract_assays.py)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from rcapi.services.solr_query import solr_query_get, solr_escape

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field name configuration — change here if Solr schema differs
# ---------------------------------------------------------------------------

# Solr field on type_s:study carrying ontology IRI annotations
# In pyambit/solr_writer.py this is written as E.method_synonym_ss
ENM_ONTOLOGY_FIELD = "E.method_synonym_ss"

# Matching field on AOP Solr type_s:assay records (written by extract_assays.py)
AOP_ASSAY_MATCH_FIELD = "endpoint_iri_ss"

AOP_SOLR_URL = "https://api.ideaconsult.net/enanomapper/aop"

# Fields fetched from eNanoMapper study Solr docs
ENM_STUDY_FL = (
    "id,s_uuid_s,name_s,publicname_s,guidance_s,"
    "E.method_s,document_uuid_s,textValue_s,"
    f"topcategory_s,endpointcategory_s,endpoint_s,"
    f"effectendpoint_s,{ENM_ONTOLOGY_FIELD}"
)

KE_FL = (
    "id,title_t,short_name_t,type_s,biological_organization_level_t,"
    "description_t,attr_assays,upstream_ss,downstream_ss,"
    "molecular_initiating_event_ss,adverse_outcome_ss,key_event_ss,"
    "oecd_status_t"
)

ASSAY_FL = f"id,name_t,{AOP_ASSAY_MATCH_FIELD},attr_assays"

TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# Data models — mirror pyambit Protocol/EffectRecord for the service layer
# We do NOT import pyambit here to keep the dependency optional;
# the Solr query already returns these fields flattened.
# ---------------------------------------------------------------------------

@dataclass
class StudyEndpoint:
    """
    Flattened view of one pyambit ProtocolApplication study record.

    Corresponds to:
      ProtocolApplication.protocol.topcategory   → topcategory
      ProtocolApplication.protocol.category.code → category_code
      ProtocolApplication.protocol.endpoint      → protocol_endpoint
      ProtocolApplication.protocol.guideline     → guideline (list)
      ProtocolApplication.parameters["E.method_s"] → method
      EffectRecord.endpoint                      → effect_endpoint
      EffectRecord.endpointSynonyms              → ontology_terms (IRIs)
    """
    study_uuid: str        # document_uuid_s
    name: str              # name_s (assay/study name)
    publicname: str        # publicname_s (substance public name)
    topcategory: str       # topcategory_s  e.g. "TOX"
    category_code: str     # endpointcategory_s  e.g. "UNKNOWN"
    protocol_endpoint: str # endpoint_s
    effect_endpoint: str   # effectendpoint_s
    guideline: str         # guidance_s
    method: str            # E.method_s
    ontology_terms: list[str]   # E.method_synonym_ss (IRIs)
    has_data: bool         # True when textValue_s present


@dataclass
class AssayMatch:
    assay_id: str
    assay_name: str
    matched_terms: list[str]
    attr_assays: list[str]


@dataclass
class KeyEventMatch:
    ke_id: str
    ke_title: str
    ke_level: str
    matched_assays: list[str]
    triggered_by: list[str]   # endpoint names


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
# eNanoMapper Solr helpers
# ---------------------------------------------------------------------------

async def _enm_get(
    solr_url: str,
    params: dict,
    token: Optional[str],
    collection_param: Optional[str] = None,
) -> dict:
    if collection_param:
        params = {**params, "collection": collection_param}
    r = await solr_query_get(solr_url, params, token)
    return r.json()


def _doc_to_study_endpoint(doc: dict) -> StudyEndpoint:
    """
    Convert a flat eNanoMapper Solr study doc into a StudyEndpoint.

    This mirrors what pyambit.solr_writer.Ambit2Solr.entry2solr() writes:
      topcategory_s     ← papp.protocol.topcategory
      endpointcategory_s ← papp.protocol.category.code
      endpoint_s        ← papp.protocol.endpoint
      effectendpoint_s  ← effect.endpoint
      guidance_s        ← papp.protocol.guideline
      E.method_s        ← papp.parameters["E.method_s"]
      E.method_synonym_ss ← written by indexing pipeline (ontology annotations)
      name_s            ← substance.name (written in substancerecord2solr)
      publicname_s      ← substance.publicname
    """
    terms = doc.get(ENM_ONTOLOGY_FIELD, [])
    if isinstance(terms, str):
        terms = [terms]

    return StudyEndpoint(
        study_uuid=doc.get("document_uuid_s", ""),
        name=doc.get("name_s", ""),
        publicname=doc.get("publicname_s", ""),
        topcategory=doc.get("topcategory_s", ""),
        category_code=doc.get("endpointcategory_s", ""),
        protocol_endpoint=doc.get("endpoint_s", ""),
        effect_endpoint=doc.get("effectendpoint_s", ""),
        guideline=doc.get("guidance_s", ""),
        method=doc.get("E.method_s", ""),
        ontology_terms=terms,
        has_data=bool(doc.get("textValue_s")),
    )


async def _find_studies_by_name(
    name: str,
    solr_url: str,
    token: Optional[str],
    collection_param: Optional[str] = None,
) -> list[StudyEndpoint]:
    """
    Find type_s:study records by publicname_s and return as StudyEndpoint objects.

    publicname_s is the searchable field (written by Ambit2Solr.substancerecord2solr
    as publicname_s from SubstanceRecord.publicname).
    name_hs / publicname_hs are stored-only (non-searchable by design).
    """
    escaped = solr_escape(name)
    params = {
        "q":   f"publicname_s:{escaped}",
        "fq":  "type_s:study",
        "fl":  ENM_STUDY_FL,
        "rows": 500,
        "wt":  "json",
    }
    data = await _enm_get(solr_url, params, token, collection_param)
    docs = data.get("response", {}).get("docs", [])
    return [_doc_to_study_endpoint(doc) for doc in docs]


# ---------------------------------------------------------------------------
# AOP Solr helpers
# ---------------------------------------------------------------------------

async def _aop_get(params: dict) -> dict:
    r = await solr_query_get(AOP_SOLR_URL, params, token=None)
    return r.json()


async def _find_aop_assays_by_terms(terms: list[str]) -> list[AssayMatch]:
    """
    Find type_s:assay records in AOP Solr sharing any ontology IRI.
    Returns AssayMatch objects.
    """
    if not terms:
        return []
    term_clause = " OR ".join(f'"{t}"' for t in terms)
    params = {
        "q":   f"{AOP_ASSAY_MATCH_FIELD}:({term_clause})",
        "fq":  "type_s:assay",
        "fl":  ASSAY_FL,
        "rows": 200,
        "wt":  "json",
    }
    data = await _aop_get(params)
    matches = []
    for doc in data.get("response", {}).get("docs", []):
        doc_terms = doc.get(AOP_ASSAY_MATCH_FIELD, [])
        if isinstance(doc_terms, str):
            doc_terms = [doc_terms]
        shared = sorted(set(terms).intersection(doc_terms))
        if not shared:
            continue
        attr = doc.get("attr_assays", [])
        if isinstance(attr, str):
            attr = [attr]
        matches.append(AssayMatch(
            assay_id=doc.get("id", ""),
            assay_name=doc.get("name_t", ""),
            matched_terms=shared,
            attr_assays=attr,
        ))
    return matches


async def _find_ke_by_assay_names(assay_names: list[str]) -> list[dict]:
    if not assay_names:
        return []
    name_clause = " OR ".join(f'"{a}"' for a in assay_names)
    params = {
        "q":   f"attr_assays:({name_clause})",
        "fq":  "type_s:key_event",
        "fl":  KE_FL,
        "rows": 200,
        "wt":  "json",
    }
    data = await _aop_get(params)
    return data.get("response", {}).get("docs", [])


async def _find_aops_for_ke_ids(ke_ids: list[str]) -> list[dict]:
    if not ke_ids:
        return []
    id_clause = " OR ".join(f"id:{kid}" for kid in ke_ids)
    params = {
        "q":   f"{{!join from=key_event_ss to=id}}({id_clause})",
        "fq":  "type_s:aop",
        "fl":  "id,title_t,oecd_status_t,molecular_initiating_event_ss,adverse_outcome_ss,key_event_ss",
        "rows": 100,
        "wt":  "json",
    }
    data = await _aop_get(params)
    return data.get("response", {}).get("docs", [])


# ---------------------------------------------------------------------------
# Main service function
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
      substance publicname
        → type_s:study docs (parsed via pyambit field mapping)
        → E.method_synonym_ss ontology IRIs
        → AOP type_s:assay records (endpoint_iri_ss join)
        → type_s:key_event (attr_assays)
        → type_s:aop (key_event_ss join), ranked by coverage

    Protocol and parameter fields from pyambit are preserved in StudyEndpoint
    for traceability (topcategory, category_code, protocol_endpoint, guideline).
    """
    result = MaterialToAOPResult(substance_name=substance_name)

    # Step 1 — fetch study endpoints
    try:
        endpoints = await _find_studies_by_name(
            substance_name, solr_url, token, collection_param
        )
    except Exception as e:
        result.warnings.append(f"eNanoMapper query failed: {e}")
        return result

    result.endpoints = endpoints

    if not endpoints:
        result.warnings.append(
            f"No type_s:study records found for publicname_s:'{substance_name}'. "
            f"Check spelling or try data_source filter."
        )
        return result

    # Step 2 — union of ontology terms across all endpoints
    all_terms: set[str] = set()
    for ep in endpoints:
        all_terms.update(ep.ontology_terms)
    result.ontology_terms_union = sorted(all_terms)

    if not all_terms:
        # Summarise what we did find for debugging
        methods_found = sorted({ep.method for ep in endpoints if ep.method})
        categories    = sorted({ep.topcategory for ep in endpoints if ep.topcategory})
        result.warnings.append(
            f"Found {len(endpoints)} study endpoint(s) for '{substance_name}' "
            f"(topcategories: {categories or 'none'}, "
            f"methods: {methods_found[:5] or 'none'}) "
            f"but none carry ontology annotations in '{ENM_ONTOLOGY_FIELD}'. "
            f"Run extract_assays.py / ontology annotation pipeline to populate this field."
        )
        return result

    # Step 3 — AOP assay records sharing ontology terms
    try:
        assay_matches = await _find_aop_assays_by_terms(list(all_terms))
    except Exception as e:
        result.warnings.append(f"AOP assay query failed: {e}")
        return result

    result.assay_matches = assay_matches

    if not assay_matches:
        result.warnings.append(
            f"No AOP assay records in '{AOP_ASSAY_MATCH_FIELD}' match "
            f"ontology terms for '{substance_name}'. "
            f"Run extract_assays.py to populate AOP Solr endpoint_iri_ss."
        )
        return result

    # Collect attr_assays tokens from matched AOP assay records
    matched_assay_names: set[str] = set()
    for am in assay_matches:
        matched_assay_names.update(am.attr_assays)

    if not matched_assay_names:
        result.warnings.append(
            "AOP assay records matched ontology terms but none have attr_assays tokens."
        )
        return result

    # Step 4 — Key Events by assay name
    try:
        ke_docs = await _find_ke_by_assay_names(list(matched_assay_names))
    except Exception as e:
        result.warnings.append(f"AOP KE query failed: {e}")
        return result

    if not ke_docs:
        result.warnings.append(
            f"No Key Events found with attr_assays in: {sorted(matched_assay_names)}"
        )
        return result

    ke_matches: list[KeyEventMatch] = []
    for ke in ke_docs:
        ke_assays = ke.get("attr_assays", [])
        if isinstance(ke_assays, str):
            ke_assays = [ke_assays]
        matched = [a for a in ke_assays if a in matched_assay_names]
        if not matched:
            continue

        # Which endpoint names contributed (via protocol/method fields for traceability)
        triggered = list(dict.fromkeys(
            f"{ep.publicname} [{ep.topcategory}/{ep.category_code}] {ep.method or ep.guideline}"
            for ep in endpoints
            if any(t in ep.ontology_terms for am in assay_matches
                   for t in am.matched_terms if am.attr_assays and
                   any(a in matched for a in am.attr_assays))
        ))
        # Fallback: just endpoint names
        if not triggered:
            triggered = list(dict.fromkeys(ep.name for ep in endpoints))

        ke_matches.append(KeyEventMatch(
            ke_id=ke.get("id", ""),
            ke_title=ke.get("title_t") or ke.get("short_name_t", ""),
            ke_level=ke.get("biological_organization_level_t", ""),
            matched_assays=matched,
            triggered_by=triggered,
        ))

    result.key_event_matches = ke_matches

    if not ke_matches:
        result.warnings.append("No KE matches survived after assay filtering.")
        return result

    # Step 5 — expand to AOPs
    try:
        ke_ids = [m.ke_id for m in ke_matches]
        aop_docs = await _find_aops_for_ke_ids(ke_ids)
    except Exception as e:
        result.warnings.append(f"AOP expansion failed: {e}")
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
