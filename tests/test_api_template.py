from fastapi.testclient import TestClient
import re
from rcapi.main import app
from pathlib import Path
import json
import warnings
import pytest
from importlib import resources
import yaml
import os.path 
TEST_JSON_PATH = Path(__file__).parent / "resources/templates/dose_response.json"

client = TestClient(app)
#warnings.warn("test")


@pytest.fixture(scope="module")
def config_dict():
    print("\nModule-level setup: Loading config or other resources")
    with resources.path('rcapi.config', 'config.yaml') as config_path:
        with open(config_path, 'r') as config_file:
            CONFIG_DICT = yaml.safe_load(config_file)
            assert "upload_dir" in CONFIG_DICT,CONFIG_DICT
    return CONFIG_DICT

@pytest.fixture
def clean_template_dir(config_dict):
    print("\nSetting up resources before the test")
    TEMPLATE_DIR = os.path.join(config_dict["upload_dir"],"TEMPLATES")
    print(TEMPLATE_DIR)
    remove_files_in_folder(TEMPLATE_DIR)
    # Perform setup operations here, if any
    yield  # This is where the test runs
    print("\nCleaning up resources after the test")
    remove_files_in_folder(TEMPLATE_DIR)
    # Perform cleanup operations here, if any

def remove_files_in_folder(folder_path):
    folder_path = Path(folder_path)
    file_list = folder_path.glob('*')
    for file_path in file_list:
        try:
            if file_path.is_file():
                file_path.unlink()
                print(f"Removed file: {file_path}")
        except Exception as e:
            print(f"Error removing file {file_path}: {e}")

def test_template(clean_template_dir):
    response = client.get("/template")
    assert response.status_code == 200
    assert response.json() == {"template" : []}

def get_task_result(response_post):
    assert response_post.status_code == 200, response_post.status_code
    task_json = response_post.json()
    result_uuid = task_json.get("result_uuid")
    assert result_uuid is not None, task_json
    return result_uuid

def test_upload_and_retrieve_json(clean_template_dir):
    # Step 1: Upload JSON
    json_content = {}
    with open(TEST_JSON_PATH, "rb") as file:
        json_content = json.load(file)
    response_upload = client.post("/template", json=json_content)
    result_uuid = get_task_result(response_upload)
    # Step 2: Retrieve JSON using the result_uuid
    response_retrieve = client.get(f"/template/{result_uuid}")
    assert response_retrieve.status_code == 200, response_retrieve.status_code
    retrieved_json = response_retrieve.json()
    # Step 3: Compare uploaded and retrieved JSON
    with open(TEST_JSON_PATH, "r") as file:
        expected_json = json.load(file)
    assert retrieved_json == expected_json    