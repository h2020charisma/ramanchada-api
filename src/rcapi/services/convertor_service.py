from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import numpy as np
from numcompress import compress
from pynanomapper.clients.datamodel_simple import StudyRaman
import h5py, h5pyd 
from rcapi.services.solr_query import solr_query_get,SOLR_VECTOR
import traceback
import tempfile
import shutil
from ramanchada2.spectrum import from_local_file
import os
import hashlib
from typing import Tuple

def empty_figure(figsize,title,label) -> Figure:
    fig = Figure(figsize=figsize)
    axis = fig.add_subplot(1, 1, 1)
    axis.axis('off')
       #axis.set_xticks([])
        #axis.set_yticks([])
    axis.scatter([0,1],[0,0],s=0)
    axis.annotate(label,(0,0))
    axis.title.set_fontsize(8)
    axis.set_title(title)
    return fig

def dict2figure(pm,figsize) -> Figure:
    fig = Figure(figsize=figsize)
    axis = fig.add_subplot(1, 1, 1)
    n = 0
    for key in pm:
        if key=="domain" or key=="id" or key=="score":
            continue
        if type(pm[key])==str:
            n=n+1
    score = float(pm["score"])
       #axis.bar(["score"],[score],width=0.1)
        #axis.bar(["score"],[1-score],width=0.1)
    y = np.arange(0,n)
    x = np.repeat(0,n)

    axis.scatter(x,y,s=0)
    axis.axis('off')
    i = 0
    clr = {"high" : "r", "medium" : "y", "low" : "g", "fulfilled" : "b", "not fulfilled" : "c"}
    for key in pm:
        if key=="domain" or key=="id" or key=="score":
            continue
        if type(pm[key])==str:
            try:
                color = clr[pm[key]]
            except:
                color="k"
            axis.annotate("{}: {}".format(key.replace("_s",""),pm[key]),(0,i),color=color)
            i = i+1
    axis.title.set_fontsize(8)
    axis.set_xlim(0,1)
    axis.set_title(pm["domain"])
    return fig


def knnquery(domain,dataset="raw"):
    try:
        with h5pyd.File(domain,mode="r") as h5:
            x = h5[dataset][0]
            y = h5[dataset][1]
            (cdf,pdf) = StudyRaman.h52embedding(h5,dataset="raw",xlinspace = StudyRaman.x4search(2048))
            result_json = {}
            result_json["cdf"] = compress(pdf.tolist(),precision=6)
            #result_json["pdf"] = compress(pdf.tolist(),precision=6)
            #return ','.join(map(str, cdf))
            try:
                px = 1/plt.rcParams['figure.dpi']  # pixel in inches
                fig = Figure(figsize=(300*px, 200*px))
                axis = fig.add_subplot(1, 1, 1)
                axis.plot(x, y)
                axis.set_ylabel(h5[dataset].dims[1].label)
                axis.set_xlabel(h5[dataset].dims[0].label)
                axis.title.set_text("query")
                output = BytesIO()
                FigureCanvas(fig).print_png(output)
                base64_bytes = base64.b64encode(output.getvalue())
                result_json["imageLink"] = "data:image/png;base64,{}".format(str(base64_bytes,'utf-8'))
            except Exception as err:
                print(err)
            return result_json
    except Exception as err:
        raise(err)
    
def generate_etag(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()
    
async def solr2image(solr_url: str,domain : str,figsize=(6,4),extraprm =None,token : str = None) -> Tuple[Figure, str]:
    rs = None
    try:
        
        query="textValue_s:{}{}{}".format('"',domain,'"')
        params = {"q": query, "fq" : ["type_s:study"], "fl" : "name_s,textValue_s,reference_s,reference_owner_s,{},updated_s,_version_".format(SOLR_VECTOR)}
        
        rs =  await solr_query_get(solr_url, params, token = token)
        if rs is not None and rs.status_code == 200:
            response_json = rs.json()
            if "response" in response_json:
                if response_json["response"]["numFound"] == 0:
                    return empty_figure(figsize,title="not found",label="{}".format(domain.split("/")[-1])),None
                x = None
                for doc in response_json["response"]["docs"]:
                    y = doc[SOLR_VECTOR]
                    if y is None:
                        continue
                    if x is None:
                        x = StudyRaman.x4search(len(y))
                    fig = Figure(figsize=figsize)
                    axis = fig.add_subplot(1, 1, 1)
                    axis.plot(x, y)
                    axis.set_ylabel("a.u.")
                    axis.set_xlabel("Wavenumber [1/cm]")
                    axis.title.set_text("{} {} {} ({})".format("" if extraprm is None else extraprm,
                                doc["name_s"],doc["reference_owner_s"],doc["reference_s"]))
                    etag = generate_etag("{}{}{}".format(doc["textValue_s"],doc.get("updated_s",""),doc.get("_version_","")))
                    return fig,etag
        
        return empty_figure(figsize,"{} {}".format(rs.status_code,rs.reason),"{}".format(domain.split("/")[-1])),None

    except Exception as err:
        print(traceback.format_exc())
        return empty_figure(figsize,title="{}".format(err),label="{}".format(domain.split("/")[-1])),None
    finally:
        if not (rs is None):
            await rs.aclose()


def recursive_copy(
    src_group: h5py.Group | h5pyd.Group, dst_group: h5py.Group | h5pyd.Group, level=0
):
    # every File instance is also an HDF5 group
    # Copy attributes of the current group
    for attr_name, attr_value in src_group.attrs.items():
        dst_group.attrs[attr_name] = attr_value    
    for index,key in enumerate(src_group):
        try:
            item = src_group[key]
            if isinstance(item, (h5py.Group, h5pyd.Group)):
                # Create the group in the destination file
                new_group = dst_group.create_group(key)
                recursive_copy(item, new_group,level+1)
            elif isinstance(item, (h5py.Dataset, h5pyd.Dataset)):
                if item.shape == ():  # Scalar dataset
                    # Copy the scalar value directly
                    dst_dataset = dst_group.create_dataset(key, data=item[()])
                else:
                    # Copy the dataset to the destination file
                    dst_dataset = dst_group.create_dataset(key, data=item[:])
                for attr_name, attr_value in item.attrs.items():
                    dst_dataset.attrs[attr_name] = attr_value  
                #dst_dataset.flush()     
        except Exception as err:
            print(traceback.format_exc())
             


def read_spectrum_native(file,file_name,prefix="rcapi_"):
    native_filename=None
    try:
        filename, file_extension = os.path.splitext(file_name)
        # because rc2 works with file paths only, no url nor file objects
        with tempfile.NamedTemporaryFile(delete=False,prefix=prefix,suffix=file_extension) as tmp:
            shutil.copyfileobj(file,tmp)
            native_filename = tmp.name
        spe =  from_local_file(native_filename)
        return spe
    except Exception as err:
        raise err
    finally:
        if native_filename!=None:
            os.remove(native_filename)