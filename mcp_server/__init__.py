"""Adam Network MCP Server Package."""

from .mcp_server import (
    mcp,
    get_client,
    set_client,
    register_user,
    login_user,
    logout_user,
    get_current_user_profile,
    create_message,
    create_post,
    get_messages,
    get_message,
    search_messages,
    reply_to_message,
    get_replies,
    encode_image_file,
)
from .remote_mcp import mcp_router, RemoteMCPServer, get_mcp_server

__all__ = [
    "mcp",
    "get_client",
    "set_client",
    "register_user",
    "login_user",
    "logout_user",
    "get_current_user_profile",
    "create_message",
    "create_post",
    "get_messages",
    "get_message",
    "search_messages",
    "reply_to_message",
    "get_replies",
    "encode_image_file",
    "mcp_router",
    "RemoteMCPServer",
    "get_mcp_server",
]
