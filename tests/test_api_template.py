from fastapi.testclient import TestClient
import re
from rcapi.main import app

client = TestClient(app)

def test_template():
    response = client.get("/template")
    assert response.status_code == 200
    assert response.json() == {"template" : []}