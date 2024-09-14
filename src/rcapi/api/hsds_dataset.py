from fastapi import APIRouter, Query, HTTPException
from typing import Optional,  List, Union
from pydantic import BaseModel
import h5pyd

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
):
    if domain.endswith(".cha"):
        result = {"subdomains": [], "domain": domain, "annotation": [], "datasets": []}
        return read_cha(domain,result,read_values=values)
    else:
        raise HTTPException(status_code=400, detail="Invalid domain format. Must end with '.cha'.")

def read_cha(domain, result,  read_values=False, filter={"sample" : None}):
    
    with h5pyd.File(domain) as file:
        tmp, datasets = get_file_annotations(file, read_values, filter)
        if tmp is None or datasets is None:
            return result
        else:
            result["annotation"].append(tmp)
            result["datasets"] = datasets
    return result

def get_file_annotations(file=None,read_values=False,filter={"sample" : None}):
    
    annotation = {}
    datasets = []

    #print(filter)
    if filter is None or filter["sample"] is None:
        pass
    else:
        if file["annotation_sample"].attrs["sample"]!= filter["sample"]:
            return None, None

    for key in file.keys():
        
        if key=="annotation_sample":
            for item in file[key].attrs:
                annotation[item]=file[key].attrs[item] 
        elif key=="annotation_study":
            for item in file[key].attrs:
                annotation[item]=file[key].attrs[item]  
        else:
            _dataset = {"key" : key, "uuid" : file[key].id.uuid, "name" : file[key].name, 
                                "shape" : file[key].shape, "size" : file[key].size}
            if read_values:
                _dataset["value"] = file[key][()].tolist()
                _dataset["dims"] = []
                for dim in file[key].dims:
                    _dataset["dims"].append(dim.label)

            datasets.append(_dataset)

    return annotation,datasets
