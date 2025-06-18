import tempfile
import os
import yaml
import pytest

from rcapi.config.app_config import load_config, AppConfig


@pytest.fixture
def temp_config_file():
    config_data = {
        'upload_dir': '/tmp/uploads',
        'nmparse_url': 'http://localhost:8080/nmparse',
        'SOLR_COLLECTIONS': {
            'default': 'custom_public_1',
            'public': [
                {'name': 'custom_public_1', 'description': 'Public 1'},
                {'name': 'custom_public_2', 'description': 'Public 2'}
            ],
            'private': [
                {'name': 'custom_private_1', 'description': 'Private 1'},
                {'name': 'custom_private_2', 'description': 'Private 2'}
            ]
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

    # Default collection
    assert config.SOLR_COLLECTIONS.default == 'custom_public_1'

    # Public collections
    assert len(config.SOLR_COLLECTIONS.public) == 2
    assert config.SOLR_COLLECTIONS.public[0].name == 'custom_public_1'
    assert config.SOLR_COLLECTIONS.public[0].description == 'Public 1'
    assert config.SOLR_COLLECTIONS.public[1].name == 'custom_public_2'
    assert config.SOLR_COLLECTIONS.public[1].description == 'Public 2'

    # Private collections
    assert len(config.SOLR_COLLECTIONS.private) == 2
    assert config.SOLR_COLLECTIONS.private[0].name == 'custom_private_1'
    assert config.SOLR_COLLECTIONS.private[0].description == 'Private 1'
    assert config.SOLR_COLLECTIONS.private[1].name == 'custom_private_2'
    assert config.SOLR_COLLECTIONS.private[1].description == 'Private 2'

    # Defaults
    assert config.SOLR_ROOT == "https://solr-kc.ideaconsult.net/solr/"
    assert config.SOLR_VECTOR == "spectrum_p1024"
