"""Unit tests for Adam Network MCP Server tools."""

import base64
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server.mcp_server as mcp_module
from client import (
    AdamClient,
    AuthenticationError,
    LogoutResponse,
    Message,
    NotFoundError,
    Token,
    User,
    ValidationError,
)

BASE_URL = "http://127.0.0.1:8003"


@pytest.fixture(scope="module")
def api_server():
    """Starts a live uvicorn server for MCP integration tests."""
    try:
        subprocess.run(
            ["bash", "-lc", "lsof -ti tcp:8003 | xargs -r kill -9"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8003"],
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
        raise RuntimeError(f"API server did not start on port 8003. stdout={stdout} stderr={stderr}")

    yield BASE_URL

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


# ---------------------------------------------------------------------------
# Unit Tests with Mock Client
# ---------------------------------------------------------------------------


def test_mcp_client_getter_and_setter():
    original = mcp_module.get_client()
    new_client = AdamClient(base_url="http://mock-url:9999", token="mock-tok")
    mcp_module.set_client(new_client)
    assert mcp_module.get_client() is new_client
    # Restore
    mcp_module.set_client(original)


def test_register_user_tool_mock():
    mock_client = MagicMock(spec=AdamClient)
    mock_client.register.return_value = User(username="charlie", email="charlie@example.com", is_guest=False)
    mcp_module.set_client(mock_client)

    res = mcp_module.register_user(username="charlie", email="charlie@example.com", password="password123")
    assert res["success"] is True
    assert res["user"]["username"] == "charlie"
    assert res["user"]["email"] == "charlie@example.com"
    assert res["user"]["is_guest"] is False

    # Error path
    mock_client.register.side_effect = ValidationError("Passwords do not match")
    err_res = mcp_module.register_user(username="charlie", email="charlie@example.com", password="p1", confirm_password="p2")
    assert err_res["success"] is False
    assert "Passwords do not match" in err_res["error"]


def test_login_and_logout_user_tool_mock():
    mock_client = MagicMock(spec=AdamClient)
    mock_client.login.return_value = Token(access_token="fake_jwt_token_123", token_type="bearer")
    mock_client.logout.return_value = LogoutResponse(message="User charlie logged out successfully.")
    mcp_module.set_client(mock_client)

    # Login
    login_res = mcp_module.login_user(username="charlie", password="password123")
    assert login_res["success"] is True
    assert login_res["token"]["access_token"] == "fake_jwt_token_123"
    assert login_res["token"]["token_type"] == "bearer"

    # Login Error
    mock_client.login.side_effect = AuthenticationError("Incorrect username or password")
    login_err = mcp_module.login_user(username="charlie", password="wrong")
    assert login_err["success"] is False
    assert "Incorrect username or password" in login_err["error"]

    # Logout
    logout_res = mcp_module.logout_user()
    assert logout_res["success"] is True
    assert "logged out" in logout_res["result"]["message"]

    # Logout Error
    mock_client.logout.side_effect = Exception("Logout failed")
    logout_err = mcp_module.logout_user()
    assert logout_err["success"] is False
    assert "Logout failed" in logout_err["error"]


def test_get_current_user_profile_tool_mock():
    mock_client = MagicMock(spec=AdamClient)
    mock_client.get_me.return_value = User(username="alice", email="alice@example.com", is_guest=False)
    mcp_module.set_client(mock_client)

    res = mcp_module.get_current_user_profile()
    assert res["success"] is True
    assert res["user"]["username"] == "alice"

    # Error path
    mock_client.get_me.side_effect = Exception("Network error")
    err_res = mcp_module.get_current_user_profile()
    assert err_res["success"] is False
    assert "Network error" in err_res["error"]


def test_create_message_and_post_tool_mock():
    mock_client = MagicMock(spec=AdamClient)
    mock_msg = Message(
        id=42,
        text="Hello world via MCP",
        username="alice",
        tags=["general", "test"],
        image_data=None,
        created_at="2026-08-29T12:00:00Z",
        views=0,
        reply_count=0,
    )
    mock_client.create_message.return_value = mock_msg
    mcp_module.set_client(mock_client)

    # create_message
    res = mcp_module.create_message(text="Hello world via MCP", tags=["general", "test"])
    assert res["success"] is True
    assert res["message"]["id"] == 42
    assert res["message"]["text"] == "Hello world via MCP"
    assert res["message"]["tags"] == ["general", "test"]

    # create_post (alias)
    res_post = mcp_module.create_post(message="Hello world via MCP", tags=["general", "test"])
    assert res_post["success"] is True
    assert res_post["message"]["id"] == 42

    # Error path
    mock_client.create_message.side_effect = AuthenticationError("Login required")
    err_res = mcp_module.create_message(text="Unauthorized message")
    assert err_res["success"] is False
    assert "Login required" in err_res["error"]


def test_get_messages_and_get_message_tool_mock():
    mock_client = MagicMock(spec=AdamClient)
    mock_msgs = [
        Message(id=1, text="Post 1", username="user1", tags=["news"]),
        Message(id=2, text="Post 2", username="user2", tags=["tech"]),
    ]
    mock_client.get_messages.return_value = mock_msgs
    mock_client.get_message.return_value = mock_msgs[0]
    mcp_module.set_client(mock_client)

    # get_messages
    res = mcp_module.get_messages(skip=0, limit=10)
    assert res["success"] is True
    assert res["count"] == 2
    assert len(res["messages"]) == 2
    assert res["messages"][0]["id"] == 1

    # get_message
    single = mcp_module.get_message(message_id=1)
    assert single["success"] is True
    assert single["message"]["id"] == 1

    # get_message not found
    mock_client.get_message.side_effect = NotFoundError("Message not found")
    not_found = mcp_module.get_message(message_id=999)
    assert not_found["success"] is False
    assert "Message not found" in not_found["error"]


def test_search_messages_tool_mock():
    mock_client = MagicMock(spec=AdamClient)
    mock_msgs = [
        Message(id=10, text="Searching MCP", username="alice", tags=["search", "mcp"]),
    ]
    mock_client.search_messages.return_value = mock_msgs
    mcp_module.set_client(mock_client)

    res = mcp_module.search_messages(search_text="Searching", tags="search, mcp")
    assert res["success"] is True
    assert res["count"] == 1
    assert res["messages"][0]["id"] == 10
    mock_client.search_messages.assert_called_with(
        search_text="Searching",
        tags=["search", "mcp"],
        skip=0,
        limit=1000,
    )

    # Error path
    mock_client.search_messages.side_effect = Exception("Search error")
    err_res = mcp_module.search_messages(search_text="fail")
    assert err_res["success"] is False
    assert err_res["messages"] == []


def test_reply_to_message_and_get_replies_mock():
    mock_client = MagicMock(spec=AdamClient)
    mock_reply = Message(
        id=101,
        text="This is a reply",
        username="bob",
        tags=["message_reply_10", "custom"],
    )
    mock_client.reply_to_message.return_value = mock_reply
    mock_client.get_replies.return_value = [mock_reply]
    mcp_module.set_client(mock_client)

    # reply_to_message
    res = mcp_module.reply_to_message(message_id=10, text="This is a reply", tags=["custom"])
    assert res["success"] is True
    assert res["message"]["id"] == 101
    assert "message_reply_10" in res["message"]["tags"]

    # get_replies
    replies_res = mcp_module.get_replies(message_id=10)
    assert replies_res["success"] is True
    assert replies_res["message_id"] == 10
    assert replies_res["count"] == 1
    assert replies_res["replies"][0]["id"] == 101

    # Error path
    mock_client.reply_to_message.side_effect = Exception("Reply failed")
    err_reply = mcp_module.reply_to_message(message_id=10, text="test")
    assert err_reply["success"] is False


def test_encode_image_file_tool(tmp_path):
    img_file = tmp_path / "sample.png"
    img_bytes = b"fake_png_data_content"
    img_file.write_bytes(img_bytes)

    res = mcp_module.encode_image_file(str(img_file))
    assert res["success"] is True
    assert res["data_url"].startswith("data:image/png;base64,")

    # Non existent file
    err_res = mcp_module.encode_image_file(str(tmp_path / "non_existent.jpg"))
    assert err_res["success"] is False
    assert "not found" in err_res["error"].lower()


# ---------------------------------------------------------------------------
# Integration Tests against Live Server
# ---------------------------------------------------------------------------


def test_mcp_tools_live_workflow(api_server):
    live_client = AdamClient(base_url=api_server)
    mcp_module.set_client(live_client)

    uid = uuid.uuid4().hex[:8]
    username = f"mcpuser_{uid}"
    email = f"{username}@example.com"
    password = "StrongPassword123"

    # 1. Register User
    reg_res = mcp_module.register_user(
        username=username,
        email=email,
        password=password,
        confirm_password=password,
    )
    assert reg_res["success"] is True
    assert reg_res["user"]["username"] == username

    # 2. Login User
    login_res = mcp_module.login_user(username=username, password=password)
    assert login_res["success"] is True
    assert "token" in login_res
    assert login_res["token"]["access_token"] != ""

    # 3. Get User Profile
    me_res = mcp_module.get_current_user_profile()
    assert me_res["success"] is True
    assert me_res["user"]["username"] == username
    assert me_res["user"]["email"] == email

    # 4. Create Message
    msg_res = mcp_module.create_message(
        text=f"Hello MCP live test {uid}",
        tags=["mcp_test", "live"],
    )
    assert msg_res["success"] is True
    msg_id = msg_res["message"]["id"]
    assert msg_id > 0
    assert msg_res["message"]["text"] == f"Hello MCP live test {uid}"

    # 5. Fetch Message by ID
    single_res = mcp_module.get_message(message_id=msg_id)
    assert single_res["success"] is True
    assert single_res["message"]["id"] == msg_id

    # 6. Reply to Message
    reply_res = mcp_module.reply_to_message(
        message_id=msg_id,
        text=f"Replying from MCP {uid}",
        tags=["mcp_reply"],
    )
    assert reply_res["success"] is True
    assert f"message_reply_{msg_id}" in reply_res["message"]["tags"]

    # 7. Get Replies
    replies_res = mcp_module.get_replies(message_id=msg_id)
    assert replies_res["success"] is True
    assert replies_res["count"] >= 1
    assert any(r["id"] == reply_res["message"]["id"] for r in replies_res["replies"])

    # 8. Search Messages
    search_res = mcp_module.search_messages(search_text=uid)
    assert search_res["success"] is True
    assert any(m["id"] == msg_id for m in search_res["messages"])

    # 9. Get Messages stream
    all_msgs = mcp_module.get_messages(skip=0, limit=20)
    assert all_msgs["success"] is True
    assert all_msgs["count"] > 0

    # 10. Logout User
    logout_res = mcp_module.logout_user()
    assert logout_res["success"] is True
    assert "message" in logout_res["result"]
