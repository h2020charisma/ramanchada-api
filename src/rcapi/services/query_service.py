import requests
from typing import Optional, Literal
from fastapi import Request, HTTPException

# Define the Solr base URL and core
SOLR_URL = "http://your-solr-server/solr/charisma/select"

def process(
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
    if query_type == "knnquery":
        knnQuery = ann
        if (knnQuery is None) or (knnQuery ==""):
            raise HTTPException(status_code=400, detail="?ann parameter missing")
    
        else:
            #knnQuery = ','.join(map(str, decompress(knnQuery)))
            #rs = self.knn(solr_url,textQuery,q_reference,q_provider,knnQuery,topk=40,page=0 if page is None else page,pagesize = 10 if pagesize is None else pagesize)

            pass
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
    #tbd
    headers = {}
    #_token = self.h5service.tokenservice.api_key()
    #if _token != None:
    #    headers["Authorization"] = "Bearer {}".format(_token);
    #url = "{}?start={}&rows={}".format(solrUrl,page,pagesize)

    embedded_images = img=="embedded"
    thumbnail = "image" if img=="original" else "thumbnail"

    # Query the Solr server
    url = "{}?start={}&rows={}".format(solr_url,page,pagesize)
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
                image_link = "tbdembedded"
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
