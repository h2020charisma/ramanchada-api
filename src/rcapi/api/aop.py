"""
api/aop.py — FastAPI router for material → AOP plausibility

Endpoints
---------
GET /db/aop/material
    Find AOPs plausibly relevant to a substance via ontology-term matching.

GET /db/aop/ke
    Query AOP Solr Key Events by ontology IRI(s) directly.

These routes follow the same auth / collection-routing pattern as /db/query.
"""

from __future__ import annotations

from typing import Optional, Set, List
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from pydantic import BaseModel
import traceback

from rcapi.services.kc import get_token
from rcapi.services.solr_query import SOLR_ROOT, SOLR_COLLECTIONS
from rcapi.services import aop_service
from rcapi.services.aop_service import (
    MaterialToAOPResult,
    StudyEndpoint,
    KeyEventMatch,
    AOPResult,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models (Pydantic, so FastAPI can serialise dataclasses)
# ---------------------------------------------------------------------------

class StudyEndpointOut(BaseModel):
    study_uuid: str
    name: str
    guidance: str
    ontology_terms: List[str]
    has_data: bool

    @classmethod
    def from_dc(cls, ep: StudyEndpoint) -> "StudyEndpointOut":
        return cls(**ep.__dict__)


class KeyEventMatchOut(BaseModel):
    ke_id: str
    ke_title: str
    ke_level: str
    ke_ontology_terms: List[str]
    matched_terms: List[str]
    triggered_by: List[str]

    @classmethod
    def from_dc(cls, m: KeyEventMatch) -> "KeyEventMatchOut":
        return cls(**m.__dict__)


class AOPResultOut(BaseModel):
    aop_id: str
    aop_title: str
    oecd_status: str
    mie_ids: List[str]
    ao_ids: List[str]
    ke_ids: List[str]
    matched_ke_ids: List[str]
    coverage: float

    @classmethod
    def from_dc(cls, a: AOPResult) -> "AOPResultOut":
        return cls(**a.__dict__)


class MaterialToAOPResponse(BaseModel):
    substance_name: str
    n_endpoints: int
    n_ontology_terms: int
    n_key_event_matches: int
    n_aops: int
    ontology_terms_union: List[str]
    endpoints: List[StudyEndpointOut]
    key_event_matches: List[KeyEventMatchOut]
    aops: List[AOPResultOut]
    warnings: List[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/aop/material",
    response_model=MaterialToAOPResponse,
    summary="Find AOPs related to a substance via ontology term matching",
    description=(
        "Given a nanomaterial or substance name/code, retrieves all measured "
        "study endpoints from eNanoMapper, extracts their ontology term annotations, "
        "matches those to Key Events in AOP-Wiki sharing the same terms, then "
        "expands to containing AOPs with a coverage score (matched KEs / total KEs).\n\n"
        "The ontology join field is configurable in aop_service.py "
        "(ENM_ONTOLOGY_FIELD / AOP_ONTOLOGY_FIELD)."
    ),
    openapi_extra={
        "x-mcp-prompt": (
            "Use this tool to find which Adverse Outcome Pathways are plausibly "
            "relevant to a nanomaterial or substance, based on shared ontology "
            "annotations between measured endpoints and AOP Key Events. "
            "Provide the substance name or code (e.g. 'NM-401', 'NRCWE-006', 'TiO2 17nm'). "
            "Optionally filter by data_source (Solr collection) and min_coverage "
            "(minimum fraction of AOP Key Events that must match, 0.0–1.0). "
            "Returns: matched endpoints, matching Key Events with shared ontology terms, "
            "and AOPs ranked by coverage."
        )
    },
)
async def material_to_aop(
    request: Request,
    name: str = Query(
        ...,
        description="Substance name or code, e.g. 'NM-401', 'NRCWE-006', 'TiO2 17nm'",
    ),
    data_source: Optional[Set[str]] = Query(
        default=None,
        description="Solr collection(s) to search (defaults to configured default)",
    ),
    min_coverage: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum fraction of an AOP's Key Events that must match to include "
            "that AOP in results. 0.0 = any match; 1.0 = all KEs must match."
        ),
    ),
    token: Optional[str] = Depends(get_token),
):
    try:
        solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
            SOLR_ROOT, data_source, drop_private=token is None
        )
        print(solr_url, collection_param)
        result: MaterialToAOPResult = await aop_service.material_to_aop(
            substance_name=name,
            solr_url=solr_url,
            token=token,
            collection_param=collection_param,
            min_coverage=min_coverage,
        )

        return MaterialToAOPResponse(
            substance_name=result.substance_name,
            n_endpoints=len(result.endpoints),
            n_ontology_terms=len(result.ontology_terms_union),
            n_key_event_matches=len(result.key_event_matches),
            n_aops=len(result.aops),
            ontology_terms_union=result.ontology_terms_union,
            endpoints=[StudyEndpointOut.from_dc(e) for e in result.endpoints],
            key_event_matches=[KeyEventMatchOut.from_dc(m) for m in result.key_event_matches],
            aops=[AOPResultOut.from_dc(a) for a in result.aops],
            warnings=result.warnings,
        )

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal error in AOP plausibility service")


@router.get(
    "/aop/ke",
    summary="Query AOP Key Events by ontology IRI",
    description=(
        "Direct lookup: given one or more ontology term IRIs, returns Key Events "
        "in AOP-Wiki that carry those annotations. Useful for building the ontology "
        "bridge independently of a specific substance."
    ),
    openapi_extra={
        "x-mcp-prompt": (
            "Use this tool to find AOP Key Events annotated with specific ontology "
            "term IRIs. Provide one or more IRIs (e.g. from NPO, BAO, or EFO). "
            "Returns matching Key Events with their biological organisation level "
            "and assay annotations."
        )
    },
)
async def ke_by_ontology(
    iri: List[str] = Query(
        ...,
        description="One or more ontology term IRIs to look up in AOP Key Events",
    ),
):
    try:
        ke_docs = await aop_service._find_ke_by_ontology(iri)
        return {
            "query_iris": iri,
            "n_key_events": len(ke_docs),
            "key_events": [
                {
                    "id": doc.get("id"),
                    "title": doc.get("title_t") or doc.get("short_name_t", ""),
                    "biological_level": doc.get("biological_organization_level_t", ""),
                    "attr_assays": doc.get("attr_assays", []),
                    "ontology_terms": doc.get(aop_service.AOP_ONTOLOGY_FIELD, []),
                    "upstream": doc.get("upstream_ss", []),
                    "downstream": doc.get("downstream_ss", []),
                }
                for doc in ke_docs
            ],
        }
    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="AOP KE lookup failed")
