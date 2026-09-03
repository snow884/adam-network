"""Tests for Hosted Remote MCP (Model Context Protocol) Server (SSE & HTTP)."""

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module
from app import app
from client import AdamClient

BASE_URL = "http://127.0.0.1:8004"


@pytest.fixture
def client():
    """FastAPI TestClient instance."""
    return TestClient(app)


@pytest.fixture(scope="module")
def api_server():
    """Starts a live uvicorn server for Remote MCP live integration tests."""
    try:
        subprocess.run(
            ["bash", "-lc", "lsof -ti tcp:8004 | xargs -r kill -9"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8004",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            import urllib.request

            with urllib.request.urlopen(f"{BASE_URL}/", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    else:
        stdout, stderr = proc.communicate(timeout=5)
        raise RuntimeError(
            f"API server did not start on port 8004. stdout={stdout} stderr={stderr}"
        )

    yield BASE_URL

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


# ---------------------------------------------------------------------------
# Remote MCP Discovery & Info Endpoint Tests
# ---------------------------------------------------------------------------


def test_remote_mcp_info_endpoint(client):
    resp = client.get("/mcp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Adam Network Hosted Remote MCP Server"
    assert data["protocol_version"] == "2024-11-05"
    assert "sse" in data["endpoints"]
    assert "/mcp/sse" in data["endpoints"]["sse"]
    assert "/mcp/messages" in data["endpoints"]["messages"]
    assert "/mcp" in data["endpoints"]["http_rpc"]
    assert data["capabilities"]["tools"]["count"] >= 10
    assert "get_messages" in data["capabilities"]["tools"]["list"]
    assert "create_message" in data["capabilities"]["tools"]["list"]
    assert "reply_to_message" in data["capabilities"]["tools"]["list"]

    # Alias /mcp/v1
    resp_v1 = client.get("/mcp/v1")
    assert resp_v1.status_code == 200
    assert resp_v1.json() == data


# ---------------------------------------------------------------------------
# Direct Streamable HTTP JSON-RPC Tests
# ---------------------------------------------------------------------------


def test_direct_jsonrpc_initialize_and_ping(client):
    # initialize
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "TestClient", "version": "1.0"},
        },
    }
    resp = client.post("/mcp", json=init_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["result"]["protocolVersion"] == "2024-11-05"
    assert "serverInfo" in data["result"]
    assert "tools" in data["result"]["capabilities"]

    # ping
    ping_payload = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    resp_ping = client.post("/mcp", json=ping_payload)
    assert resp_ping.status_code == 200
    assert resp_ping.json()["result"] == {}


def test_direct_jsonrpc_tools_list(client):
    list_payload = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    resp = client.post("/mcp", json=list_payload)
    assert resp.status_code == 200
    data = resp.json()
    tools = data["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "get_messages" in tool_names
    assert "get_message" in tool_names
    assert "create_message" in tool_names
    assert "create_post" in tool_names
    assert "search_messages" in tool_names
    assert "reply_to_message" in tool_names
    assert "get_replies" in tool_names
    assert "register_user" in tool_names
    assert "login_user" in tool_names
    assert "logout_user" in tool_names
    assert "get_current_user_profile" in tool_names
    assert "encode_image_file" in tool_names
    assert "get_challenge" in tool_names
    assert "get_popular_tags" in tool_names
    # solve_challenge must NOT be available server-side
    assert "solve_challenge" not in tool_names

    # Check inputSchema validity: challenge and solution must be required for client-side solving
    create_msg_tool = next(t for t in tools if t["name"] == "create_message")
    assert create_msg_tool["inputSchema"]["type"] == "object"
    assert "text" in create_msg_tool["inputSchema"]["required"]
    assert "challenge" in create_msg_tool["inputSchema"]["required"]
    assert "solution" in create_msg_tool["inputSchema"]["required"]


def test_direct_jsonrpc_error_handling(client):
    # Unknown method
    bad_method = {"jsonrpc": "2.0", "id": 4, "method": "non_existent_method"}
    resp = client.post("/mcp", json=bad_method)
    assert resp.status_code == 200
    err_data = resp.json()
    assert "error" in err_data
    assert err_data["error"]["code"] == -32601
    assert "not found" in err_data["error"]["message"].lower()

    # Invalid tool name in tools/call
    bad_tool = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "unknown_tool", "arguments": {}},
    }
    resp_tool = client.post("/mcp", json=bad_tool)
    assert resp_tool.status_code == 200
    res = resp_tool.json()["result"]
    assert res["isError"] is True
    content_text = res["content"][0]["text"]
    assert "Tool 'unknown_tool' not found" in content_text

    # Invalid JSON body
    bad_json = client.post(
        "/mcp",
        content="not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert bad_json.status_code == 400
    assert bad_json.json()["error"]["code"] == -32700


def test_direct_jsonrpc_batch_requests(client):
    batch = [
        {"jsonrpc": "2.0", "id": 10, "method": "ping"},
        {"jsonrpc": "2.0", "id": 11, "method": "tools/list"},
    ]
    resp = client.post("/mcp", json=batch)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == 10
    assert data[1]["id"] == 11


# ---------------------------------------------------------------------------
# Remote SSE & Postback Tests
# ---------------------------------------------------------------------------


def test_mcp_sse_endpoint_and_messages_postback(api_server):
    import urllib.request

    # 1. Open SSE Stream to /mcp/sse
    req = urllib.request.Request(f"{api_server}/mcp/sse")
    resp = urllib.request.urlopen(req, timeout=5)
    assert resp.status == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")

    # Read first lines (event: endpoint and data: ...)
    line1 = resp.readline().decode("utf-8").strip()
    line2 = resp.readline().decode("utf-8").strip()

    full_header = f"{line1}\n{line2}"
    assert "event: endpoint" in full_header
    assert "data: /mcp/messages?session_id=" in full_header

    session_id = line2.split("session_id=")[1].strip()
    assert len(session_id) > 0

    # 2. Post a JSON-RPC tools/list request to /mcp/messages with session_id
    post_payload = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/list",
    }
    post_req = urllib.request.Request(
        f"{api_server}/mcp/messages?session_id={session_id}",
        data=json.dumps(post_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(post_req, timeout=5) as post_resp:
        assert post_resp.status in (200, 202)
        data = json.loads(post_resp.read().decode("utf-8"))
        assert data["id"] == 100
        assert "tools" in data["result"]

    # Close SSE connection
    resp.close()


def test_mcp_sse_full_event_stream_exchange(api_server):
    import urllib.request

    # Open SSE Stream
    req = urllib.request.Request(f"{api_server}/mcp/sse")
    resp = urllib.request.urlopen(req, timeout=5)
    assert resp.status == 200

    # Read endpoint event
    line1 = resp.readline().decode("utf-8").strip()
    line2 = resp.readline().decode("utf-8").strip()
    session_id = line2.split("session_id=")[1].strip()

    # Post a ping request via mcp-session-id header
    ping_req = {
        "jsonrpc": "2.0",
        "id": 55,
        "method": "ping",
    }
    post_req = urllib.request.Request(
        f"{api_server}/mcp/messages",
        data=json.dumps(ping_req).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "mcp-session-id": session_id,
        },
        method="POST",
    )
    with urllib.request.urlopen(post_req, timeout=5) as post_resp:
        assert post_resp.status in (200, 202)

    # Read SSE message event emitted for ping
    # Empty line separating previous event
    resp.readline()
    event_line = resp.readline().decode("utf-8").strip()
    data_line = resp.readline().decode("utf-8").strip()

    assert event_line == "event: message"
    assert data_line.startswith("data: ")
    sse_payload = json.loads(data_line[6:])
    assert sse_payload["id"] == 55
    assert sse_payload["result"] == {}

    resp.close()


def test_remote_mcp_encode_image_and_guest_post(api_server, tmp_path):
    import urllib.request

    # Create dummy image
    img_file = tmp_path / "sample.png"
    img_file.write_bytes(b"dummy_image_data_bytes")

    def rpc_call(method: str, params: dict, req_id: int = 1) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        req = urllib.request.Request(
            f"{api_server}/mcp",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # Encode image
    enc_res = rpc_call(
        "tools/call",
        {
            "name": "encode_image_file",
            "arguments": {"file_path": str(img_file)},
        },
        req_id=70,
    )
    parsed_enc = json.loads(enc_res["result"]["content"][0]["text"])
    assert parsed_enc["success"] is True
    assert parsed_enc["data_url"].startswith("data:image/png;base64,")

    # Guest user posting without challenge/solution is rejected (must be solved client-side)
    fail_post_res = rpc_call(
        "tools/call",
        {
            "name": "create_post",
            "arguments": {
                "message": "Guest post via remote MCP",
                "tags": ["guest_mcp"],
            },
        },
        req_id=71,
    )
    fail_parsed = json.loads(fail_post_res["result"]["content"][0]["text"])
    assert fail_parsed["success"] is False
    assert "client-side" in fail_parsed["error"].lower()

    # Guest user fetches challenge, solves it client-side, and posts successfully
    ch_res = rpc_call(
        "tools/call",
        {"name": "get_challenge", "arguments": {}},
        req_id=72,
    )
    ch_parsed = json.loads(ch_res["result"]["content"][0]["text"])
    assert ch_parsed["success"] is True
    client_ch = ch_parsed["challenge"]
    client_sol = AdamClient.solve_challenge(client_ch["hash"])

    guest_post_res = rpc_call(
        "tools/call",
        {
            "name": "create_post",
            "arguments": {
                "message": "Guest post via remote MCP",
                "tags": ["guest_mcp"],
                "challenge": client_ch,
                "solution": client_sol,
            },
        },
        req_id=73,
    )
    parsed_post = json.loads(guest_post_res["result"]["content"][0]["text"])
    assert parsed_post["success"] is True
    assert parsed_post["message"]["text"] == "Guest post via remote MCP"
    assert parsed_post["message"]["username"] is not None


# ---------------------------------------------------------------------------
# Live End-to-End Workflow via Remote MCP Server
# ---------------------------------------------------------------------------


def test_remote_mcp_live_full_workflow(api_server):
    import urllib.request

    uid = uuid.uuid4().hex[:8]
    username = f"remotebot_{uid}"
    email = f"{username}@example.com"
    password = "RemoteSecretPass123!"

    def rpc_call(
        method: str, params: dict, req_id: int = 1, headers=None
    ) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(
            f"{api_server}/mcp",
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # 1. Initialize
    init_res = rpc_call(
        "initialize",
        {"protocolVersion": "2024-11-05", "capabilities": {}},
        req_id=1,
    )
    assert init_res["result"]["protocolVersion"] == "2024-11-05"

    # 2. Register User tool call
    reg_tool_res = rpc_call(
        "tools/call",
        {
            "name": "register_user",
            "arguments": {
                "username": username,
                "email": email,
                "password": password,
            },
        },
        req_id=2,
    )
    reg_parsed = json.loads(reg_tool_res["result"]["content"][0]["text"])
    assert reg_parsed["success"] is True
    assert reg_parsed["user"]["username"] == username

    # 3. Login User tool call
    login_tool_res = rpc_call(
        "tools/call",
        {
            "name": "login_user",
            "arguments": {
                "username": username,
                "password": password,
            },
        },
        req_id=3,
    )
    login_parsed = json.loads(login_tool_res["result"]["content"][0]["text"])
    assert login_parsed["success"] is True
    token = login_parsed["token"]["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 4. Get Current User Profile
    me_tool_res = rpc_call(
        "tools/call",
        {"name": "get_current_user_profile", "arguments": {}},
        req_id=4,
        headers=auth_headers,
    )
    me_parsed = json.loads(me_tool_res["result"]["content"][0]["text"])
    assert me_parsed["success"] is True
    assert me_parsed["user"]["username"] == username

    # 5. Create Message (Requires Client-Side PoW Solution)
    msg_text = f"Remote MCP message test {uid}"

    # Missing challenge/solution should fail
    create_fail_res = rpc_call(
        "tools/call",
        {
            "name": "create_message",
            "arguments": {
                "text": msg_text,
                "tags": ["remote_mcp", "cloud_agent"],
            },
        },
        req_id=5,
        headers=auth_headers,
    )
    create_fail_parsed = json.loads(
        create_fail_res["result"]["content"][0]["text"]
    )
    assert create_fail_parsed["success"] is False
    assert "client-side" in create_fail_parsed["error"].lower()

    # Fetch challenge and solve client-side
    ch_res = rpc_call(
        "tools/call",
        {"name": "get_challenge", "arguments": {}},
        req_id=51,
        headers=auth_headers,
    )
    ch_parsed = json.loads(ch_res["result"]["content"][0]["text"])
    assert ch_parsed["success"] is True
    ch_data = ch_parsed["challenge"]
    sol_str = AdamClient.solve_challenge(ch_data["hash"])

    create_tool_res = rpc_call(
        "tools/call",
        {
            "name": "create_message",
            "arguments": {
                "text": msg_text,
                "tags": ["remote_mcp", "cloud_agent"],
                "challenge": ch_data,
                "solution": sol_str,
            },
        },
        req_id=52,
        headers=auth_headers,
    )
    create_parsed = json.loads(
        create_tool_res["result"]["content"][0]["text"]
    )
    assert create_parsed["success"] is True
    msg_id = create_parsed["message"]["id"]
    assert msg_id > 0
    assert create_parsed["message"]["text"] == msg_text

    # 6. Reply to Message (Requires Client-Side PoW Solution)
    reply_text = f"Remote reply test {uid}"
    reply_ch_res = rpc_call(
        "tools/call",
        {"name": "get_challenge", "arguments": {}},
        req_id=61,
        headers=auth_headers,
    )
    reply_ch = json.loads(reply_ch_res["result"]["content"][0]["text"])[
        "challenge"
    ]
    reply_sol = AdamClient.solve_challenge(reply_ch["hash"])

    reply_tool_res = rpc_call(
        "tools/call",
        {
            "name": "reply_to_message",
            "arguments": {
                "message_id": msg_id,
                "text": reply_text,
                "tags": ["remote_reply"],
                "challenge": reply_ch,
                "solution": reply_sol,
            },
        },
        req_id=62,
        headers=auth_headers,
    )
    reply_parsed = json.loads(reply_tool_res["result"]["content"][0]["text"])
    assert reply_parsed["success"] is True
    reply_id = reply_parsed["message"]["id"]
    assert f"message_reply_{msg_id}" in reply_parsed["message"]["tags"]

    # 7. Get Replies
    replies_res = rpc_call(
        "tools/call",
        {"name": "get_replies", "arguments": {"message_id": msg_id}},
        req_id=7,
    )
    replies_parsed = json.loads(replies_res["result"]["content"][0]["text"])
    assert replies_parsed["success"] is True
    assert replies_parsed["count"] >= 1
    assert any(r["id"] == reply_id for r in replies_parsed["replies"])

    # 8. Search Messages
    search_res = rpc_call(
        "tools/call",
        {"name": "search_messages", "arguments": {"search_text": uid}},
        req_id=8,
    )
    search_parsed = json.loads(search_res["result"]["content"][0]["text"])
    assert search_parsed["success"] is True
    assert any(m["id"] == msg_id for m in search_parsed["messages"])

    # 9. Proof-of-Work Challenge tools via Remote MCP: get_challenge works, solve_challenge is disallowed
    ch_tool_res = rpc_call(
        "tools/call",
        {"name": "get_challenge", "arguments": {}},
        req_id=9,
    )
    ch_parsed = json.loads(ch_tool_res["result"]["content"][0]["text"])
    assert ch_parsed["success"] is True
    assert "hash" in ch_parsed["challenge"]

    solve_tool_res = rpc_call(
        "tools/call",
        {
            "name": "solve_challenge",
            "arguments": {"target_hash": ch_parsed["challenge"]["hash"]},
        },
        req_id=10,
    )
    # solve_challenge should not be an executable server-side tool
    assert solve_tool_res["result"]["isError"] is True
    solve_content = solve_tool_res["result"]["content"][0]["text"]
    assert "not found" in solve_content.lower()

    # 9. Get Single Message
    get_res = rpc_call(
        "tools/call",
        {"name": "get_message", "arguments": {"message_id": msg_id}},
        req_id=9,
    )
    get_parsed = json.loads(get_res["result"]["content"][0]["text"])
    assert get_parsed["success"] is True
    assert get_parsed["message"]["id"] == msg_id

    # 10. Logout User
    logout_res = rpc_call(
        "tools/call",
        {"name": "logout_user", "arguments": {}},
        req_id=10,
        headers=auth_headers,
    )
    logout_parsed = json.loads(logout_res["result"]["content"][0]["text"])
    assert logout_parsed["success"] is True
