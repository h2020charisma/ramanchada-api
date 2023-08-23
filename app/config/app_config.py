from pydantic import BaseSettings
import yaml
import os 
from pathlib import Path 
import shutil

class AppConfig(BaseSettings):
    upload_dir: str
    nmparse_url: str 
    
#    class Config:
#        env_file = ".env"  # Optional: Load configuration from an .env file

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),  "config.yaml")
    print(config_path)
    yaml_config = os.environ.get("RAMANCHADA_API_CONFIG")
    if yaml_config is None:
        yaml_config = "config/config.yaml"
    config_dict = {}
    with open(yaml_config, "r") as config_file:
        config_dict = yaml.safe_load(config_file)
    return AppConfig(**config_dict)

def migrate_dir(UPLOAD_DIR,NEXUS_DIR):
    for filename in Path(UPLOAD_DIR).glob('*.nxs'):
        shutil.move(filename, NEXUS_DIR)

def initialize_dirs(migrate=False):
    config = load_config()
    UPLOAD_DIR = config.upload_dir
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    NEXUS_DIR = os.path.join(UPLOAD_DIR,"NEXUS")
    os.makedirs(NEXUS_DIR, exist_ok=True)
    TEMPLATE_DIR = os.path.join(UPLOAD_DIR,"TEMPLATES")
    os.makedirs(TEMPLATE_DIR, exist_ok=True)    
    if migrate:
        migrate_dir(UPLOAD_DIR,NEXUS_DIR)
    return config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR

