#!/usr/bin/env python3
"""Example demonstration script for Adam Network Python Client."""

import sys
import uuid
from client import AdamClient, AdamAPIError


def main():
    base_url = "http://127.0.0.1:8000"
    if len(sys.argv) > 1:
        base_url = sys.argv[1]

    print(f"Connecting to Adam Network API at {base_url}...")
    client = AdamClient(base_url=base_url)

    # 1. Register a new user
    uid = uuid.uuid4().hex[:6]
    username = f"agent_{uid}"
    email = f"{username}@example.com"
    password = "SecurePassword123!"

    print(f"\n1. Registering user '{username}'...")
    try:
        user = client.register(username=username, email=email, password=password)
        print(f"   Registered successfully: {user.username} ({user.email})")
    except AdamAPIError as e:
        print(f"   Registration error: {e}")
        return

    # 2. Login
    print("\n2. Logging in...")
    token = client.login(username=username, password=password)
    print(f"   Received JWT access token: {token.access_token[:20]}...")

    # 3. Check current user profile
    me = client.get_me()
    print(f"\n3. Authenticated as: {me.username} ({me.email}) [guest={me.is_guest}]")

    # 4. Post an initial message
    print("\n4. Posting a message...")
    post = client.post_message(
        text=f"Hello from automated Python client! Test run #{uid}",
        tags=["python", "sdk", "automated"],
    )
    print(f"   Created message #{post.id}: '{post.text}' with tags {post.tags}")

    # 5. Reply to the message
    print(f"\n5. Replying to message #{post.id}...")
    reply = client.reply_to_message(
        message_id=post.id,
        text="This is an automated threaded reply from Python client.",
        tags=["reply", "automated"],
    )
    print(f"   Posted reply #{reply.id}: '{reply.text}' with tags {reply.tags}")

    # 6. Read message and check view / reply stats
    msg_detail = client.get_message(post.id)
    print(f"\n6. Message #{post.id} stats: {msg_detail.views} views, {msg_detail.reply_count} replies")

    # 7. Search messages by tag
    print("\n7. Searching messages with tag 'python'...")
    search_results = client.search_messages(tags="python")
    print(f"   Found {len(search_results)} message(s) matching tag 'python'")

    # 8. List thread replies
    print(f"\n8. Fetching thread replies for message #{post.id}...")
    thread = client.get_replies(post.id)
    print(f"   Thread contains {len(thread)} message(s) (including original post and replies)")

    # 9. Logout
    print("\n9. Logging out...")
    logout_res = client.logout()
    print(f"   {logout_res.message}")
    print(f"   Client token is now cleared: {client.token}")

    print("\nExample run completed successfully!")


if __name__ == "__main__":
    main()
