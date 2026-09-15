"""Unit tests for adam-network-crewai."""

import json
from unittest.mock import MagicMock
import pytest

from adam_network_crewai import (
    AdamNetworkTool,
    AdamPostTool,
    AdamReadFeedTool,
    AdamReplyTool,
    AdamSearchTool,
)


@pytest.fixture
def mock_adam_client():
    client = MagicMock()
    msg = MagicMock()
    msg.id = 101
    msg.text = "CrewAI Agent Message"
    msg.created_at = "2026-09-15T12:00:00Z"
    msg.username = "crewai_bot"
    msg.tags = ["crewai", "agents"]
    msg.reply_to_id = None
    msg.replies_count = 0
    client.create_message.return_value = msg

    reply = MagicMock()
    reply.id = 102
    reply.reply_to_id = 101
    reply.text = "CrewAI Reply"
    reply.created_at = "2026-09-15T12:01:00Z"
    reply.username = "crewai_bot"
    reply.tags = ["crewai"]
    client.reply_to_message.return_value = reply

    client.get_messages.return_value = [msg]
    client.search_messages.return_value = [msg]
    client.get_replies.return_value = [reply]

    tag_obj = MagicMock()
    tag_obj.tag = "crewai"
    tag_obj.count = 5
    tag_obj.view_count = 25
    client.get_popular_tags.return_value = [tag_obj]

    return client


def test_crewai_post_tool(mock_adam_client):
    tool = AdamPostTool(client=mock_adam_client)
    res_str = tool.run({"text": "Hello from CrewAI", "tags": ["crewai"]})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["id"] == 101
    mock_adam_client.create_message.assert_called_once_with(
        text="Hello from CrewAI",
        tags=["crewai"],
        image_file=None,
        image_data=None,
    )


def test_crewai_reply_tool(mock_adam_client):
    tool = AdamReplyTool(client=mock_adam_client)
    res_str = tool.run({"message_id": 101, "text": "Replying from CrewAI"})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["id"] == 102
    assert res["reply_to_id"] == 101
    mock_adam_client.reply_to_message.assert_called_once_with(
        message_id=101,
        text="Replying from CrewAI",
        tags=None,
        image_file=None,
        image_data=None,
    )


def test_crewai_read_feed_tool(mock_adam_client):
    tool = AdamReadFeedTool(client=mock_adam_client)
    res_str = tool.run({"limit": 5, "tag": "crewai"})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["count"] == 1
    mock_adam_client.get_messages.assert_called_once_with(
        skip=0, limit=5, tag="crewai", include_image_data=False
    )


def test_crewai_search_tool(mock_adam_client):
    tool = AdamSearchTool(client=mock_adam_client)
    res_str = tool.run({"query": "agents"})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["query"] == "agents"
    mock_adam_client.search_messages.assert_called_once_with(
        query="agents", skip=0, limit=20, include_image_data=False
    )


def test_crewai_unified_tool_post(mock_adam_client):
    tool = AdamNetworkTool(client=mock_adam_client)
    res_str = tool.run({"action": "post", "text": "Unified post"})
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["action"] == "post"
    assert res["id"] == 101


def test_crewai_unified_tool_actions(mock_adam_client):
    tool = AdamNetworkTool(client=mock_adam_client)
    # reply
    res = json.loads(
        tool.run({"action": "reply", "message_id": 101, "text": "reply"})
    )
    assert res["status"] == "success"
    # read_feed
    res = json.loads(tool.run({"action": "read_feed"}))
    assert res["status"] == "success"
    # search
    res = json.loads(tool.run({"action": "search", "query": "test"}))
    assert res["status"] == "success"
    # get_replies
    res = json.loads(tool.run({"action": "get_replies", "message_id": 101}))
    assert res["status"] == "success"
    # popular_tags
    res = json.loads(tool.run({"action": "popular_tags"}))
    assert res["status"] == "success"
