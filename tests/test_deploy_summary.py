"""Tests for the post-deployment summary script."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client import Message  # noqa: E402

# Import the deploy summary module from .github/scripts
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
import post_deploy_summary  # noqa: E402


def test_build_summary_message_success():
    msg = post_deploy_summary.build_summary_message(
        status="success",
        repository="snow884/adam-network",
        ref_name="refs/heads/main",
        commit_sha="1234567890abcdef",
        actor="alice",
        commit_msg="Add new feature\n\nMore details here",
        service_name="adam-network-backend",
        server_url="https://github.com",
        run_id="998877",
        live_url="https://adam-network.up.railway.app",
    )

    assert "🚀 Railway Deployment Succeeded!" in msg
    assert "snow884/adam-network" in msg
    assert "(`main`)" in msg
    assert "1234567" in msg
    assert "Add new feature" in msg
    assert "@alice" in msg
    assert "adam-network-backend" in msg
    assert "https://adam-network.up.railway.app" in msg
    assert "actions/runs/998877" in msg
    assert "✅" in msg


def test_build_summary_message_failure():
    msg = post_deploy_summary.build_summary_message(
        status="failure",
        repository="snow884/adam-network",
        ref_name="production",
        commit_sha="abcdef123456",
        actor="bob",
        commit_msg="Fix critical issue",
        server_url="https://github.com",
        run_id="112233",
        extra_details="Deployment timed out after 10m",
    )

    assert "❌ Railway Deployment Failed!" in msg
    assert "snow884/adam-network" in msg
    assert "(`production`)" in msg
    assert "@bob" in msg
    assert "⚠️" in msg
    assert "Deployment timed out after 10m" in msg


def test_build_summary_message_cancelled():
    msg = post_deploy_summary.build_summary_message(
        status="cancelled",
        repository="snow884/adam-network",
        ref_name="main",
        commit_sha="fedcba987654",
        actor="charlie",
    )

    assert "⚠️ Railway Deployment Cancelled!" in msg
    assert "🛑" in msg
    assert "@charlie" in msg


def test_post_deployment_summary_dry_run(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "snow884/adam-network")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_SHA", "abc123456789")
    monkeypatch.setenv("GITHUB_ACTOR", "deployer")
    monkeypatch.setenv("COMMIT_MESSAGE", "CI deploy test")

    result = post_deploy_summary.post_deployment_summary(
        status="success",
        dry_run=True,
    )
    assert "🚀 Railway Deployment Succeeded!" in result
    assert "snow884/adam-network" in result
    assert "abc1234" in result


def test_post_deployment_summary_client_call(monkeypatch):
    mock_msg = Message(
        id=42,
        text="Test deployment summary",
        tags=["platform"],
    )
    mock_client = MagicMock()
    mock_client.token = None
    mock_client.post_message.return_value = mock_msg

    with patch(
        "post_deploy_summary.AdamClient", return_value=mock_client
    ) as mock_cls:
        monkeypatch.setenv("ADAM_NETWORK_USERNAME", "admin_bot")
        monkeypatch.setenv("ADAM_NETWORK_PASSWORD", "secret123")

        post_deploy_summary.post_deployment_summary(
            status="success",
            base_url="https://custom.adam-network.app",
            tags=["platform"],
            dry_run=False,
        )

        mock_cls.assert_called_once_with(
            base_url="https://custom.adam-network.app", token=None
        )
        mock_client.login.assert_called_once_with(
            username="admin_bot", password="secret123"
        )
        mock_client.post_message.assert_called_once()
        _, kwargs = mock_client.post_message.call_args
        assert "platform" in kwargs["tags"]
        assert "🚀 Railway Deployment Succeeded!" in kwargs["text"]
