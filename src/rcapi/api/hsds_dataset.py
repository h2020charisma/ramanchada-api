from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional,  List, Union, Set
from pydantic import BaseModel
import h5pyd
from rcapi.services.solr_query import (
    solr_query_get, SOLR_ROOT, SOLR_COLLECTIONS, solr_escape, SOLR_VECTOR
)
from pynanomapper.clients.datamodel_simple import StudyRaman
from rcapi.services.kc import get_token
from rcapi.services.convertor_service import x4search
from rcapi.services.hsds_domain import validate_hsds_file_domain
router = APIRouter()


# Response models to mimic hsds /dataset previously used for .cha file
class Dataset(BaseModel):
    key: str
    uuid: str
    name: str
    shape: List[int]
    size: int
    value: List[List[Union[float, int]]]
    dims: List[str]


class Annotation(BaseModel):
    sample: str
    instrument: str
    investigation: str
    laser_power: str
    native_filename: str
    optical_path: str
    provider: str
    wavelength: str


class ResponseModel(BaseModel):
    subdomains: List[str]
    domain: str
    annotation: List[Annotation]
    datasets: List[Dataset]


@router.get("/dataset")
async def get_dataset(
    domain: str = Query(..., description="The hsds domain to query"),
    values: Optional[bool] = Query(None, description="Whether to include values or not"),
    bucket: str = Query(None, description="The HSDS bucket"),
    data_source: Optional[Set[str]] = Query(default=None),
    token: Optional[str] = Depends(get_token),
):
    if domain.endswith(".chaold"):  # all goes through solr now
        result = {"subdomains": [], "domain": domain, "annotation": [], "datasets": []}
        return read_cha(domain, result, read_values=values, token=token)
    else: # resort to solr index
        escaped_value = solr_escape(domain)
        query = f'textValue_s:"{domain}"'
        fields = "name_s,reference_s,reference_owner_s,document_uuid_s,updated_s, guidance_s, _version_"
        if values:
            # unit_s / x_name_s / x_unit_s label the dense vectors and are
            # written on the same document by the indexer, so they only
            # matter when the values themselves are requested.
            fields = (
                f"{fields},{SOLR_VECTOR},dense_a512,dense_b512,"
                "unit_s,x_name_s,x_unit_s"
            )
        params = {"q": query, "fq": ["type_s:study"], "fl": fields}
        rs = None
        try:
            solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
                SOLR_ROOT, data_source, drop_private=token is None)
            # print("/dataset", data_source, collection_param)
            if collection_param is not None:
                params["collection"] = collection_param
            rs = await solr_query_get(solr_url, params, token)
            return await read_solr_study4dataset(
                domain, rs.json(), values, data_source, token)
        except HTTPException as err:
            raise err
        finally:
            if rs is not None:
                await rs.aclose()


def axis_title(name, unit):
    """Compose an axis title from whatever the indexed document knows --
    "Concentration [ug/mL]", "Concentration", "[%]", or "" when it knows
    neither. Units are passed through exactly as indexed (no LaTeX
    rewriting); the frontend runs them through latexToUnicode, which
    leaves a plain unit alone.
    """
    name = (name or "").strip()
    unit = (unit or "").strip()
    if name and unit:
        return "{} [{}]".format(name, unit)
    if name:
        return name
    if unit:
        return "[{}]".format(unit)
    return ""


async def read_solr_study4dataset(
        domain, response_data, with_values=False,
        data_source: Optional[Set[str]] = Query(default=None),token=None):
    # print(response_data)
    _domain = domain.split('#', 1)[0] if '#' in domain else domain

    result = {"subdomains": [], "domain": _domain, "annotation": [], "datasets": []}
    for doc in response_data["response"]["docs"]:
        annotation = {
            "sample": doc.get("name_s", ""),
            "provider": doc.get("reference_owner_s", ""),
            "investigation": doc.get("reference_s", "")
        }
        result["annotation"].append(annotation)

        dataset_name = domain.split('#', 1)[1] if '#' in domain else "indexed"
        dataset = {"key": dataset_name, "name": dataset_name}
        if with_values:
            y = doc.get(SOLR_VECTOR, None)
            if y is None:
               # Generic x/y vector pair (dense_a512/dense_b512): could be a
               # dose-response curve, a calibration curve, etc. -- not
               # necessarily a Raman spectrum. The indexer writes whatever
               # it knew about the axes onto this same document, so use
               # that; a doc that carries neither name nor unit still gets
               # a blank title rather than a guess.
               y = doc.get("dense_b512", None)
               x = doc.get("dense_a512", None)
               xtitle = axis_title(doc.get("x_name_s"), doc.get("x_unit_s"))
               ytitle = axis_title(None, doc.get("unit_s"))
            else:
               # SOLR_VECTOR is a Raman spectrum resampled onto the fixed
               # wavenumber search grid, so these titles are always correct.
               dim = len(y)
               x = StudyRaman.x4search(dim).tolist()
               xtitle = r'wavenumber [$\mathrm{cm}^{-1}$]'
               ytitle = "intensity [a.u.]"
               
            if y is None or x is None:
                dataset = None
            else:
                dim = len(y)
                dataset["shape"] = [2, dim]
                dataset["size"] = dim
                dataset["value"] = []
                dataset["value"].append(x)
                dataset["value"].append(y)
                dataset["xtitle"] = xtitle
                dataset["ytitle"] = ytitle

        result["datasets"].append(dataset)

        doc_uuid = doc.get("document_uuid_s", "")
        params = {"q": "document_uuid_s:{}".format(doc_uuid), "fq": ["type_s:params"]}
        rs = None
        try:
            solr_url, collection_param, dropped = SOLR_COLLECTIONS.get_url(
                SOLR_ROOT, data_source, drop_private=token is None)
            if collection_param is not None:
                params["collection"] = collection_param
            rs = await solr_query_get(solr_url, params, token)
            rs_params_json = rs.json() # one study has one set of params by definition
            for doc_param in rs_params_json.get("response", {}).get("docs", []):
                # these should come from parameters ...
                annotation["method"] = doc_param.get("E.method_s", "")
                annotation["instrument"] = doc_param.get("instrument_s", "")
                break
        except HTTPException as err:
            raise err
        finally:
            if rs is not None:
                await rs.aclose()

        break
    return result


def read_cha(domain, result,  read_values=False, filter={"sample": None}, token=None):
    domain = validate_hsds_file_domain(domain, suffix=".chaold")
    with h5pyd.File(domain, api_key=token) as file:
        tmp, datasets = get_file_annotations(file, read_values, filter)
        if tmp is None or datasets is None:
            return result
        else:
            result["annotation"].append(tmp)
            result["datasets"] = datasets
    return result


def get_file_annotations(file=None, read_values=False, filter={"sample": None}):

    annotation = {}
    datasets = []

    # print(filter)
    if filter is None or filter["sample"] is None:
        pass
    else:
        if file["annotation_sample"].attrs["sample"]!= filter["sample"]:
            return None, None

    for key in file.keys():
        
        if key == "annotation_sample":
            for item in file[key].attrs:
                annotation[item]=file[key].attrs[item] 
        elif key == "annotation_study":
            for item in file[key].attrs:
                annotation[item] = file[key].attrs[item]  
        else:
            _dataset = {"key": key, "uuid": file[key].id.uuid, "name": file[key].name,
                                "shape": file[key].shape, "size": file[key].size}
            if read_values:
                _dataset["value"] = file[key][()].tolist()
                _dataset["dims"] = []
                for dim in file[key].dims:
                    _dataset["dims"].append(dim.label)

            datasets.append(_dataset)

    return annotation, datasets
