from matplotlib.patches import Rectangle
from matplotlib.collections import PatchCollection
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import io
from io import BytesIO
import base64
import numpy as np
from numcompress import compress
from pynanomapper.clients.datamodel_simple import StudyRaman
import h5py, h5pyd 
from rcapi.services.solr_query import solr_query_post,solr_query_get,SOLR_ROOT,SOLR_COLLECTION,SOLR_VECTOR
import traceback

def empty_figure(figsize,title,label):
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

def dict2figure(pm,figsize):
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
            (cdf,pdf) = StudyRaman.h52embedding(h5,dataset="raw",xlinspace = StudyRaman.x4search())
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
                output = io.BytesIO()
                FigureCanvas(fig).print_png(output)
                base64_bytes = base64.b64encode(output.getvalue())
                result_json["imageLink"] = "data:image/png;base64,{}".format(str(base64_bytes,'utf-8'))
            except Exception as err:
                print(err)
            return result_json
    except Exception as err:
        raise(err)
    
async def solr2image(solr_url,domain,figsize=(6,4),extraprm=None):
    rs = None
    try:
        query="textValue_s:\"{}\"".format(domain.replace(" ","\ "))
        params = {"q": query, "fq" : ["type_s:study"], "fl" : "name_s,textValue_s,reference_s,reference_owner_s,{}".format(SOLR_VECTOR)}
        rs =  await solr_query_get(solr_url, params)
        if rs.status_code==200:
            x = None
            for doc in rs.json()["response"]["docs"]:
                y = doc[SOLR_VECTOR]
                if x is None:
                    x = StudyRaman.x4search(len(y))
                fig = Figure(figsize=figsize)
                axis = fig.add_subplot(1, 1, 1)
                axis.plot(x, y)
                axis.set_ylabel("a.u.")
                axis.set_xlabel("Wavenumber [1/cm]")
                axis.title.set_text("{} {} {} ({})".format("" if extraprm is None else extraprm,
                            doc["name_s"],doc["reference_owner_s"],doc["reference_s"]))
                return fig
        else:
            return empty_figure(figsize,"{} {}".format(rs.status_code,rs.reason),"{}".format(domain.split("/")[-1]))

    except Exception as err:
        raise(err)
    finally:
        if not (rs is None):
            rs.close    


def recursive_copy(src_group : h5py.Group, dst_group : h5py.Group,level=0):
    # every File instance is also an HDF5 group
    # Copy attributes of the current group
    for attr_name, attr_value in src_group.attrs.items():
        dst_group.attrs[attr_name] = attr_value    
    for index,key in enumerate(src_group):
        try:
            item = src_group[key]
            if isinstance(item, h5pyd.Group):
                # Create the group in the destination file
                new_group = dst_group.create_group(key)
                recursive_copy(item, new_group,level+1)
            elif isinstance(item, h5pyd.Dataset):
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
        #if level == 0 and index>25:
        #    break              
