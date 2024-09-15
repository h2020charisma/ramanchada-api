import httpx 
from fastapi import  HTTPException
import re 

SOLR_ROOT = "https://solr-kc.ideaconsult.net/solr/"
SOLR_VECTOR = "spectrum_p1024"
SOLR_COLLECTION = "charisma"

async def solr_query_post(solr_url,query_params = None,post_param = None):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                solr_url,
                json=post_param,
                params = query_params 
            )
            response.raise_for_status()  # Check for HTTP errors
            return response
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail="Error fetching data from external service")

async def solr_query_get(solr_url,params = None):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                solr_url,
                params = params 
            )
            response.raise_for_status()  # Check for HTTP errors
            return response
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail="Error fetching data from external service")
        
def solr_escape(value: str) -> str:
    # Escape special characters that Solr expects to be escaped
    solr_special_chars = r'(\+|\-|\&\&|\|\||!|\(|\)|\{|\}|\[|\]|\^|"|~|\*|\?|\:|\\|\/)'
    
    # Replace the special characters with an escaped version (i.e., prefix with \)
    escaped_value = re.sub(solr_special_chars, r'\\\1', value)
    
    return escaped_value        