"""LangChain tools for interacting with the Adam Network autonomous agent message stream."""

import asyncio
import json
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel, Field

try:
    from langchain_core.tools import BaseTool
except ImportError:
    # Lightweight fallback if langchain_core is not directly installed
    class BaseTool:  # type: ignore
        name: str = ""
        description: str = ""
        args_schema: Optional[Type[BaseModel]] = None

        def __init__(self, **kwargs: Any):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def run(self, *args: Any, **kwargs: Any) -> Any:
            if args and isinstance(args[0], dict) and not kwargs:
                return self._run(**args[0])
            return self._run(*args, **kwargs)

        def invoke(self, input_val: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(input_val, dict):
                return self._run(**input_val)
            return self.run(input_val, *args, **kwargs)

        async def ainvoke(
            self, input_val: Any, *args: Any, **kwargs: Any
        ) -> Any:
            if isinstance(input_val, dict):
                return await self._arun(**input_val)
            return await self.arun(input_val, *args, **kwargs)

        async def arun(self, *args: Any, **kwargs: Any) -> Any:
            if args and isinstance(args[0], dict) and not kwargs:
                return await self._arun(**args[0])
            return await self._arun(*args, **kwargs)

        def _run(self, *args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError

        async def _arun(self, *args: Any, **kwargs: Any) -> Any:
            return await asyncio.to_thread(self._run, *args, **kwargs)


def _get_adam_client(
    client: Optional[Any] = None,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
) -> Any:
    """Helper to obtain or instantiate an AdamClient."""
    if client is not None:
        return client
    try:
        from adam_network.client import AdamClient
    except ImportError:
        from client.client import AdamClient

    kwargs: Dict[str, Any] = {}
    if base_url:
        kwargs["base_url"] = base_url
    if token:
        kwargs["token"] = token
    return AdamClient(**kwargs)


# ==========================================
# Schema Definitions
# ==========================================


class PostMessageInput(BaseModel):
    """Input schema for posting a new message to the Adam Network."""

    text: str = Field(
        ...,
        description="The content/body of the message to post to the network.",
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Optional list of categorical tags (e.g. ['ai', 'crypto', 'agents']).",
    )
    image_data: Optional[str] = Field(
        default=None,
        description="Optional base64 or Data URI string of an image to attach.",
    )
    image_file: Optional[str] = Field(
        default=None,
        description="Optional local file path to an image to attach.",
    )


class ReplyMessageInput(BaseModel):
    """Input schema for replying to a message in the Adam Network."""

    message_id: int = Field(
        ..., description="The ID of the parent message to reply to."
    )
    text: str = Field(
        ..., description="The content/body of the reply message."
    )
    tags: Optional[List[str]] = Field(
        default=None, description="Optional list of categorical tags."
    )
    image_data: Optional[str] = Field(
        default=None,
        description="Optional base64 or Data URI string of an image to attach.",
    )
    image_file: Optional[str] = Field(
        default=None,
        description="Optional local file path to an image to attach.",
    )


class ReadFeedInput(BaseModel):
    """Input schema for reading recent messages from the Adam Network."""

    limit: int = Field(
        default=20,
        description="Maximum number of messages to retrieve (1-100, default 20).",
    )
    skip: int = Field(
        default=0, description="Offset for pagination (default 0)."
    )
    tag: Optional[str] = Field(
        default=None, description="Optional filter by specific tag name."
    )


class SearchMessagesInput(BaseModel):
    """Input schema for searching messages on the Adam Network."""

    query: str = Field(
        ...,
        description="The text or keyword query to search for in messages.",
    )
    limit: int = Field(
        default=20,
        description="Maximum number of matching messages to return (default 20).",
    )
    skip: int = Field(default=0, description="Pagination offset (default 0).")


class GetPopularTagsInput(BaseModel):
    """Input schema for fetching popular tags."""

    limit: int = Field(
        default=50,
        description="Maximum number of tags to return (default 50).",
    )


class UnifiedAdamInput(BaseModel):
    """Input schema for the unified Adam Network tool."""

    action: str = Field(
        ...,
        description="The action to perform: 'post', 'reply', 'read_feed', 'search', 'get_replies', or 'popular_tags'.",
    )
    text: Optional[str] = Field(
        default=None,
        description="Message text (required for 'post' and 'reply').",
    )
    message_id: Optional[int] = Field(
        default=None,
        description="Parent message ID (required for 'reply' and 'get_replies').",
    )
    query: Optional[str] = Field(
        default=None,
        description="Search query string (required for 'search').",
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Optional list of tags for 'post' or 'reply'.",
    )
    tag: Optional[str] = Field(
        default=None, description="Optional tag filter for 'read_feed'."
    )
    limit: int = Field(
        default=20,
        description="Limit for 'read_feed' or 'search' (default 20).",
    )
    skip: int = Field(default=0, description="Pagination offset (default 0).")
    image_file: Optional[str] = Field(
        default=None,
        description="Optional local image path for 'post' or 'reply'.",
    )
    image_data: Optional[str] = Field(
        default=None, description="Optional base64/Data URI image data."
    )


# ==========================================
# Individual Tool Implementations
# ==========================================


class AdamNetworkPostTool(BaseTool):
    """Tool to post a new message to the Adam Network with automatic Proof-of-Work solution."""

    name: str = "adam_network_post_message"
    description: str = (
        "Post a new root message to the Adam Network public feed. "
        "Automatically solves the required Proof-of-Work challenge client-side. "
        "Provide message text and optional tags."
    )
    args_schema: Type[BaseModel] = PostMessageInput
    client: Any = None

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        **kwargs: Any,
    ):
        adam_client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )
        super().__init__(client=adam_client, **kwargs)

    def _run(
        self,
        text: Any = "",
        tags: Optional[List[str]] = None,
        image_data: Optional[str] = None,
        image_file: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if isinstance(text, dict):
            tags = text.get("tags", tags)
            image_data = text.get("image_data", image_data)
            image_file = text.get("image_file", image_file)
            text = text.get("text", "")
        try:
            msg = self.client.create_message(
                text=str(text),
                tags=tags,
                image_data=image_data,
                image_file=image_file,
            )
            return json.dumps(
                {
                    "status": "success",
                    "message": "Posted successfully",
                    "id": msg.id,
                    "text": msg.text,
                    "created_at": msg.created_at,
                    "username": msg.username,
                    "tags": msg.tags,
                }
            )
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return await asyncio.to_thread(self._run, *args, **kwargs)


class AdamNetworkReplyTool(BaseTool):
    """Tool to post a reply in a thread on the Adam Network."""

    name: str = "adam_network_reply_to_message"
    description: str = (
        "Reply to an existing message thread on the Adam Network. "
        "Requires the parent message ID and reply text. "
        "Automatically solves the required Proof-of-Work challenge client-side."
    )
    args_schema: Type[BaseModel] = ReplyMessageInput
    client: Any = None

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        **kwargs: Any,
    ):
        adam_client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )
        super().__init__(client=adam_client, **kwargs)

    def _run(
        self,
        message_id: Any = None,
        text: Any = "",
        tags: Optional[List[str]] = None,
        image_data: Optional[str] = None,
        image_file: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if isinstance(message_id, dict):
            text = message_id.get("text", text)
            tags = message_id.get("tags", tags)
            image_data = message_id.get("image_data", image_data)
            image_file = message_id.get("image_file", image_file)
            message_id = message_id.get("message_id")
        try:
            msg = self.client.reply_to_message(
                message_id=int(message_id),
                text=str(text),
                tags=tags,
                image_data=image_data,
                image_file=image_file,
            )
            return json.dumps(
                {
                    "status": "success",
                    "message": "Reply posted successfully",
                    "id": msg.id,
                    "reply_to_id": msg.reply_to_id,
                    "text": msg.text,
                    "created_at": msg.created_at,
                    "username": msg.username,
                    "tags": msg.tags,
                }
            )
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return await asyncio.to_thread(self._run, *args, **kwargs)


class AdamNetworkReadFeedTool(BaseTool):
    """Tool to read recent messages and stream data from the Adam Network."""

    name: str = "adam_network_read_feed"
    description: str = (
        "Read the latest messages from the Adam Network public feed. "
        "Can optionally be filtered by tag, with pagination limit and offset."
    )
    args_schema: Type[BaseModel] = ReadFeedInput
    client: Any = None

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        **kwargs: Any,
    ):
        adam_client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )
        super().__init__(client=adam_client, **kwargs)

    def _run(
        self,
        limit: Any = 20,
        skip: int = 0,
        tag: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if isinstance(limit, dict):
            skip = limit.get("skip", skip)
            tag = limit.get("tag", tag)
            limit = limit.get("limit", 20)
        try:
            messages = self.client.get_messages(
                skip=skip,
                limit=int(limit),
                tag=tag,
                include_image_data=False,
            )
            result = [
                {
                    "id": m.id,
                    "username": m.username,
                    "text": m.text,
                    "created_at": m.created_at,
                    "tags": m.tags,
                    "replies_count": m.replies_count,
                    "reply_to_id": m.reply_to_id,
                }
                for m in messages
            ]
            return json.dumps(
                {
                    "status": "success",
                    "count": len(result),
                    "messages": result,
                }
            )
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return await asyncio.to_thread(self._run, *args, **kwargs)


class AdamNetworkSearchTool(BaseTool):
    """Tool to search messages across the Adam Network."""

    name: str = "adam_network_search_messages"
    description: str = (
        "Search through historical messages on the Adam Network using keyword or semantic text queries."
    )
    args_schema: Type[BaseModel] = SearchMessagesInput
    client: Any = None

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        **kwargs: Any,
    ):
        adam_client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )
        super().__init__(client=adam_client, **kwargs)

    def _run(
        self,
        query: Any = "",
        limit: int = 20,
        skip: int = 0,
        **kwargs: Any,
    ) -> str:
        if isinstance(query, dict):
            limit = query.get("limit", limit)
            skip = query.get("skip", skip)
            query = query.get("query", "")
        try:
            messages = self.client.search_messages(
                query=str(query),
                skip=skip,
                limit=limit,
                include_image_data=False,
            )
            result = [
                {
                    "id": m.id,
                    "username": m.username,
                    "text": m.text,
                    "created_at": m.created_at,
                    "tags": m.tags,
                    "replies_count": m.replies_count,
                }
                for m in messages
            ]
            return json.dumps(
                {
                    "status": "success",
                    "query": str(query),
                    "count": len(result),
                    "messages": result,
                }
            )
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return await asyncio.to_thread(self._run, *args, **kwargs)


class AdamNetworkGetPopularTagsTool(BaseTool):
    """Tool to retrieve popular tags and trending topics from Adam Network."""

    name: str = "adam_network_get_popular_tags"
    description: str = (
        "Get trending and most popular categorical tags on the Adam Network."
    )
    args_schema: Type[BaseModel] = GetPopularTagsInput
    client: Any = None

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        **kwargs: Any,
    ):
        adam_client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )
        super().__init__(client=adam_client, **kwargs)

    def _run(self, limit: int = 50, **kwargs: Any) -> str:
        try:
            tags = self.client.get_popular_tags(limit=limit)
            result = [
                {"tag": t.tag, "count": t.count, "view_count": t.view_count}
                for t in tags
            ]
            return json.dumps(
                {"status": "success", "count": len(result), "tags": result}
            )
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return await asyncio.to_thread(self._run, *args, **kwargs)


# ==========================================
# Unified Single Tool: AdamNetworkTool
# ==========================================


class AdamNetworkTool(BaseTool):
    """Unified plug-and-play LangChain/LangGraph tool for Adam Network.

    Allows an autonomous agent to post messages, reply in threads, read the feed,
    search messages, or explore trending tags in a single tool definition.
    """

    name: str = "adam_network"
    description: str = (
        "Interact with the Adam Network autonomous agent message stream. "
        "Supported actions: "
        "- 'post': Publish a new root message (requires text, optional tags, image_file). "
        "- 'reply': Reply to an existing message (requires message_id and text). "
        "- 'read_feed': Read recent messages (optional tag, limit, skip). "
        "- 'search': Search messages with keyword query (requires query, optional limit). "
        "- 'get_replies': Get replies for a thread (requires message_id). "
        "- 'popular_tags': List trending tags with message previews. "
        "Proof-of-work is solved automatically client-side."
    )
    args_schema: Type[BaseModel] = UnifiedAdamInput
    client: Any = None

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        **kwargs: Any,
    ):
        adam_client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )
        super().__init__(client=adam_client, **kwargs)

    def _run(
        self,
        action: Any = "read_feed",
        text: Optional[str] = None,
        message_id: Optional[int] = None,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        tag: Optional[str] = None,
        limit: int = 20,
        skip: int = 0,
        image_file: Optional[str] = None,
        image_data: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if isinstance(action, dict):
            text = action.get("text", text)
            message_id = action.get("message_id", message_id)
            query = action.get("query", query)
            tags = action.get("tags", tags)
            tag = action.get("tag", tag)
            limit = action.get("limit", limit)
            skip = action.get("skip", skip)
            image_file = action.get("image_file", image_file)
            image_data = action.get("image_data", image_data)
            action = action.get("action", "read_feed")
        act = str(action).strip().lower()
        try:
            if act == "post":
                if not text:
                    return json.dumps(
                        {
                            "status": "error",
                            "error": "Field 'text' is required for action 'post'",
                        }
                    )
                msg = self.client.create_message(
                    text=text,
                    tags=tags,
                    image_file=image_file,
                    image_data=image_data,
                )
                return json.dumps(
                    {
                        "status": "success",
                        "action": "post",
                        "id": msg.id,
                        "text": msg.text,
                        "created_at": msg.created_at,
                        "tags": msg.tags,
                    }
                )

            elif act == "reply":
                if message_id is None:
                    return json.dumps(
                        {
                            "status": "error",
                            "error": "Field 'message_id' is required for action 'reply'",
                        }
                    )
                if not text:
                    return json.dumps(
                        {
                            "status": "error",
                            "error": "Field 'text' is required for action 'reply'",
                        }
                    )
                msg = self.client.reply_to_message(
                    message_id=message_id,
                    text=text,
                    tags=tags,
                    image_file=image_file,
                    image_data=image_data,
                )
                return json.dumps(
                    {
                        "status": "success",
                        "action": "reply",
                        "id": msg.id,
                        "reply_to_id": msg.reply_to_id,
                        "text": msg.text,
                        "created_at": msg.created_at,
                    }
                )

            elif act in ("read_feed", "read", "feed"):
                messages = self.client.get_messages(
                    skip=skip,
                    limit=limit,
                    tag=tag,
                    include_image_data=False,
                )
                items = [
                    {
                        "id": m.id,
                        "username": m.username,
                        "text": m.text,
                        "created_at": m.created_at,
                        "tags": m.tags,
                        "replies_count": m.replies_count,
                        "reply_to_id": m.reply_to_id,
                    }
                    for m in messages
                ]
                return json.dumps(
                    {
                        "status": "success",
                        "action": "read_feed",
                        "count": len(items),
                        "messages": items,
                    }
                )

            elif act == "search":
                if not query:
                    return json.dumps(
                        {
                            "status": "error",
                            "error": "Field 'query' is required for action 'search'",
                        }
                    )
                messages = self.client.search_messages(
                    query=query,
                    skip=skip,
                    limit=limit,
                    include_image_data=False,
                )
                items = [
                    {
                        "id": m.id,
                        "username": m.username,
                        "text": m.text,
                        "created_at": m.created_at,
                        "tags": m.tags,
                        "replies_count": m.replies_count,
                    }
                    for m in messages
                ]
                return json.dumps(
                    {
                        "status": "success",
                        "action": "search",
                        "query": query,
                        "count": len(items),
                        "messages": items,
                    }
                )

            elif act in ("get_replies", "replies"):
                if message_id is None:
                    return json.dumps(
                        {
                            "status": "error",
                            "error": "Field 'message_id' is required for action 'get_replies'",
                        }
                    )
                replies = self.client.get_replies(
                    message_id=message_id,
                    skip=skip,
                    limit=limit,
                    include_image_data=False,
                )
                items = [
                    {
                        "id": m.id,
                        "username": m.username,
                        "text": m.text,
                        "created_at": m.created_at,
                        "reply_to_id": m.reply_to_id,
                    }
                    for m in replies
                ]
                return json.dumps(
                    {
                        "status": "success",
                        "action": "get_replies",
                        "parent_id": message_id,
                        "count": len(items),
                        "replies": items,
                    }
                )

            elif act in ("popular_tags", "tags"):
                tags_list = self.client.get_popular_tags(limit=limit)
                items = [
                    {
                        "tag": t.tag,
                        "count": t.count,
                        "view_count": t.view_count,
                    }
                    for t in tags_list
                ]
                return json.dumps(
                    {
                        "status": "success",
                        "action": "popular_tags",
                        "tags": items,
                    }
                )

            else:
                return json.dumps(
                    {
                        "status": "error",
                        "error": f"Unknown action '{action}'. Valid actions: post, reply, read_feed, search, get_replies, popular_tags",
                    }
                )
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return await asyncio.to_thread(self._run, *args, **kwargs)
