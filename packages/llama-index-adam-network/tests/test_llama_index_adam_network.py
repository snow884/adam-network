"""Unit tests for llama-index-adam-network."""

from unittest.mock import MagicMock
import pytest

from llama_index_adam_network import AdamNetworkReader, AdamNetworkToolSpec


@pytest.fixture
def mock_adam_client():
    client = MagicMock()
    msg = MagicMock()
    msg.id = 201
    msg.text = "LlamaIndex Document Post"
    msg.created_at = "2026-09-15T12:00:00Z"
    msg.username = "llama_bot"
    msg.tags = ["llamaindex", "rag"]
    msg.reply_to_id = None
    msg.replies_count = 1
    client.create_message.return_value = msg

    reply = MagicMock()
    reply.id = 202
    reply.reply_to_id = 201
    reply.text = "LlamaIndex Reply Node"
    reply.created_at = "2026-09-15T12:01:00Z"
    reply.username = "reply_bot"
    reply.tags = ["rag"]
    client.reply_to_message.return_value = reply

    client.get_messages.return_value = [msg]
    client.search_messages.return_value = [msg]
    client.get_replies.return_value = [reply]

    tag_obj = MagicMock()
    tag_obj.tag = "rag"
    tag_obj.count = 8
    tag_obj.view_count = 40
    client.get_popular_tags.return_value = [tag_obj]

    return client


def test_tool_spec_functions(mock_adam_client):
    spec = AdamNetworkToolSpec(client=mock_adam_client)
    tools = spec.to_tool_list()
    assert len(tools) == 6

    # Test post_message
    res = spec.post_message(text="Hello from LlamaIndex", tags=["llama"])
    assert res["status"] == "success"
    assert res["id"] == 201
    mock_adam_client.create_message.assert_called_once_with(
        text="Hello from LlamaIndex", tags=["llama"], image_file=None
    )

    # Test reply_to_message
    res_reply = spec.reply_to_message(message_id=201, text="Replying")
    assert res_reply["status"] == "success"
    assert res_reply["id"] == 202
    mock_adam_client.reply_to_message.assert_called_once_with(
        message_id=201, text="Replying", tags=None, image_file=None
    )

    # Test read_feed
    feed = spec.read_feed(limit=5)
    assert len(feed) == 1
    assert feed[0]["id"] == 201

    # Test search_messages
    search_res = spec.search_messages(query="rag")
    assert len(search_res) == 1

    # Test get_popular_tags
    tags = spec.get_popular_tags()
    assert len(tags) == 1
    assert tags[0]["tag"] == "rag"


def test_reader_load_data(mock_adam_client):
    reader = AdamNetworkReader(client=mock_adam_client)
    docs = reader.load_data(tag="rag", limit=10, include_replies=True)
    assert len(docs) == 2  # 1 root message + 1 reply
    assert "LlamaIndex Document Post" in docs[0].text
    assert docs[0].extra_info["message_id"] == 201
    assert "LlamaIndex Reply Node" in docs[1].text
    assert docs[1].extra_info["reply_to_id"] == 201


def test_reader_search_data(mock_adam_client):
    reader = AdamNetworkReader(client=mock_adam_client)
    docs = reader.load_data(query="llamaindex")
    assert len(docs) == 1
    mock_adam_client.search_messages.assert_called_once_with(
        query="llamaindex", skip=0, limit=50, include_image_data=False
    )
