from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Query, Depends
from fastapi.responses import Response
from typing import Optional, Literal
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import logging
import io
import base64
import traceback
import os.path
import ramanchada2 as rc2
from pynanomapper.clients.datamodel_simple import StudyRaman
from numcompress import compress
from rcapi.services.convertor_service import empty_figure,dict2figure,  solr2image, knnquery, recursive_copy,read_spectrum_native
#from rcapi.services.kc import inject_api_key_h5pyd, inject_api_key_into_httpx, get_api_key
import h5py, h5pyd 
from rcapi.services.solr_query import SOLR_ROOT,SOLR_VECTOR,SOLR_COLLECTION
import tempfile
import shutil


router = APIRouter()


@router.get("/download", )
async def convert_get(
    request: Request,
    domain: str,    
    what: Optional[Literal["h5", "image", "empty", "dict", "thumbnail","b64png"]] = "h5",
    dataset: Optional[str] = "raw",
    w: Optional[int] = 300,
    h: Optional[int] = 200,
    extra: Optional[str] = None
    #api_key: Optional[str] = Depends(get_api_key)
) :
    if not domain:
        #tr.set_error("missing domain")
        raise HTTPException(status_code=400, detail=str("missing domain"))
    
    solr_url = "{}{}/select".format(SOLR_ROOT,SOLR_COLLECTION)

    width = w
    height = h
    px = 1 / plt.rcParams['figure.dpi']  # pixel in inches
    figsize = width * px, height * px
       
    try:
        if what == "empty":
            fig = empty_figure(figsize, domain, extra)
            output = io.BytesIO()
            FigureCanvas(fig).print_png(output)
            return Response(content=output.getvalue(), media_type='image/png')
        
        
        if what == "dict":
            prm = dict(request.query_params)
            prm["what"] = None
            fig = dict2figure(prm, figsize)
            output = io.BytesIO()
            FigureCanvas(fig).print_png(output)
            return Response(content=output.getvalue(), media_type='image/png')
        elif what in ["thumbnail","b64png","image"]: #solr query
                #async with inject_api_key_into_httpx(api_key):
                try:
                    fig,etag = await solr2image(solr_url, domain, figsize, extra)
                    # Check if ETag matches the client's If-None-Match header
                    if request.headers.get("if-none-match") == etag:
                        # Return 304 Not Modified if the resource hasn't changed
                        return Response(status_code=304)                    
                    output = io.BytesIO()
                    FigureCanvas(fig).print_png(output)
                    if what == "b64png":
                        base64_bytes = base64.b64encode(output.getvalue())
                        return Response(content=base64_bytes, media_type='text/plain',headers={"ETag": etag})         
                    else:
                        return Response(content=output.getvalue(), media_type='image/png',headers={"ETag": etag})
                except Exception as err:
                    raise HTTPException(status_code=500, detail=f" error: {str(err)}")
        elif what  == "h5":  # h5 query
            try:
                #with inject_api_key_h5pyd(api_key):
                if what == "h5":
                    try:
                        with io.BytesIO() as tmpfile:
                            with h5pyd.File(domain,mode="r") as fin:   
                                with h5py.File(tmpfile,"w") as fout:
                                    recursive_copy(fin,fout)                         
                            tmpfile.seek(0)
                            return Response(content=tmpfile.read(), media_type="application/x-hdf5", headers={"Content-Disposition": "attachment; filename=download.h5"})
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f" error: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f" error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Unsupported 'what' parameter: {what}")
    
    except HTTPException as err:
        raise err
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))
    
@router.post("/download")
async def convert_post(
        what: Literal["knnquery", "b64png" ]  = Query("knnquery") ,
        files: list[UploadFile] = File(...)
        #api_key: Optional[str] = Depends(get_api_key) 
    ):
    logging.info("convert_file function called")
    logging.info(f"Received parameter 'what': {what}")
    logging.info(f"Number of files received: {len(files)}")    
    
    if not files:
        #tr.set_error("Missing file")
        raise HTTPException(status_code=400, detail=f"Missing file")
    
    try:
        result = ""
        for uf in files:
            print(uf.filename)
            f_name = uf.filename
            _filename, file_extension = os.path.splitext(f_name)
            
            if file_extension not in (".cha",".nxs"):
                spe = read_spectrum_native(uf.file, uf.filename)
                if what == "knnquery":
                    _cdf, pdf = StudyRaman.xy2embedding(spe.x, spe.y, StudyRaman.x4search(dim=2048))
                    result_json = {"cdf": compress(pdf.tolist(), precision=6)}
                    px = 1 / plt.rcParams['figure.dpi']  # pixel in inches
                    fig = plt.Figure(figsize=(300 * px, 200 * px))
                    axis = fig.add_subplot(1, 1, 1)
                    axis.plot(spe.x, spe.y, color='green')
                    output = io.BytesIO()
                    FigureCanvas(fig).print_png(output)
                    base64_bytes = base64.b64encode(output.getvalue())
                    result_json["imageLink"] = f"data:image/png;base64,{base64_bytes.decode('utf-8')}"
                    return result_json
                
                elif what == "b64png":
                    fig = plt.Figure(figsize=(2, 1))
                    axis = fig.add_subplot(1, 1, 1)
                    axis.plot(spe.x, spe.y)
                    output = io.BytesIO()
                    FigureCanvas(fig).print_png(output)
                    base64_bytes = base64.b64encode(output.getvalue())
                    return Response(content=base64_bytes, media_type='text/plain')
                else:
                    raise HTTPException(status_code=500, detail=f"Unsupported 'what' parameter: {what}")
   
    except HTTPException as err:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(traceback.format_exc()))
    except Exception as err:
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(traceback.format_exc()))
    
    