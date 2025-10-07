from io import BytesIO
import base64
import numpy as np
from numcompress import compress
import h5py
import h5pyd 
from rcapi.services.solr_query import solr_query_get, SOLR_VECTOR
import traceback
import tempfile
import shutil
from ramanchada2.spectrum import from_local_file
import os
import hashlib
from typing import Tuple
import ramanchada2 as rc2
import numpy.typing as npt
from scipy.interpolate import Akima1DInterpolator
import matplotlib  # noqa: E402
matplotlib.use('Agg')
from matplotlib.backends.backend_agg import (  # noqa: E402
    FigureCanvasAgg as FigureCanvas)
from matplotlib.figure import Figure  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

x4search = np.linspace(140, 3*1024+140, num=2048)


def empty_figure(figsize, title, label) -> Figure:
    fig = Figure(figsize=figsize)
    axis = fig.add_subplot(1, 1, 1)
    axis.axis('off')
       #axis.set_xticks([])
        #axis.set_yticks([])
    axis.scatter([0,1],[0,0],s=0)
    axis.annotate(label, (0,0))
    axis.title.set_fontsize(8)
    axis.set_title(title)
    return fig


def dict2figure(pm, figsize) -> Figure:
    fig = Figure(figsize=figsize)
    axis = fig.add_subplot(1, 1, 1)
    n = 0
    for key in pm:
        if key == "domain" or key == "id" or key == "score":
            continue
        if type(pm[key]) == str:
            n = n+1
    score = float(pm["score"])
       #axis.bar(["score"],[score],width=0.1)
        #axis.bar(["score"],[1-score],width=0.1)
    y = np.arange(0, n)
    x = np.repeat(0, n)

    axis.scatter(x, y, s=0)
    axis.axis('off')
    i = 0
    clr = {"high" : "r", "medium" : "y", "low" : "g", "fulfilled" : "b", "not fulfilled" : "c"}
    for key in pm:
        if key == "domain" or key == "id" or key == "score":
            continue
        if type(pm[key]) == str:
            try:
                color = clr[pm[key]]
            except Exception:
                color = "k"
            axis.annotate("{}: {}".format(key.replace("_s", ""), pm[key]), (0,i), color=color)
            i = i+1
    axis.title.set_fontsize(8)
    axis.set_xlim(0, 1)
    axis.set_title(pm["domain"])
    return fig


def knnquery(domain, dataset="raw"):
    try:
        with h5pyd.File(domain, mode="r") as h5:
            x = h5[dataset][0]
            y = h5[dataset][1]
            spe = rc2.spectrum.Spectrum(x, y)
            spe_processed = preprocess_spectrum(spe, x4search, baseline=False)
            result_json = {}
            result_json["cdf"] = compress(spe_processed.y.tolist(), precision=6)
            # result_json["pdf"] = compress(pdf.tolist(),precision=6)
            # return ','.join(map(str, cdf))
            try:
                px = 1/plt.rcParams['figure.dpi']  # pixel in inches
                fig = plot_spectrum(x, y, "query", 
                                    h5[dataset].dims[0]. label,
                                    h5[dataset].dims[1].label,
                                    figsize=(300*px, 200*px),
                                    thumbnail=True, 
                                    plot_kwargs={'color': 'green'})
                output = BytesIO()
                FigureCanvas(fig).print_png(output)
                base64_bytes = base64.b64encode(output.getvalue())
                result_json["imageLink"] = "data:image/png;base64,{}".format(str(base64_bytes, 'utf-8'))
            except Exception as err:
                print(err)
            return result_json
    except Exception as err:
        raise err


def plot_spectrum(x, y, title=None, xlabel=None, ylabel=None, thumbnail=True, figsize=None, plot_kwargs=None):
    if figsize is None:
        figsize = (6, 4)
    if xlabel is None:
        xlabel = r'wavenumber [$\mathrm{cm}^{-1}$]'
    if ylabel is None:
        ylabel = "intensity [a.u.]"
    fig = Figure(figsize=figsize, constrained_layout=True)
    if plot_kwargs is None:
        plot_kwargs = {}
    axis = fig.add_subplot(1, 1, 1)
    axis.plot(x, y, **plot_kwargs)
    axis.set_xlabel(xlabel)
    plt.subplots_adjust(bottom=0.1)                  
    if not thumbnail:
        axis.title.set_text(title)
        axis.set_ylabel(ylabel)
    else:
        axis.set_yticks([])
        axis.set_yticklabels([]) 
    return fig


def resample_spline(spe: rc2.spectrum.Spectrum, x4search: npt.NDArray):
    spline = Akima1DInterpolator(spe.x, spe.y)
    spe_spline = np.zeros_like(x4search)
    xmin, xmax = spe.x.min(), spe.x.max()
    within_range = (x4search >= xmin) & (x4search <= xmax)
    spe_spline[within_range] = spline(x4search[within_range])
    return rc2.spectrum.Spectrum(x=x4search, y=spe_spline)


def preprocess_spectrum(spe:  rc2.spectrum.Spectrum, x4search: npt.NDArray, baseline=False):
    spe_nopedestal = rc2.spectrum.Spectrum(x=spe.x, y=spe.y - np.min(spe.y))
    spe_resampled = resample_spline(spe_nopedestal, x4search)
    # baseline 
    if baseline:
        spe_resampled = spe_resampled.subtract_baseline_rc1_snip(niter=40)  
    # L2 norm for searching
    l2_norm = np.linalg.norm(spe_resampled.y)

    return rc2.spectrum.Spectrum(x4search, spe_resampled.y / l2_norm)


def generate_etag(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()


async def solr2image(solr_url: str, domain: str, figsize=(6, 4),
                     extraprm=None, thumbnail: bool = True,
                     collections: str = None,
                     token: str = None) -> Tuple[Figure, str]:
    rs = None
    try:
        query = "textValue_s:{}{}{}".format('"', domain, '"')
        params = {"q": query, "fq": ["type_s:study"], 
                  "fl": f"name_s,textValue_s,reference_s,reference_owner_s,{SOLR_VECTOR},updated_s,_version_,dense_a512,dense_b512"}
        if collections is not None:
            params["collection"] = collections
        rs = await solr_query_get(solr_url, params, token=token)
        if rs is not None and rs.status_code == 200:
            response_json = rs.json()
            # print(response_json)
            if "response" in response_json:
                if response_json["response"]["numFound"] == 0:
                    return empty_figure(figsize, title="not found", label="{}".format(domain.split("/")[-1])), None
                x = None
                for doc in response_json["response"]["docs"]:
                    y = doc.get(SOLR_VECTOR, None)
                    if y is None:
                        y = doc.get("dense_b512", None)
                        x = doc.get("dense_a512", None)
                        if y is None and x is None:
                            continue
                        plot_kwargs={"color": "#FF7F0E"}
                        xtitle = ""
                    else:
                        x = x4search
                        plot_kwargs={}
                        xtitle = r'wavenumber [$\mathrm{cm}^{-1}$]'

                    _title = None if thumbnail else "{} {} {} ({})".format(
                        "" if extraprm is None else extraprm,
                        doc["name_s"], 
                        doc["reference_owner_s"], doc["reference_s"])
                    fig = plot_spectrum(x, y, _title, xtitle, "intensity [a.u.]",
                                        figsize=figsize, thumbnail=thumbnail, plot_kwargs=plot_kwargs)
                    etag = generate_etag("{}{}{}".format(doc["textValue_s"],
                            doc.get("updated_s",""), doc.get("_version_", "")))
                    return fig, etag
        return empty_figure(figsize, "{} {}".format(rs.status_code, getattr(rs, "reason", "")), "{}".format(domain.split("/")[-1])), None
    except Exception as err:
        print(traceback.format_exc())
        return empty_figure(figsize, title="{}".format(err), 
                            label="{}".format(domain.split("/")[-1])), None
    finally:
        if rs is not None:
            await rs.aclose()


def recursive_copy(
    src_group: h5py.Group | h5pyd.Group, dst_group: h5py.Group | h5pyd.Group, 
    level=0
):
    # every File instance is also an HDF5 group
    # Copy attributes of the current group
    for attr_name, attr_value in src_group.attrs.items():
        dst_group.attrs[attr_name] = attr_value    
    for index, key in enumerate(src_group):
        try:
            item = src_group[key]
            if isinstance(item, (h5py.Group, h5pyd.Group)):
                # Create the group in the destination file
                new_group = dst_group.create_group(key)
                recursive_copy(item, new_group, level+1)
            elif isinstance(item, (h5py.Dataset, h5pyd.Dataset)):
                if item.shape == ():  # Scalar dataset
                    # Copy the scalar value directly
                    dst_dataset = dst_group.create_dataset(key, data=item[()])
                else:
                    # Copy the dataset to the destination file
                    dst_dataset = dst_group.create_dataset(key, data=item[:])
                for attr_name, attr_value in item.attrs.items():
                    dst_dataset.attrs[attr_name] = attr_value
                # dst_dataset.flush()
        except Exception:
            print(traceback.format_exc())


def read_spectrum_native(file, file_name, prefix="rcapi_"):
    native_filename = None
    try:
        filename, file_extension = os.path.splitext(file_name)
        # because rc2 works with file paths only, no url nor file objects
        with tempfile.NamedTemporaryFile(delete=False,
                                         prefix=prefix,
                                         suffix=file_extension) as tmp:
            shutil.copyfileobj(file, tmp)
            native_filename = tmp.name
        spe = from_local_file(native_filename)
        return spe
    except Exception as err:
        raise err
    finally:
        if native_filename != None:
            os.remove(native_filename)