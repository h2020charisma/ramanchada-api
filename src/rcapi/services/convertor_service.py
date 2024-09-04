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
import h5pyd 
import requests
from .kc import AuthenticatedRequest

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

def image(domain,dataset="raw",figsize=(6,4),extraprm=""):
    try:
        with h5pyd.File(domain,mode="r") as h5:
            x = h5[dataset][0]
            y = h5[dataset][1]
            try:
                _sample = h5["annotation_sample"].attrs["sample"]
            except:
                _sample = None
            try:
                _provider = h5["annotation_study"].attrs["provider"]
            except:
                _provider = None
            try:
                _wavelength = h5["annotation_study"].attrs["wavelength"]
            except:
                _wavelength = None
            fig = Figure(figsize=figsize)
            axis = fig.add_subplot(1, 1, 1)
            axis.plot(x, y, color='black')
            axis.set_ylabel(h5[dataset].dims[1].label)
            axis.set_xlabel(h5[dataset].dims[0].label)
            axis.title.set_text("{} {} ({}) {}".format(extraprm,_sample,_provider,_wavelength))
            #domain.split("/")[-1],dataset))
            return fig
    except Exception as err:
        return empty_figure(figsize,"Error","{}".format(domain.split("/")[-1]))

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
    
def thumbnail(solr_url,domain,figsize=(6,4),extraprm=""):
    rs = None
    try:
        query="textValue_s:\"{}\"".format(domain.replace(" ","\ "))
        params = {"q": query, "fq" : ["type_s:study"], "fl" : "name_s,textValue_s,reference_s,reference_owner_s,spectrum_p1024"}
        rs =  solrquery_get(solr_url, params = params)
        if rs.status_code==200:
            x = StudyRaman.x4search()
            for doc in rs.json()["response"]["docs"]:
                y = doc["spectrum_p1024"]
                fig = Figure(figsize=figsize)
                axis = fig.add_subplot(1, 1, 1)
                axis.plot(x, y)
                axis.set_ylabel("a.u.")
                axis.set_xlabel("Raman shift [1/cm]")
                axis.title.set_text("{} {} {} ({})".format(extraprm,doc["name_s"],doc["reference_owner_s"],doc["reference_s"]))
                return fig
        else:
            return empty_figure(figsize,"{} {}".format(rs.status_code,rs.reason),"{}".format(domain.split("/")[-1]))

    except Exception as err:
        raise(err)
    finally:
        if not (rs is None):
            rs.close    

def solrquery_get(solr_url, params):
    headers = {}

    with AuthenticatedRequest(get_token):
        requests.get()

        return requests.get(solr_url, params = params, headers= headers)            