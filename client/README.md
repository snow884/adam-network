# Adam Network Python API Client

A clean, strongly-typed Python client for interacting with the **Adam Network API**.

## Features

- **Standard Library only**: Uses standard `urllib` — zero mandatory third-party runtime dependencies.
- **Authentication Support**: Full OAuth2 / JWT login, registration, token storage, and logout.
- **Messaging Stream**: Post messages, attach images (file path, raw bytes, or base64 Data URL), retrieve streams.
- **Threading & Replies**: Convenience methods for posting replies and fetching threaded discussions (`message_reply_{id}`).
- **Search & Filters**: Search messages by keywords and tags.
- **Context Manager**: Supports `with AdamClient(...) as client:`.
- **Rich Error Handling**: Typed exceptions (`AuthenticationError`, `ValidationError`, `NotFoundError`, `ServerError`, `ConnectionError`).

---

## Installation / Import

Simply import `AdamClient` from the `client` package:

```python
from client import AdamClient, AdamAPIError, AuthenticationError, ValidationError, NotFoundError
```

---

## Quickstart

```python
from client import AdamClient

# Initialize client
client = AdamClient(base_url="http://127.0.0.1:8000")

# Register
user = client.register(
    username="alice",
    email="alice@example.com",
    password="my-secure-password",
)

# Login (automatically stores JWT in client)
token = client.login(username="alice", password="my-secure-password")
print(f"Logged in: {token.access_token}")

# Get current user
me = client.get_me()
print(f"Current user: {me.username}")

# Post a message
msg = client.post_message(
    text="Hello World from Python Client!",
    tags=["welcome", "python"],
)
print(f"Created message #{msg.id}")

# Post a reply
reply = client.reply_to_message(
    message_id=msg.id,
    text="This is a reply to the first post.",
)

# Fetch all messages
all_messages = client.get_messages(limit=50)

# Search messages
results = client.search_messages(search_text="Hello", tags="python")

# Fetch thread replies
thread = client.get_replies(message_id=msg.id)

# Logout
client.logout()
```

---

## Attaching Images

You can attach images using a file path, raw bytes, or base64 Data URLs:

```python
# From a local image file:
client.post_message(
    text="Check out this diagram",
    tags=["diagram"],
    image_file="/path/to/image.png",
)

# From raw bytes:
with open("photo.jpg", "rb") as f:
    img_bytes = f.read()

client.post_message(
    text="Byte attachment",
    tags=["photo"],
    image_bytes=img_bytes,
    image_mime_type="image/jpeg",
)
```

---

## API Reference

### Class: `AdamClient(base_url="http://127.0.0.1:8000", token=None, timeout=30.0)`

#### Authentication Methods
- `register(username, email, password, confirm_password=None) -> User`
- `login(username, password) -> Token`
- `logout() -> LogoutResponse`
- `get_me() -> User`

#### Message Methods
- `create_message(text, tags=None, image_data=None, image_file=None, image_bytes=None, image_mime_type="image/png", created_at=None) -> Message`
- `post_message(...) -> Message` (alias of `create_message`)
- `get_messages(skip=0, limit=1000) -> List[Message]`
- `get_message(message_id) -> Message`
- `search_messages(search_text=None, tags=None, skip=0, limit=1000) -> List[Message]`
- `reply_to_message(message_id, text, tags=None, image_data=None, image_file=None, image_bytes=None, image_mime_type="image/png") -> Message`
- `get_replies(message_id, skip=0, limit=1000) -> List[Message]`

#### Utilities
- `encode_image_file(file_path) -> str` (Data URL)
- `encode_image_bytes(data, mime_type="image/png") -> str` (Data URL)

---

## Running the Example Script

```bash
python -m client.example http://127.0.0.1:8000
```
