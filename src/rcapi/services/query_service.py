from typing import Optional, Literal
from fastapi import Request, HTTPException
from numcompress import  decompress
from rcapi.services.solr_query import (
    get_query_fields, solr_query_post, solr_doc_filter
)
import urllib.parse
from rcapi.api.utils import get_baseurl
from rcapi.services.standard_response import StandardResponse


def get_predefined(param):
    PREDEFINED = {
        "q_reference": "reference_s",
        "q_provider": "reference_owner_s",
        "q_method": "guidance_s"
        }
    return PREDEFINED.get(param, param)


def build_solr_filters(filters=[], **kwargs):
    """
    Build a list of Solr filter queries based on provided keyword arguments.
    
    Example:
        build_solr_filters(solr_doc_filter, q_reference='abc', q_method='*')
    """
    for param, value in kwargs.items():
        if value != "*":  # skip wildcards
            field_name = get_predefined(param)
            filters.append(f"{field_name}:\"{value}\"")
    return filters


async def process(request: Request,
                  solr_url: str,
                  q: Optional[str] = "*",
                  query_type: Optional[str] = None,
                  q_reference: Optional[str] = None,
                  q_provider: Optional[str] = None,
                  q_method: Optional[str] = None,
                  ann: Optional[str] = None,
                  page: Optional[int] = 0,
                  pagesize: Optional[int] = 10,
                  img: Optional[Literal["embedded", "original", "thumbnail"]]="thumbnail",
                  vector_field: str = "spectrum_p1024",
                  collections = None,
                  token=None) -> StandardResponse:

    query_fields = get_query_fields()
    embedded_images = img == "embedded"
    if embedded_images:
        query_fields = "{},{}".format(query_fields,vector_field)

    thumbnail = "image" if img == "original" else "thumbnail"
    query_params = { "start": page*pagesize, "rows": pagesize}
    if collections is not None:
        query_params["collection"] = collections

    if query_type != "knnquery":
        textQuery = q
        textQuery = "*" if textQuery is None or textQuery=="" else textQuery
        _filter = [solr_doc_filter()]
        _filter = build_solr_filters(
            _filter, q_reference=q_reference,
            q_provider=q_provider, q_method=q_method)
        post_params = {"query": textQuery, "filter": _filter,
                       "fields": query_fields}

        response = None
        try:
            response = await solr_query_post(solr_url, query_params, post_params, token)
            response_data = response.json()
            results = parse_solr_response(
                response_data, get_baseurl(request), embedded_images,
                thumbnail, vector_field=None, collections=collections)
            return StandardResponse(
                status=0,
                numFound=response_data.get("response", {}).get("numFound", 0),
                start=response_data.get("response", {}).get("start", 0),
                response=results)
        except Exception as err:
            raise err
        finally:
            if response is not None:
                await response.aclose()
    else:
        query_fields = "{},score".format(query_fields)
        knnQuery = ann
        if (knnQuery is None) or (knnQuery ==""):
            raise HTTPException(status_code=400, detail="?ann parameter missing")
        else:
            knnQuery = ','.join(map(str, decompress(knnQuery)))
            query = "!knn f={} topK={}".format(vector_field, 40)
            _filter = [solr_doc_filter()]
            _filter = build_solr_filters(
                _filter, q_reference=q_reference, 
                q_provider=q_provider, q_method=q_method)
            post_params = {"query": "{"+query+"}[" + knnQuery + "]",
                           "filter": _filter, "fields": query_fields}

            response = None
            try:
                response = await solr_query_post(solr_url,query_params,post_params,token)
                response_data = response.json()
                results = parse_solr_response(response_data,request.base_url,embedded_images,thumbnail,vector_field,collections=collections)
                return StandardResponse(
                    status=0,
                    numFound=response_data.get("response", {}).get("numFound", 0),
                    start=response_data.get("response", {}).get("start", 0),
                    response=results)
            except Exception as err:
                raise err
            finally:
                if response is not None:
                    await response.aclose()        


def parse_solr_response(response_data, base_url=None, embedded_images=False,thumbnail="image",vector_field=None,collections=None):
# Process Solr response and construct the output
    results = []
    response = response_data.get("response", {})
    for doc in response.get("docs", []):
        type_s = doc.get("type_s", "")
        domain = f"{doc.get(f'{type_s}_domain', None)}"
        text = f"{doc.get(f'{type_s}_name', '')}"
        id = urllib.parse.quote(doc.get("id", None))
        if embedded_images:
            try:
                #px = 1/plt.rcParams['figure.dpi']  # pixel in inches
                #fig = self.h5service.image(doc["textValue_s"],"raw",figsize=(300*px, 200*px))
                #output = io.BytesIO()
                #FigureCanvas(fig).print_png(output)
                #base64_bytes = base64.b64encode(output.getvalue())
                #image_link = "data:image/png;base64,{}".format(str(base64_bytes,'utf-8'))
                image_link = "tbd"
            except Exception as err:
                print(err)    
        else:
            if collections is None:
                data_source = ""
            else:
                data_source = "&".join(f"data_source={c}" for c in collections.split(","))

            if domain is None:
                image_link = f"{base_url}db/download?what={thumbnail}&domain=id:{id}&id={id}&extra={type_s}&{data_source}"
            else:
                encoded_domain = urllib.parse.quote(domain)
                image_link = f"{base_url}db/download?what={thumbnail}&domain={encoded_domain}&id={id}&extra={type_s}&{data_source}"
        _tmp = {
            "value": domain,
            "id": id,
            "type": type_s,
            "text": text,
            "imageLink": image_link
        }            
        _score = doc.get("score", None)
        if _score is not None:
            _tmp["score"] = _score
        if vector_field is not None:
            _vector_value = doc.get(vector_field, None)    
            if _vector_value is not None:
                _tmp[vector_field] = _vector_value
        results.append(_tmp)

    return results
    
