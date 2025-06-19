import json
from pathlib import Path
from rcapi.services.kc import get_roles_from_token
import jwt
import base64

TEST_TOKEN = Path(__file__).parent / "resources/api/access_token.json"


def mock_decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        key='',  # or a dummy public key
        algorithms=["RS256"],
        options={
            "verify_signature": False,
            "verify_exp": False,
            "verify_aud": False,
            "verify_iss": False
        }
    )


def get_jwt_header(token: str) -> dict:
    header_b64 = token.split('.')[0]
    padded = header_b64 + '=' * (-len(header_b64) % 4)  # pad base64
    return json.loads(base64.urlsafe_b64decode(padded))

with open(TEST_TOKEN, 'r') as json_file:
    token = json.load(json_file)
roles = get_roles_from_token(token["access_token"], validate=False)
print(roles)
#print(get_jwt_header(token["access_token"]))

assert roles, "roles must not be empty"