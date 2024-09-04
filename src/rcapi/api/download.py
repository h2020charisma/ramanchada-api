from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import Response
from typing import Optional, Literal
from rcapi.services import query_service
from rcapi.models.models import Task 
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import logging
import io
import base64
import traceback
from pynanomapper.clients.service_charisma import H5Service
import os.path
import ramanchada2 as rc2
from pynanomapper.clients.datamodel_simple import StudyRaman
from numcompress import compress

router = APIRouter()

solr_root = "https://solr-kc.ideaconsult.net/solr/"

@router.get("/download", )
async def download_get(
    request: Request,
    domain: str,    
    what: Optional[str] = "h5",
    dataset: Optional[str] = "raw",
    w: Optional[int] = 300,
    h: Optional[int] = 200,
    extra: Optional[str] = None) :

    tr = Task(f"GET /download")
    
    if not domain:
        tr.set_error("missing domain")
        raise HTTPException(status_code=400, detail=str("missing domain"))
    
    solr_url = "{}charisma/select".format(solr_root)

    width = w
    height = h
    px = 1 / plt.rcParams['figure.dpi']  # pixel in inches
    figsize = width * px, height * px
       
    try:
        # Replace `H5Service` with the actual service you use.
        if what == "empty":
            fig = H5Service.empty_figure(figsize, domain, extra)
            output = io.BytesIO()
            FigureCanvas(fig).print_png(output)
            return Response(content=output.getvalue(), media_type='image/png')
        
        if what == "dict":
            prm = dict(request.query_params)
            prm["what"] = None
            fig = H5Service.dict2figure(prm, figsize)
            output = io.BytesIO()
            FigureCanvas(fig).print_png(output)
            return Response(content=output.getvalue(), media_type='image/png')
        
        if what == "image":
            fig = H5Service.image(domain, dataset, figsize, extra)
            output = io.BytesIO()
            FigureCanvas(fig).print_png(output)
            return Response(content=output.getvalue(), media_type='image/png')
        
        if what == "thumbnail":
            fig = H5Service.thumbnail(solr_url, domain, figsize, extra)
            output = io.BytesIO()
            FigureCanvas(fig).print_png(output)
            return Response(content=output.getvalue(), media_type='image/png')
        
        if what == "b64png":
            fig = H5Service.image(domain, dataset)
            output = io.BytesIO()
            FigureCanvas(fig).print_png(output)
            base64_bytes = base64.b64encode(output.getvalue())
            return Response(content=base64_bytes, media_type='text/plain')
        
        if what == "knnquery":
            return H5Service.knnquery(domain, dataset)
        
        if what == "h5":
            with io.BytesIO() as tmpfile:
                H5Service.download(domain, tmpfile)
                tmpfile.seek(0)
                return Response(content=tmpfile.read(), media_type="application/x-hdf5", headers={"Content-Disposition": "attachment; filename=download.h5"})
        
        raise HTTPException(status_code=500, detail=f"Unsupported 'what' parameter: {what}")
    
    except HTTPException as err:
        raise err
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))
    
@router.get("/download", )
async def convert_file(
        what: str = "knnquery",
        files: list[UploadFile] = File(...)
    ):
    tr = Task(f"POST /download")
    
    if not files:
        tr.set_error("Missing file")
        raise HTTPException(status_code=400, detail=f"Missing file")
    
    try:
        result = ""
        for uf in files:
            f_name = uf.filename
            _filename, file_extension = os.path.splitext(f_name)
            
            if file_extension != ".cha":
                x, y, _meta = rc2.spectrum.from_local_file(file=uf.file, f_name=f_name)
                
                if what == "knnquery":
                    _cdf, pdf = StudyRaman.xy2embedding(x, y, StudyRaman.x4search())
                    result_json = {"cdf": compress(pdf.tolist(), precision=6)}
                    px = 1 / plt.rcParams['figure.dpi']  # pixel in inches
                    fig = plt.Figure(figsize=(300 * px, 200 * px))
                    axis = fig.add_subplot(1, 1, 1)
                    axis.plot(x, y, color='green')
                    output = io.BytesIO()
                    FigureCanvas(fig).print_png(output)
                    base64_bytes = base64.b64encode(output.getvalue())
                    result_json["imageLink"] = f"data:image/png;base64,{base64_bytes.decode('utf-8')}"
                    return result_json
                
                elif what == "b64png":
                    fig = plt.Figure(figsize=(2, 1))
                    axis = fig.add_subplot(1, 1, 1)
                    axis.plot(x, y)
                    output = io.BytesIO()
                    FigureCanvas(fig).print_png(output)
                    base64_bytes = base64.b64encode(output.getvalue())
                    return Response(content=base64_bytes, media_type='text/plain')
        
        tr.set_completed(result)
        return tr.to_dict()
    
    except HTTPException as err:
        logging.error(traceback.format_exc())
        raise err
    except Exception as err:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(err))