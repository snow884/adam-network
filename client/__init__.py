"""Adam Network Python API Client Package."""

from .client import AdamClient
from .exceptions import (
    AdamAPIError,
    AuthenticationError,
    ConnectionError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from .models import (
    Challenge,
    LogoutResponse,
    Message,
    PopularTag,
    PopularTagMessagePreview,
    Token,
    User,
)

__version__ = "0.1.0"

__all__ = [
    "AdamClient",
    "Challenge",
    "User",
    "Token",
    "Message",
    "PopularTag",
    "PopularTagMessagePreview",
    "LogoutResponse",
    "AdamAPIError",
    "AuthenticationError",
    "ValidationError",
    "NotFoundError",
    "ServerError",
    "ConnectionError",
    "__version__",
]
