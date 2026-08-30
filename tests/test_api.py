import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module


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
        json={"text": "guest attempt", "tags": ["public"]},
    )
    assert guest_post.status_code == 201
    assert guest_post.json()["username"] == "guest"
    assert guest_post.json()["text"] == "guest attempt"

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
        json={"text": "hello world", "tags": ["greeting"]},
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
        json={"text": "first message", "tags": ["alpha", "beta"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    second = client.post(
        "/messages/",
        json={"text": "second message", "tags": ["beta", "gamma"]},
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

    response = client.post(
        "/messages/",
        json={
            "text": "image post",
            "tags": ["photo"],
            "image_data": "data:image/png;base64,abcd1234",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["image_data"] == "data:image/png;base64,abcd1234"
    assert response.json()["created_at"] is not None


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
        json={"text": "Original parent post", "tags": ["topic"]},
    )
    assert parent.status_code == 201
    parent_id = parent.json()["id"]

    reply1 = client.post(
        "/messages/",
        json={"text": "First reply", "tags": [f"messsage_reply_{parent_id}"]},
    )
    assert reply1.status_code == 201

    reply2 = client.post(
        "/messages/",
        json={
            "text": "Second reply",
            "tags": [f"messsage_reply_{parent_id}"],
        },
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
        json={"text": "Parent view test", "tags": ["stats"]},
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
        json={"text": "Reply one", "tags": [f"message_reply_{parent_id}"]},
    )
    assert reply1.status_code == 201
    reply1_id = reply1.json()["id"]

    reply2 = client.post(
        "/messages/",
        json={
            "text": "Reply two",
            "tags": [f"message_reply_{parent_id}", "extra"],
        },
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
        "/messages/", json={"text": "Msg 1", "tags": []}
    ).json()
    msg_id_1 = msg1["id"]

    # Create a dummy message tagged with message_reply_{msg_id_1}0
    client.post(
        "/messages/",
        json={
            "text": "Reply to msg 10",
            "tags": [f"message_reply_{msg_id_1}0"],
        },
    )

    # msg 1 should still have 0 replies, not 1
    check_msg1 = client.get(f"/messages/{msg_id_1}").json()
    assert check_msg1["reply_count"] == 0


def test_seo_robots_and_sitemap(client):
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "User-agent: *" in robots.text
    assert "Sitemap:" in robots.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "application/xml" in sitemap.headers.get("content-type", "")
    assert "<urlset" in sitemap.text
    assert "<loc>https://adam-network.up.railway.app/</loc>" in sitemap.text


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
