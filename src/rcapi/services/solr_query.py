import httpx 
from fastapi import  HTTPException
import re 
from rcapi.config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()
SOLR_ROOT = config.SOLR_ROOT
SOLR_VECTOR = config.SOLR_VECTOR
SOLR_COLLECTIONS = config.SOLR_COLLECTIONS


async def solr_query_post(
        solr_url, query_params=None, post_param=None, token=None):
    async with httpx.AsyncClient() as client:
        try:
            headers = {}
            if token:
                headers['Authorization'] = f'Bearer {token}'  # Add token to headers                  
            response = await client.post(
                solr_url,
                json=post_param,
                params=query_params,
                headers=headers  # Pass headers
            )
            response.raise_for_status()  # Check for HTTP errors
            return response
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail="external service ({})".
                format("-" if token is None else "+"))


async def solr_query_get(solr_url, params=None, token=None):
    async with httpx.AsyncClient() as client:
        try:
            headers = {}
            if token:
                headers['Authorization'] = f'Bearer {token}'  
            response = await client.get(
                solr_url,
                params=params,
                headers=headers  # Pass headers
            )
            response.raise_for_status()  # Check for HTTP errors
            return response
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail="external service ({})".format(
                    "-" if token is None else "+"))


def solr_escape(value: str) -> str:
    # Escape special characters that Solr expects to be escaped
    solr_special_chars = r'(\+|\-|\&\&|\|\||!|\(|\)|\{|\}|\[|\]|\^|"|~|\*|\?|\:|\\|\/)'
    # Replace the special characters with an escaped version (i.e., prefix with \)
    escaped_value = re.sub(solr_special_chars, r'\\\1', value)
    return escaped_value
