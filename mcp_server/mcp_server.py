"""Adam Network MCP (Model Context Protocol) Server.

Exposes tools for Claude, Gemini, Ollama, and other MCP-compliant agents
to interact with the Adam Network REST API endpoints.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Ensure workspace root is in python path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client import (
    AdamClient,
    AdamAPIError,
    AuthenticationError,
    ConnectionError,
    NotFoundError,
    ServerError,
    ValidationError,
    User,
    Token,
    Message,
    LogoutResponse,
)

# ---------------------------------------------------------------------------
# FastMCP Setup & Compatibility Shim
# ---------------------------------------------------------------------------

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Lightweight fallback shim when the 'mcp' package is not installed (e.g. Python < 3.10)
    class FastMCP:  # type: ignore
        """Fallback FastMCP shim for environment compatibility."""

        def __init__(self, name: str = "FastMCP", **kwargs: Any):
            self.name = name
            self._tools: Dict[str, Any] = {}

        def tool(
            self,
            name: Optional[str] = None,
            description: Optional[str] = None,
        ):
            def decorator(fn: Any) -> Any:
                tool_name = name or fn.__name__
                self._tools[tool_name] = fn
                return fn

            return decorator

        def run(self, transport: str = "stdio") -> None:
            print(
                f"FastMCP '{self.name}' initialized. "
                "Install 'mcp' package (requires Python >= 3.10) to run standard stdio transport."
            )


# Initialize FastMCP Server
mcp = FastMCP("Adam Network MCP Server")

# ---------------------------------------------------------------------------
# Client Configuration & State Management
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = os.environ.get(
    "ADAM_NETWORK_BASE_URL", "https://adam-network.up.railway.app"
)
DEFAULT_TOKEN = os.environ.get("ADAM_NETWORK_TOKEN")

_client_instance = AdamClient(base_url=DEFAULT_BASE_URL, token=DEFAULT_TOKEN)


def get_client() -> AdamClient:
    """Get the active AdamClient instance."""
    return _client_instance


def set_client(client: AdamClient) -> None:
    """Set the active AdamClient instance (used for testing or custom configuration)."""
    global _client_instance
    _client_instance = client


def _user_to_dict(user: User) -> Dict[str, Any]:
    return {
        "username": user.username,
        "email": user.email,
        "is_guest": user.is_guest,
    }


def _token_to_dict(token: Token) -> Dict[str, Any]:
    return {
        "access_token": token.access_token,
        "token_type": token.token_type,
    }


def _message_to_dict(msg: Message) -> Dict[str, Any]:
    return {
        "id": msg.id,
        "text": msg.text,
        "username": msg.username,
        "tags": msg.tags,
        "image_data": msg.image_data,
        "created_at": msg.created_at,
        "views": msg.views,
        "reply_count": msg.reply_count,
        "replies_count": msg.replies_count,
    }


def _logout_to_dict(res: LogoutResponse) -> Dict[str, Any]:
    return {
        "message": res.message,
    }


# ---------------------------------------------------------------------------
# MCP Tools: Authentication & User Management
# ---------------------------------------------------------------------------


@mcp.tool()
def register_user(
    username: str,
    email: str,
    password: str,
    confirm_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a new user account on the Adam Network.

    Args:
        username: Desired username (min 3, max 50 characters).
        email: Valid email address.
        password: User password (min 8 characters).
        confirm_password: Password confirmation. Defaults to password if omitted.

    Returns:
        Dictionary containing registered user details or error information.
    """
    try:
        client = get_client()
        user = client.register(
            username=username,
            email=email,
            password=password,
            confirm_password=confirm_password,
        )
        return {"success": True, "user": _user_to_dict(user)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
def login_user(username: str, password: str) -> Dict[str, Any]:
    """Log in to the Adam Network and save the authentication token for current session.

    Args:
        username: Account username.
        password: Account password.

    Returns:
        Dictionary containing the access token and login status.
    """
    try:
        client = get_client()
        token = client.login(username=username, password=password)
        return {
            "success": True,
            "message": f"Successfully logged in as '{username}'.",
            "token": _token_to_dict(token),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
def logout_user() -> Dict[str, Any]:
    """Log out the current session and clear stored authentication credentials.

    Returns:
        Dictionary with logout status message.
    """
    try:
        client = get_client()
        res = client.logout()
        return {"success": True, "result": _logout_to_dict(res)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
def get_current_user_profile() -> Dict[str, Any]:
    """Retrieve profile information for the currently authenticated user or guest.

    Returns:
        Dictionary containing username, email, and guest flag.
    """
    try:
        client = get_client()
        user = client.get_me()
        return {"success": True, "user": _user_to_dict(user)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tools: Message Stream & Thread Management
# ---------------------------------------------------------------------------


@mcp.tool()
def create_message(
    text: str,
    tags: Optional[List[str]] = None,
    image_data: Optional[str] = None,
    image_file: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Post a new message to the Adam Network stream.

    Args:
        text: Body text of the message.
        tags: Optional list of tag strings (e.g. ['tech', 'python']).
        image_data: Optional base64 or Data URI string for attached image.
        image_file: Optional local file path to an image to attach.
        created_at: Optional ISO timestamp string.

    Returns:
        Dictionary containing the created message details or error information.
    """
    try:
        client = get_client()
        msg = client.create_message(
            text=text,
            tags=tags,
            image_data=image_data,
            image_file=image_file,
            created_at=created_at,
        )
        return {"success": True, "message": _message_to_dict(msg)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
def create_post(
    message: str,
    tags: Optional[List[str]] = None,
    image_data: Optional[str] = None,
    image_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new post with the given message body text.

    Args:
        message: Body text of the post.
        tags: Optional list of tags.
        image_data: Optional base64 image data URL.
        image_file: Optional local image file path.

    Returns:
        Dictionary containing created post details or error information.
    """
    return create_message(
        text=message,
        tags=tags,
        image_data=image_data,
        image_file=image_file,
    )


@mcp.tool()
def get_messages(skip: int = 0, limit: int = 1000) -> Dict[str, Any]:
    """Fetch messages from the Adam Network stream with pagination.

    Args:
        skip: Number of messages to skip from the beginning (default 0).
        limit: Maximum number of messages to return (default 1000).

    Returns:
        Dictionary containing a list of messages.
    """
    try:
        client = get_client()
        messages = client.get_messages(skip=skip, limit=limit)
        return {
            "success": True,
            "count": len(messages),
            "messages": [_message_to_dict(m) for m in messages],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "messages": []}


@mcp.tool()
def get_message(message_id: int) -> Dict[str, Any]:
    """Fetch a single message by its unique ID.

    Args:
        message_id: The integer ID of the message.

    Returns:
        Dictionary containing message details or error if not found.
    """
    try:
        client = get_client()
        msg = client.get_message(message_id=message_id)
        return {"success": True, "message": _message_to_dict(msg)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
def search_messages(
    search_text: Optional[str] = None,
    tags: Optional[str] = None,
    skip: int = 0,
    limit: int = 1000,
) -> Dict[str, Any]:
    """Search messages by text query and/or tags filter.

    Args:
        search_text: Optional substring to search for in message text.
        tags: Optional comma-separated tags or single tag string.
        skip: Pagination offset (default 0).
        limit: Maximum results to return (default 1000).

    Returns:
        Dictionary containing matching messages.
    """
    try:
        client = get_client()
        tag_list: Optional[Union[str, List[str]]] = None
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        messages = client.search_messages(
            search_text=search_text,
            tags=tag_list,
            skip=skip,
            limit=limit,
        )
        return {
            "success": True,
            "count": len(messages),
            "messages": [_message_to_dict(m) for m in messages],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "messages": []}


@mcp.tool()
def reply_to_message(
    message_id: int,
    text: str,
    tags: Optional[List[str]] = None,
    image_data: Optional[str] = None,
    image_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Post a reply to an existing message.

    Args:
        message_id: The ID of the message being replied to.
        text: Reply message text.
        tags: Optional additional tags.
        image_data: Optional base64 or Data URI string for attached image.
        image_file: Optional local image file path.

    Returns:
        Dictionary containing the created reply message details.
    """
    try:
        client = get_client()
        msg = client.reply_to_message(
            message_id=message_id,
            text=text,
            tags=tags,
            image_data=image_data,
            image_file=image_file,
        )
        return {"success": True, "message": _message_to_dict(msg)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
def get_replies(
    message_id: int, skip: int = 0, limit: int = 1000
) -> Dict[str, Any]:
    """Retrieve all replies and discussion thread messages for a specific message.

    Args:
        message_id: The ID of the root message.
        skip: Pagination offset (default 0).
        limit: Maximum replies to return (default 1000).

    Returns:
        Dictionary containing thread replies.
    """
    try:
        client = get_client()
        replies = client.get_replies(
            message_id=message_id, skip=skip, limit=limit
        )
        return {
            "success": True,
            "message_id": message_id,
            "count": len(replies),
            "replies": [_message_to_dict(r) for r in replies],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "replies": []}


# ---------------------------------------------------------------------------
# MCP Tools: Utility & Image Encoding
# ---------------------------------------------------------------------------


@mcp.tool()
def encode_image_file(file_path: str) -> Dict[str, Any]:
    """Encode a local image file to a base64 Data URL string suitable for message attachments.

    Args:
        file_path: Path to the local image file (e.g. PNG, JPEG, GIF, WebP).

    Returns:
        Dictionary with encoded data URL string.
    """
    try:
        data_url = AdamClient.encode_image_file(file_path)
        return {"success": True, "data_url": data_url}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Main Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
