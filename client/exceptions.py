"""Exception classes for Adam Network API Client."""

from typing import Any, Optional


class AdamAPIError(Exception):
    """Base exception for all Adam Network API client errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Any = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class AuthenticationError(AdamAPIError):
    """Raised when authentication fails (HTTP 401 / 403 or invalid credentials)."""

    pass


class ValidationError(AdamAPIError):
    """Raised when request payload fails validation (HTTP 400 / 422)."""

    pass


class NotFoundError(AdamAPIError):
    """Raised when a resource is not found (HTTP 404)."""

    pass


class ServerError(AdamAPIError):
    """Raised when server returns an HTTP 5xx error."""

    pass


class ConnectionError(AdamAPIError):
    """Raised when unable to connect to the Adam Network API server."""

    pass
