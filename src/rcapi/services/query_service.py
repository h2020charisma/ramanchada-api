from typing import Optional, Literal
from fastapi import Request, HTTPException
from numcompress import  decompress
from rcapi.services.solr_query import solr_query_post
import urllib.parse
from rcapi.api.utils import get_baseurl


async def process(request: Request,
    solr_url: str,
    q: Optional[str] = "*",
    query_type: Optional[str] = None,
    q_reference: Optional[str] = "*",
    q_provider: Optional[str] = "*",
    ann: Optional[str] = None,
    page: Optional[int] = 0,
    pagesize: Optional[int] = 10,
    img: Optional[Literal["embedded", "original", "thumbnail"]] = "thumbnail",
    vector_field = "spectrum_p1024",
    collections = None,
    token=None):

    query_fields = "id,name_s,textValue_s"
    embedded_images = img=="embedded"
    if embedded_images:
        query_fields = "{},{}".format(query_fields,vector_field)

    thumbnail = "image" if img=="original" else "thumbnail"
    query_params = { "start" : page, "rows" : pagesize}
    if collections is not None:
        query_params["collection"] = collections

    if query_type != "knnquery":
        textQuery = q
        textQuery = "*" if textQuery is None or textQuery=="" else textQuery
        solr_params = {
            "query": textQuery, 
            "filter" : [
                "type_s:study",
                "reference_s:{}".format(q_reference),"reference_owner_s:{}".format(q_provider)], 
                "fields" : query_fields}
        response = None
        try:
            response = await solr_query_post(solr_url,query_params,solr_params,token)
            response_data = response.json()
            return parse_solr_response(response_data,get_baseurl(request),embedded_images,thumbnail,vector_field=None)
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
            query = "!knn f={} topK={}".format(vector_field,40)
            solr_params= {"query": "{"+query+"}[" + knnQuery + "]", 
                "filter" : ["type_s:study",
                            "reference_s:{}".format(q_reference),
                            "reference_owner_s:{}".format(q_provider)  ], 
                            "fields" : query_fields}
            response = None
            try:
                response = await solr_query_post(solr_url,query_params,solr_params,token)
                response_data = response.json()
                return parse_solr_response(response_data,request.base_url,embedded_images,thumbnail,vector_field)
            except Exception as err:
                raise err
            finally:
                if response is not None:
                    await response.aclose()        


def parse_solr_response(response_data,base_url=None,embedded_images=False,thumbnail="image",vector_field=None):
# Process Solr response and construct the output
    results = []
    for doc in response_data.get("response", {}).get("docs", []):
        value = doc.get("textValue_s", "")
        text = f"{doc.get('name_s', '')}"
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
            encoded_domain = urllib.parse.quote(value)
            image_link = f"{base_url}db/download?what={thumbnail}&domain={encoded_domain}&extra="
        _tmp = {
            "value": value,
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
    
