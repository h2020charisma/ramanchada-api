from fastapi.testclient import TestClient
import re
from rcapi.main import app
from pathlib import Path
import json
import warnings


TEST_JSON_PATH = Path(__file__).parent / "resources/templates/dose_response.json"

client = TestClient(app)
#warnings.warn("test")
#print("test")

def test_template():
    response = client.get("/template")
    assert response.status_code == 200
    assert response.json() == {"template" : []}

def get_task_result(response_post):
    assert response_post.status_code == 200, response_post.status_code
    task_json = response_post.json()
    result_uuid = task_json.get("result_uuid")
    assert result_uuid is not None, task_json
    return result_uuid

def test_upload_and_retrieve_json():
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