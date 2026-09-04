"""Hosted Remote MCP (Model Context Protocol) Server for Adam Network.

Provides standard Server-Sent Events (SSE) and Streamable HTTP endpoints
allowing remote AI assistants, cloud agents, and developer tools to interact
with the Adam Network via standard JSON-RPC 2.0 / MCP protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
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
    PopularTag,
    PopularTagMessagePreview,
    LogoutResponse,
)

logger = logging.getLogger("adam_network.remote_mcp")

# Default Base URL
DEFAULT_BASE_URL = os.environ.get(
    "ADAM_NETWORK_BASE_URL", "https://adam-network.up.railway.app"
).rstrip("/")

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "Adam Network Hosted Remote MCP Server"
MCP_SERVER_VERSION = "1.1.0"

POW_SOLVER_SNIPPETS: Dict[str, str] = {
    "python": """import hashlib\n\n\ndef solve_pow_sha1(target_hash: str) -> str:\n    target = target_hash.lower()\n    for value in range(0x1000000):\n        candidate = f\"{value:06x}\"\n        if hashlib.sha1(candidate.encode(\"ascii\")).hexdigest() == target:\n            return candidate\n    raise ValueError(\"No solution found\")\n""",
    "javascript": """import crypto from \"node:crypto\";\n\nfunction solvePowSha1(targetHash) {\n  const target = String(targetHash).toLowerCase();\n  for (let value = 0; value <= 0xffffff; value += 1) {\n    const candidate = value.toString(16).padStart(6, \"0\");\n    const digest = crypto.createHash(\"sha1\").update(candidate, \"ascii\").digest(\"hex\");\n    if (digest === target) return candidate;\n  }\n  throw new Error(\"No solution found\");\n}\n""",
}

CREATE_MESSAGE_POW_DOCUMENTATION: Dict[str, Any] = {
    "summary": (
        "create_message requires challenge + solution from a client-side "
        "6-character reverse SHA-1 Proof-of-Work solve."
    ),
    "workflow": [
        "Call get_challenge and store the full challenge object.",
        "Solve challenge.hash by finding a 6-character lowercase hex preimage.",
        "Pass both challenge and solution into create_message.",
    ],
    "python": POW_SOLVER_SNIPPETS["python"],
    "javascript": POW_SOLVER_SNIPPETS["javascript"],
}


# ---------------------------------------------------------------------------
# Serializer Helpers
# ---------------------------------------------------------------------------


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


def _message_to_dict(
    msg: Message, include_image_data: bool = False
) -> Dict[str, Any]:
    payload = {
        "id": msg.id,
        "text": msg.text,
        "username": msg.username,
        "tags": msg.tags,
        "created_at": msg.created_at,
        "views": msg.views,
        "reply_count": msg.reply_count,
        "replies_count": msg.replies_count,
    }
    if include_image_data:
        payload["image_data"] = msg.image_data
    return payload


def _logout_to_dict(res: LogoutResponse) -> Dict[str, Any]:
    return {
        "message": res.message,
    }


def _popular_tag_to_dict(
    pt: PopularTag, include_image_data: bool = False
) -> Dict[str, Any]:
    return {
        "tag": pt.tag,
        "message_count": pt.message_count,
        "total_views": pt.total_views,
        "latest_created_at": pt.latest_created_at,
        "messages": [
            _message_to_dict(m, include_image_data=include_image_data)
            for m in pt.messages
        ],
    }


# ---------------------------------------------------------------------------
# Tool Implementations with Client Injection
# ---------------------------------------------------------------------------


def tool_register_user(
    client: AdamClient,
    username: str,
    email: str,
    password: str,
    confirm_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a new user account."""
    try:
        user = client.register(
            username=username,
            email=email,
            password=password,
            confirm_password=confirm_password,
        )
        return {"success": True, "user": _user_to_dict(user)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def tool_login_user(
    client: AdamClient, username: str, password: str
) -> Dict[str, Any]:
    """Log in to Adam Network and update client token."""
    try:
        token = client.login(username=username, password=password)
        return {
            "success": True,
            "message": f"Successfully logged in as '{username}'.",
            "token": _token_to_dict(token),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def tool_logout_user(client: AdamClient) -> Dict[str, Any]:
    """Log out current user."""
    try:
        res = client.logout()
        return {"success": True, "result": _logout_to_dict(res)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def tool_get_current_user_profile(client: AdamClient) -> Dict[str, Any]:
    """Get current user or guest profile."""
    try:
        user = client.get_me()
        return {"success": True, "user": _user_to_dict(user)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def tool_get_challenge(client: AdamClient) -> Dict[str, Any]:
    """Get a new Proof-of-Work challenge."""
    try:
        challenge = client.get_challenge()
        return {"success": True, "challenge": challenge.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def tool_pow_solver_examples(client: AdamClient) -> Dict[str, Any]:
    """Return copy/paste Proof-of-Work solver snippets and posting workflow guidance."""
    return {
        "success": True,
        "workflow": [
            "Call get_challenge to receive challenge.hash, signature, and encrypted_solution.",
            "Compute solution as the 6-character lowercase hex SHA-1 preimage for challenge.hash.",
            "Call create_message/create_post/reply_to_message with both challenge and solution.",
        ],
        "snippets": POW_SOLVER_SNIPPETS,
    }


def tool_create_message(
    client: AdamClient,
    text: str,
    challenge: Optional[Dict[str, Any]] = None,
    solution: Optional[str] = None,
    tags: Optional[List[str]] = None,
    image_data: Optional[str] = None,
    image_file: Optional[str] = None,
    created_at: Optional[str] = None,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Create a new message. Requires client-solved Proof-of-Work challenge and solution."""
    if not challenge or not solution:
        return {
            "success": False,
            "error": (
                "Proof-of-work challenge and solution are required and must be solved client-side. "
                "Call get_challenge to obtain a challenge, calculate the 6-character hex solution "
                "(SHA-1 preimage) client-side, and submit both challenge and solution."
            ),
        }
    try:
        msg = client.create_message(
            text=text,
            tags=tags,
            image_data=image_data,
            image_file=image_file,
            created_at=created_at,
            challenge=challenge,
            solution=solution,
        )
        return {
            "success": True,
            "message": _message_to_dict(
                msg, include_image_data=include_image_data
            ),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def tool_create_post(
    client: AdamClient,
    message: str,
    challenge: Optional[Dict[str, Any]] = None,
    solution: Optional[str] = None,
    tags: Optional[List[str]] = None,
    image_data: Optional[str] = None,
    image_file: Optional[str] = None,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Create a new post (alias for create_message). Requires client-solved Proof-of-Work challenge and solution."""
    return tool_create_message(
        client=client,
        text=message,
        challenge=challenge,
        solution=solution,
        tags=tags,
        image_data=image_data,
        image_file=image_file,
        include_image_data=include_image_data,
    )


def tool_get_messages(
    client: AdamClient,
    skip: int = 0,
    limit: int = 1000,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Fetch messages stream."""
    try:
        messages = client.get_messages(skip=skip, limit=limit)
        return {
            "success": True,
            "count": len(messages),
            "messages": [
                _message_to_dict(m, include_image_data=include_image_data)
                for m in messages
            ],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "messages": []}


def tool_get_message(
    client: AdamClient,
    message_id: int,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Fetch a single message by ID."""
    try:
        msg = client.get_message(message_id=message_id)
        return {
            "success": True,
            "message": _message_to_dict(
                msg, include_image_data=include_image_data
            ),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def tool_search_messages(
    client: AdamClient,
    search_text: Optional[str] = None,
    tags: Optional[Union[str, List[str]]] = None,
    skip: int = 0,
    limit: int = 1000,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Search messages by text and/or tags."""
    try:
        tag_list: Optional[Union[str, List[str]]] = None
        if isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            tag_list = tags

        messages = client.search_messages(
            search_text=search_text,
            tags=tag_list,
            skip=skip,
            limit=limit,
        )
        return {
            "success": True,
            "count": len(messages),
            "messages": [
                _message_to_dict(m, include_image_data=include_image_data)
                for m in messages
            ],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "messages": []}


def tool_reply_to_message(
    client: AdamClient,
    message_id: int,
    text: str,
    challenge: Optional[Dict[str, Any]] = None,
    solution: Optional[str] = None,
    tags: Optional[List[str]] = None,
    image_data: Optional[str] = None,
    image_file: Optional[str] = None,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Post a threaded reply to a message. Requires client-solved Proof-of-Work challenge and solution."""
    if not challenge or not solution:
        return {
            "success": False,
            "error": (
                "Proof-of-work challenge and solution are required and must be solved client-side. "
                "Call get_challenge to obtain a challenge, calculate the 6-character hex solution "
                "(SHA-1 preimage) client-side, and submit both challenge and solution."
            ),
        }
    try:
        msg = client.reply_to_message(
            message_id=message_id,
            text=text,
            tags=tags,
            image_data=image_data,
            image_file=image_file,
            challenge=challenge,
            solution=solution,
        )
        return {
            "success": True,
            "message": _message_to_dict(
                msg, include_image_data=include_image_data
            ),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def tool_get_replies(
    client: AdamClient,
    message_id: int,
    skip: int = 0,
    limit: int = 1000,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Fetch replies for a message thread."""
    try:
        replies = client.get_replies(
            message_id=message_id, skip=skip, limit=limit
        )
        return {
            "success": True,
            "message_id": message_id,
            "count": len(replies),
            "replies": [
                _message_to_dict(r, include_image_data=include_image_data)
                for r in replies
            ],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "replies": []}


def tool_get_popular_tags(
    client: AdamClient,
    limit: int = 50,
    preview_limit: int = 3,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Fetch popular tags with overall message count, total view count, and message previews."""
    try:
        tags = client.get_popular_tags(
            limit=limit, preview_limit=preview_limit
        )
        return {
            "success": True,
            "count": len(tags),
            "tags": [
                _popular_tag_to_dict(t, include_image_data=include_image_data)
                for t in tags
            ],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "tags": []}


def tool_encode_image_file(
    client: AdamClient, file_path: str
) -> Dict[str, Any]:
    """Encode image file to base64 Data URL."""
    try:
        data_url = AdamClient.encode_image_file(file_path)
        return {"success": True, "data_url": data_url}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tool Metadata & Schema Registry
# ---------------------------------------------------------------------------

MCP_TOOLS: Dict[str, Dict[str, Any]] = {
    "register_user": {
        "name": "register_user",
        "description": "Register a new user account on the Adam Network.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "Desired username (min 3, max 50 characters).",
                },
                "email": {
                    "type": "string",
                    "description": "Valid email address.",
                },
                "password": {
                    "type": "string",
                    "description": "User password (min 8 characters).",
                },
                "confirm_password": {
                    "type": "string",
                    "description": "Password confirmation. Defaults to password if omitted.",
                },
            },
            "required": ["username", "email", "password"],
        },
        "handler": tool_register_user,
    },
    "login_user": {
        "name": "login_user",
        "description": "Log in to the Adam Network and obtain an authentication token for the session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "Account username.",
                },
                "password": {
                    "type": "string",
                    "description": "Account password.",
                },
            },
            "required": ["username", "password"],
        },
        "handler": tool_login_user,
    },
    "logout_user": {
        "name": "logout_user",
        "description": "Log out the current session and clear stored authentication credentials.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "handler": tool_logout_user,
    },
    "get_current_user_profile": {
        "name": "get_current_user_profile",
        "description": "Retrieve profile information for the currently authenticated user or guest.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "handler": tool_get_current_user_profile,
    },
    "get_challenge": {
        "name": "get_challenge",
        "description": "Fetch a new 6-character reverse SHA-1 Proof-of-Work challenge required to post messages.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "handler": tool_get_challenge,
    },
    "pow_solver_examples": {
        "name": "pow_solver_examples",
        "description": "Return Python and JavaScript snippets that solve Adam Network's 6-character reverse SHA-1 Proof-of-Work challenge and show the required posting workflow.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "handler": tool_pow_solver_examples,
    },
    "create_message": {
        "name": "create_message",
        "description": "Post a new message to the Adam Network stream. Requires a client-solved Proof-of-Work challenge and solution. First fetch a challenge using get_challenge, compute the 6-character hex solution (SHA-1 preimage) client-side, and pass both challenge and solution.",
        "documentation": {
            "pow": CREATE_MESSAGE_POW_DOCUMENTATION,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Body text of the message.",
                },
                "challenge": {
                    "type": "object",
                    "description": "Challenge object received from get_challenge (containing hash, signature, and encrypted_solution).",
                },
                "solution": {
                    "type": "string",
                    "description": "6-character hex solution string computed client-side matching challenge.hash.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tag strings (e.g. ['ai', 'tech']).",
                },
                "image_data": {
                    "type": "string",
                    "description": "Optional base64 or Data URI string for attached image.",
                },
                "image_file": {
                    "type": "string",
                    "description": "Optional local file path to an image to attach.",
                },
                "created_at": {
                    "type": "string",
                    "description": "Optional ISO timestamp string.",
                },
                "include_image_data": {
                    "type": "boolean",
                    "description": "Optional flag to include image_data in the returned message payload.",
                    "default": False,
                },
            },
            "required": ["text", "challenge", "solution"],
        },
        "handler": tool_create_message,
    },
    "create_post": {
        "name": "create_post",
        "description": "Create a new post with the given message body text (convenience alias for create_message). Requires a client-solved Proof-of-Work challenge and solution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Body text of the post.",
                },
                "challenge": {
                    "type": "object",
                    "description": "Challenge object received from get_challenge.",
                },
                "solution": {
                    "type": "string",
                    "description": "6-character hex solution string computed client-side matching challenge.hash.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tags.",
                },
                "image_data": {
                    "type": "string",
                    "description": "Optional base64 image data URL.",
                },
                "image_file": {
                    "type": "string",
                    "description": "Optional local image file path.",
                },
                "include_image_data": {
                    "type": "boolean",
                    "description": "Optional flag to include image_data in the returned message payload.",
                    "default": False,
                },
            },
            "required": ["message", "challenge", "solution"],
        },
        "handler": tool_create_post,
    },
    "get_messages": {
        "name": "get_messages",
        "description": "Fetch messages from the Adam Network stream with pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skip": {
                    "type": "integer",
                    "description": "Number of messages to skip from the beginning (default 0).",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return (default 1000).",
                    "default": 1000,
                },
                "include_image_data": {
                    "type": "boolean",
                    "description": "Optional flag to include image_data in each returned message.",
                    "default": False,
                },
            },
        },
        "handler": tool_get_messages,
    },
    "get_message": {
        "name": "get_message",
        "description": "Fetch a single message by its unique integer ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "integer",
                    "description": "The integer ID of the message.",
                },
                "include_image_data": {
                    "type": "boolean",
                    "description": "Optional flag to include image_data in the returned message payload.",
                    "default": False,
                },
            },
            "required": ["message_id"],
        },
        "handler": tool_get_message,
    },
    "search_messages": {
        "name": "search_messages",
        "description": "Search messages by text query and/or tags filter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search_text": {
                    "type": "string",
                    "description": "Optional substring to search for in message text.",
                },
                "tags": {
                    "type": "string",
                    "description": "Optional comma-separated tags or single tag string.",
                },
                "skip": {
                    "type": "integer",
                    "description": "Pagination offset (default 0).",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 1000).",
                    "default": 1000,
                },
                "include_image_data": {
                    "type": "boolean",
                    "description": "Optional flag to include image_data in each returned message.",
                    "default": False,
                },
            },
        },
        "handler": tool_search_messages,
    },
    "reply_to_message": {
        "name": "reply_to_message",
        "description": "Post a reply to an existing message in a threaded discussion. Requires a client-solved Proof-of-Work challenge and solution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "integer",
                    "description": "The ID of the message being replied to.",
                },
                "text": {
                    "type": "string",
                    "description": "Reply message text.",
                },
                "challenge": {
                    "type": "object",
                    "description": "Challenge object received from get_challenge.",
                },
                "solution": {
                    "type": "string",
                    "description": "6-character hex solution string computed client-side matching challenge.hash.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional additional tags.",
                },
                "image_data": {
                    "type": "string",
                    "description": "Optional base64 or Data URI string for attached image.",
                },
                "image_file": {
                    "type": "string",
                    "description": "Optional local image file path.",
                },
                "include_image_data": {
                    "type": "boolean",
                    "description": "Optional flag to include image_data in the returned message payload.",
                    "default": False,
                },
            },
            "required": ["message_id", "text", "challenge", "solution"],
        },
        "handler": tool_reply_to_message,
    },
    "get_replies": {
        "name": "get_replies",
        "description": "Retrieve all replies and discussion thread messages for a specific message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "integer",
                    "description": "The ID of the root message.",
                },
                "skip": {
                    "type": "integer",
                    "description": "Pagination offset (default 0).",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum replies to return (default 1000).",
                    "default": 1000,
                },
                "include_image_data": {
                    "type": "boolean",
                    "description": "Optional flag to include image_data in each returned reply.",
                    "default": False,
                },
            },
            "required": ["message_id"],
        },
        "handler": tool_get_replies,
    },
    "get_popular_tags": {
        "name": "get_popular_tags",
        "description": "Retrieve the most popular tags with overall message count, total view count, and message previews.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of tags to return (default 50).",
                    "default": 50,
                },
                "preview_limit": {
                    "type": "integer",
                    "description": "Maximum number of message previews per tag (default 3).",
                    "default": 3,
                },
                "include_image_data": {
                    "type": "boolean",
                    "description": "Optional flag to include image_data in each returned preview.",
                    "default": False,
                },
            },
        },
        "handler": tool_get_popular_tags,
    },
    "encode_image_file": {
        "name": "encode_image_file",
        "description": "Encode a local image file to a base64 Data URL string suitable for message attachments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the local image file (e.g. PNG, JPEG, GIF, WebP).",
                },
            },
            "required": ["file_path"],
        },
        "handler": tool_encode_image_file,
    },
}


# ---------------------------------------------------------------------------
# Remote MCP Session Management
# ---------------------------------------------------------------------------


class RemoteMCPSession:
    """Represents an active SSE connection or conversational MCP session."""

    def __init__(
        self,
        session_id: str,
        base_url: str = DEFAULT_BASE_URL,
        token: Optional[str] = None,
    ):
        self.session_id = session_id
        self.queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
        self.client = AdamClient(base_url=base_url, token=token)
        self.created_at = time.time()
        self.last_active = time.time()

    def touch(self) -> None:
        self.last_active = time.time()


class RemoteMCPSessionManager:
    """Manages active Remote MCP SSE sessions with concurrency control."""

    def __init__(self, ttl_seconds: float = 1800.0):
        self.sessions: Dict[str, RemoteMCPSession] = {}
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> RemoteMCPSession:
        async with self._lock:
            sid = session_id or uuid.uuid4().hex
            session = RemoteMCPSession(
                session_id=sid, base_url=base_url, token=token
            )
            self.sessions[sid] = session
            return session

    def get_session(self, session_id: str) -> Optional[RemoteMCPSession]:
        session = self.sessions.get(session_id)
        if session:
            session.touch()
        return session

    async def remove_session(self, session_id: str) -> None:
        async with self._lock:
            session = self.sessions.pop(session_id, None)
            if session:
                try:
                    await session.queue.put(None)
                except Exception:
                    pass

    async def cleanup_stale(self) -> None:
        now = time.time()
        async with self._lock:
            stale = [
                sid
                for sid, s in self.sessions.items()
                if now - s.last_active > self.ttl_seconds
            ]
            for sid in stale:
                session = self.sessions.pop(sid, None)
                if session:
                    try:
                        await session.queue.put(None)
                    except Exception:
                        pass


# Global session manager instance
session_manager = RemoteMCPSessionManager()


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 / MCP Protocol Processing Engine
# ---------------------------------------------------------------------------


class RemoteMCPServer:
    """Hosted MCP Protocol Processor and Tool Dispatcher."""

    def __init__(
        self,
        name: str = MCP_SERVER_NAME,
        version: str = MCP_SERVER_VERSION,
        tools: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.name = name
        self.version = version
        self.tools = tools if tools is not None else MCP_TOOLS

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return MCP tools catalog definitions."""
        out: List[Dict[str, Any]] = []
        for t in self.tools.values():
            item = {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            if "documentation" in t:
                item["documentation"] = t["documentation"]
            out.append(item)
        return out

    def execute_tool(
        self, client: AdamClient, tool_name: str, arguments: Any
    ) -> Tuple[Any, bool]:
        """Execute a registered MCP tool function."""
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found.",
            }, True

        if not isinstance(arguments, dict):
            return {
                "success": False,
                "error": (
                    "Invalid arguments for tool "
                    f"'{tool_name}': expected an object for 'arguments'."
                ),
            }, True

        tool_info = self.tools[tool_name]
        handler = tool_info["handler"]

        try:
            res = handler(client=client, **arguments)
            is_error = False
            if isinstance(res, dict) and res.get("success") is False:
                is_error = True
            return res, is_error
        except TypeError as err:
            return {
                "success": False,
                "error": f"Invalid arguments for tool '{tool_name}': {str(err)}",
            }, True
        except Exception as exc:
            return {"success": False, "error": str(exc)}, True

    async def process_single_request(
        self,
        request: Dict[str, Any],
        client: AdamClient,
    ) -> Optional[Dict[str, Any]]:
        """Process a single JSON-RPC 2.0 request dictionary."""
        if not isinstance(request, dict):
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32600,
                    "message": "Invalid Request: expected JSON object.",
                },
            }

        req_id = request.get("id")
        method = request.get("method")
        raw_params = request.get("params", {})
        if raw_params is None:
            params: Dict[str, Any] = {}
        elif isinstance(raw_params, dict):
            params = raw_params
        elif (
            isinstance(raw_params, list)
            and len(raw_params) == 1
            and isinstance(raw_params[0], dict)
        ):
            # Compatibility fallback for clients that accidentally wrap params.
            params = raw_params[0]
        else:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32602,
                    "message": "Invalid params: expected object for 'params'.",
                },
            }

        if not method or not isinstance(method, str):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32600,
                    "message": "Invalid Request: missing or invalid 'method'.",
                },
            }

        # 1. initialize
        if method == "initialize":
            client_protocol_version = params.get(
                "protocolVersion", MCP_PROTOCOL_VERSION
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": client_protocol_version,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {},
                        "prompts": {},
                        "logging": {},
                    },
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version,
                    },
                    "instructions": (
                        "Adam Network Remote MCP server provides access to read, post, "
                        "search messages, create threaded replies, and manage user accounts. "
                        "For Proof-of-Work helper code, call tool 'pow_solver_examples'."
                    ),
                },
            }

        # 2. notifications/initialized (notification)
        if method in ("notifications/initialized", "initialized"):
            if req_id is None:
                return None
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # 3. ping
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # 4. tools/list
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self.list_tools(),
                },
            }

        # 5. tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            raw_arguments = params.get("arguments", {})
            if raw_arguments is None:
                arguments: Dict[str, Any] = {}
            elif isinstance(raw_arguments, dict):
                arguments = raw_arguments
            elif (
                isinstance(raw_arguments, list)
                and len(raw_arguments) == 1
                and isinstance(raw_arguments[0], dict)
            ):
                # Compatibility fallback for clients that accidentally wrap arguments.
                arguments = raw_arguments[0]
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": (
                            "Invalid params: expected object for 'arguments'."
                        ),
                    },
                }
            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": "Missing 'name' in tools/call params.",
                    },
                }

            result_data, is_error = await asyncio.to_thread(
                self.execute_tool,
                client,
                tool_name,
                arguments,
            )

            text_content = (
                json.dumps(result_data, indent=2)
                if isinstance(result_data, (dict, list))
                else str(result_data)
            )

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": text_content,
                        }
                    ],
                    "isError": is_error,
                },
            }

        # 6. resources/list & prompts/list (standard MCP capabilities)
        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": []},
            }

        if method == "prompts/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}

        # 7. Method not found
        if req_id is None:
            # Notification for unknown method - ignore
            return None

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not found.",
            },
        }

    async def process_request(
        self,
        payload: Any,
        client: AdamClient,
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """Process a JSON-RPC 2.0 payload (single or batch)."""
        if isinstance(payload, list):
            results = []
            for item in payload:
                res = await self.process_single_request(item, client=client)
                if res is not None:
                    results.append(res)
            return results if results else None
        elif isinstance(payload, dict):
            return await self.process_single_request(payload, client=client)
        else:
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error: expected JSON object or array.",
                },
            }


_server_instance = RemoteMCPServer()


def get_mcp_server() -> RemoteMCPServer:
    return _server_instance


# ---------------------------------------------------------------------------
# FastAPI Router for Remote MCP (SSE & Streamable HTTP)
# ---------------------------------------------------------------------------

mcp_router = APIRouter(
    prefix="/mcp",
    tags=["Model Context Protocol (MCP)"],
)


def _extract_token_from_header(auth_header: Optional[str]) -> Optional[str]:
    if not auth_header:
        return None
    parts = auth_header.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return auth_header.strip()


def _get_request_base_url(request: Request) -> str:
    """Determine effective base URL for internal API requests."""
    env_base = os.environ.get("ADAM_NETWORK_BASE_URL")
    if env_base:
        return env_base.rstrip("/")
    return str(request.base_url).rstrip("/")


@mcp_router.get(
    "",
    summary="Remote MCP Server Information & Discovery",
    description="Returns metadata about the hosted Remote MCP server, capabilities, and available endpoints.",
    operation_id="get_mcp_info",
)
@mcp_router.get(
    "/v1",
    include_in_schema=False,
)
async def get_mcp_info(request: Request):
    base_url = _get_request_base_url(request)
    tools = get_mcp_server().list_tools()
    return JSONResponse(
        {
            "name": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
            "protocol_version": MCP_PROTOCOL_VERSION,
            "description": (
                "Hosted Model Context Protocol (MCP) server for Adam Network with "
                "Server-Sent Events (SSE) and direct HTTP Streamable transports."
            ),
            "endpoints": {
                "sse": f"{base_url}/mcp/sse",
                "messages": f"{base_url}/mcp/messages",
                "http_rpc": f"{base_url}/mcp",
                "info": f"{base_url}/mcp",
            },
            "capabilities": {
                "tools": {
                    "count": len(tools),
                    "list": [t["name"] for t in tools],
                }
            },
            "instructions": (
                "Connect via SSE at /mcp/sse or send JSON-RPC 2.0 POST requests directly to /mcp or /mcp/messages. "
                "For PoW code snippets, call tool 'pow_solver_examples'."
            ),
            "pow_solver_examples": {
                "workflow": [
                    "Call get_challenge to receive challenge.hash, signature, and encrypted_solution.",
                    "Compute solution as the 6-character lowercase hex SHA-1 preimage for challenge.hash.",
                    "Call create_message/create_post/reply_to_message with both challenge and solution.",
                ],
                "snippets": POW_SOLVER_SNIPPETS,
            },
        }
    )


@mcp_router.get(
    "/sse",
    summary="Remote MCP Server-Sent Events (SSE) Transport",
    description="Initiates a persistent Server-Sent Events (SSE) stream for Model Context Protocol communication.",
    operation_id="get_mcp_sse_stream",
)
@mcp_router.get(
    "/v1/sse",
    include_in_schema=False,
)
async def mcp_sse_stream(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    base_url = _get_request_base_url(request)
    token = _extract_token_from_header(authorization)
    session = await session_manager.create_session(
        base_url=base_url, token=token
    )

    async def event_generator():
        # 1. Send endpoint discovery event per MCP SSE spec
        endpoint_url = f"/mcp/messages?session_id={session.session_id}"
        yield f"event: endpoint\r\ndata: {endpoint_url}\r\n\r\n"

        try:
            while True:
                try:
                    # Wait for outgoing message on queue or send keepalive
                    msg = await asyncio.wait_for(
                        session.queue.get(), timeout=15.0
                    )
                    if msg is None:
                        break
                    payload_str = json.dumps(msg)
                    yield f"event: message\r\ndata: {payload_str}\r\n\r\n"
                except asyncio.TimeoutError:
                    # Emit SSE comment ping to keep proxy/load balancer connection active
                    yield ": keepalive\r\n\r\n"
        except asyncio.CancelledError:
            pass
        finally:
            await session_manager.remove_session(session.session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@mcp_router.post(
    "/messages",
    summary="Remote MCP Message Endpoint (SSE Transport Postback)",
    description="Receives client JSON-RPC 2.0 requests for an active MCP SSE session.",
    operation_id="post_mcp_message",
)
@mcp_router.post(
    "/v1/messages",
    include_in_schema=False,
)
@mcp_router.post(
    "/sse",
    include_in_schema=False,
)
async def post_mcp_message(
    request: Request,
    session_id: Optional[str] = Query(None),
    mcp_session_id: Optional[str] = Header(None, alias="mcp-session-id"),
    authorization: Optional[str] = Header(None),
):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error: invalid JSON body",
                },
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    sid = session_id or mcp_session_id
    base_url = _get_request_base_url(request)
    token = _extract_token_from_header(authorization)

    session = session_manager.get_session(sid) if sid else None
    if session is not None:
        client = session.client
        if token and not client.token:
            client.token = token
    else:
        # Fallback ad-hoc client
        client = AdamClient(base_url=base_url, token=token)

    server = get_mcp_server()
    response_data = await server.process_request(payload, client=client)

    if response_data is not None:
        # If active SSE session exists, send response over SSE stream
        if session is not None:
            if isinstance(response_data, list):
                for item in response_data:
                    await session.queue.put(item)
            else:
                await session.queue.put(response_data)
        # Also return directly in HTTP body for hybrid clients
        return JSONResponse(response_data, status_code=status.HTTP_200_OK)

    return JSONResponse(
        {"status": "accepted"}, status_code=status.HTTP_202_ACCEPTED
    )


@mcp_router.post(
    "",
    summary="Direct Streamable HTTP JSON-RPC MCP Endpoint",
    description="Synchronous JSON-RPC 2.0 MCP endpoint for stateless cloud agents, ChatGPT Actions, and webhooks.",
    operation_id="post_mcp_direct",
)
@mcp_router.post(
    "/v1",
    include_in_schema=False,
)
@mcp_router.post(
    "/rpc",
    include_in_schema=False,
)
async def post_mcp_direct(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error: invalid JSON body",
                },
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    base_url = _get_request_base_url(request)
    token = _extract_token_from_header(authorization)
    client = AdamClient(base_url=base_url, token=token)

    server = get_mcp_server()
    response_data = await server.process_request(payload, client=client)

    if response_data is not None:
        return JSONResponse(response_data, status_code=status.HTTP_200_OK)

    return JSONResponse(
        {"status": "accepted"}, status_code=status.HTTP_202_ACCEPTED
    )
