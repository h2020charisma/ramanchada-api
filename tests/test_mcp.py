from fastapi.testclient import TestClient
from rcapi.main import app

client = TestClient(app)

# MCP manifest endpoint
MCP_MANIFEST = "/.well-known/mcp/manifest.json"
MCP_TOOLS = "/.well-known/mcp/tools.json"


def test_mcp_manifest_public():
    response = client.get(MCP_MANIFEST)
    assert response.status_code == 200
    manifest = response.json()
    assert "version" in manifest
    assert "tools" not in manifest  # manifest doesn’t include tools
    assert "endpoints" in manifest


def test_mcp_tools_public():
    response = client.get(MCP_TOOLS)
    assert response.status_code == 200
    tools = response.json()["tools"]
    print(tools)
    assert isinstance(tools, list)
    # At least the query tool should exist
    query_tools = [t for t in tools if t["path"].endswith("/query")]
    assert query_tools
    tool = query_tools[0]
    assert "parameters" in tool
    assert "requestBody" in tool
    # Ensure URL is full
    assert tool["url"].startswith("http")