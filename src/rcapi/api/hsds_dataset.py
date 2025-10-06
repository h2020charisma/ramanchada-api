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
        fields = "name_s,reference_s,reference_owner_s,document_uuid_s,updated_s,_version_"
        if values:
            fields = "{},{}".format(fields, SOLR_VECTOR)
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
        dataset = {"key": dataset_name, "name": dataset_name, "shape": [2, len(x4search)], "size": len(x4search)}
        if with_values:
            y = doc[SOLR_VECTOR]
            dim = len(y)
            dataset["shape"] = [2, dim]
            dataset["size"] = dim
            dataset["value"] = []
            dataset["value"].append(StudyRaman.x4search(dim).tolist())
            dataset["value"].append(y)

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
                annotation["wavelength"] = doc_param.get("wavelength_d", "")
                annotation["instrument"] = doc_param.get("instrument_s", "")
                annotation["laser_power"] = ""
                annotation["native_filename"] = ""
                annotation["optical_path"] = ""
                break
        except HTTPException as err:
            raise err
        finally:
            if rs is not None:
                await rs.aclose()

        break
    return result


def read_cha(domain, result,  read_values=False, filter={"sample": None}, token=None):

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
