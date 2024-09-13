import requests
from typing import Optional, Literal
from fastapi import Request, HTTPException
from numcompress import  decompress
import httpx
import traceback 

async def process(request: Request,
    solr_url: str,
    q: Optional[str] = "*",
    query_type: Optional[str] = None,
    q_reference: Optional[str] = "*",
    q_provider: Optional[str] = "*",
    ann: Optional[str] = None,
    page: Optional[int] = 0,
    pagesize: Optional[int] = 10,
    img: Optional[Literal["embedded", "original", "thumbnail"]] = "thumbnail"):

    embedded_images = img=="embedded"
    thumbnail = "image" if img=="original" else "thumbnail"
    query_params = { "start" : page, "rows" : pagesize}

    response_data = []
    if query_type != "knnquery":
        async with httpx.AsyncClient() as client:
            textQuery = q
            textQuery = "*" if textQuery is None or textQuery=="" else textQuery
            solr_params = {
                "query": textQuery, 
                "filter" : [
                    "type_s:study",
                    "reference_s:{}".format(q_reference),"reference_owner_s:{}".format(q_provider)], 
                    "fields" : "id,score,name_s,textValue_s"}
            try:
                response = await client.post(
                    solr_url,
                    json=solr_params,
                    params = query_params 
                )
                response.raise_for_status()  # Check for HTTP errors
                response_data = response.json()
                parsed_data =  parse_response(response_data,request.base_url,embedded_images,thumbnail)
                return parsed_data
            except httpx.HTTPStatusError as e:
                print(traceback.format_exc())
                raise HTTPException(status_code=e.response.status_code, detail="Error fetching data from external service")


def parse_response(response_data,base_url=None,embedded_images=False,thumbnail="image"):
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
            image_link = f"{base_url}download?what={thumbnail}&domain={value}&extra="
        results.append({
            "value": value,
            "text": text,
            "imageLink": image_link
        })

    return results
    

def process_sync(
    request: Request,
    solr_url: str,
    q: Optional[str] = "*",
    query_type: Optional[str] = None,
    q_reference: Optional[str] = "*",
    q_provider: Optional[str] = "*",
    ann: Optional[str] = None,
    page: Optional[int] = 0,
    pagesize: Optional[int] = 10,
    img: Optional[Literal["embedded", "original", "thumbnail"]] = "thumbnail"
):
    #tbd
    headers = {}
    #_token = self.h5service.tokenservice.api_key()
    #if _token != None:
    #    headers["Authorization"] = "Bearer {}".format(_token);
    #url = "{}?start={}&rows={}".format(solrUrl,page,pagesize)
 
    embedded_images = img=="embedded"
    thumbnail = "image" if img=="original" else "thumbnail"
    url = "{}?start={}&rows={}".format(solr_url,page,pagesize)
    
    response_data = []
    if query_type == "knnquery":
        knnQuery = ann
        if (knnQuery is None) or (knnQuery ==""):
            raise HTTPException(status_code=400, detail="?ann parameter missing")
    
        else:
            knnQuery = ','.join(map(str, decompress(knnQuery)))
            response = knn(url,q_reference,q_provider,knnQuery,topk=40,headers=headers)
            response_data = response.json()
    else:
        textQuery = q
        textQuery = "*" if textQuery is None or textQuery=="" else textQuery
        # Map the incoming query to the Solr query parameters

        solr_params = {
            "query": textQuery, 
            "filter" : [
                "type_s:study",
                "reference_s:{}".format(q_reference),"reference_owner_s:{}".format(q_provider)], 
                "fields" : "id,score,name_s,textValue_s"}
        response = requests.post(url, json=solr_params)
        response_data = response.json()

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
            image_link = f"{request.base_url}download?what={thumbnail}&domain={value}&extra="
        results.append({
            "value": value,
            "text": text,
            "imageLink": image_link
        })

    return results

def knn(url,q_reference="*",q_provider="*",knnQuery=None,topk=20,headers={}):
    try:

        query = "!knn f=spectrum_p1024 topK={}".format(topk)
        data= {"query": "{"+query+"}[" + knnQuery + "]", 
               "filter" : ["type_s:study",
                           "reference_s:{}".format(q_reference),
                           "reference_owner_s:{}".format(q_provider)  ], 
                           "fields" : "id,score,name_s,textValue_s"}
        rs =  requests.post(url, json = data, headers= headers)
        return rs
    except Exception as err:
        traceback.print_exc()
        raise err