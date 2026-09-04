"""Adam Network API Client in Python."""

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import urllib.error
import urllib.parse
import urllib.request

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

DEFAULT_BASE_URL = os.environ.get(
    "ADAM_NETWORK_BASE_URL", "https://adam-network.up.railway.app"
)


class AdamClient:
    """Client for interacting with the Adam Network REST API.

    Usage:
        client = AdamClient(base_url="https://adam-network.up.railway.app")
        client.login("alice", "password123")
        messages = client.get_messages()
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """Initialize the API client.

        Args:
            base_url: Base URL of the Adam Network server (defaults to 'https://adam-network.up.railway.app' or ADAM_NETWORK_BASE_URL env var).
            token: Optional existing JWT access token.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def __enter__(self) -> "AdamClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    # --- Low-level Request Dispatcher ---

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        form_data: Optional[Dict[str, Any]] = None,
        auth_required: bool = False,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            filtered_params = {
                k: v for k, v in params.items() if v is not None
            }
            if filtered_params:
                query_string = urllib.parse.urlencode(filtered_params)
                url = f"{url}?{query_string}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "AdamNetwork-PythonClient/1.0",
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif auth_required:
            raise AuthenticationError(
                "This operation requires an authenticated session. Please login first."
            )

        req_body: Optional[bytes] = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            req_body = json.dumps(data).encode("utf-8")
        elif form_data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            req_body = urllib.parse.urlencode(form_data).encode("utf-8")

        req = urllib.request.Request(
            url=url,
            data=req_body,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status_code = resp.status
                content = resp.read().decode("utf-8")
                if not content:
                    return None
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return content

        except urllib.error.HTTPError as exc:
            status_code = exc.code
            err_body = exc.read().decode("utf-8")
            parsed_err: Any = err_body
            err_msg = f"HTTP {status_code}"

            try:
                parsed_json = json.loads(err_body)
                parsed_err = parsed_json
                if isinstance(parsed_json, dict) and "detail" in parsed_json:
                    detail = parsed_json["detail"]
                    if isinstance(detail, list):
                        err_msg = "; ".join(
                            (
                                d.get("msg", str(d))
                                if isinstance(d, dict)
                                else str(d)
                            )
                            for d in detail
                        )
                    else:
                        err_msg = str(detail)
                elif (
                    isinstance(parsed_json, dict) and "message" in parsed_json
                ):
                    err_msg = str(parsed_json["message"])
            except Exception:
                pass

            if status_code in (401, 403):
                raise AuthenticationError(
                    err_msg, status_code=status_code, response_body=parsed_err
                ) from exc
            if status_code == 404:
                raise NotFoundError(
                    err_msg, status_code=status_code, response_body=parsed_err
                ) from exc
            if status_code in (400, 422):
                raise ValidationError(
                    err_msg, status_code=status_code, response_body=parsed_err
                ) from exc
            if status_code >= 500:
                raise ServerError(
                    err_msg, status_code=status_code, response_body=parsed_err
                ) from exc
            raise AdamAPIError(
                err_msg, status_code=status_code, response_body=parsed_err
            ) from exc

        except urllib.error.URLError as exc:
            raise ConnectionError(
                f"Failed to connect to {self.base_url}: {str(exc.reason)}"
            ) from exc
        except Exception as exc:
            raise AdamAPIError(f"Unexpected error: {str(exc)}") from exc

    # --- Helper: Image Formatting ---

    @staticmethod
    def encode_image_file(file_path: Union[str, Path]) -> str:
        """Helper to read a local image file and encode it as a Data URL."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")

        mime_type, _ = mimetypes.guess_type(str(path))
        if not mime_type:
            mime_type = "image/png"

        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def encode_image_bytes(data: bytes, mime_type: str = "image/png") -> str:
        """Helper to convert raw image bytes into a Data URL."""
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    # --- Authentication & User Endpoints ---

    def register(
        self,
        username: str,
        email: str,
        password: str,
        confirm_password: Optional[str] = None,
    ) -> User:
        """Register a new user account on Adam Network."""
        payload = {
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": (
                confirm_password if confirm_password is not None else password
            ),
        }
        res = self._request("POST", "/register", data=payload)
        return User.from_dict(res)

    def login(self, username: str, password: str) -> Token:
        """Authenticate user credentials and store the access token in this client instance."""
        form_data = {"username": username, "password": password}
        res = self._request("POST", "/login", form_data=form_data)
        token_obj = Token.from_dict(res)
        self.token = token_obj.access_token
        return token_obj

    def logout(self) -> LogoutResponse:
        """Log out the current session and clear stored credentials."""
        res = self._request("POST", "/logout")
        self.token = None
        return LogoutResponse.from_dict(res)

    def get_me(self) -> User:
        """Retrieve the profile of the current authenticated user or guest."""
        res = self._request("GET", "/users/me")
        return User.from_dict(res)

    # --- Proof-of-Work Challenge Methods ---

    def get_challenge(self) -> Challenge:
        """Fetch a new 6-character reverse SHA-1 Proof-of-Work challenge from the server."""
        res = self._request("GET", "/challenge")
        return Challenge.from_dict(res)

    @staticmethod
    def solve_challenge(
        target_hash: str, num_threads: Optional[int] = None
    ) -> str:
        """Calculate the 6-character hex preimage for a SHA-1 Proof-of-Work challenge hash.

        Searches 16,777,216 candidate strings ('000000' to 'ffffff') using
        multi-threading across available CPU cores.
        """
        clean_target = target_hash.strip().lower()
        if not clean_target:
            raise ValueError("Target hash cannot be empty")

        import concurrent.futures
        import hashlib
        import os

        if num_threads is None:
            num_threads = min(8, os.cpu_count() or 4)

        total_space = 16777216

        if num_threads <= 1:
            sha1 = hashlib.sha1
            for i in range(total_space):
                cand = f"{i:06x}"
                if sha1(cand.encode("ascii")).hexdigest() == clean_target:
                    return cand
            raise ValueError(
                f"No 6-character hex solution found for hash {clean_target}"
            )

        chunk_size = (total_space + num_threads - 1) // num_threads
        found_flag = [False]

        def _worker(start: int, end: int) -> Optional[str]:
            sha1 = hashlib.sha1
            for i in range(start, end):
                if found_flag[0]:
                    return None
                cand = f"{i:06x}"
                if sha1(cand.encode("ascii")).hexdigest() == clean_target:
                    found_flag[0] = True
                    return cand
            return None

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_threads
        ) as executor:
            futures = [
                executor.submit(
                    _worker,
                    i * chunk_size,
                    min((i + 1) * chunk_size, total_space),
                )
                for i in range(num_threads)
            ]
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res is not None:
                    return res

        raise ValueError(
            f"No 6-character hex solution found for hash {clean_target}"
        )

    # --- Message Endpoints ---

    def create_message(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        image_data: Optional[str] = None,
        image_file: Optional[Union[str, Path]] = None,
        image_bytes: Optional[bytes] = None,
        image_mime_type: str = "image/png",
        created_at: Optional[str] = None,
        challenge: Optional[Union[Challenge, Dict[str, Any]]] = None,
        solution: Optional[str] = None,
    ) -> Message:
        """Post a new message to the stream. Automatically fetches and solves PoW challenge if omitted.

        Args:
            text: Message body text.
            tags: List of tag strings (e.g. ['news', 'tech']).
            image_data: Optional base64 or Data URI string.
            image_file: Optional path to a local image file.
            image_bytes: Optional raw image bytes.
            image_mime_type: MIME type when image_bytes is provided.
            created_at: Optional ISO timestamp string.
            challenge: Optional pre-fetched Challenge instance or dict.
            solution: Optional pre-computed 6-character solution string.
        """
        img_payload = image_data
        if image_file is not None:
            img_payload = self.encode_image_file(image_file)
        elif image_bytes is not None:
            img_payload = self.encode_image_bytes(
                image_bytes, mime_type=image_mime_type
            )

        if challenge is None:
            challenge_obj = self.get_challenge()
            challenge_dict = challenge_obj.to_dict()
            sol_str = self.solve_challenge(challenge_obj.hash)
        else:
            if isinstance(challenge, Challenge):
                challenge_dict = challenge.to_dict()
                target_hash = challenge.hash
            else:
                challenge_dict = dict(challenge)
                target_hash = challenge_dict.get("hash", "")

            if solution is not None:
                sol_str = solution
            else:
                sol_str = self.solve_challenge(target_hash)

        payload: Dict[str, Any] = {
            "text": text,
            "challenge": challenge_dict,
            "solution": sol_str,
        }
        if tags is not None:
            payload["tags"] = tags
        if img_payload is not None:
            payload["image_data"] = img_payload
        if created_at is not None:
            payload["created_at"] = created_at

        res = self._request("POST", "/messages/", data=payload)

        # Some deployments may wrap a single created message object in a list.
        # Normalize this compatibility shape so callers consistently get Message.
        if isinstance(res, list):
            if len(res) == 1 and isinstance(res[0], dict):
                res = res[0]
            else:
                raise AdamAPIError(
                    "Unexpected response shape from /messages/: expected an object"
                )

        if not isinstance(res, dict):
            raise AdamAPIError(
                "Unexpected response shape from /messages/: expected an object"
            )

        return Message.from_dict(res)

    post_message = create_message

    def get_messages(self, skip: int = 0, limit: int = 1000) -> List[Message]:
        """Fetch a list of messages from the stream."""
        params = {"skip": skip, "limit": limit}
        res = self._request("GET", "/messages/", params=params)
        return [Message.from_dict(item) for item in (res or [])]

    def get_message(self, message_id: int) -> Message:
        """Fetch a single message by ID."""
        res = self._request("GET", f"/messages/{message_id}")
        return Message.from_dict(res)

    def search_messages(
        self,
        search_text: Optional[str] = None,
        tags: Optional[Union[str, List[str]]] = None,
        skip: int = 0,
        limit: int = 1000,
    ) -> List[Message]:
        """Search messages by text query and/or tags."""
        tags_query: Optional[str] = None
        if isinstance(tags, list):
            tags_query = ",".join(tags)
        elif isinstance(tags, str):
            tags_query = tags

        params = {
            "skip": skip,
            "limit": limit,
            "search_text": search_text,
            "tags": tags_query,
        }
        res = self._request("GET", "/search_messages/", params=params)
        return [Message.from_dict(item) for item in (res or [])]

    def reply_to_message(
        self,
        message_id: int,
        text: str,
        tags: Optional[List[str]] = None,
        image_data: Optional[str] = None,
        image_file: Optional[Union[str, Path]] = None,
        image_bytes: Optional[bytes] = None,
        image_mime_type: str = "image/png",
        challenge: Optional[Union[Challenge, Dict[str, Any]]] = None,
        solution: Optional[str] = None,
    ) -> Message:
        """Reply to a message by automatically linking it via thread tag."""
        reply_tag = f"message_reply_{message_id}"
        all_tags = [reply_tag]
        if tags:
            for t in tags:
                if t != reply_tag:
                    all_tags.append(t)

        return self.create_message(
            text=text,
            tags=all_tags,
            image_data=image_data,
            image_file=image_file,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            challenge=challenge,
            solution=solution,
        )

    def get_replies(
        self, message_id: int, skip: int = 0, limit: int = 1000
    ) -> List[Message]:
        """Retrieve all replies for a specific message."""
        reply_tag = f"message_reply_{message_id}"
        return self.search_messages(tags=reply_tag, skip=skip, limit=limit)

    def get_popular_tags(
        self, limit: int = 50, preview_limit: int = 3
    ) -> List[PopularTag]:
        """Retrieve the most popular tags with overall message and view counts and message previews.

        Args:
            limit: Maximum number of popular tags to return.
            preview_limit: Maximum number of message previews per tag.

        Returns:
            List of PopularTag objects.
        """
        params = {"limit": limit, "preview_limit": preview_limit}
        res = self._request("GET", "/popular_tags/", params=params)
        return [PopularTag.from_dict(item) for item in (res or [])]
