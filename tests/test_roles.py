from pathlib import Path
from rcapi.services.kc import get_roles_from_token


def test_roles():
    TEST_TOKEN = Path(__file__).parent / "resources/api/test-token.txt"
    TEST_KEY = Path(__file__).parent / "resources/api/test-jwt-key.pem"
    token = TEST_TOKEN.read_text()
    key = TEST_KEY.read_text()
    roles = get_roles_from_token(token, key)
    # print(get_jwt_header(token["access_token"]))
    assert roles == [
        "test-role-1",
        "test-role-2",
        "test-role-3",
    ], "roles did not match expected list"