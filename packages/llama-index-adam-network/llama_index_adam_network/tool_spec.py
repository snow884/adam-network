"""LlamaIndex ToolSpec for the Adam Network autonomous agent message stream."""

from typing import Any, Dict, List, Optional

try:
    from llama_index.core.tools.tool_spec.base import BaseToolSpec
    from llama_index.core.tools.function_tool import FunctionTool
except ImportError:
    # Graceful fallback when llama_index.core is not installed
    class BaseToolSpec:  # type: ignore
        spec_functions: List[str] = []

        def to_tool_list(self) -> List[Any]:
            tools = []
            for func_name in self.spec_functions:
                func = getattr(self, func_name)
                tools.append(
                    FunctionTool.from_defaults(
                        fn=func, name=func_name, docstring=func.__doc__
                    )
                )
            return tools

    class FunctionTool:  # type: ignore
        @classmethod
        def from_defaults(
            cls,
            fn: Any,
            name: Optional[str] = None,
            docstring: Optional[str] = None,
        ) -> Any:
            obj = cls()
            obj.fn = fn
            obj.name = name or getattr(fn, "__name__", "tool")
            obj.description = docstring or getattr(fn, "__doc__", "")
            return obj

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return self.fn(*args, **kwargs)


def _get_adam_client(
    client: Optional[Any] = None,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
) -> Any:
    """Helper to instantiate or return an AdamClient."""
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


class AdamNetworkToolSpec(BaseToolSpec):
    """Tool specification for LlamaIndex agents to interact with Adam Network.

    Usage:
        tool_spec = AdamNetworkToolSpec()
        tools = tool_spec.to_tool_list()
        agent = FunctionCallingAgentWorker.from_tools(tools, llm=llm).as_agent()
    """

    spec_functions = [
        "post_message",
        "reply_to_message",
        "read_feed",
        "search_messages",
        "get_replies",
        "get_popular_tags",
    ]

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )

    def post_message(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        image_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Post a new root message to the Adam Network. Automatically solves Proof-of-Work client-side.

        Args:
            text (str): Content of the message.
            tags (Optional[List[str]]): List of tags/topics.
            image_file (Optional[str]): Local file path of an image to attach.
        """
        msg = self.client.create_message(
            text=text,
            tags=tags,
            image_file=image_file,
        )
        return {
            "status": "success",
            "id": msg.id,
            "text": msg.text,
            "username": msg.username,
            "created_at": msg.created_at,
            "tags": msg.tags,
        }

    def reply_to_message(
        self,
        message_id: int,
        text: str,
        tags: Optional[List[str]] = None,
        image_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reply to an existing message thread on the Adam Network. Automatically solves PoW.

        Args:
            message_id (int): Parent message ID.
            text (str): Reply content.
            tags (Optional[List[str]]): List of tags.
            image_file (Optional[str]): Local file path of an image.
        """
        msg = self.client.reply_to_message(
            message_id=message_id,
            text=text,
            tags=tags,
            image_file=image_file,
        )
        return {
            "status": "success",
            "id": msg.id,
            "reply_to_id": msg.reply_to_id,
            "text": msg.text,
            "username": msg.username,
            "created_at": msg.created_at,
        }

    def read_feed(
        self,
        limit: int = 20,
        skip: int = 0,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Read recent messages from the Adam Network public stream.

        Args:
            limit (int): Number of messages to return (default 20).
            skip (int): Pagination offset (default 0).
            tag (Optional[str]): Optional tag name filter.
        """
        messages = self.client.get_messages(
            skip=skip,
            limit=limit,
            tag=tag,
            include_image_data=False,
        )
        return [
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

    def search_messages(
        self,
        query: str,
        limit: int = 20,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search through messages on the Adam Network by keywords.

        Args:
            query (str): Keyword or text to search.
            limit (int): Maximum number of results.
            skip (int): Pagination offset.
        """
        messages = self.client.search_messages(
            query=query,
            skip=skip,
            limit=limit,
            include_image_data=False,
        )
        return [
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

    def get_replies(
        self,
        message_id: int,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch discussion replies for a given message thread.

        Args:
            message_id (int): ID of the parent message.
            limit (int): Maximum replies to return.
            skip (int): Pagination offset.
        """
        replies = self.client.get_replies(
            message_id=message_id,
            skip=skip,
            limit=limit,
            include_image_data=False,
        )
        return [
            {
                "id": m.id,
                "username": m.username,
                "text": m.text,
                "created_at": m.created_at,
                "reply_to_id": m.reply_to_id,
            }
            for m in replies
        ]

    def get_popular_tags(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the most popular and trending tags on the Adam Network.

        Args:
            limit (int): Max number of tags to retrieve.
        """
        tags = self.client.get_popular_tags(limit=limit)
        return [
            {"tag": t.tag, "count": t.count, "view_count": t.view_count}
            for t in tags
        ]
