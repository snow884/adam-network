"""LlamaIndex Reader / Data Connector for Adam Network."""

from typing import Any, Dict, List, Optional

try:
    from llama_index.core.readers.base import BaseReader
    from llama_index.core.schema import Document
except ImportError:
    # Graceful fallback when llama_index.core is not installed
    class BaseReader:  # type: ignore
        pass

    class Document:  # type: ignore
        def __init__(
            self,
            text: str,
            extra_info: Optional[Dict[str, Any]] = None,
            **kwargs: Any,
        ):
            self.text = text
            self.extra_info = extra_info or {}
            self.metadata = self.extra_info
            for k, v in kwargs.items():
                setattr(self, k, v)


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


class AdamNetworkReader(BaseReader):
    """Reader / Data Connector to load messages from the Adam Network into LlamaIndex Documents.

    Usage:
        reader = AdamNetworkReader()
        documents = reader.load_data(tag="ai", limit=100)
        index = VectorStoreIndex.from_documents(documents)
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )

    def load_data(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
        include_replies: bool = False,
    ) -> List[Document]:
        """Load messages from the Adam Network and convert them to LlamaIndex Documents.

        Args:
            query (Optional[str]): Text search query. If provided, searches messages.
            tag (Optional[str]): Tag filter.
            limit (int): Number of messages to fetch (default 50).
            skip (int): Pagination offset.
            include_replies (bool): Whether to also fetch and append thread replies for each message.

        Returns:
            List[Document]: List of LlamaIndex Document instances with message text and metadata.
        """
        if query:
            messages = self.client.search_messages(
                query=query,
                skip=skip,
                limit=limit,
                include_image_data=False,
            )
        else:
            messages = self.client.get_messages(
                skip=skip,
                limit=limit,
                tag=tag,
                include_image_data=False,
            )

        documents: List[Document] = []
        for msg in messages:
            metadata: Dict[str, Any] = {
                "message_id": msg.id,
                "username": msg.username,
                "created_at": msg.created_at,
                "tags": msg.tags,
                "replies_count": getattr(msg, "replies_count", 0),
                "reply_to_id": getattr(msg, "reply_to_id", None),
                "source": "adam_network",
            }
            doc_text = f"[{msg.created_at}] @{msg.username} (ID {msg.id}): {msg.text}"
            if msg.tags:
                doc_text += f"\nTags: {', '.join(msg.tags)}"

            documents.append(Document(text=doc_text, extra_info=metadata))

            if include_replies and getattr(msg, "replies_count", 0) > 0:
                try:
                    replies = self.client.get_replies(
                        message_id=msg.id, limit=50
                    )
                    for reply in replies:
                        reply_meta: Dict[str, Any] = {
                            "message_id": reply.id,
                            "reply_to_id": reply.reply_to_id,
                            "username": reply.username,
                            "created_at": reply.created_at,
                            "tags": reply.tags,
                            "source": "adam_network",
                        }
                        reply_text = f"[{reply.created_at}] @{reply.username} (Reply to {msg.id}): {reply.text}"
                        documents.append(
                            Document(text=reply_text, extra_info=reply_meta)
                        )
                except Exception:
                    pass

        return documents
