from fastapi import Request 

def get_baseurl(request : Request):
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "http")
    base_url = str(request.base_url) 
    if "localhost" not in base_url:
        base_url = base_url.replace("http://", "{}://".format(forwarded_proto))  
    return base_url