from fastapi.testclient import TestClient
from rcapi.main import app
import pytest
import h5py, h5pyd
import tempfile
from os import remove
import base64
from io import BytesIO
import importlib.resources
from ramanchada2.spectrum import from_local_file 

client = TestClient(app)

@pytest.fixture(scope="module")
def domain():
    params = { "query_type" : "metadata" , "pagesize" : 1} 
    response = client.get("/query",params=params)
    assert response.status_code == 200
    _domain = response.json()[0]["value"]
    return _domain



def test_access_domain(domain):
    print(h5pyd.__version__)
    print(domain)
    with h5pyd.File(domain) as top_group:
        for index,key in enumerate(top_group):
            print(index,key)

def test_download_domain(domain):
    params = { "domain" : domain , "what" : "h5"} 
    response = client.get("/download",params=params)
    assert response.status_code == 200
    print(response)

def test_download_domain_h5(domain):
    print(domain)
    params = { "domain" : domain , "what" : "h5"} 
    response = client.get("/download",params=params)
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code}"
    assert response.headers["Content-Type"] == "application/x-hdf5", "Response is not an HDF5 file but {}".format(response.headers["Content-Type"])
    # Check if the response content starts with HDF5 file signature
    hdf5_signature = b'\x89HDF\r\n\x1a\n'
    assert response.content.startswith(hdf5_signature), "Response content is not a valid HDF5 file"
    # Create a temporary file to store the HDF5 content
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp_file:
        # Write the response content to the temporary file
        tmp_file.write(response.content)
        tmp_file_path = tmp_file.name    
    # Open the saved file using h5py
    with h5py.File(tmp_file_path, 'r') as hdf:
        # Print and inspect the HDF5 file structure (e.g., datasets, attributes)
        print(f"Contents of the HDF5 file {tmp_file_path}:")
        print(list(hdf.keys()))  # This will print out the datasets/groups in the file
        # Perform assertions based on the file structure
        assert len(hdf.keys()) > 0, "HDF5 file is empty"
    # Clean up the temporary file after the test
    remove(tmp_file_path)

def test_download_domain_image(domain):
    print(domain)
    params = { "domain" : domain , "what" : "thumbnail"} 
    response = client.get("/download",params=params)
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code}"
    # Assert that the Content-Type is "image/png"
    assert response.headers["Content-Type"] == "image/png", "Response is not a PNG image"
    # Check if the response content starts with PNG header bytes
    png_signature = b'\x89PNG\r\n\x1a\n'
    assert response.content.startswith(png_signature), "Response content is not a valid PNG image"

def test_download_domain_b64png(domain):
    params = { "domain" : domain , "what" : "b64png"} 
    response = client.get("/download",params=params)
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code}"
    # Assert that the Content-Type is "image/png"
    assert response.headers["Content-Type"].startswith("text/plain"), "Response is not Base64-encoded PNG but {}".format(response.headers["Content-Type"])
     # Extract the base64-encoded data from the response
    b64_data = response.text
    # Try decoding the Base64 string
    try:
        decoded_data = base64.b64decode(b64_data)
    except Exception as e:
        assert False, f"Failed to decode Base64 data: {e}"
    # Check if the decoded data starts with the PNG signature
    png_signature = b'\x89PNG\r\n\x1a\n'
    assert decoded_data.startswith(png_signature), "Decoded data is not a valid PNG image"

def test_convert_post_files2knnquery():
    # simulate file upload
    file_path = importlib.resources.files('ramanchada2.auxiliary.spectra.datasets2.FMNT-M_BW532').joinpath('nCAL10_iR532_Probe_100_2500msx3.txt')
    with open(str(file_path), 'r') as f:
        file_content = f.read()
    
    # Files should be sent as a list of tuples (field_name, file_object)
    files = [
        ('files', (str(file_path), file_content, 'text/plain'))
    ]

    # Make the POST request to the `/download` endpoint with the 'files' parameter
    response = client.post(
        "/download", 
        data={"what": "knnquery"},  # Send the "what" query parameter
        files=files  # Send the files as multipart form-data
    )
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code}"
    response_json = response.json()
    assert "cdf" in response_json
    assert "imageLink" in response_json

def test_convert_post_files2b64png():
    # simulate file upload
    file_path = importlib.resources.files('ramanchada2.auxiliary.spectra.datasets2.FMNT-M_BW532').joinpath('nCAL10_iR532_Probe_100_2500msx3.txt')
    with open(str(file_path), 'r') as f:
        file_content = f.read()
    
    # Files should be sent as a list of tuples (field_name, file_object)
    files = [
        ('files', (str(file_path), file_content, 'text/plain'))
    ]

    response = client.post(
        "/download", 
        # data={"what": "b64png"},  #do we want query param or form data?
        params={"what": "b64png"}, 
        files=files  # Send the files as multipart form-data
    )
    assert response.headers["Content-Type"].startswith("text/plain"), "Response is not Base64-encoded PNG but {}".format(response.headers["Content-Type"])
    b64_data = response.text
    try:
        decoded_data = base64.b64decode(b64_data)
    except Exception as e:
        assert False, f"Failed to decode Base64 data: {e}"
    # Check if the decoded data starts with the PNG signature
    png_signature = b'\x89PNG\r\n\x1a\n'
    assert decoded_data.startswith(png_signature), "Decoded data is not a valid PNG image"


def test_access_resource():
    # Access the resource from rc2
    file_path = importlib.resources.files('ramanchada2.auxiliary.spectra.datasets2.FMNT-M_BW532').joinpath('nCAL10_iR532_Probe_100_2500msx3.txt')
    from_local_file(str(file_path))
    
