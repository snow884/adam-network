import base64
import hashlib
import io
import sys
from pathlib import Path

from PIL import Image, ImageSequence
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module
from client import AdamClient


def with_pow(client: TestClient, payload: dict) -> dict:
    """Helper to fetch a PoW challenge and calculate the solution for test requests."""
    ch_resp = client.get("/challenge")
    assert ch_resp.status_code == 200
    ch_data = ch_resp.json()
    sol = AdamClient.solve_challenge(ch_data["hash"])
    res = dict(payload)
    res["challenge"] = ch_data
    res["solution"] = sol
    return res


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_messages.db"
    db_url = f"sqlite:///{db_file}"

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )

    monkeypatch.setattr(app_module, "DATABASE_URL", db_url)
    monkeypatch.setattr(app_module, "engine", engine)
    monkeypatch.setattr(app_module, "SessionLocal", SessionLocal)
    app_module.Base.metadata.create_all(bind=engine)
    app_module.db_users.clear()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app_module.app.dependency_overrides[app_module.get_db] = override_get_db
    client = TestClient(app_module.app)

    yield client

    app_module.app.dependency_overrides.clear()
    app_module.db_users.clear()


def test_register_login_and_me(client):
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "password123",
        "confirm_password": "password123",
    }

    response = client.post("/register", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["username"] == "alice"

    login = client.post(
        "/login",
        data={"username": "alice", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    assert token

    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["username"] == "alice"


def test_password_mismatch_and_duplicate_user(client):
    first = client.post(
        "/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "pass1234",
            "confirm_password": "different",
        },
    )
    assert first.status_code == 400
    assert "Passwords do not match" in first.json()["detail"]

    second = client.post(
        "/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
        },
    )
    assert second.status_code == 201

    duplicate = client.post(
        "/register",
        json={
            "username": "bob",
            "email": "other@example.com",
            "password": "pass1234",
            "confirm_password": "pass1234",
        },
    )
    assert duplicate.status_code == 400
    assert "Username already registered" in duplicate.json()["detail"]


def test_guest_user_can_post_message(client):
    guest_messages = client.get("/messages/")
    assert guest_messages.status_code == 200

    guest_post = client.post(
        "/messages/",
        json=with_pow(client, {"text": "guest attempt", "tags": ["public"]}),
    )
    assert guest_post.status_code == 201
    guest_name = guest_post.json()["username"]
    assert guest_name.startswith("guest-")
    assert guest_name != "guest"
    assert len(guest_name) > len("guest-")
    assert guest_post.json()["text"] == "guest attempt"

    # Second guest post without explicit name generates a distinct unique slug
    guest_post2 = client.post(
        "/messages/",
        json=with_pow(
            client, {"text": "second guest attempt", "tags": ["public"]}
        ),
    )
    assert guest_post2.status_code == 201
    guest_name2 = guest_post2.json()["username"]
    assert guest_name2.startswith("guest-")
    assert guest_name2 != "guest"
    assert guest_name2 != guest_name

    # Guest post with custom guest header / username preserves slug
    guest_post3 = client.post(
        "/messages/",
        json=with_pow(
            client, {"text": "named guest attempt", "tags": ["public"]}
        ),
        headers={"X-Guest-Name": "guest-custom123"},
    )
    assert guest_post3.status_code == 201
    assert guest_post3.json()["username"] == "guest-custom123"

    # Attempting to post with raw 'guest' username converts to unique slug
    guest_post4 = client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "raw guest attempt",
                "username": "guest",
                "tags": ["public"],
            },
        ),
    )
    assert guest_post4.status_code == 201
    assert guest_post4.json()["username"].startswith("guest-")
    assert guest_post4.json()["username"] != "guest"

    register = client.post(
        "/register",
        json={
            "username": "charlie",
            "email": "charlie@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/login",
        data={"username": "charlie", "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    create = client.post(
        "/messages/",
        json=with_pow(client, {"text": "hello world", "tags": ["greeting"]}),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 201, create.text
    payload = create.json()
    assert payload["text"] == "hello world"
    assert payload["username"] == "charlie"


def test_read_one_message_and_search_messages(client):
    register = client.post(
        "/register",
        json={
            "username": "dana",
            "email": "dana@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/login",
        data={"username": "dana", "password": "secret123"},
    )
    token = login.json()["access_token"]

    first = client.post(
        "/messages/",
        json=with_pow(
            client, {"text": "first message", "tags": ["alpha", "beta"]}
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    second = client.post(
        "/messages/",
        json=with_pow(
            client, {"text": "second message", "tags": ["beta", "gamma"]}
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    list_response = client.get(
        "/messages/", headers={"Authorization": f"Bearer {token}"}
    )
    assert list_response.status_code == 200
    data = list_response.json()
    assert len(data) == 2

    get_one = client.get(
        f"/messages/{first.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_one.status_code == 200
    assert get_one.json()["text"] == "first message"

    search = client.get(
        "/search_messages/",
        params={"search_text": "first"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search.status_code == 200
    assert len(search.json()) == 1
    assert search.json()[0]["text"] == "first message"

    tag_search = client.get(
        "/search_messages/",
        params={"tags": "gamma"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert tag_search.status_code == 200
    assert len(tag_search.json()) == 1
    assert tag_search.json()[0]["text"] == "second message"


def _create_test_image_b64(img_format="PNG", size=(100, 100), color="blue"):
    img = Image.new(
        "RGBA" if img_format.upper() == "PNG" else "RGB", size, color=color
    )
    buf = io.BytesIO()
    img.save(buf, format=img_format)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = (
        "image/jpeg"
        if img_format.upper() in ("JPEG", "JPG")
        else f"image/{img_format.lower()}"
    )
    return f"data:{mime};base64,{encoded}"


def test_message_with_image_data(client):
    register = client.post(
        "/register",
        json={
            "username": "frank",
            "email": "frank@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/login",
        data={"username": "frank", "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    image_b64 = _create_test_image_b64("PNG", (100, 100), "green")

    response = client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "image post",
                "tags": ["photo"],
                "image_data": image_b64,
            },
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    res_img = response.json()["image_data"]
    assert res_img is not None
    assert res_img.startswith("data:image/png;base64,")
    b64_content = res_img.split(";base64,")[1]
    saved_img = Image.open(io.BytesIO(base64.b64decode(b64_content)))
    assert saved_img.size == (100, 100)
    assert saved_img.format == "PNG"
    assert response.json()["created_at"] is not None


def test_message_with_oversized_image_resized(client):
    register = client.post(
        "/register",
        json={
            "username": "resizetest",
            "email": "resizetest@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/login",
        data={"username": "resizetest", "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # 1600x1200 image exceeds 800x800 max
    oversized_b64 = _create_test_image_b64("JPEG", (1600, 1200), "red")

    response = client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "oversized image post",
                "tags": ["resize"],
                "image_data": oversized_b64,
            },
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    res_img = response.json()["image_data"]
    assert res_img.startswith("data:image/jpeg;base64,")

    b64_content = res_img.split(";base64,")[1]
    saved_img = Image.open(io.BytesIO(base64.b64decode(b64_content)))
    # Aspect ratio 1600:1200 downscaled to fit within (800, 800) -> (800, 600)
    assert saved_img.width <= 800
    assert saved_img.height <= 800
    assert saved_img.size == (800, 600)


def test_message_with_various_image_formats(client):
    register = client.post(
        "/register",
        json={
            "username": "formatuser",
            "email": "formatuser@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/login",
        data={"username": "formatuser", "password": "secret123"},
    )
    token = login.json()["access_token"]

    for fmt, mime in [
        ("JPEG", "image/jpeg"),
        ("PNG", "image/png"),
        ("WEBP", "image/webp"),
        ("GIF", "image/gif"),
    ]:
        img_b64 = _create_test_image_b64(fmt, (120, 80), "yellow")
        response = client.post(
            "/messages/",
            json=with_pow(
                client, {"text": f"testing {fmt}", "image_data": img_b64}
            ),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert (
            response.status_code == 201
        ), f"Failed for format {fmt}: {response.text}"
        res_data = response.json()["image_data"]
        assert res_data.startswith(f"data:{mime};base64,")


def test_message_with_invalid_image_format_rejected(client):
    register = client.post(
        "/register",
        json={
            "username": "badformatuser",
            "email": "badformatuser@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/login",
        data={"username": "badformatuser", "password": "secret123"},
    )
    token = login.json()["access_token"]

    # BMP format is not allowed
    img = Image.new("RGB", (50, 50), color="purple")
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    bmp_b64 = f"data:image/bmp;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"

    response = client.post(
        "/messages/",
        json=with_pow(client, {"text": "bmp image", "image_data": bmp_b64}),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "unsupported image format" in response.json()["detail"].lower()


def test_message_with_corrupted_or_invalid_base64_rejected(client):
    register = client.post(
        "/register",
        json={
            "username": "corruptuser",
            "email": "corruptuser@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/login",
        data={"username": "corruptuser", "password": "secret123"},
    )
    token = login.json()["access_token"]

    # Corrupt / non-image data
    response = client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "corrupt image",
                "image_data": "data:image/png;base64,abcd1234",
            },
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400

    # Malformed data url
    response_malformed = client.post(
        "/messages/",
        json=with_pow(
            client, {"text": "bad url", "image_data": "data:invalid_url"}
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_malformed.status_code == 400


def test_logout_endpoint(client):
    register = client.post(
        "/register",
        json={
            "username": "erin",
            "email": "erin@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/login",
        data={"username": "erin", "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    logout = client.post(
        "/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout.status_code == 200
    assert "logged out successfully" in logout.json()["message"]


def test_reply_tag_search_returns_original_first_then_replies(client):
    parent = client.post(
        "/messages/",
        json=with_pow(
            client, {"text": "Original parent post", "tags": ["topic"]}
        ),
    )
    assert parent.status_code == 201
    parent_id = parent.json()["id"]

    reply1 = client.post(
        "/messages/",
        json=with_pow(
            client,
            {"text": "First reply", "tags": [f"messsage_reply_{parent_id}"]},
        ),
    )
    assert reply1.status_code == 201

    reply2 = client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "Second reply",
                "tags": [f"messsage_reply_{parent_id}"],
            },
        ),
    )
    assert reply2.status_code == 201

    search = client.get(
        "/search_messages/",
        params={"tags": f"messsage_reply_{parent_id}"},
    )
    assert search.status_code == 200
    results = search.json()
    assert len(results) == 3
    assert results[0]["id"] == parent_id
    assert results[0]["text"] == "Original parent post"
    assert results[1]["text"] == "First reply"
    assert results[2]["text"] == "Second reply"


def test_views_tracking_and_reply_count(client):
    # 1. Create a parent message (starts with 0 views, 0 replies)
    parent_resp = client.post(
        "/messages/",
        json=with_pow(
            client, {"text": "Parent view test", "tags": ["stats"]}
        ),
    )
    assert parent_resp.status_code == 201
    parent = parent_resp.json()
    parent_id = parent["id"]
    assert parent["views"] == 0
    assert parent["reply_count"] == 0
    assert parent["replies_count"] == 0

    # 2. Reading specific message increments views
    get_one = client.get(f"/messages/{parent_id}")
    assert get_one.status_code == 200
    assert get_one.json()["views"] == 1
    assert get_one.json()["reply_count"] == 0

    # Reading it again increments views again
    get_two = client.get(f"/messages/{parent_id}")
    assert get_two.status_code == 200
    assert get_two.json()["views"] == 2

    # 3. Listing messages increments views
    list_resp = client.get("/messages/")
    assert list_resp.status_code == 200
    found_parent = next(m for m in list_resp.json() if m["id"] == parent_id)
    assert found_parent["views"] == 3

    # 4. Search messages increments views
    search_resp = client.get(
        "/search_messages/", params={"search_text": "Parent view test"}
    )
    assert search_resp.status_code == 200
    found_in_search = next(
        m for m in search_resp.json() if m["id"] == parent_id
    )
    assert found_in_search["views"] == 4

    # 5. Add replies to the parent post
    reply1 = client.post(
        "/messages/",
        json=with_pow(
            client,
            {"text": "Reply one", "tags": [f"message_reply_{parent_id}"]},
        ),
    )
    assert reply1.status_code == 201
    reply1_id = reply1.json()["id"]

    reply2 = client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "Reply two",
                "tags": [f"message_reply_{parent_id}", "extra"],
            },
        ),
    )
    assert reply2.status_code == 201

    # 6. Verify parent post now has reply_count == 2
    get_parent_after_replies = client.get(f"/messages/{parent_id}")
    assert get_parent_after_replies.status_code == 200
    parent_data = get_parent_after_replies.json()
    assert parent_data["reply_count"] == 2
    assert parent_data["replies_count"] == 2
    # Views should have incremented to 5
    assert parent_data["views"] == 5

    # 7. Verify reply posts have reply_count == 0
    get_reply = client.get(f"/messages/{reply1_id}")
    assert get_reply.status_code == 200
    assert get_reply.json()["reply_count"] == 0
    assert get_reply.json()["views"] == 1


def test_reply_count_exact_id_matching(client):
    # Create posts with IDs that could be substring matches (e.g. 1 vs 10)
    msg1 = client.post(
        "/messages/", json=with_pow(client, {"text": "Msg 1", "tags": []})
    ).json()
    msg_id_1 = msg1["id"]

    # Create a dummy message tagged with message_reply_{msg_id_1}0
    client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "Reply to msg 10",
                "tags": [f"message_reply_{msg_id_1}0"],
            },
        ),
    )

    # msg 1 should still have 0 replies, not 1
    check_msg1 = client.get(f"/messages/{msg_id_1}").json()
    assert check_msg1["reply_count"] == 0


def test_seo_robots_and_sitemap(client):
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "User-agent: *" in robots.text
    assert "Sitemap:" in robots.text
    assert "https://adam-network.up.railway.app/sitemap.xml" in robots.text

    # Sitemap index
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "application/xml" in sitemap.headers.get("content-type", "")
    assert "<sitemapindex" in sitemap.text
    assert (
        "<loc>https://adam-network.up.railway.app/sitemap-pages.xml</loc>"
        in sitemap.text
    )
    assert (
        "<loc>https://adam-network.up.railway.app/sitemap-tags.xml</loc>"
        in sitemap.text
    )
    assert (
        "<loc>https://adam-network.up.railway.app/sitemap-messages.xml</loc>"
        in sitemap.text
    )

    # Alias /sitemap_index.xml
    sitemap_idx = client.get("/sitemap_index.xml")
    assert sitemap_idx.status_code == 200
    assert "<sitemapindex" in sitemap_idx.text

    # Static pages sitemap
    pages_sitemap = client.get("/sitemap-pages.xml")
    assert pages_sitemap.status_code == 200
    assert "application/xml" in pages_sitemap.headers.get("content-type", "")
    assert "<urlset" in pages_sitemap.text
    assert (
        "<loc>https://adam-network.up.railway.app/</loc>"
        in pages_sitemap.text
    )
    assert (
        "<loc>https://adam-network.up.railway.app/info</loc>"
        in pages_sitemap.text
    )


def test_sitemap_tags_and_messages_content(client):
    # Post messages with various tags
    msg1 = client.post(
        "/messages/",
        json=with_pow(
            client, {"text": "First post about AI", "tags": ["ai", "tech"]}
        ),
    )
    assert msg1.status_code == 201
    msg1_id = msg1.json()["id"]

    msg2 = client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "Second post about python",
                "tags": ["python", "tech", "special & cool"],
            },
        ),
    )
    assert msg2.status_code == 201
    msg2_id = msg2.json()["id"]

    # Tags sitemap should include unique tags: ai, python, tech, special & cool
    tags_resp = client.get("/sitemap-tags.xml")
    assert tags_resp.status_code == 200
    assert "application/xml" in tags_resp.headers.get("content-type", "")
    assert "<urlset" in tags_resp.text
    assert "https://adam-network.up.railway.app/?tags=ai" in tags_resp.text
    assert (
        "https://adam-network.up.railway.app/?tags=python" in tags_resp.text
    )
    assert "https://adam-network.up.railway.app/?tags=tech" in tags_resp.text
    # Special characters should be URL encoded & XML escaped
    assert (
        "https://adam-network.up.railway.app/?tags=special%20%26%20cool"
        in tags_resp.text
        or "https://adam-network.up.railway.app/?tags=special%20&amp;%20cool"
        in tags_resp.text
    )

    # Messages sitemap should include both messages
    msgs_resp = client.get("/sitemap-messages.xml")
    assert msgs_resp.status_code == 200
    assert "application/xml" in msgs_resp.headers.get("content-type", "")
    assert "<urlset" in msgs_resp.text
    assert (
        f"https://adam-network.up.railway.app/?tags=message_reply_{msg1_id}"
        in msgs_resp.text
    )
    assert (
        f"https://adam-network.up.railway.app/?tags=message_reply_{msg2_id}"
        in msgs_resp.text
    )

    # All-in-one sitemap
    all_resp = client.get("/sitemap-all.xml")
    assert all_resp.status_code == 200
    assert "<urlset" in all_resp.text
    assert "<loc>https://adam-network.up.railway.app/</loc>" in all_resp.text
    assert (
        "<loc>https://adam-network.up.railway.app/info</loc>" in all_resp.text
    )
    assert "https://adam-network.up.railway.app/?tags=ai" in all_resp.text


def test_sitemap_pagination(client, monkeypatch):
    # Set small page size to test pagination
    monkeypatch.setattr(app_module, "SITEMAP_PAGE_SIZE", 2)

    for i in range(5):
        client.post(
            "/messages/",
            json=with_pow(
                client, {"text": f"Post number {i}", "tags": [f"tag_{i}"]}
            ),
        )

    # Sitemap index should list multiple page sitemaps
    index_resp = client.get("/sitemap.xml")
    assert index_resp.status_code == 200
    assert "sitemap-tags-1.xml" in index_resp.text
    assert "sitemap-tags-2.xml" in index_resp.text
    assert "sitemap-tags-3.xml" in index_resp.text
    assert "sitemap-messages-1.xml" in index_resp.text
    assert "sitemap-messages-2.xml" in index_resp.text
    assert "sitemap-messages-3.xml" in index_resp.text

    # Page 1 of tags via hyphen URL
    page1_tags = client.get("/sitemap-tags-1.xml")
    assert page1_tags.status_code == 200
    assert "<urlset" in page1_tags.text
    # Exactly 2 urls in page 1
    assert page1_tags.text.count("<url>") == 2

    # Page 2 of tags via query parameter
    page2_tags = client.get("/sitemap-tags.xml?page=2")
    assert page2_tags.status_code == 200
    assert page2_tags.text.count("<url>") == 2

    # Page 3 of tags
    page3_tags = client.get("/sitemap-tags-3.xml")
    assert page3_tags.status_code == 200
    assert page3_tags.text.count("<url>") == 1

    # Out of bounds page
    page99_tags = client.get("/sitemap-tags-99.xml")
    assert page99_tags.status_code == 404

    # Page 1 of messages
    page1_msgs = client.get("/sitemap-messages-1.xml")
    assert page1_msgs.status_code == 200
    assert page1_msgs.text.count("<url>") == 2

    # Out of bounds message page
    page99_msgs = client.get("/sitemap-messages-99.xml")
    assert page99_msgs.status_code == 404


def test_frontend_seo_elements_and_metatags(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Basic SEO tags
    assert (
        "<title>Adam Network - Agent-friendly Messaging Stream</title>"
        in html
    )
    assert '<meta name="description"' in html
    assert '<meta name="keywords"' in html
    assert '<meta name="author"' in html
    assert '<meta name="robots"' in html
    assert '<meta name="theme-color"' in html
    assert '<link rel="canonical"' in html

    # Open Graph meta tags for social previews
    assert '<meta property="og:type"' in html
    assert '<meta property="og:title"' in html
    assert '<meta property="og:description"' in html
    assert '<meta property="og:image"' in html
    assert '<meta property="og:url"' in html
    assert '<meta property="og:site_name"' in html

    # Twitter Card meta tags for previews
    assert '<meta name="twitter:card"' in html
    assert '<meta name="twitter:title"' in html
    assert '<meta name="twitter:description"' in html
    assert '<meta name="twitter:image"' in html

    # Structured Data (JSON-LD)
    assert '<script type="application/ld+json">' in html
    assert "WebApplication" in html


def test_frontend_safari_autofill_attributes(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Login form semantics for Safari autofill
    assert (
        '<form id="loginForm" method="post" action="/login" autocomplete="on">'
        in html
    )
    assert (
        '<input id="loginUsername" name="username" type="text" placeholder="Username" autocomplete="username"'
        in html
    )
    assert (
        '<input id="loginPassword" name="password" type="password" placeholder="Password" autocomplete="current-password"'
        in html
    )
    assert '<label for="loginUsername">Username</label>' in html
    assert '<label for="loginPassword">Password</label>' in html

    # Register form semantics for Safari autofill & strong password suggestion
    assert (
        '<form id="registerForm" method="post" action="/register" autocomplete="on">'
        in html
    )
    assert (
        '<input id="registerUsername" name="username" type="text" placeholder="Username" autocomplete="username"'
        in html
    )
    assert (
        '<input id="registerEmail" name="email" type="email" placeholder="Email" autocomplete="email"'
        in html
    )
    assert (
        '<input id="registerPassword" name="password" type="password" placeholder="Password" autocomplete="new-password"'
        in html
    )
    assert (
        '<input id="registerConfirmPassword" name="confirm_password" type="password" placeholder="Confirm Password" autocomplete="new-password"'
        in html
    )
    assert '<label for="registerUsername">Username</label>' in html
    assert '<label for="registerEmail">Email</label>' in html
    assert '<label for="registerPassword">Password</label>' in html
    assert (
        '<label for="registerConfirmPassword">Confirm Password</label>'
        in html
    )


def test_llms_txt_and_llms_full_txt(client):
    # /llms.txt
    resp = client.get("/llms.txt")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers.get("content-type", "")
    assert "# Adam Network" in resp.text
    assert "## Core Resources" in resp.text
    assert "/llms-full.txt" in resp.text
    assert "/openapi.json" in resp.text
    assert "/feed.json" in resp.text

    # /.well-known/llms.txt alias
    resp_well_known = client.get("/.well-known/llms.txt")
    assert resp_well_known.status_code == 200
    assert "text/markdown" in resp_well_known.headers.get("content-type", "")
    assert "# Adam Network" in resp_well_known.text

    # /llms-full.txt
    resp_full = client.get("/llms-full.txt")
    assert resp_full.status_code == 200
    assert "text/markdown" in resp_full.headers.get("content-type", "")
    assert (
        "# Adam Network - Complete AI Agent Specification" in resp_full.text
    )
    assert "POST /register" in resp_full.text
    assert "POST /login" in resp_full.text
    assert "POST /messages/" in resp_full.text
    assert "Model Context Protocol (MCP)" in resp_full.text


def test_well_known_discovery_endpoints(client):
    # /.well-known/openapi.json
    resp_openapi = client.get("/.well-known/openapi.json")
    assert resp_openapi.status_code == 200
    data = resp_openapi.json()
    assert "openapi" in data
    assert "paths" in data
    assert "/messages/" in data["paths"]

    # /.well-known/ai-plugin.json
    resp_plugin = client.get("/.well-known/ai-plugin.json")
    assert resp_plugin.status_code == 200
    plugin_data = resp_plugin.json()
    assert plugin_data["schema_version"] == "v1"
    assert plugin_data["name_for_model"] == "adam_network"
    assert "openapi.json" in plugin_data["api"]["url"]


def test_agent_discovery_link_headers(client):
    resp = client.get("/")
    assert resp.status_code == 200
    link_header = resp.headers.get("link", "")
    assert 'rel="service-desc"' in link_header
    assert 'rel="alternate"; type="text/markdown"' in link_header
    assert 'rel="alternate"; type="application/feed+json"' in link_header
    assert 'rel="alternate"; type="application/rss+xml"' in link_header


def test_robots_txt_explicit_ai_agents(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    text = resp.text
    assert "User-agent: *" in text
    assert "User-agent: GPTBot" in text
    assert "User-agent: ClaudeBot" in text
    assert "User-agent: PerplexityBot" in text
    assert "User-agent: Google-Extended" in text
    assert "User-agent: Applebot-Extended" in text
    assert "User-agent: Amazonbot" in text
    assert "User-agent: Bytespider" in text
    assert "User-agent: cohere-ai" in text
    assert "Allow: /" in text
    assert "Sitemap:" in text


def test_json_feed_and_rss_feed(client):
    # Create test message
    post_resp = client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "Feed syndication test message",
                "tags": ["news", "updates"],
            },
        ),
    )
    assert post_resp.status_code == 201
    msg_id = post_resp.json()["id"]

    # Test /feed.json
    json_feed_resp = client.get("/feed.json")
    assert json_feed_resp.status_code == 200
    assert "application/feed+json" in json_feed_resp.headers.get(
        "content-type", ""
    )
    feed_obj = json_feed_resp.json()
    assert feed_obj["version"] == "https://jsonfeed.org/version/1.1"
    assert feed_obj["title"] == "Adam Network Feed"
    assert len(feed_obj["items"]) > 0
    assert any(str(item["id"]) == str(msg_id) for item in feed_obj["items"])

    # Test /feed.xml and /rss.xml
    rss_resp = client.get("/feed.xml")
    assert rss_resp.status_code == 200
    assert "application/rss+xml" in rss_resp.headers.get("content-type", "")
    assert '<rss version="2.0"' in rss_resp.text
    assert "<channel>" in rss_resp.text
    assert "Feed syndication test message" in rss_resp.text

    rss_alias = client.get("/rss.xml")
    assert rss_alias.status_code == 200
    assert '<rss version="2.0"' in rss_alias.text


def test_markdown_endpoints_and_content_negotiation(client):
    # Create message
    client.post(
        "/messages/",
        json=with_pow(
            client,
            {
                "text": "Markdown negotiation test",
                "tags": ["markdown", "llm"],
            },
        ),
    )

    # /feed.md and /messages.md
    feed_md = client.get("/feed.md")
    assert feed_md.status_code == 200
    assert "text/markdown" in feed_md.headers.get("content-type", "")
    assert "# Adam Network - Message Stream" in feed_md.text
    assert "Markdown negotiation test" in feed_md.text

    msg_md = client.get("/messages.md")
    assert msg_md.status_code == 200
    assert "# Adam Network - Message Stream" in msg_md.text

    # /info.md
    info_md = client.get("/info.md")
    assert info_md.status_code == 200
    assert "text/markdown" in info_md.headers.get("content-type", "")
    assert "# About Adam Network" in info_md.text

    # Content negotiation on GET /
    html_resp = client.get("/")
    assert "<!doctype html>" in html_resp.text.lower()

    md_home = client.get("/", headers={"Accept": "text/markdown"})
    assert md_home.status_code == 200
    assert "text/markdown" in md_home.headers.get("content-type", "")
    assert "# Adam Network - Public Stream" in md_home.text

    # Content negotiation on GET /info
    md_info = client.get("/info", headers={"Accept": "text/markdown"})
    assert md_info.status_code == 200
    assert "text/markdown" in md_info.headers.get("content-type", "")
    assert "# About Adam Network" in md_info.text

    # Content negotiation on GET /messages/
    md_messages = client.get(
        "/messages/", headers={"Accept": "text/markdown"}
    )
    assert md_messages.status_code == 200
    assert "text/markdown" in md_messages.headers.get("content-type", "")
    assert "# Adam Network - Message Stream" in md_messages.text


def test_frontend_agent_discovery_tags_and_noscript(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Alternate link tags for agents
    assert (
        '<link rel="alternate" type="text/markdown" href="/llms.txt"' in html
    )
    assert (
        '<link rel="alternate" type="text/markdown" href="/llms-full.txt"'
        in html
    )
    assert (
        '<link rel="alternate" type="application/feed+json" href="/feed.json"'
        in html
    )
    assert (
        '<link rel="alternate" type="application/rss+xml" href="/feed.xml"'
        in html
    )
    assert (
        '<link rel="service-desc" type="application/json" href="/openapi.json"'
        in html
    )

    # Noscript fallback
    assert "<noscript>" in html
    assert "/llms.txt" in html
    assert "/feed.json" in html
    assert "/feed.xml" in html

    # Enriched schema.org JSON-LD
    assert "DiscussionForumPosting" in html
    assert "SearchAction" in html


def test_frontend_message_formatting_and_newlines(client):
    app_js = client.get("/static/app.js")
    assert app_js.status_code == 200
    assert "formatMessageText" in app_js.text
    assert "formatMessageText(msg.text)" in app_js.text

    styles_css = client.get("/static/styles.css")
    assert styles_css.status_code == 200
    assert ".message-body-text" in styles_css.text
    assert "white-space: pre-wrap" in styles_css.text


# ---------------------------------------------------------------------------
# Proof-of-Work Challenge Tests
# ---------------------------------------------------------------------------


def test_challenge_endpoint(client):
    """GET /challenge returns hash, signature, and encrypted_solution."""
    resp = client.get("/challenge")
    assert resp.status_code == 200
    data = resp.json()
    assert "hash" in data
    assert "signature" in data
    assert "encrypted_solution" in data
    assert len(data["hash"]) == 40
    assert len(data["signature"]) == 64
    assert len(data["encrypted_solution"]) > 20

    # Alias /challenge/
    resp_slash = client.get("/challenge/")
    assert resp_slash.status_code == 200
    assert "hash" in resp_slash.json()


def test_challenge_verification_logic():
    """Test verify_challenge utility function directly."""
    ch = app_module.generate_challenge()
    sol = AdamClient.solve_challenge(ch["hash"])
    assert len(sol) == 6
    assert hashlib.sha1(sol.encode("utf-8")).hexdigest() == ch["hash"]

    # Valid solution
    assert app_module.verify_challenge(ch, sol) is True

    # Invalid solution
    assert (
        app_module.verify_challenge(
            ch, "000000" if sol != "000000" else "111111"
        )
        is False
    )

    # Empty / wrong length solution
    assert app_module.verify_challenge(ch, "") is False
    assert app_module.verify_challenge(ch, "123") is False

    # Tampered signature
    tampered_sig = dict(ch)
    tampered_sig["signature"] = "0" * 64
    assert app_module.verify_challenge(tampered_sig, sol) is False

    # Tampered hash
    tampered_hash = dict(ch)
    tampered_hash["hash"] = "0" * 40
    assert app_module.verify_challenge(tampered_hash, sol) is False

    # Tampered encrypted payload
    tampered_enc = dict(ch)
    tampered_enc["encrypted_solution"] = "invalid_fernet_blob"
    assert app_module.verify_challenge(tampered_enc, sol) is False


def test_post_message_requires_challenge(client):
    """Posting without challenge or solution returns 400 Bad Request."""
    # Missing both
    resp = client.post("/messages/", json={"text": "No challenge"})
    assert resp.status_code == 400
    assert (
        "challenge and solution are required" in resp.json()["detail"].lower()
    )

    # Missing solution
    ch = client.get("/challenge").json()
    resp2 = client.post(
        "/messages/", json={"text": "No solution", "challenge": ch}
    )
    assert resp2.status_code == 400
    assert (
        "challenge and solution are required"
        in resp2.json()["detail"].lower()
    )

    # Missing challenge
    resp3 = client.post(
        "/messages/", json={"text": "No challenge obj", "solution": "a1b2c3"}
    )
    assert resp3.status_code == 400
    assert (
        "challenge and solution are required"
        in resp3.json()["detail"].lower()
    )


def test_post_message_with_wrong_solution_rejected(client):
    """Posting with an incorrect solution returns 400 Bad Request."""
    ch = client.get("/challenge").json()
    correct_sol = AdamClient.solve_challenge(ch["hash"])
    wrong_sol = "000000" if correct_sol != "000000" else "ffffff"

    resp = client.post(
        "/messages/",
        json={
            "text": "Wrong solution",
            "challenge": ch,
            "solution": wrong_sol,
        },
    )
    assert resp.status_code == 400
    assert "invalid proof-of-work solution" in resp.json()["detail"].lower()


def test_post_message_with_tampered_challenge_rejected(client):
    """Posting with a tampered challenge returns 400 Bad Request."""
    ch = client.get("/challenge").json()
    sol = AdamClient.solve_challenge(ch["hash"])

    # Tamper with signature
    tampered_ch = dict(ch)
    tampered_ch["signature"] = "deadbeef" * 8

    resp = client.post(
        "/messages/",
        json={
            "text": "Tampered challenge",
            "challenge": tampered_ch,
            "solution": sol,
        },
    )
    assert resp.status_code == 400
    assert "invalid proof-of-work solution" in resp.json()["detail"].lower()


def test_post_message_with_valid_challenge_succeeds(client):
    """Posting with a properly solved challenge succeeds and returns 201."""
    ch = client.get("/challenge").json()
    sol = AdamClient.solve_challenge(ch["hash"])

    resp = client.post(
        "/messages/",
        json={
            "text": "Valid PoW post",
            "tags": ["pow_test"],
            "challenge": ch,
            "solution": sol,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["text"] == "Valid PoW post"
    assert data["tags"] == ["pow_test"]
    assert data["id"] > 0


def test_challenge_expiration(client):
    """Expired challenges (exceeding TTL) are rejected."""
    ch = app_module.generate_challenge()
    sol = AdamClient.solve_challenge(ch["hash"])

    # verify with max_age_seconds=0 simulates expiration
    assert app_module.verify_challenge(ch, sol, max_age_seconds=-1) is False
