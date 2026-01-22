import httpx 
from fastapi import  HTTPException
import re 
from rcapi.config.app_config import initialize_dirs

config, UPLOAD_DIR, NEXUS_DI, TEMPLATE_DIR = initialize_dirs()
SOLR_ROOT = config.SOLR_ROOT
SOLR_VECTOR = config.SOLR_VECTOR
SOLR_SIMILARITY = config.SOLR_SIMILARITY
SOLR_COLLECTIONS = config.SOLR_COLLECTIONS
SOLR_FIELDS = config.SOLR_FIELDS
APPLICATION_NAME = config.application_name


def get_query_fields():
    _fields = "id,type_s"
    if "study" in config.SOLR_DOCS:
        _fields = f"{_fields},study_name:name_s,study_domain:textValue_s"
    if "substance" in config.SOLR_DOCS:
        _fields = f"{_fields},substance_name:name_hs"
    if "composition" in config.SOLR_DOCS:
        _fields = f"{_fields},composition_name:ChemicalName_s"
    if "chemical" in config.SOLR_DOCS:
        _fields = f"{_fields},chemical_name:preferred_name_t"
    if "prediction" in config.SOLR_DOCS:
        _fields = f"{_fields},prediction_name:concat(dsstox_id_s, ': ' ,guidance_s, ' ', reference_s, ' model predictions')"
    #if "aop" in config.SOLR_DOCS or "key_event" in config.SOLR_DOCS:
    #    _fields = f"{_fields},title_t,name_s:name_t"
    return _fields


def solr_doc_filter() -> str:
    docs = config.SOLR_DOCS or ["study"]
    quoted = [f'"{v}"' for v in docs]
    
    return f"type_s:({ ' OR '.join(quoted) })"


async def solr_query_post(
        solr_url, query_params=None, post_param=None, token=None):
    async with httpx.AsyncClient() as client:
        try:
            headers = {}
            if token:
                headers['Authorization'] = f'Bearer {token}'  # Add token to headers                  
            # print(query_params, post_param)
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
