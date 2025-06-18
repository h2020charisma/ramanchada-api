import unittest
import tempfile
import os
import yaml

from rcapi.config.app_config import load_config, AppConfig 


class TestAppConfig(unittest.TestCase):
    def setUp(self):
        # Create a temporary YAML config file matching the nested structure
        self.temp_config = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.yaml')
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
        yaml.dump(config_data, self.temp_config)
        self.temp_config.close()  # Important on Windows
        os.environ['RAMANCHADA_API_CONFIG'] = self.temp_config.name

    def tearDown(self):
        os.unlink(self.temp_config.name)
        del os.environ['RAMANCHADA_API_CONFIG']

    def test_load_config(self):
        config = load_config()

        self.assertIsInstance(config, AppConfig)
        self.assertEqual(config.upload_dir, '/tmp/uploads')
        self.assertEqual(config.nmparse_url, 'http://localhost:8080/nmparse')

        # Check default collection
        self.assertEqual(config.SOLR_COLLECTIONS.default, 'custom_public_1')

        # Check public collections
        self.assertEqual(len(config.SOLR_COLLECTIONS.public), 2)
        self.assertEqual(
            config.SOLR_COLLECTIONS.public[0].name, 'custom_public_1')
        self.assertEqual(
            config.SOLR_COLLECTIONS.public[0].description, 'Public 1')
        self.assertEqual(
            config.SOLR_COLLECTIONS.public[1].name, 'custom_public_2')
        self.assertEqual(
            config.SOLR_COLLECTIONS.public[1].description, 'Public 2')

        # Check private collections
        self.assertEqual(len(config.SOLR_COLLECTIONS.private), 2)
        self.assertEqual(
            config.SOLR_COLLECTIONS.private[0].name, 'custom_private_1')
        self.assertEqual(
            config.SOLR_COLLECTIONS.private[0].description, 'Private 1')
        self.assertEqual(
            config.SOLR_COLLECTIONS.private[1].name, 'custom_private_2')
        self.assertEqual
        (config.SOLR_COLLECTIONS.private[1].description, 'Private 2')

        # Check default values
        self.assertEqual(
            config.SOLR_ROOT, "https://solr-kc.ideaconsult.net/solr/")
        self.assertEqual(config.SOLR_VECTOR, "spectrum_p1024")


if __name__ == '__main__':
    unittest.main()
