import tempfile
import os
import yaml
import pytest

from rcapi.config.app_config import load_config, AppConfig, SolrCollectionEntry


@pytest.fixture
def temp_config_file():
    config_data = {
        'upload_dir': '/tmp/uploads',
        'nmparse_url': 'http://localhost:8080/nmparse',
        'SOLR_COLLECTIONS': {
            'default': 'custom_public_1',
            'collections': [
                {'name': 'custom_public_1', 'description': 'Public 1', 'roles': ['public']},
                {'name': 'custom_public_2', 'description': 'Public 2', 'roles': ['public']},
                {'name': 'custom_private_1', 'description': 'Private 1', 'roles': ['private']},
                {'name': 'custom_private_2', 'description': 'Private 2', 'roles': ['private']}
            ],
        },
        "KEYCLOAK": {
            "SERVER_URL": "https://example.org/",
            "REALM_NAME": "test",
            "CLIENT_ID": "test",
            "CLIENT_SECRET": "secret"
        }
    }

    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.yaml') as temp_file:
        yaml.dump(config_data, temp_file)
        temp_file_path = temp_file.name

    os.environ['RAMANCHADA_API_CONFIG'] = temp_file_path
    yield temp_file_path

    os.unlink(temp_file_path)
    del os.environ['RAMANCHADA_API_CONFIG']


def test_load_config(temp_config_file):
    config = load_config()

    assert isinstance(config, AppConfig)
    assert config.upload_dir == '/tmp/uploads'
    assert config.nmparse_url == 'http://localhost:8080/nmparse'
    assert config.SOLR_COLLECTIONS.default == 'custom_public_1'

    collections = config.SOLR_COLLECTIONS.collections
    assert isinstance(collections, list)
    assert all(isinstance(c, SolrCollectionEntry) for c in collections)

    # Validate expected structure
    assert len(collections) == 4

    # Index by name for convenience
    name_map = {c.name: c for c in collections}

    assert name_map['custom_public_1'].description == 'Public 1'
    assert 'public' in name_map['custom_public_1'].roles

    assert name_map['custom_private_2'].description == 'Private 2'
    assert 'private' in name_map['custom_private_2'].roles

    # Validate role-based lookup
    public = config.SOLR_COLLECTIONS.for_roles(['public'])
    assert len(public) == 2
    assert {c.name for c in public} == {'custom_public_1', 'custom_public_2'}

    private = config.SOLR_COLLECTIONS.for_roles(['private'])
    assert len(private) == 2
    assert {c.name for c in private} == {'custom_private_1', 'custom_private_2'}

    public_and_private = config.SOLR_COLLECTIONS.for_roles(['public', 'private'])
    assert len(public_and_private) == 4

    assert config.SOLR_ROOT == "https://solr-kc.ideaconsult.net/solr/"
    assert config.SOLR_VECTOR == "spectrum_p1024"
