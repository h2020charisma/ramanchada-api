from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field
from typing import List, Dict, Set
import yaml
import os
from importlib import resources
from pathlib import Path
import shutil


class SolrCollectionEntry(BaseModel):
    name: str
    description: str
    roles: List[str] = Field(default_factory=list)


class SolrCollectionSettings(BaseModel):
    default: str = "charisma"
    collections: List[SolrCollectionEntry] = Field(default_factory=list)

    def all_roles(self) -> Set[str]:
        """Return a set of all roles used across all collections."""
        return {
            role
            for collection in self.collections
            for role in collection.roles
        }

    def for_roles(self, user_roles: List[str]) -> List[SolrCollectionEntry]:
        """Return collections accessible to any of the given user roles."""
        user_role_set = set(user_roles)
        return [
            c for c in self.collections
            if user_role_set.intersection(c.roles)
        ]

    def by_role(self) -> Dict[str, List[SolrCollectionEntry]]:
        """Index collections by role for quick lookup."""
        role_map: Dict[str, List[SolrCollectionEntry]] = {}
        for collection in self.collections:
            for role in collection.roles:
                role_map.setdefault(role, []).append(collection)
        return role_map

    def public_collections(self) -> List[SolrCollectionEntry]:
        """Convenience shortcut for public-accessible collections."""
        return self.for_roles(["public"])

    
class KeycloakConfig(BaseModel):
    SERVER_URL: str
    REALM_NAME: str
    CLIENT_ID: str
    CLIENT_SECRET: str


class AppConfig(BaseSettings):
    upload_dir: str
    nmparse_url: str
    SOLR_ROOT: str = "https://solr-kc.ideaconsult.net/solr/"
    SOLR_VECTOR: str = "spectrum_p1024"
    SOLR_COLLECTIONS: SolrCollectionSettings = SolrCollectionSettings()
    KEYCLOAK: KeycloakConfig

    @classmethod
    def from_yaml(cls, path: str) -> "AppConfig":
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)


def load_config():
    config_dict = {}
    yaml_config = os.environ.get("RAMANCHADA_API_CONFIG")
    if yaml_config is None:
        config_path = resources.as_file(
            resources.files('rcapi.config').joinpath('config.yaml')
        )
        with config_path as p:
            with p.open() as f:
                config_dict = yaml.safe_load(f)
    else:
        with open(yaml_config, "r") as config_file:
            config_dict = yaml.safe_load(config_file)
    return AppConfig(**config_dict)


def migrate_dir(UPLOAD_DIR, NEXUS_DIR):
    for filename in Path(UPLOAD_DIR).glob('*.nxs'):
        shutil.move(filename, NEXUS_DIR)


def initialize_dirs(migrate=False):
    config = load_config()
    UPLOAD_DIR = config.upload_dir
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    NEXUS_DIR = os.path.join(UPLOAD_DIR, "NEXUS")
    os.makedirs(NEXUS_DIR, exist_ok=True)
    TEMPLATE_DIR = os.path.join(UPLOAD_DIR, "TEMPLATES")
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    if migrate:
        migrate_dir(UPLOAD_DIR, NEXUS_DIR)
    return config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR
