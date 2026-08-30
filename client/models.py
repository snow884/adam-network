"""Data models and schemas for Adam Network API Client."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class User:
    """Represents an Adam Network user account."""

    username: str
    email: str
    is_guest: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        return cls(
            username=data.get("username", ""),
            email=data.get("email", ""),
            is_guest=bool(data.get("is_guest", False)),
        )


@dataclass
class Token:
    """Represents an OAuth2 authentication token."""

    access_token: str
    token_type: str = "bearer"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Token":
        return cls(
            access_token=data.get("access_token", ""),
            token_type=data.get("token_type", "bearer"),
        )


@dataclass
class Message:
    """Represents a message posted to Adam Network."""

    id: int
    text: str
    username: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    image_data: Optional[str] = None
    created_at: Optional[str] = None
    views: int = 0
    reply_count: int = 0
    replies_count: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        raw_tags = data.get("tags")
        if raw_tags is None:
            tags = []
        elif isinstance(raw_tags, list):
            tags = [str(t) for t in raw_tags]
        else:
            tags = [str(raw_tags)]

        reply_count = (
            data.get("reply_count", data.get("replies_count", 0)) or 0
        )
        views = data.get("views", 0) or 0

        return cls(
            id=int(data.get("id", 0)),
            text=str(data.get("text", "")),
            username=data.get("username"),
            tags=tags,
            image_data=data.get("image_data"),
            created_at=data.get("created_at"),
            views=int(views),
            reply_count=int(reply_count),
            replies_count=int(reply_count),
        )


@dataclass
class LogoutResponse:
    """Represents the response from logging out."""

    message: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogoutResponse":
        return cls(message=str(data.get("message", "")))
