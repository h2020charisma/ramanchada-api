from fastapi.testclient import TestClient
from rcapi.main import app

client = TestClient(app)
def test_query():
    response_retrieve = client.get("/query")
    assert response_retrieve.status_code == 200, response_retrieve.status_code
    retrieved_json = response_retrieve.json()
    print(retrieved_json)
    #with open(TEST_DEFAULT_PATH, "r") as file:
    #    expected_json = json.load(file)
    #assert retrieved_json == expected_json        
