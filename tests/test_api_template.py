from fastapi.testclient import TestClient
from rcapi.main import app
from pathlib import Path
import json
import warnings
import pytest
from importlib import resources
import yaml
import os.path 
import shutil
from datetime import datetime, timedelta
import pandas as pd
from rcapi.api.templates import fetch_materials

#from unittest import TestCase

TEST_DEFAULT_PATH = Path(__file__).parent / "resources/templates/dose_response.json"
TEST_INVALID_PATH = Path(__file__).parent / "resources/templates/null.json"
TEST_NONAME_PATH = Path(__file__).parent / "resources/templates/dose_response_noname.json"
TEST_RAMAN_PATH = Path(__file__).parent / "resources/templates/raman.json"

TEMPLATE_UUID_RAMAN = "a282b2c4-8dfe-4cca-9bcd-1d276a23bb4e"
TEMPLATE_UUID = "3c22a1f0-a933-4855-848d-05fcc26ceb7a"
TEMPLATE_UUID_invalid = "3c22a1f0-a933-4855-848d-05fcc26ceb7b"
TEMPLATE_UUID_noname = "3c22a1f0-a933-4855-848d-05fcc26ceb7c"

_TEMPLATES =  [ (TEST_DEFAULT_PATH,TEMPLATE_UUID),
                (TEST_INVALID_PATH,TEMPLATE_UUID_invalid),
                (TEST_NONAME_PATH,TEMPLATE_UUID_noname),
                (TEST_RAMAN_PATH,TEMPLATE_UUID_RAMAN)
               ]

client = TestClient(app)
#warnings.warn("test")


@pytest.fixture(scope="module")
def config_dict():
    print("\nModule-level setup: Loading config or other resources")
    config_path = resources.as_file(
        resources.files('rcapi.config').joinpath('config.yaml')
    )
    with config_path as p:
        with p.open() as f:
            CONFIG_DICT = yaml.safe_load(f)
            assert "upload_dir" in CONFIG_DICT,CONFIG_DICT
    return CONFIG_DICT

@pytest.fixture(scope="module")
def get_good_templates():
    return [(TEST_DEFAULT_PATH,TEMPLATE_UUID)]

@pytest.fixture(scope="module")
def get_bad_templates():
    return [(TEST_INVALID_PATH,TEMPLATE_UUID_invalid),(TEST_NONAME_PATH,TEMPLATE_UUID_noname)]

@pytest.fixture
def clean_template_dir(config_dict):
    print("\nSetting up resources before the test")
    TEMPLATE_DIR = os.path.join(config_dict["upload_dir"],"TEMPLATES")
    remove_files_in_folder(TEMPLATE_DIR)
    # Perform setup operations here, if any
    #yield  # This is where the test runs
    #print("\nCleaning up resources after the test")
    #remove_files_in_folder(TEMPLATE_DIR)
    # Perform cleanup operations here, if any

@pytest.fixture
def setup_template_dir(config_dict):
    print("\nSetting up resources before the test")
    TEMPLATE_DIR = os.path.join(config_dict["upload_dir"],"TEMPLATES")
    remove_files_in_folder(TEMPLATE_DIR)
    for TEST_JSON_PATH,TEMPLATE_UUID in _TEMPLATES:
        print(TEST_JSON_PATH)
        file_path = os.path.join(TEMPLATE_DIR,"{}.json".format(TEMPLATE_UUID))
        shutil.copy(TEST_JSON_PATH,file_path )
        new_modified_date = datetime.now() - timedelta(hours=24)
        timestamp = new_modified_date.timestamp()
        os.utime(file_path, times=(timestamp, timestamp))
        now_date = datetime.utcnow() - timedelta(hours=12)
        #headers = {"If-Modified-Since": now_date.strftime("%a, %d %b %Y %H:%M:%S GMT")}
        assert new_modified_date <= now_date,new_modified_date
    # Perform setup operations here, if any
    #yield  # This is where the test runs
    #print("\nCleaning up resources after the test")
    #remove_files_in_folder(TEMPLATE_DIR)
    # Perform cleanup operations here, if any
    return TEMPLATE_DIR


def remove_files_in_folder(folder_path):
    folder_path = Path(folder_path)
    file_list = folder_path.glob('*')
    for file_path in file_list:
        try:
            if file_path.is_file():
                file_path.unlink()
                #print(f"Removed file: {file_path}")
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
    with open(TEST_DEFAULT_PATH, "rb") as file:
        json_content = json.load(file)
    response_upload = client.post("/template", json=json_content)
    result_uuid = get_task_result(response_upload)
    # Step 2: Retrieve JSON using the result_uuid
    response_retrieve = client.get(f"/template/{result_uuid}")
    assert response_retrieve.status_code == 200, response_retrieve.status_code
    retrieved_json = response_retrieve.json()
    # Step 3: Compare uploaded and retrieved JSON
    with open(TEST_DEFAULT_PATH, "r") as file:
        expected_json = json.load(file)
    assert retrieved_json == expected_json    


def test_gettemplate(setup_template_dir):
    # Step 1: get predefined JSON
    response_retrieve = client.get("/template/{}".format(TEMPLATE_UUID))
    assert response_retrieve.status_code == 200, response_retrieve.status_code
    retrieved_json = response_retrieve.json()
    # Step 1: Compare predefined and retrieved JSON
    with open(TEST_DEFAULT_PATH, "r") as file:
        expected_json = json.load(file)
    assert retrieved_json == expected_json        


def test_gettemplate_notmodified(setup_template_dir):
    modified_date = datetime.utcnow() - timedelta(hours=12)
    headers = {"If-Modified-Since": modified_date.strftime("%a, %d %b %Y %H:%M:%S GMT")}
    response_retrieve = client.get("/template",headers=headers)
    assert response_retrieve.status_code == 304,response_retrieve.content


def test_gettemplateuuid_notmodified(setup_template_dir):
    modified_date = datetime.utcnow() - timedelta(hours=12)
    headers = {"If-Modified-Since": modified_date.strftime("%a, %d %b %Y %H:%M:%S GMT")}
    response_retrieve = client.get("/template/{}".format(TEMPLATE_UUID),headers=headers)
    assert response_retrieve.status_code == 304,response_retrieve.content

def test_makecopy(setup_template_dir):
    # Step 1: make copy JSON
    response_copy = client.post("/template/{}/copy".format(TEMPLATE_UUID))
    result_uuid = get_task_result(response_copy)
    # Step 2: Retrieve JSON using the result_uuid
    response_retrieve = client.get(f"/template/{result_uuid}")
    assert response_retrieve.status_code == 200, response_retrieve.status_code
    retrieved_json = response_retrieve.json()
    # Step 3: Compare uploaded and retrieved JSON
    with open(TEST_DEFAULT_PATH, "r") as file:
        expected_json = json.load(file)
        expected_json["origin_uuid"] = TEMPLATE_UUID
    assert retrieved_json == expected_json , retrieved_json      

def test_makecopy_finalized(setup_template_dir):
    tag_finalized="confirm_statuschange"
    # Step 1: make copy JSON
    response_copy = client.post("/template/{}/copy".format(TEMPLATE_UUID_noname))
    result_uuid = get_task_result(response_copy)
    # Step 2: Retrieve JSON using the result_uuid
    response_retrieve = client.get(f"/template/{result_uuid}")
    assert response_retrieve.status_code == 200, response_retrieve.status_code
    retrieved_json = response_retrieve.json()
    assert tag_finalized in retrieved_json
    assert "DRAFT" in retrieved_json[tag_finalized]
    assert "DRAFT" == retrieved_json["template_status"]
    # Step 3: Compare uploaded and retrieved JSON
    expected_json = None
    with open(TEST_NONAME_PATH, "r") as file:
        expected_json = json.load(file)
        expected_json["origin_uuid"] = TEMPLATE_UUID_noname
        assert tag_finalized in expected_json
        assert "FINALIZED" in expected_json[tag_finalized], f"{tag_finalized} should be in the original file"
        assert "FINALIZED" in expected_json["template_status"]
        expected_json[tag_finalized] = ["DRAFT"]
        expected_json["template_status"] = "DRAFT"
    assert expected_json == retrieved_json 
    #TestCase().assertDictEqual(retrieved_json, expected_json) 

    

def test_doseresponse_excel(setup_template_dir):
    modified_date = datetime.utcnow() - timedelta(hours=12)
    headers = {"If-Modified-Since": modified_date.strftime("%a, %d %b %Y %H:%M:%S GMT")}
    #we ignore the header, want to generate the file on-the-fly
    response_xlsx = client.get("/template/{}?format=xlsx&project=nanoreg".format(TEMPLATE_UUID),headers=headers)
    assert response_xlsx.status_code == 200, response_xlsx.headers
    #print(response_xlsx.headers)
    save_path = os.path.join(setup_template_dir, '{}.xlsx'.format(TEMPLATE_UUID))
    with open(save_path, 'wb') as file:
        file.write(response_xlsx.content)    
    df = pd.read_excel(save_path, sheet_name='Materials')
    assert df.shape[0]>0,"materials"

def test_raman_excel(setup_template_dir):
    modified_date = datetime.utcnow() - timedelta(hours=12)
    headers = {"If-Modified-Since": modified_date.strftime("%a, %d %b %Y %H:%M:%S GMT")}
    #we ignore the header, want to generate the file on-the-fly
    response_xlsx = client.get("/template/{}?format=xlsx&project=charisma".format(TEMPLATE_UUID_RAMAN),headers=headers)
    assert response_xlsx.status_code == 200, response_xlsx.headers
    #print(response_xlsx.headers)
    save_path = os.path.join(setup_template_dir, '{}.xlsx'.format(TEMPLATE_UUID_RAMAN))
    with open(save_path, 'wb') as file:
        file.write(response_xlsx.content)    
    df = pd.read_excel(save_path, sheet_name='Materials')
    assert df.shape[0]>0,"materials"

def test_doseresponse_nmparser(setup_template_dir):
    modified_date = datetime.utcnow() - timedelta(hours=12)
    headers = {"If-Modified-Since": modified_date.strftime("%a, %d %b %Y %H:%M:%S GMT")}
    #we ignore the header, want to generate the file on-the-fly
    response_nmparser = client.get("/template/{}?format=nmparser".format(TEMPLATE_UUID),headers=headers)
    assert response_nmparser.status_code == 200, response_nmparser.headers
    print(response_nmparser.headers)
    save_path = os.path.join(setup_template_dir, '{}.json.nmparser'.format(TEMPLATE_UUID))
    with open(save_path, 'wb') as file:
        file.write(response_nmparser.content)          

def delete_template(_uuid,expected_response=404):
    _template = "/template/{}".format(_uuid)
    response_delete = client.delete(_template)
    assert response_delete.status_code == 200, response_delete.status_code
    task_json = response_delete.json()
    result_uuid = task_json.get("result_uuid")
    assert result_uuid is None, task_json
    response = client.get(_template)
    assert response.status_code == expected_response, response.status_code
    #assert response.json() == {"template" : []}, response.json() 


def test_delete(setup_template_dir):
    delete_template(TEMPLATE_UUID)

def test_delete_invalidjson(setup_template_dir):
    delete_template(TEMPLATE_UUID_invalid)

def test_delete_noname(setup_template_dir):
    #this is a finalized template, should not be deleted
    delete_template(TEMPLATE_UUID_noname,200)

def test_getmaterials():
    materials = fetch_materials("nanoreg")
    assert len(materials)>0
