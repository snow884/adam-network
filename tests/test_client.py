"""Tests for Adam Network Python API Client."""

import base64
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client import (
    AdamClient,
    AdamAPIError,
    AuthenticationError,
    ValidationError,
    NotFoundError,
    User,
    Token,
    Message,
)

BASE_URL = "http://127.0.0.1:8002"


@pytest.fixture(scope="module")
def api_server():
    """Starts a live uvicorn server for client integration tests."""
    try:
        subprocess.run(
            ["bash", "-lc", "lsof -ti tcp:8002 | xargs -r kill -9"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8002"],
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
        raise RuntimeError(f"API server did not start on port 8002. stdout={stdout} stderr={stderr}")

    yield BASE_URL

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def test_client_initialization():
    client = AdamClient(base_url="http://127.0.0.1:8000/", token="initial_token")
    assert client.base_url == "http://127.0.0.1:8000"
    assert client.token == "initial_token"


def test_client_image_encoding(tmp_path):
    dummy_img = tmp_path / "test.png"
    dummy_bytes = b"fake_png_binary_data"
    dummy_img.write_bytes(dummy_bytes)

    encoded_from_file = AdamClient.encode_image_file(dummy_img)
    assert encoded_from_file.startswith("data:image/png;base64,")

    encoded_from_bytes = AdamClient.encode_image_bytes(dummy_bytes, mime_type="image/jpeg")
    assert encoded_from_bytes.startswith("data:image/jpeg;base64,")


def test_client_full_workflow(api_server):
    client = AdamClient(base_url=api_server)
    uid = uuid.uuid4().hex[:8]
    username = f"clientuser_{uid}"
    email = f"{username}@example.com"
    password = "StrongPassword123"

    # 1. Register
    user = client.register(username=username, email=email, password=password)
    assert isinstance(user, User)
    assert user.username == username
    assert user.email == email

    # 2. Login
    token = client.login(username=username, password=password)
    assert isinstance(token, Token)
    assert token.access_token
    assert client.token == token.access_token

    # 3. Get profile
    me = client.get_me()
    assert me.username == username
    assert me.email == email

    # 4. Post message
    msg = client.post_message(
        text=f"API client post {uid}",
        tags=["client_test", "integration"],
    )
    assert isinstance(msg, Message)
    assert msg.id > 0
    assert msg.text == f"API client post {uid}"
    assert "client_test" in msg.tags

    # 5. Reply to message
    reply = client.reply_to_message(
        message_id=msg.id,
        text=f"API client reply {uid}",
        tags=["reply_tag"],
    )
    assert isinstance(reply, Message)
    assert f"message_reply_{msg.id}" in reply.tags

    # 6. Read message by ID
    fetched_msg = client.get_message(msg.id)
    assert fetched_msg.id == msg.id
    assert fetched_msg.reply_count >= 1

    # 7. Search messages
    search_results = client.search_messages(search_text=uid)
    assert len(search_results) >= 1
    assert any(m.id == msg.id for m in search_results)

    tag_results = client.search_messages(tags="client_test")
    assert len(tag_results) >= 1
    assert any(m.id == msg.id for m in tag_results)

    # 8. Get replies / thread
    thread = client.get_replies(msg.id)
    assert len(thread) >= 2
    assert any(m.id == msg.id for m in thread)
    assert any(m.id == reply.id for m in thread)

    # 9. Logout
    logout_res = client.logout()
    assert "logged out" in logout_res.message.lower()
    assert client.token is None


def test_client_error_handling(api_server):
    client = AdamClient(base_url=api_server)

    # Invalid login
    with pytest.raises(ValidationError):
        client.login("non_existent_user", "wrong_password")

    # Non-existent message
    with pytest.raises(NotFoundError):
        client.get_message(999999)

    # Register validation failure (password mismatch)
    with pytest.raises(ValidationError):
        client.register(
            username="test_mismatch",
            email="mismatch@example.com",
            password="pass1",
            confirm_password="pass2",
        )


def test_client_context_manager(api_server):
    with AdamClient(base_url=api_server) as client:
        messages = client.get_messages(limit=5)
        assert isinstance(messages, list)
