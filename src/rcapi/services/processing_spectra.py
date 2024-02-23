import os
from app.models.models import Task
from pynanomapper.datamodel.nexus_parser import SpectrumParser
from  pynanomapper.datamodel.nexus_spectra import peaks2nxdata
from ..config.app_config import initialize_dirs

#from ramanchada2.protocols.calibration import CalibrationModel

config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs()

def open_dataset(nexus_dataset_url: str,base_url: str):
    print(nexus_dataset_url,base_url)
    if nexus_dataset_url.startswith(base_url):
        uuid = nexus_dataset_url.split("/")[-1]
        spectrum_parser = SpectrumParser()
        spectrum_parser.parse(os.path.join(NEXUS_DIR,f"{uuid}.nxs"))
        return spectrum_parser
    else:
        return None

class ProcessMock:
    def process(task : Task,nexus_dataset_url: str,base_url: str):
        spectrum_parser : SpectrumParser = open_dataset(nexus_dataset_url,base_url)
        for key in spectrum_parser.parsed_objects:
            spe = spectrum_parser.parsed_objects[key]
            print("Spectrum data", key, spe)
            #spe.plot()     


class ProcessCalibrate:
    def process(task : Task,nexus_dataset_url: str,base_url: str):
        #calmodel = CalibrationModel(laser_wl)
        #calmodel.derive_model_x(spe_neon,spe_neon_units="cm-1",ref_neon=None,ref_neon_units="nm",spe_sil=None,spe_sil_units="cm-1",ref_sil=None,ref_sil_units="cm-1")
        pass
       

class ProcessFindPeak:
    def process(task : Task,nexus_dataset_url: str,base_url: str):
        spectrum_parser : SpectrumParser = open_dataset(nexus_dataset_url,base_url)
        for key in spectrum_parser.parsed_objects:
            spe = spectrum_parser.parsed_objects[key]
            print("Spectrum data", key, spe)
            peak_candidates = spe.find_peak_multipeak(sharpening='hht', strategy='topo')
            fitres = spe.fit_peak_multimodel(profile='Moffat', candidates=peak_candidates, no_fit=True)
            print(fitres.to_dataframe_peaks())