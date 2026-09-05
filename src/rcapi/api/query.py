from fastapi import APIRouter, Request, HTTPException, Depends, Query, Body
from typing import Optional, Literal, Set, List, Dict, Any
import json
import traceback

from rcapi.services import query_service
from rcapi.services.standard_response import StandardResponse
from rcapi.services.solr_query import (
    SOLR_ROOT, SOLR_VECTOR, SOLR_COLLECTIONS, SOLR_FIELDS, SOLR_SIMILARITY,
    solr_query_get, solr_doc_filter, APPLICATION_NAME
)
from rcapi.services.kc import get_token, get_roles_from_token

router = APIRouter()

# --- /query/summary ------------------------------------------------------------------
# Fields that can identify "one imported thing", best first. __input_file_s is the
# original file a record was imported from -- the only one of the three that answers
# "was my spreadsheet imported?". nexus_file_ss is the *transformed* .nxs, a usable
# stand-in for a NeXus-backed collection that has no input-file provenance yet.
# reference_s (the dataset/investigation) is the last resort for a collection that
# records no file at all.
SUMMARY_GROUP_FIELDS = ("__input_file_s", "nexus_file_ss", "reference_s")

# Whitelisted aggregations. A caller never supplies a Solr function -- these are the
# only expressions that can reach json.facet, so no caller string is ever interpolated
# into it (see CODE_REVIEW.md 2.1 on Solr escaping).
SUMMARY_METRICS = {
    "studies": "hll(document_uuid_s)",
    "materials": "hll(publicname_s)",
    "methods": "hll(E.method_s)",
    "endpoints": "hll(effectendpoint_s)",
    "investigations": "hll(investigation_title_s)",
    "effects": "sum(n_effects_d)",
    "spectra": "sum(n_vectors_d)",
}
DEFAULT_SUMMARY_METRICS = ("studies", "materials", "methods", "endpoints")

# One representative document per bucket, so a row has something to open. These are
# the same three fields get_query_fields hands the frontend for a study hit: the
# viewers registry dispatches on textValue_s (".nxs#" -> the NeXus viewers, anything
# else -> the AMBIT study viewer), and needs both uuids to load it.
SUMMARY_REPRESENTATIVE = {
    "uuid": "document_uuid_s",
    "substance_uuid": "s_uuid_s",
    "value": "textValue_s",
}

# Values, not just a count: the "one file, several investigations" and "title reused
# across files" checks need the titles themselves, and re-querying per row would be
# one request per file.
SUMMARY_INVESTIGATION_LIMIT = 10


def _summary_facet(group_fields: List[str], metrics: List[str]) -> dict:
    """Nested json.facet for `group_fields`, innermost carrying the measures.

    `missing: True` is deliberate and load-bearing: the bucket of documents with no
    value for the grouping field is exactly the "no provenance recorded" finding the
    report exists to surface. Dropping it would hide the very defect being looked for.
    """
    leaf = {name: SUMMARY_METRICS[name] for name in metrics}
    leaf["investigation"] = {
        "type": "terms",
        "field": "investigation_title_s",
        "limit": SUMMARY_INVESTIGATION_LIMIT,
    }
    for alias, field in SUMMARY_REPRESENTATIVE.items():
        leaf[alias] = {"type": "terms", "field": field, "limit": 1}

    facet = leaf
    for field in reversed(group_fields):
        facet = {
            "group": {
                "type": "terms",
                "field": field,
                "limit": -1,
                "mincount": 1,
                "missing": True,
                "facet": facet,
            }
        }
    return facet


def _summary_rows(bucket_holder: dict, group_fields: List[str],
                  metrics: List[str], prefix: Optional[dict] = None) -> List[dict]:
    """Flatten the nested facet response to one row per innermost bucket."""
    group = bucket_holder.get("group")
    if group is None:
        return []
    field = group_fields[0]
    rest = group_fields[1:]
    rows = []

    buckets = list(group.get("buckets", []))
    missing = group.get("missing")
    if missing is not None and missing.get("count", 0) > 0:
        # Surfaced as an explicit null rather than dropped or renamed to a
        # sentinel string, so a caller can tell "no value recorded" apart from
        # a document whose value happens to be the word "missing".
        rows.extend(_bucket_rows({**missing, "val": None}, field, rest, metrics, prefix))
    for bucket in buckets:
        rows.extend(_bucket_rows(bucket, field, rest, metrics, prefix))
    return rows


def _bucket_rows(bucket: dict, field: str, rest: List[str],
                 metrics: List[str], prefix: Optional[dict]) -> List[dict]:
    here = dict(prefix or {})
    here[field] = bucket.get("val")
    if rest:
        return _summary_rows(bucket, rest, metrics, here)

    row = dict(here)
    row["count"] = bucket.get("count", 0)
    for name in metrics:
        row[name] = bucket.get(name)
    row["investigation"] = [
        b.get("val") for b in bucket.get("investigation", {}).get("buckets", [])
    ]
    for alias in SUMMARY_REPRESENTATIVE:
        values = bucket.get(alias, {}).get("buckets", [])
        row[alias] = values[0].get("val") if values else None
    return [row]


@router.api_route(
    "/query",
    operation_id="db_query_universal",
    methods=["GET", "POST"],
    response_model=StandardResponse[List[dict]],
    summary="Search experiments",
    description="Perform a search for study types as in ambit data model using query parameters or filters.",
    openapi_extra={
        "x-mcp-prompt": (
            "Use this tool to search the ambit/enanomapper  database. Provide query terms, "
            "dynamic query fields, and optional parameters. Example for metadata search: "
            "{'query_type': 'metadata', 'q': '*', 'qdynamic': {'name_s': 'polystyrene'}, 'data_source': 'charisma'}. "
            "For vector similarity search: {'query_type': 'knnquery', 'ann': '<base64_vector>'}. "
            "Include pagination with 'page' and 'pagesize'."
        )
    }
)
async def query_universal(
    request: Request,
    # standard GET parameters
    q: Optional[str] = Query(default="*"),
    query_type: Optional[Literal["metadata", "text", "knnquery"]] = "text",
    q_reference: Optional[str] = "*",
    q_provider: Optional[str] = "*",
    q_method: Optional[str] = "*",
    ann: Optional[str] = None,
    page: Optional[int] = 0,
    pagesize: Optional[int] = 10,
    img: Optional[Literal["embedded", "original", "thumbnail"]] = "thumbnail",
    vector_field: Optional[str] = None,
    data_source: Optional[Set[str]] = Query(default=None),
    # flexible JSON input for POST 
    qdynamic: Optional[Dict[str, Any]] = Body(
        default=None,
        example={"name_s": "Anatase"},
        description="Optional dict of field:value dynamic query (keys limited by configuration)"
    ),
    token: Optional[str] = Depends(get_token),
):
    """
    Universal query endpoint for spectra and safety-related data.

    - **GET** supports classic query-string style .
    - **POST** accepts structured JSON for MCP or automated clients.

    Example POST body:
    ```json
    {
      "q": "PP",
      "data_source": "charisma",
      "qdynamic": {"name_s": "Anatase"},
      "page": 0,
      "pagesize": 10
    }
    ```
    """
    try:
        # --- handle POST body (merge JSON with query params) --------------------------
        if request.method == "POST":
            body = await request.json()
            q = body.get("q", q)
            query_type = body.get("query_type", query_type)
            q_reference = body.get("q_reference", q_reference)
            q_provider = body.get("q_provider", q_provider)
            q_method = body.get("q_method", q_method)
            ann = body.get("ann", ann)
            page = body.get("page", page)
            pagesize = body.get("pagesize", pagesize)
            img = body.get("img", img)
            vector_field = body.get("vector_field", vector_field)
            # Allow both str and list for data_source
            ds = body.get("data_source", data_source)
            data_source = {ds} if isinstance(ds, str) else set(ds or [])
            qdynamic = body.get("qdynamic", qdynamic)
        # --- GET: extract filters.* parameters -----------------------------------
        elif request.method == "GET":
            QUOTE_KEYS = {"SMILES_s"} 
            query_dynamic = {
                k[len("qdynamic."):]: (
                    f'"{v}"' if k[len("qdynamic."):] in QUOTE_KEYS else v
                )
                for k, v in request.query_params.items()
                if k.startswith("qdynamic.")
            }
            if query_dynamic:
                qdynamic = query_dynamic

        # --- determine which collections user can access ------------------------------
        solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
            SOLR_ROOT, data_source, drop_private=token is None
        )

        # --- filter sanitization ------------------------------------------------------
        allowed_fields = [
            f.field.removeprefix("qdynamic.") 
            for f in SOLR_FIELDS
        ]
        qdynamic = sanitize_filters(qdynamic, allowed_fields)

        # --- merge filters into Solr query string -------------------------------------
        textQuery = q or "*"
        if qdynamic:
            filter_query = " AND ".join(f"{k}:{v}" for k, v in qdynamic.items())
            textQuery = f"({textQuery}) AND ({filter_query})" if textQuery != "*" else filter_query

        # --- call Solr service --------------------------------------------------------
        stdResponse = await query_service.process(
            request=request,
            solr_url=solr_url,
            q=textQuery,
            query_type=query_type,
            q_reference=q_reference,
            q_provider=q_provider,
            q_method=q_method,
            ann=ann,
            page=page,
            pagesize=pagesize,
            img=img,
            collections=collection_param,
            vector_field=SOLR_VECTOR if vector_field is None else vector_field,
            token=token,
        )
        stdResponse.status = 1 if dropped else 0
        return stdResponse
    except HTTPException as err:
        raise err
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(err))


@router.get(
    "/query/field",
    summary="Get facet values for a query field",
    description="Return all possible values for a given query field",
    openapi_extra={
        "x-mcp-prompt": (
            "Use this resource to get the list of values for a specific field. "
            "Provide the field name (e.g., 'instrument_s') and optional data sources. "
            "Returns read-only metadata with counts for each value."
        )
    },
    response_model=StandardResponse[List[dict]]
)
async def get_field(
    request: Request,
    name: str = "publicname_s",
    data_source: Optional[Set[str]] = Query(default=None),
    token: Optional[str] = Depends(get_token),
):
    solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
        SOLR_ROOT, data_source, drop_private=token is None
    )
    try:
        # we need the original field names
        _name = name.replace("qdynamic.", "")
        _name = query_service.get_predefined(_name)
        params = {"q": "*", "rows": 0, "facet.field": _name, "facet": "true"}
        if collection_param is not None:
            params["collection"] = collection_param
        rs = await solr_query_get(solr_url, params, token)
        # Extract the facet field values
        facet_field_values = rs.json()["facet_counts"]["facet_fields"][_name]
        # Convert to an array of objects with name and count properties
        result = []
        for i in range(0, len(facet_field_values), 2):
            result.append({"value": facet_field_values[i],
                           "count": facet_field_values[i + 1]})
        return StandardResponse(status=1 if dropped else 0, response=result)
    except HTTPException as err:
        raise err
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(err))


@router.get(
    "/query/field/terms",
    summary="Prefix-based term lookup for a query field",
    description=(
        "Autocomplete prefix lookup. For string fields (_s), uses Solr TermsComponent. "
        "For other fields, performs a wildcard prefix query (q=field:prefix*)."
    ),
    response_model=StandardResponse[List[str]],
)
async def get_field_terms(
    request: Request,
    name: str = "publicname_s",
    prefix: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=500),
    data_source: Optional[Set[str]] = Query(default=None),
    token: Optional[str] = Depends(get_token),
):
    """
    Prefix lookup for autocomplete.

    - For *_s fields → uses TermsComponent (fast, exact).
    - For *_t fields → uses q=<field>:<prefix>* query and extracts distinct values.
    """

    solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
        SOLR_ROOT, data_source, drop_private=token is None
    )

    try:
        # Normalize field name
        field = name.replace("qdynamic.", "")
        field = query_service.get_predefined(field)

        # ---------------------------------------------
        # CASE 1: String fields (_s) — facet over values
        # ---------------------------------------------
        # Faceting rather than the TermsComponent, for two reasons:
        #   * `terms` is not a stock /select component -- it has to be registered on the
        #     handler, so it answers on some collections and silently returns nothing on
        #     others (an empty "terms" section reads exactly like "no matches").
        #     facet.* is core /select behaviour everywhere.
        #   * terms.prefix is a left-anchored prefix over the whole indexed string, but
        #     these are string fields holding phrases: typing "FTIR" could never match
        #     "ATR-FTIR spectroscopy", nor "GC" match "Py-GC-MS". facet.contains does
        #     substring matching, which is what a type-ahead is expected to do.
        if field.endswith("_s") or field.endswith("_ss"):
            params = {
                "wt": "json",
                "q": "*",
                "rows": 0,
                "facet": "true",
                "facet.field": field,
                "facet.limit": limit,
                "facet.mincount": 1,
                # Alphabetical, as the TermsComponent listing was (terms.sort=index);
                # a suggestion list is scanned by name, not by popularity.
                "facet.sort": "index",
            }
            if prefix:
                params["facet.contains"] = prefix
                params["facet.contains.ignoreCase"] = "true"
            if collection_param is not None:
                params["collection"] = collection_param

            rs = await solr_query_get(solr_url, params, token)
            j = rs.json()
            counts = j.get("facet_counts", {}).get("facet_fields", {}).get(field, [])

            # facet_fields is a flat [value, count, value, count, ...] list
            terms = [counts[i] for i in range(0, len(counts), 2)]

            return StandardResponse(status=1 if dropped else 0, response=terms)

        # -----------------------------------------------------
        # CASE 2: Text fields (_t) — wildcard prefix query
        # -----------------------------------------------------
        else: # field.endswith("_t"):
            params = {
                "wt": "json",
                "q": f"{field}:{prefix}*" if prefix else "*:*",
                "rows": limit,
                "fl": field,
            }
            if collection_param is not None:
                params["collection"] = collection_param

            rs = await solr_query_get(solr_url, params, token)
            docs = rs.json().get("response", {}).get("docs", [])

            # Collect unique values
            seen = set()
            values = []

            for d in docs:
                v = d.get(field)
                if isinstance(v, list):
                    for x in v:
                        if isinstance(x, str) and x not in seen:
                            seen.add(x)
                            values.append(x)
                elif isinstance(v, str):
                    if v not in seen:
                        seen.add(v)
                        values.append(v)

            return StandardResponse(status=1 if dropped else 0,
                                    response=values[:limit])

    except HTTPException:
        raise
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(err))


@router.get(
    "/query/field/range",
    summary="Facet counts over a numeric range for a query field",
    description=(
        "Returns per-bucket counts for a numeric field using Solr facet.range. "
        "Useful for rendering a histogram or range slider (e.g. concentration_count_i)."
    ),
    response_model=StandardResponse[List[dict]],
)
async def get_field_range(
    request: Request,
    name: str = "concentration_count_i",
    start: float = Query(default=0),
    end: float = Query(default=20),
    gap: float = Query(default=1),
    fq: Optional[str] = Query(default=None),
    data_source: Optional[Set[str]] = Query(default=None),
    token: Optional[str] = Depends(get_token),
):
    solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
        SOLR_ROOT, data_source, drop_private=token is None
    )
    try:
        field = name.replace("qdynamic.", "")
        field = query_service.get_predefined(field)
        params = {
            "q": "*",
            "rows": 0,
            "facet": "true",
            "facet.range": field,
            "f.{}.facet.range.start".format(field): start,
            "f.{}.facet.range.end".format(field): end,
            "f.{}.facet.range.gap".format(field): gap,
            "f.{}.facet.range.other".format(field): "after",
        }
        if fq:
            params["fq"] = fq
        if collection_param is not None:
            params["collection"] = collection_param
        rs = await solr_query_get(solr_url, params, token)
        counts = rs.json()["facet_counts"]["facet_ranges"][field]["counts"]
        result = [{"value": counts[i], "count": counts[i + 1]}
                  for i in range(0, len(counts), 2)]
        # append the "after" bucket (values above end) if non-zero
        after = rs.json()["facet_counts"]["facet_ranges"][field].get("after", 0)
        if after:
            result.append({"value": ">{}".format(end), "count": after})
        return StandardResponse(status=1 if dropped else 0, response=result)
    except HTTPException as err:
        raise err
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(err))


@router.get(
    "/query/summary",
    summary="Group a data source by import provenance, with counts",
    description=(
        "One row per imported file (or whatever provenance field the collection "
        "actually records), with distinct-value counts and a representative document "
        "to open. Answers 'what is in this collection and where did it come from', "
        "which the per-field facet endpoints cannot: they take one field at a time and "
        "cannot say which collection a count came from."
    ),
    openapi_extra={
        "x-mcp-prompt": (
            "Use this tool to inventory what has been imported into a data source. "
            "Returns one entry per data source, each with the provenance field it was "
            "grouped by and one row per distinct value. Example: "
            "{'data_source': 'charisma', 'metrics': ['studies', 'materials']}. "
            "Omit group_by to let the server pick the best available provenance field."
        )
    },
    response_model=StandardResponse[List[dict]],
)
async def get_summary(
    request: Request,
    group_by: Optional[List[str]] = Query(
        default=None,
        description=(
            "Field(s) to group by, at most 3. Omit to let the server pick the best "
            "provenance field this collection actually populates."
        ),
    ),
    metrics: Optional[List[str]] = Query(
        default=None,
        description="Any of: {}".format(", ".join(sorted(SUMMARY_METRICS))),
    ),
    fq: Optional[str] = Query(default=None),
    data_source: Optional[Set[str]] = Query(default=None),
    token: Optional[str] = Depends(get_token),
):
    """One entry per data source, each grouped independently.

    Deliberately one Solr request per collection rather than one joined
    multi-collection query: a merged response cannot be attributed back: hits carry no
    collection marker and get_query_fields does not request the [shard] augmenter, so
    "which of the selected sources does this row belong to" would be unanswerable --
    and that attribution is the whole point of the report. It also means one
    unreachable collection degrades to an error on its own entry instead of failing
    the request.
    """
    # Gate once, for the whole selection: this raises 401/403 for a caller who cannot
    # see the sources they asked for, exactly as every other route does.
    _url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
        SOLR_ROOT, data_source, drop_private=token is None
    )
    sources = (
        collection_param.split(",") if collection_param
        else [SOLR_COLLECTIONS.default]
    )

    if metrics:
        unknown = [m for m in metrics if m not in SUMMARY_METRICS]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail="Unknown metric(s): {}. Available: {}".format(
                    ", ".join(sorted(unknown)), ", ".join(sorted(SUMMARY_METRICS))
                ),
            )
        selected_metrics = list(dict.fromkeys(metrics))
    else:
        selected_metrics = list(DEFAULT_SUMMARY_METRICS)

    requested_groups = None
    if group_by:
        if len(group_by) > 3:
            raise HTTPException(
                status_code=400,
                detail="At most 3 group_by fields, got {}".format(len(group_by)),
            )
        # Same normalization the other field endpoints apply, so a caller can pass
        # either the qdynamic-prefixed name the frontend holds or the raw Solr field.
        requested_groups = [
            query_service.get_predefined(g.replace("qdynamic.", "")) for g in group_by
        ]

    result = []
    for source in sources:
        solr_url = "{}/{}/select".format(SOLR_ROOT.rstrip("/"), source)
        entry: Dict[str, Any] = {"data_source": source}
        try:
            # What provenance does this collection actually record? Answering from the
            # index rather than from configuration is what keeps the report generic:
            # nothing here knows which collection is AMBIT-backed and which is
            # NeXus-backed, and a collection added later needs no change.
            probe_params = {
                # "*:*", not the "*" the older endpoints use -- that is a wildcard on
                # the default field, not "all documents".
                "q": "*:*",
                "rows": 0,
                "fq": solr_doc_filter(),
                "json.facet": json.dumps({
                    field: {"type": "query", "q": "{}:*".format(field)}
                    for field in SUMMARY_GROUP_FIELDS
                }),
            }
            probe = (await solr_query_get(solr_url, probe_params, token)).json()
            provenance = {
                field: probe.get("facets", {}).get(field, {}).get("count", 0)
                for field in SUMMARY_GROUP_FIELDS
            }
            entry["provenance"] = provenance
            entry["numFound"] = probe.get("response", {}).get("numFound", 0)

            groups = requested_groups or [
                next(
                    (f for f in SUMMARY_GROUP_FIELDS if provenance.get(f)),
                    SUMMARY_GROUP_FIELDS[0],
                )
            ]
            entry["group_by"] = groups

            params = {
                "q": "*:*",
                "rows": 0,
                "fq": solr_doc_filter(),
                "json.facet": json.dumps(_summary_facet(groups, selected_metrics)),
            }
            if fq:
                params["fq"] = [params["fq"], fq]
            rs = await solr_query_get(solr_url, params, token)
            entry["rows"] = _summary_rows(
                rs.json().get("facets", {}), groups, selected_metrics
            )
        except HTTPException as err:
            # One collection being unreadable must not lose the others.
            entry["error"] = err.detail
            entry.setdefault("rows", [])
        except Exception as err:  # noqa: BLE001
            print(traceback.format_exc())
            entry["error"] = str(err)
            entry.setdefault("rows", [])
        result.append(entry)

    return StandardResponse(status=1 if dropped else 0, response=result)


# https://github.com/h2020charisma/ramanchada-api/issues/59
@router.get(
    "/query/sources",
    summary="List available data sources",
    description="Return  collections accessible to the user along with field metadata.",
    openapi_extra={
        "x-mcp-prompt": (
            "Use this resource to discover which data sources are available for queries. "
            "Returns a list of collections with names, descriptions, and accessibility. "
            "This is read-only metadata."
        )
    },
)
async def get_sources(
        request: Request,
        token: Optional[str] = Depends(get_token)
        ):
    try:
        if token is not None:
            user_roles = get_roles_from_token(token)
        else:
            user_roles = []
        user_roles.append("public")
        # Filter collections based on user's roles
        accessible_collections = SOLR_COLLECTIONS.for_roles(user_roles)

        return {
            "application_name" : APPLICATION_NAME,
            "default": SOLR_COLLECTIONS.default,
            "data_sources": [
                {"name": c.name,
                 "description": c.description,
                 "public": "public" in c.roles}
                for c in accessible_collections
            ],
            "fields": SOLR_FIELDS,
            "similarity": SOLR_SIMILARITY
        }

    except HTTPException as err:
        raise err
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(err))


# --- helper for safe filter handling -------------------------------------------------
def sanitize_filters(filters: Optional[dict], allowed_fields: list[str]) -> dict:
    """
    Keep only filters that match allowed Solr field names.
    Ignore unknown or malformed filters.
    """
    if not filters:
        return {}
    safe = {}
    for key, value in filters.items():
        if key in allowed_fields and isinstance(value, (str, int, float)):
            safe[key] = value
    return safe