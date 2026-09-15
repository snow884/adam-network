"""Unit tests for langchain-adam-network."""

import json
from unittest.mock import MagicMock
import pytest

from langchain_adam_network import (
    AdamNetworkGetPopularTagsTool,
    AdamNetworkPostTool,
    AdamNetworkReadFeedTool,
    AdamNetworkReplyTool,
    AdamNetworkSearchTool,
    AdamNetworkTool,
    AdamNetworkToolkit,
)


@pytest.fixture
def mock_adam_client():
    client = MagicMock()
    # Mock create_message
    msg = MagicMock()
    msg.id = 42
    msg.text = "Hello Adam Network"
    msg.created_at = "2026-09-15T12:00:00Z"
    msg.username = "guest"
    msg.tags = ["test", "ai"]
    msg.reply_to_id = None
    msg.replies_count = 0
    client.create_message.return_value = msg

    # Mock reply_to_message
    reply = MagicMock()
    reply.id = 43
    reply.reply_to_id = 42
    reply.text = "This is a reply"
    reply.created_at = "2026-09-15T12:01:00Z"
    reply.username = "agent_bot"
    reply.tags = ["test"]
    client.reply_to_message.return_value = reply

    # Mock get_messages
    client.get_messages.return_value = [msg]

    # Mock search_messages
    client.search_messages.return_value = [msg]

    # Mock get_replies
    client.get_replies.return_value = [reply]

    # Mock get_popular_tags
    tag_obj = MagicMock()
    tag_obj.tag = "ai"
    tag_obj.count = 10
    tag_obj.view_count = 50
    client.get_popular_tags.return_value = [tag_obj]

    return client


def test_post_tool(mock_adam_client):
    tool = AdamNetworkPostTool(client=mock_adam_client)
    res_str = tool.run({"text": "Hello world", "tags": ["agent", "ai"]})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["id"] == 42
    assert res["text"] == "Hello Adam Network"
    mock_adam_client.create_message.assert_called_once_with(
        text="Hello world",
        tags=["agent", "ai"],
        image_data=None,
        image_file=None,
    )


def test_reply_tool(mock_adam_client):
    tool = AdamNetworkReplyTool(client=mock_adam_client)
    res_str = tool.run(
        {"message_id": 42, "text": "This is a reply", "tags": ["test"]}
    )
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["id"] == 43
    assert res["reply_to_id"] == 42
    mock_adam_client.reply_to_message.assert_called_once_with(
        message_id=42,
        text="This is a reply",
        tags=["test"],
        image_data=None,
        image_file=None,
    )


def test_read_feed_tool(mock_adam_client):
    tool = AdamNetworkReadFeedTool(client=mock_adam_client)
    res_str = tool.run({"limit": 10, "skip": 0, "tag": "ai"})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["count"] == 1
    assert res["messages"][0]["id"] == 42
    mock_adam_client.get_messages.assert_called_once_with(
        skip=0, limit=10, tag="ai", include_image_data=False
    )


def test_search_tool(mock_adam_client):
    tool = AdamNetworkSearchTool(client=mock_adam_client)
    res_str = tool.run({"query": "crypto", "limit": 5})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["query"] == "crypto"
    assert res["count"] == 1
    mock_adam_client.search_messages.assert_called_once_with(
        query="crypto", skip=0, limit=5, include_image_data=False
    )


def test_unified_adam_tool_post(mock_adam_client):
    tool = AdamNetworkTool(client=mock_adam_client)
    res_str = tool.run(
        {"action": "post", "text": "Unified post", "tags": ["unify"]}
    )
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["action"] == "post"
    assert res["id"] == 42


def test_unified_adam_tool_reply(mock_adam_client):
    tool = AdamNetworkTool(client=mock_adam_client)
    res_str = tool.run(
        {"action": "reply", "message_id": 42, "text": "Unified reply"}
    )
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["action"] == "reply"
    assert res["id"] == 43


def test_unified_adam_tool_read_feed(mock_adam_client):
    tool = AdamNetworkTool(client=mock_adam_client)
    res_str = tool.run({"action": "read_feed", "limit": 10})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["action"] == "read_feed"
    assert res["count"] == 1


def test_toolkit(mock_adam_client):
    toolkit = AdamNetworkToolkit(client=mock_adam_client)
    tools = toolkit.get_tools()
    assert len(tools) == 5
    tool_names = [t.name for t in tools]
    assert "adam_network_post_message" in tool_names
    assert "adam_network_reply_to_message" in tool_names
    assert "adam_network_read_feed" in tool_names
    assert "adam_network_search_messages" in tool_names
    assert "adam_network_get_popular_tags" in tool_names
