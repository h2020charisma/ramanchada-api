from pydantic import BaseSettings
import yaml
import os 

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