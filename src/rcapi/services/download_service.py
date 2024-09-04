import requests
from typing import Optional, Literal
from fastapi import Request, HTTPException
from numcompress import compress, decompress
import traceback 



class DownloadService:
    def process(
        request: Request,
        solr_url: str,
    ):
        pass