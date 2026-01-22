from io import BytesIO
import base64
import numpy as np
from numcompress import compress
import h5py
import h5pyd 
from rcapi.services.solr_query import (
    solr_query_get, SOLR_VECTOR, solr_doc_filter
    )
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
from matplotlib.patches import Circle, Rectangle, RegularPolygon, FancyBboxPatch, Ellipse, Polygon
import matplotlib.pyplot as plt  # noqa: E402
from rdkit import Chem
from rdkit.Chem import Draw, AllChem
from rdkit.DataStructs import ConvertToNumpyArray
from functools import reduce


x4search = np.linspace(140, 3*1024+140, num=2048)


def entity_icon(entity_type: str,
                title: str = "",
                figsize=(2, 2),
                title_fontsize=9,
                label_fontsize=8) -> Figure:
    """
    Generate a predefined symbolic matplotlib Figure for a given entity type,
    with both a title (top) and a central type label.

    Parameters
    ----------
    entity_type : str
        Entity type (e.g. 'AOP', 'Key Event', 'Assay', 'Chemical', etc.)
    title : str
        Title text displayed above the figure (optional)
    figsize : tuple
        Figure size in inches (width, height)
    title_fontsize : int
        Font size for the title text
    label_fontsize : int
        Font size for the central type label

    Returns
    -------
    matplotlib.figure.Figure
        Figure object (no canvas, suitable for streaming)
    """
    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(1, 1, 1)
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    entity = entity_type.lower().replace(" ", "_")
    text_inside = entity_type.upper()
    patches = []
    # --- define shape and color ---
    if entity == "aop":
        patches = [FancyBboxPatch((0.15, 0.35), 0.7, 0.3,
                               boxstyle="round,pad=0.1",
                               linewidth=2, edgecolor="steelblue", facecolor="lightblue")]
    elif entity in ("key_event", "ke"):
        patches = [Circle((0.5, 0.5), 0.25,
                       facecolor="orange", edgecolor="darkorange", linewidth=2)]
    elif entity == "assay":
        patches = [Polygon([[0.2, 0.1], [0.8, 0.1], [0.5, 0.8]], closed=True,
                        facecolor="mediumseagreen", edgecolor="seagreen", linewidth=2)]
    elif entity in ("chemical", "substance"):
        patches = [RegularPolygon((0.5, 0.5), numVertices=6, radius=0.25,
                               facecolor="violet", edgecolor="purple", linewidth=2)]
    elif entity in ("biological_object", "gene", "protein", "cell"):
        patches = [Ellipse((0.5, 0.5), 0.6, 0.35,
                        facecolor="turquoise", edgecolor="teal", linewidth=2)]
    elif entity in ("endpoint", "effect"):
        patches = [RegularPolygon((0.5, 0.5), numVertices=4, radius=0.3, orientation=0.785,
                               facecolor="lightcoral", edgecolor="red", linewidth=2)]
    elif entity == "prediction interval":
        text_inside = title
        title = "90% prediction interval"
        patches = [FancyBboxPatch((0.1, 0.3), 0.8, 0.4,
                           boxstyle="round,pad=0.12",
                           facecolor="none",          # important
                           edgecolor="firebrick",
                           linewidth=3,
                           linestyle="--"),
                    Rectangle((0.1, 0.35), 0.6, 0.1,
                            facecolor="firebrick",
                            alpha=0.35,
                            edgecolor="none")]
    elif entity == "prediction":
        text_inside = title
        title = "90% prediction set"
        patches = [FancyBboxPatch((0.1, 0.3), 0.8, 0.4,
                           boxstyle="round,pad=0.12",
                           facecolor="none",          # important
                           edgecolor="gray",
                           linewidth=3,
                           linestyle="--")]
        for x in [0.3, 0.5, 0.7]:
            patches.append(Circle((x, 0.25), 0.04,
                        facecolor="firebrick",
                        alpha=0.7,
                        edgecolor="none"))
    elif entity in ("model", "tool"):
        patches = [Rectangle((0.2, 0.3), 0.6, 0.4,
                          facecolor="lightgray", edgecolor="dimgray", linewidth=2)]
    else:
        patches = [Rectangle((0.2, 0.3), 0.6, 0.4,
                          facecolor="white", edgecolor="black", linewidth=1)]

    for patch in patches:
        ax.add_patch(patch)

    # --- main label (centered type) ---
    ax.text(0.5, 0.5, text_inside,
            ha="center", va="center", fontsize=label_fontsize, weight="bold")

    # --- title (optional, above figure) ---
    if title:
        ax.text(0.5, 0.92, title,
                ha="center", va="center", fontsize=title_fontsize)

    return fig


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


def plot_structure(smiles, title=None, thumbnail=True, figsize=None, **draw_kwargs):
    """
    Plot a 2D chemical structure from a SMILES string.

    Parameters
    ----------
    smiles : str
        SMILES representation of the molecule.
    title : str, optional
        Title of the plot.
    thumbnail : bool, default=True
        If True, hide title and axes for compact display.
    figsize : tuple, optional
        Size of the figure (in inches), default (4, 4).
    **draw_kwargs :
        Additional keyword arguments passed to RDKit's Draw.MolToImage.
    """

    if smiles is None:
        raise ValueError("No structure")
    if figsize is None:
        figsize = (4, 4)

    # Create molecule from SMILES
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")
    return plot_mol(mol, title, thumbnail, figsize, draw_kwargs)


def plot_mol(mol, title=None, thumbnail=True, figsize=None, **draw_kwargs):
    if mol is None:
        raise ValueError("No structure")
    if figsize is None:
        figsize = (4, 4)
    img = Draw.MolToImage(mol, size=(int(figsize[0]*100), int(figsize[1]*100)), **draw_kwargs)
    fig = Figure(figsize=figsize, constrained_layout=True)
    ax = fig.add_subplot(1, 1, 1)
    ax.imshow(img)
    ax.axis("off" if thumbnail else "on")
    if not thumbnail and title:
        ax.set_title(title)
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


def doc2spectrum(doc, extraprm, thumbnail, figsize):
    y = doc.get(SOLR_VECTOR, None)
    if y is None:
        # make this configurable
        y = doc.get("dense_b512", None)
        x = doc.get("dense_a512", None)
        if y is None and x is None:
            return None, None
        plot_kwargs = {"color": "#FF7F0E"}
        xtitle = ""
    else:
        x = x4search
        plot_kwargs = {}
        xtitle = r'wavenumber [$\mathrm{cm}^{-1}$]'
    _title = None if thumbnail else "{} {} {} ({})".format(
        "" if extraprm is None else extraprm,
        doc["name_s"], 
        doc["reference_owner_s"], doc["reference_s"])
    fig = plot_spectrum(x, y, _title, xtitle, "intensity [a.u.]",
                        figsize=figsize, thumbnail=thumbnail,
                        plot_kwargs=plot_kwargs)
    etag = generate_etag("{}{}{}".format(
        doc["textValue_s"], doc.get("updated_s",""), doc.get("_version_", "")))
    return fig, etag    


async def solr2image(solr_url: str, domain: str, figsize=(6, 4),
                     extraprm=None, thumbnail: bool = True,
                     collections: str = None,
                     token: str = None) -> Tuple[Figure, str]:
    rs = None
    try:
        query = domain
        if extraprm == "composition":
            params = {"q": query, "fq": [f"type_s:{extraprm}"], 
                            "fl": "id,type_s,chemname:ChemicalName_s,SMILES:SMILES_s,updated_s,_version_"}
        elif extraprm == "chemical":
            params = {"q": query, "fq": [f"type_s:{extraprm}"], 
                            "fl": "id,type_s,chemname:preferred_name_t,SMILES:SMILES_s,updated_s,_version_"}
        elif extraprm == "prediction":
            params = {"q": query, "fq": [f"type_s:{extraprm}"], 
                            "fl": "id,type_s,chemname:dsstox_id_s,attr_method,updated_s,_version_"}
        elif extraprm == "inventory":
            params = {"q": query, "fq": [f"type_s:{extraprm}"], 
                            "fl": "id,type_s,chemname:Name_s,SMILES:SMILES_x_s,_version_"}                
        else:
            if domain is None or domain.startswith("id:"):
                return entity_icon(entity_type=extraprm, title=f"{domain}", figsize=figsize), None
            else:
                query = "textValue_s:{}{}{}".format('"', domain, '"')
                params = {"q": query, "fq": [solr_doc_filter()], 
                        "fl": f"name_s,textValue_s,reference_s,reference_owner_s,{SOLR_VECTOR},updated_s,_version_,dense_a512,dense_b512"}
        if collections is not None:
            params["collection"] = collections

        rs = await solr_query_get(solr_url, params, token=token)
        if rs is not None and rs.status_code == 200:
            response_json = rs.json()
            if "response" in response_json:

                if response_json["response"]["numFound"] == 0:
                    return empty_figure(figsize, title="not found", label="{}".format(domain.split("/")[-1])), None
                elif extraprm in ["composition", "inventory", "chemical"]:
                    #print(response_json["response"]["docs"])
                    for doc in response_json["response"]["docs"]:
                        smiles = doc.get("SMILES", None)
                        chemname = doc.get("chemname", None)
                        if smiles is not None:
                            fig = plot_structure(
                                smiles=smiles,
                                title=chemname,
                                thumbnail=thumbnail, figsize=figsize)
                            etag = generate_etag(
                                "{}{}{}".format(doc["id"], doc.get("updated_s", ""),
                                                doc.get("_version_", "")))
                            return fig, etag
                        else:
                            return entity_icon(entity_type=extraprm, title=f"{chemname}", figsize=figsize), etag
                elif extraprm in ["study"]:
                    for doc in response_json["response"]["docs"]:
                        fig, etag = doc2spectrum(doc, extraprm=extraprm, thumbnail=thumbnail, figsize=figsize)
                        if fig is None:
                            continue
                        return fig, etag
                elif extraprm == "prediction":
                    for doc in response_json["response"]["docs"]: 
                        methods = doc.get("attr_method", None)
                        #chemname = doc.get("chemname", None)
                        etag = generate_etag("{}{}{}".format(
                            doc["id"], doc.get("updated_s",""), doc.get("_version_", "")))
                        return entity_icon(entity_type=extraprm, title=f"{methods}", figsize=figsize), etag
                    
                return empty_figure(figsize, title=extraprm, label=f"{domain}"), None                    
        return empty_figure(figsize, "{} {}".format(rs.status_code, getattr(rs, "reason", "")), "{}".format(domain.split("/")[-1])), None
    except Exception as err:
        traceback.format_exc()
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


def get_ecfp(mol):
    fp = AllChem.GetMorganFingerprintAsBitVect(
        mol,
        radius=2,        # ECFP4
        nBits=2048
    )
    arr = np.zeros((2048,), dtype=int)
    ConvertToNumpyArray(fp, arr)
    return arr


def read_molecule(file, file_name, n=1, prefix="rcapi_"):
    filename, file_extension = os.path.splitext(file_name)
    result_json = {}
    with tempfile.NamedTemporaryFile(delete=False,
                                     prefix=prefix,
                                     suffix=file_extension) as tmp:
        shutil.copyfileobj(file, tmp)
        native_filename = tmp.name
        print(native_filename)
    if file_extension == ".mol":
        mol = Chem.MolFromMolFile(native_filename)
    else:
        suppl = Chem.SmilesMolSupplier(native_filename)
        mols = [mol for mol in suppl if mol is not None][:n]
        mol = reduce(Chem.CombineMols, mols)
    combined_smiles = Chem.MolToSmiles(mol)
    px = 1 / plt.rcParams['figure.dpi']  # pixel in inches
    fig = plot_mol(mol, title=None, thumbnail=True, figsize=(320*px, 80*px))
    output = BytesIO()
    FigureCanvas(fig).print_png(output)
    base64_bytes = base64.b64encode(output.getvalue())
    result_json["imageLink"] = f"data:image/png;base64,{base64_bytes.decode('utf-8')}"
    result_json["smiles"] = combined_smiles
    result_json["cdf"] = compress(get_ecfp(mol).tolist(), precision=6)
    return result_json
    
