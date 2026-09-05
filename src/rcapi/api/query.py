from fastapi import APIRouter, Request, HTTPException, Depends, Query, Body
from typing import Optional, Literal, Set, List, Dict, Any
import json
import traceback

from rcapi.services import query_service
from rcapi.services.standard_response import StandardResponse
from rcapi.services.solr_query import (
    SOLR_ROOT, SOLR_VECTOR, SOLR_COLLECTIONS, SOLR_FIELDS, SOLR_SIMILARITY,
    solr_query_get, solr_doc_filter, config, APPLICATION_NAME
)
from rcapi.services.kc import get_token, get_roles_from_token

router = APIRouter()

# --- /query/summary ------------------------------------------------------------------
# The question this endpoint answers is "which files were imported", and only
# __input_file_s -- the file a record was actually imported FROM -- answers it. It is
# therefore the default grouping, unconditionally.
#
# It is deliberately NOT auto-substituted when a collection lacks it. nexus_file_ss is
# the *transformed* .nxs, reference_s is a dataset citation; grouping by either
# produces a plausible-looking table that answers a different question, which is worse
# than an empty one -- the caller cannot tell that "was my spreadsheet imported?" went
# unanswered. A collection with no __input_file_s has an import-pipeline defect, and
# reporting that is the useful output. Callers wanting another axis ask for it
# explicitly via group_by.
SUMMARY_INPUT_FILE_FIELD = "__input_file_s"

# Only the input file. The data provider is what people navigate by -- a partner
# looks for their own organisation first -- but it CANNOT be a grouping level here:
# reference_owner_s lives on the study record while __input_file_s lives on the
# params child, and a Solr nested facet can only group on fields the grouped
# documents carry. Grouping by owner would have reported "no data provider
# recorded" for every row of a collection that records it perfectly well.
#
# It comes back through the join instead, as a value on each row, and the caller
# groups by it for display.
#
# Broken down by category under the file, because one file is often the whole
# import: in GRACIOUS every phys-chem study comes from the same spreadsheet, so a
# row per file collapses the entire collection into one line and says nothing
# about what is in it. topcategory_s and endpointcategory_s are on the params
# child alongside the input file, so they cost no extra join.
SUMMARY_DEFAULT_GROUPS = (
    SUMMARY_INPUT_FILE_FIELD,
    "topcategory_s",
    "endpointcategory_s",
)

# Read through the join, per row: who provided the studies this import produced.
# A list, because an import covering more than one provider is itself worth seeing.
SUMMARY_PROVIDER_FIELD = "reference_owner_s"
SUMMARY_PROVIDER_LIMIT = 5

# Probed per collection and reported alongside the rows, so a caller can say what
# provenance this collection does record, and offer the alternative axes as an
# explicit choice rather than a silent substitution.
SUMMARY_PROVENANCE_FIELDS = ("__input_file_s", "nexus_file_ss", "reference_s")

# Whitelisted aggregations. A caller never supplies a Solr function -- these are the
# only expressions that can reach json.facet, so no caller string is ever interpolated
# into it (see CODE_REVIEW.md 2.1 on Solr escaping).
# hll() everywhere, because it is distinct-by-value and therefore immune to the
# per-effect duplication of both study and params documents. The one sum() is not
# immune, and is only correct because n_effects_d exists solely in the NeXus assay
# index, which writes one study document per assay.
#
# There is deliberately no vector count here. sum(n_vectors_d) was offered as
# "spectra", which is wrong for most corpora -- the embedder keeps a vector per
# dose-response curve just as readily as per spectrum -- and no honest name for it
# is one a reader of this report would recognise. A number nobody can interpret is
# not worth a column.
SUMMARY_METRICS = {
    "studies": "hll(document_uuid_s)",
    "materials": "hll(publicname_s)",
    "methods": "hll(E.method_s)",
    "endpoints": "hll(effectendpoint_s)",
    "investigations": "hll(investigation_title_s)",
    "effects": "sum(n_effects_d)",
}
DEFAULT_SUMMARY_METRICS = ("studies", "materials", "methods", "endpoints")

# One representative document per bucket, so a row has something to open. These are
# the same three fields get_query_fields hands the frontend for a study hit: the
# viewers registry dispatches on textValue_s (".nxs#" -> the NeXus viewers, anything
# else -> the AMBIT study viewer), and needs both uuids to load it.
#
# They MUST be nested inside each document's own bucket, not sit beside it as
# independent top-1 facets: a row covers many studies, so separate facets each pick
# their own winner and the row ends up describing several different documents -- a
# studyId from one and a substanceId from another, which opens the wrong record or
# nothing at all. Observed on a real collection before this was nested.
#
# A LIST rather than one representative: picking one member of a group of four and
# labelling it "1 of 4" leaves the reader unable to reach the other three, and
# unable to tell which one they got. The caller offers the list and lets them
# choose. `sort: index` keeps the order stable between requests.
SUMMARY_REPRESENTATIVE_ID = "document_uuid_s"
SUMMARY_REPRESENTATIVE_FIELDS = {
    "substance_uuid": "s_uuid_s",
    "value": "textValue_s",
    # What the study actually is, so a chooser can show "PA6.6 <1um -- Cytokine
    # release" instead of a uuid. Without these the list is unusable: nobody can
    # pick between four identifiers.
    "material": "publicname_s",
    "method": "E.method_s",
}
# Enough to choose from without turning one response into a document dump. A row
# with more than this reports `entries` so the caller can say how many are listed.
SUMMARY_DOCUMENTS_LIMIT = 25

# Values, not just a count: the "one file, several investigations" and "title reused
# across files" checks need the titles themselves, and re-querying per row would be
# one request per file.
SUMMARY_INVESTIGATION_LIMIT = 10

# Likewise the method names. hll(E.method_s) says an import produced 3 methods,
# which does not let anyone judge whether the right ones arrived -- "Raman
# spectroscopy, ATR-FTIR spectroscopy" does. Same facet, so no extra request.
SUMMARY_METHOD_LIMIT = 10


def _grouping_doc_types(carriers: List[str]) -> List[str]:
    """Which document type to group over, given the types carrying the field.

    A provenance field can sit on more than one type at once: the NeXus index
    writes protocol-application parameters onto the type_s:params child AND copies
    them onto the type_s:study record. Grouping over both counts each protocol
    application twice, so exactly one type is chosen.

    params wins when present, because in an AMBIT-indexed collection it is the
    only place the provenance field exists at all -- and Solr can only group on a
    field the grouped documents carry.

    It is NOT the case that params is one document per protocol application: the
    export duplicates the params child per effect, exactly as it duplicates the
    study document per effect. So no raw document count from either side is a
    study count. Everything the report shows is hll(document_uuid_s) -- one
    document_uuid_s is one protocol application -- which is immune to both
    duplications. See _summary_facet.
    """
    present = [t for t in carriers if t]
    if not present:
        return []
    if "params" in present:
        return ["params"]
    record_types = set(config.SOLR_DOCS or ["study"])
    preferred = [t for t in present if t in record_types]
    return preferred or present[:1]


def _summary_facet(group_fields: List[str], metrics: List[str]) -> dict:
    """Nested json.facet for `group_fields`, innermost carrying the measures.

    `missing: True` is deliberate and load-bearing: the bucket of documents with no
    value for the grouping field is exactly the "no provenance recorded" finding the
    report exists to surface. Dropping it would hide the very defect being looked for.

    The grouping runs over the documents that carry the provenance field -- usually
    the type_s:params child, one per protocol application (see
    _grouping_doc_types). The measures then have to reach the study documents,
    which is what the `detail` join does: document_uuid_s is the protocol-application
    uuid both carry, so a bucket's params documents reach exactly their own studies.

    Without the join, grouping params documents would report zero materials and
    zero endpoints for every import, since those fields exist only on the study
    record. Grouping the study documents instead would avoid the join but count
    each protocol application once per effect, because the AMBIT index duplicates
    the study document per effect.
    """
    leaf = {}
    # `studies` is forced in, not merely offered: it is hll(document_uuid_s), the
    # only count in this response that means anything. Every raw document count
    # here is inflated -- the AMBIT export writes one study document per effect
    # AND duplicates the params child per effect -- so a caller that omitted this
    # metric would be left with nothing but effect-level numbers.
    detail = {name: SUMMARY_METRICS[name] for name in metrics}
    detail["studies"] = SUMMARY_METRICS["studies"]
    detail["investigation"] = {
        "type": "terms",
        "field": "investigation_title_s",
        "limit": SUMMARY_INVESTIGATION_LIMIT,
    }
    detail["method_names"] = {
        "type": "terms",
        "field": "E.method_s",
        "limit": SUMMARY_METHOD_LIMIT,
    }
    # Who provided the studies this import produced. On the study record, not on
    # the params child, so it can only be read here -- which is why it is a value
    # on the row rather than a grouping level.
    detail["provider"] = {
        "type": "terms",
        "field": SUMMARY_PROVIDER_FIELD,
        "limit": SUMMARY_PROVIDER_LIMIT,
    }
    detail["documents"] = {
        "type": "terms",
        "field": SUMMARY_REPRESENTATIVE_ID,
        "limit": SUMMARY_DOCUMENTS_LIMIT,
        "sort": "index",
        "facet": {
            alias: {"type": "terms", "field": field, "limit": 1}
            for alias, field in SUMMARY_REPRESENTATIVE_FIELDS.items()
        },
    }
    leaf["detail"] = {
        "type": "query",
        "q": "*:*",
        "domain": {
            "join": {"from": "document_uuid_s", "to": "document_uuid_s"},
            "filter": solr_doc_filter(),
        },
        "facet": detail,
    }

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
    # The section total, in the same unit as every row: distinct protocol
    # applications. numFound would be the raw matched-document count, which is
    # effect-level, so a reader comparing it against the rows would find they do
    # not add up and have no way to know why.
    facet["entries"] = SUMMARY_METRICS["studies"]
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
    # RAW document count, and not a study count: the AMBIT export writes a params
    # child per effect rather than once per protocol application (a long-standing
    # duplication), so this over-counts by however many measurements each entry
    # has. Kept for transparency; never present it as "studies". `entries` below
    # is the honest unit.
    row["count"] = bucket.get("count", 0)

    # Everything measured about the studies themselves comes from the joined
    # sub-facet, since the grouped documents are the params children.
    detail = bucket.get("detail", {})
    for name in metrics:
        row[name] = detail.get(name)
    row["investigation"] = [
        b.get("val") for b in detail.get("investigation", {}).get("buckets", [])
    ]
    row["provider"] = [
        b.get("val") for b in detail.get("provider", {}).get("buckets", [])
    ]
    row["method_names"] = [
        b.get("val") for b in detail.get("method_names", {}).get("buckets", [])
    ]

    # Every study this row covers, each read from inside its OWN bucket so its
    # uuid and the fields describing it belong together. A list, not one pick:
    # the caller offers them and the reader chooses, instead of being handed an
    # arbitrary member labelled "1 of 4" with no way to reach the other three.
    documents = []
    for chosen in detail.get("documents", {}).get("buckets", []):
        doc = {"uuid": chosen.get("val")}
        for alias in SUMMARY_REPRESENTATIVE_FIELDS:
            values = chosen.get(alias, {}).get("buckets", [])
            doc[alias] = values[0].get("val") if values else None
        documents.append(doc)
    row["documents"] = documents

    # The first, flattened onto the row, so a caller that only wants to open
    # something does not have to reach into the list.
    first = documents[0] if documents else {}
    row["uuid"] = first.get("uuid")
    for alias in SUMMARY_REPRESENTATIVE_FIELDS:
        row[alias] = first.get(alias)

    # The number of protocol applications this import produced -- distinct by
    # document_uuid_s, so neither the params duplication nor the one-study-doc-
    # per-effect shape inflates it. This is what "studies" means in the report,
    # and what the representative document stands for.
    entries = detail.get("studies")
    row["entries"] = entries if isinstance(entries, (int, float)) else None
    row["represents"] = row["entries"] if row["entries"] else row["count"]
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

    # Always the input file unless the caller asked for something else. No
    # substitution: a collection that records no input files is reported as such,
    # because answering a different question with a full-looking table hides the
    # import-pipeline defect instead of showing it.
    groups = requested_groups or list(SUMMARY_DEFAULT_GROUPS)

    # Probe the fields actually being grouped by, not only the fixed provenance
    # list. Without the group fields here they are never located, `carriers` comes
    # out empty, and the grouping silently falls back to the study-only filter --
    # which for an AMBIT collection groups documents that do not carry the input
    # file at all, so every row reports "no input file" while the probe right
    # above it says there are 9974 of them.
    probe_fields = list(
        dict.fromkeys(list(SUMMARY_PROVENANCE_FIELDS) + groups)
    )

    result = []
    for source in sources:
        solr_url = "{}/{}/select".format(SOLR_ROOT.rstrip("/"), source)
        entry: Dict[str, Any] = {"data_source": source}
        try:
            # What provenance does this collection actually record? Answering from the
            # index rather than from configuration is what keeps the report generic:
            # nothing here knows which collection is AMBIT-backed and which is
            # NeXus-backed, and a collection added later needs no change.
            # Probed with the two request forms that are known to work on these
            # collections: a top-level fq of "<field>:*" for the count, and a
            # classic facet.field for the breakdown. An earlier version asked the
            # same question as a JSON facet {"type":"query","q":"<field>:*"} and
            # got 0 back from a collection that answers 15836 to the identical
            # query at top level -- so that form is not usable here, whatever the
            # reason. One small rows=0 request per field.
            #
            # No document-type filter: "does this collection record input files"
            # is a question about the collection, not about its study documents,
            # and the field lives on the type_s:params child.
            provenance = {}
            located = {}
            for field in probe_fields:
                fr = await solr_query_get(
                    solr_url,
                    {
                        "q": "*:*",
                        "rows": 0,
                        "fq": "{}:*".format(field),
                        "facet": "true",
                        "facet.field": "type_s",
                        "facet.mincount": 1,
                    },
                    token,
                )
                fj = fr.json()
                provenance[field] = fj.get("response", {}).get("numFound", 0)
                counts = (
                    fj.get("facet_counts", {})
                    .get("facet_fields", {})
                    .get("type_s", [])
                )
                located[field] = [counts[i] for i in range(0, len(counts), 2)]

            provenance_on = {
                field: located.get(field, []) for field in SUMMARY_PROVENANCE_FIELDS
            }
            entry["provenance"] = {
                field: provenance.get(field, 0)
                for field in SUMMARY_PROVENANCE_FIELDS
            }
            entry["provenance_on"] = provenance_on
            # Every document rcapi can see here, so a view narrower than the one
            # an admin session sees is diagnosable rather than looking like
            # "not recorded".
            total = await solr_query_get(solr_url, {"q": "*:*", "rows": 0}, token)
            entry["documents_total"] = total.json().get("response", {}).get(
                "numFound", 0
            )

            entry["group_by"] = groups
            entry["records_input_files"] = bool(
                provenance.get(SUMMARY_INPUT_FILE_FIELD)
            )

            # Run the grouping over the documents that actually carry the grouping
            # field. It is not always the study record: Ambit2Solr writes
            # protocol-application parameters onto the type_s:params child, and
            # copies them onto the study document only on some index paths. Using
            # the study-only filter everywhere reports "no input files recorded"
            # for a collection that records them perfectly well -- a false negative
            # on the one question this endpoint answers.
            #
            # Metrics that live only on the study record (materials, endpoints)
            # come back empty when the grouping runs over params documents. That is
            # visible -- the column is dropped rather than shown as zeroes -- which
            # is the honest degradation.
            # groups[0], not groups[-1]: the first level is the row identity
            # (the input file) and the one that must exist on the grouped
            # documents. The levels under it only break that row down.
            carriers = _grouping_doc_types(located.get(groups[0], []))
            doc_filter = (
                "type_s:({})".format(" OR ".join('"{}"'.format(t) for t in carriers))
                if carriers
                else solr_doc_filter()
            )
            entry["grouped_over"] = carriers or None

            params = {
                "q": "*:*",
                "rows": 0,
                "fq": doc_filter,
                "json.facet": json.dumps(_summary_facet(groups, selected_metrics)),
            }
            if fq:
                params["fq"] = [params["fq"], fq]
            rs = await solr_query_get(solr_url, params, token)
            body = rs.json()
            facets = body.get("facets", {})
            # Distinct protocol applications -- one document_uuid_s is one
            # protocol application in AMBIT, and that is the unit every row is in.
            entry["entries"] = facets.get("entries", 0)
            # The raw matched-document count, kept only so the duplication is
            # visible rather than hidden. It is effect-level and will exceed
            # `entries`, often by a lot; never show it as a study count.
            entry["documents_matched"] = body.get(
                "response", {}
            ).get("numFound", 0)
            entry["rows"] = _summary_rows(facets, groups, selected_metrics)
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