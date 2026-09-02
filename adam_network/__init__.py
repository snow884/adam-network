"""Adam Network Python API Client Package."""

from client.client import AdamClient, DEFAULT_BASE_URL
from client.exceptions import (
    AdamAPIError,
    AuthenticationError,
    ConnectionError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from client.models import Challenge, LogoutResponse, Message, Token, User

__version__ = "0.1.0"

__all__ = [
    "AdamClient",
    "DEFAULT_BASE_URL",
    "Challenge",
    "User",
    "Token",
    "Message",
    "LogoutResponse",
    "AdamAPIError",
    "AuthenticationError",
    "ValidationError",
    "NotFoundError",
    "ServerError",
    "ConnectionError",
    "__version__",
]
