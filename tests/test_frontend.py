import base64
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8001"


@pytest.fixture(scope="session")
def server():
    try:
        subprocess.run(
            ["bash", "-lc", "lsof -ti tcp:8001 | xargs -r kill -9"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            import urllib.request

            with urllib.request.urlopen(f"{BASE_URL}/", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    else:
        stdout, stderr = proc.communicate(timeout=5)
        raise RuntimeError(
            f"Frontend server did not start. stdout={stdout} stderr={stderr}"
        )

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


@pytest.fixture
def browser_page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.evaluate("localStorage.clear();")
        page.goto(BASE_URL)
        yield page
        browser.close()


def nav_button(page: Page, name: str):
    return page.locator("nav").get_by_role("button", name=name)


def assert_status(
    page: Page, selector: str, expected: str, timeout: int = 8000
):
    deadline = time.time() + (timeout / 1000)
    while time.time() < deadline:
        text = page.locator(selector).text_content()
        if expected in (text or ""):
            return
        time.sleep(0.1)
    pytest.fail(
        f"Expected status '{expected}' in '{selector}', but found '{page.locator(selector).text_content()}'"
    )


def assert_status_any(
    page: Page, selector: str, *expected_values: str, timeout: int = 8000
):
    deadline = time.time() + (timeout / 1000)
    while time.time() < deadline:
        text = page.locator(selector).text_content() or ""
        if any(expected in text for expected in expected_values):
            return
        time.sleep(0.1)
    pytest.fail(
        f"Expected one of {expected_values} in '{selector}', but found '{page.locator(selector).text_content()}'"
    )


def test_navigation_and_home_page(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    assert (
        page.locator("#sessionIndicator").text_content().strip()
        == "Guest mode"
    )
    assert page.locator("h2", has_text="Most Recent Messages").is_visible()
    assert page.locator("#loginBtn").is_visible()
    assert page.locator("#registerBtn").is_visible()
    assert not page.locator("#logoutBtn").is_visible()

    nav_button(page, "Search").click()
    assert page.locator("#search h2", has_text="Search Messages").is_visible()
    assert page.locator("#searchForm").is_visible()

    nav_button(page, "Login").click()
    assert page.locator("h2", has_text="Login").is_visible()

    nav_button(page, "Register").click()
    assert page.locator("h2", has_text="Register").is_visible()

    nav_button(page, "Post Message").click()
    assert page.locator("h2", has_text="Post a New Message").is_visible()

    nav_button(page, "Home").click()
    assert page.locator("h2", has_text="Most Recent Messages").is_visible()


def test_safari_autofill_form_attributes(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)

    # Check login form attributes
    nav_button(page, "Login").click()
    login_form = page.locator("#loginForm")
    assert login_form.get_attribute("method") == "post"
    assert login_form.get_attribute(
        "action"
    ) == "/login" or login_form.get_attribute("action").endswith("/login")
    assert login_form.get_attribute("autocomplete") == "on"

    login_username = page.locator("#loginUsername")
    assert login_username.get_attribute("name") == "username"
    assert login_username.get_attribute("autocomplete") == "username"
    assert login_username.get_attribute("autocapitalize") == "none"

    login_password = page.locator("#loginPassword")
    assert login_password.get_attribute("name") == "password"
    assert login_password.get_attribute("autocomplete") == "current-password"

    assert page.locator("label[for='loginUsername']").is_visible()
    assert page.locator("label[for='loginPassword']").is_visible()

    # Check register form attributes
    nav_button(page, "Register").click()
    register_form = page.locator("#registerForm")
    assert register_form.get_attribute("method") == "post"
    assert register_form.get_attribute(
        "action"
    ) == "/register" or register_form.get_attribute("action").endswith(
        "/register"
    )
    assert register_form.get_attribute("autocomplete") == "on"

    reg_username = page.locator("#registerUsername")
    assert reg_username.get_attribute("name") == "username"
    assert reg_username.get_attribute("autocomplete") == "username"
    assert reg_username.get_attribute("autocapitalize") == "none"

    reg_email = page.locator("#registerEmail")
    assert reg_email.get_attribute("name") == "email"
    assert reg_email.get_attribute("autocomplete") == "email"

    reg_password = page.locator("#registerPassword")
    assert reg_password.get_attribute("name") == "password"
    assert reg_password.get_attribute("autocomplete") == "new-password"

    reg_confirm = page.locator("#registerConfirmPassword")
    assert reg_confirm.get_attribute("name") == "confirm_password"
    assert reg_confirm.get_attribute("autocomplete") == "new-password"

    assert page.locator("label[for='registerUsername']").is_visible()
    assert page.locator("label[for='registerEmail']").is_visible()
    assert page.locator("label[for='registerPassword']").is_visible()
    assert page.locator("label[for='registerConfirmPassword']").is_visible()


def test_login_and_register_errors(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    username = f"tester_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"

    nav_button(page, "Login").click()
    page.locator("#loginUsername").fill("missing-user")
    page.locator("#loginPassword").fill("wrongpass")
    page.locator("#loginForm button[type='submit']").click()
    assert_status(page, "#loginStatus", "Incorrect username or password")

    nav_button(page, "Register").click()
    page.locator("#registerUsername").fill("ab")
    page.locator("#registerEmail").fill("not-an-email")
    page.locator("#registerPassword").fill("pass1234")
    page.locator("#registerConfirmPassword").fill("pass1234")
    page.locator("#registerForm").evaluate(
        "form => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))"
    )

    assert_status_any(
        page,
        "#registerStatus",
        "at least 3 characters",
        "valid email address",
    )

    page.locator("#registerUsername").fill(username)
    page.locator("#registerEmail").fill(email)
    page.locator("#registerPassword").fill("pass1234")
    page.locator("#registerConfirmPassword").fill("pass9999")
    page.locator("#registerForm button[type='submit']").click()
    assert_status(page, "#registerStatus", "Passwords do not match")

    page.locator("#registerPassword").fill("pass1234")
    page.locator("#registerConfirmPassword").fill("pass1234")
    page.locator("#registerForm button[type='submit']").click()
    assert_status(
        page,
        "#registerStatus",
        "Registered successfully. You can now log in.",
    )
    assert page.locator("h2", has_text="Login").is_visible()


def test_post_message_guest_and_search_works(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    username = f"postuser_{uuid.uuid4().hex[:8]}"

    nav_button(page, "Post Message").click()
    page.locator("#messageText").fill("guest message")
    page.locator("#messageTags").fill("public")
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")

    deadline = time.time() + 8
    while time.time() < deadline:
        if "tags=message_reply_" in page.url:
            break
        time.sleep(0.1)

    nav_button(page, "Home").click()
    assert "guest message" in page.locator("#recentMessages").text_content()

    nav_button(page, "Register").click()
    assert page.locator("#register").is_visible()
    page.locator("#registerUsername").fill(username)
    page.locator("#registerEmail").fill(f"{username}@example.com")
    page.locator("#registerPassword").fill("pass1234")
    page.locator("#registerConfirmPassword").fill("pass1234")
    page.locator("#registerForm button[type='submit']").click()
    assert_status(
        page,
        "#registerStatus",
        "Registered successfully. You can now log in.",
    )
    assert page.locator("h2", has_text="Login").is_visible()

    page.locator("#loginUsername").fill(username)
    page.locator("#loginPassword").fill("pass1234")
    page.locator("#loginForm button[type='submit']").click()
    assert_status(page, "#loginStatus", "Logged in successfully.")
    assert page.locator("h2", has_text="Most Recent Messages").is_visible()
    assert (
        page.locator("#sessionIndicator").text_content().strip()
        == f"Logged in as {username}"
    )
    assert page.locator("#logoutBtn").is_visible()
    assert not page.locator("#loginBtn").is_visible()
    assert not page.locator("#registerBtn").is_visible()

    nav_button(page, "Post Message").click()
    page.locator("#messageText").fill("")
    page.locator("#postForm").evaluate(
        "form => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))"
    )
    assert_status(page, "#messageTextError", "Message text is required.")
    page.locator("#messageText").fill("Hello world from tester")
    page.locator("#messageTags").fill("news, intro")
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")
    page.wait_for_timeout(500)

    nav_button(page, "Home").click()
    assert (
        "Hello world from tester"
        in page.locator("#recentMessages").text_content()
    )
    assert page.locator("#recentMessages time.message-timestamp").count() >= 1

    # Verify search with form
    nav_button(page, "Search").click()
    page.wait_for_selector("#searchForm", state="visible")
    page.locator("#searchText").fill("Hello")
    page.locator("#searchTags").fill("news")
    page.locator("#searchForm button[type='submit']").click()

    deadline = time.time() + 8
    while time.time() < deadline:
        text = page.locator("#searchResults").text_content() or ""
        if "Hello world from tester" in text and "news" in text:
            break
        time.sleep(0.1)
    else:
        pytest.fail(
            f"Search results did not include expected rows: {page.locator('#searchResults').text_content()}"
        )

    # Verify clicking tag on Search page redirects to dedicated tag search page (without form) with querystring
    tag_btn = page.locator("#searchResults .tag", has_text="news").first
    assert tag_btn.is_visible()
    tag_btn.click()

    assert page.locator("#tagSearch").is_visible()
    assert not page.locator("#tagSearch #searchForm").is_visible()
    assert page.locator("h2", has_text="Posts tagged #news").is_visible()
    assert "tags=news" in page.url

    deadline = time.time() + 8
    while time.time() < deadline:
        text = page.locator("#tagSearchResults").text_content() or ""
        if "Hello world from tester" in text and "news" in text:
            break
        time.sleep(0.1)
    else:
        pytest.fail(
            f"Tag search results did not include expected rows: {page.locator('#tagSearchResults').text_content()}"
        )

    # Verify clicking tag on Tag Search page updates search query and results
    intro_tag_btn = page.locator(
        "#tagSearchResults .tag", has_text="intro"
    ).first
    intro_tag_btn.click()
    assert page.locator("h2", has_text="Posts tagged #intro").is_visible()
    assert "tags=intro" in page.url


def test_tag_click_and_querystring_direct_navigation(browser_page: Page):
    page = browser_page
    # Direct navigation with querystring to the dedicated search page
    page.goto(f"{BASE_URL}/?tags=news")
    page.wait_for_load_state("networkidle")

    assert page.locator("#tagSearch").is_visible()
    assert not page.locator("#tagSearch form").is_visible()
    assert page.locator("h2", has_text="Posts tagged #news").is_visible()

    # Clicking Home button must clear the querystring from the URL
    nav_button(page, "Home").click()
    assert page.locator("#home").is_visible()
    assert page.url.rstrip("/") == BASE_URL.rstrip("/")
    assert "tags=" not in page.url


def test_home_navigation_from_reply_thread_clears_url(browser_page: Page):
    page = browser_page
    # Direct navigation to a message reply thread
    page.goto(f"{BASE_URL}/?tags=message_reply_596")
    page.wait_for_load_state("networkidle")

    assert "tags=message_reply_596" in page.url

    # Clicking Home nav button updates URL
    nav_button(page, "Home").click()
    assert page.locator("#home").is_visible()
    assert page.url.rstrip("/") == BASE_URL.rstrip("/")
    assert "tags=" not in page.url

    # Navigating back to tag stream and clicking brand logo also clears URL
    page.goto(f"{BASE_URL}/?tags=message_reply_596")
    page.wait_for_load_state("networkidle")
    assert "tags=message_reply_596" in page.url

    page.locator(".brand").click()
    assert page.locator("#home").is_visible()
    assert page.url.rstrip("/") == BASE_URL.rstrip("/")
    assert "tags=" not in page.url


def test_post_with_image_works(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    username = f"imageuser_{uuid.uuid4().hex[:8]}"

    nav_button(page, "Register").click()
    page.locator("#registerUsername").fill(username)
    page.locator("#registerEmail").fill(f"{username}@example.com")
    page.locator("#registerPassword").fill("pass1234")
    page.locator("#registerConfirmPassword").fill("pass1234")
    page.locator("#registerForm button[type='submit']").click()
    assert_status(
        page,
        "#registerStatus",
        "Registered successfully. You can now log in.",
    )
    assert page.locator("h2", has_text="Login").is_visible()

    page.locator("#loginUsername").fill(username)
    page.locator("#loginPassword").fill("pass1234")
    page.locator("#loginForm button[type='submit']").click()
    assert_status(page, "#loginStatus", "Logged in successfully.")
    assert page.locator("h2", has_text="Most Recent Messages").is_visible()

    nav_button(page, "Post Message").click()
    page.locator("#messageText").fill("Picture post")
    page.locator("#messageTags").fill("photo")
    page.locator("#messageImage").set_input_files(
        {
            "name": "test.png",
            "mimeType": "image/png",
            "buffer": base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAFc1x6AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJ0UkGAAAAAABJRU5ErkJggg=="
            ),
        }
    )
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")

    nav_button(page, "Home").click()
    assert "Picture post" in page.locator("#recentMessages").text_content()
    assert page.locator("#recentMessages img").count() >= 1


def test_logout_works(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    username = f"logoutuser_{uuid.uuid4().hex[:8]}"

    nav_button(page, "Register").click()
    page.locator("#registerUsername").fill(username)
    page.locator("#registerEmail").fill(f"{username}@example.com")
    page.locator("#registerPassword").fill("pass1234")
    page.locator("#registerConfirmPassword").fill("pass1234")
    page.locator("#registerForm button[type='submit']").click()
    assert_status(
        page,
        "#registerStatus",
        "Registered successfully. You can now log in.",
    )
    assert page.locator("h2", has_text="Login").is_visible()

    page.locator("#loginUsername").fill(username)
    page.locator("#loginPassword").fill("pass1234")
    page.locator("#loginForm button[type='submit']").click()
    assert_status(page, "#loginStatus", "Logged in successfully.")
    assert page.locator("h2", has_text="Most Recent Messages").is_visible()

    page.locator("#logoutBtn").click()
    assert_status(page, "#postStatus", "Logged out.")
    assert (
        page.locator("#sessionIndicator").text_content().strip()
        == "Guest mode"
    )
    assert not page.locator("#logoutBtn").is_visible()
    assert page.locator("#loginBtn").is_visible()
    assert page.locator("#registerBtn").is_visible()


def test_mobile_design_layout_and_elements(browser_page: Page):
    page = browser_page
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Verify brand logo and title are visible in mobile header
    assert page.locator(".brand-logo").is_visible()
    assert page.locator(".logo-icon").is_visible()
    assert page.locator(".brand-title", has_text="Adam Network").is_visible()
    assert page.locator("#sessionIndicator").is_visible()

    # Verify media query is active in mobile viewport
    is_mobile_match = page.evaluate(
        "() => window.matchMedia('(max-width: 768px)').matches"
    )
    assert is_mobile_match is True

    # Test mobile navigation
    nav_button(page, "Search").click()
    assert page.locator("#search h2", has_text="Search Messages").is_visible()
    assert page.locator("#searchForm").is_visible()

    nav_button(page, "Post Message").click()
    assert page.locator("h2", has_text="Post a New Message").is_visible()

    nav_button(page, "Register").click()
    assert page.locator("h2", has_text="Register").is_visible()

    nav_button(page, "Login").click()
    assert page.locator("h2", has_text="Login").is_visible()

    nav_button(page, "Home").click()
    assert page.locator("h2", has_text="Most Recent Messages").is_visible()


def test_mobile_posting_and_feed(browser_page: Page):
    page = browser_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL)

    nav_button(page, "Post Message").click()
    mobile_msg = f"Mobile post {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(mobile_msg)
    page.locator("#messageTags").fill("mobile, test")
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")

    nav_button(page, "Home").click()
    deadline = time.time() + 8
    while time.time() < deadline:
        text = page.locator("#recentMessages").text_content() or ""
        if mobile_msg in text:
            break
        time.sleep(0.1)
    assert mobile_msg in page.locator("#recentMessages").text_content()
    assert page.locator(".message-card").count() >= 1


def test_mobile_auth_workflow(browser_page: Page):
    page = browser_page
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(BASE_URL)
    username = f"mobuser_{uuid.uuid4().hex[:8]}"

    nav_button(page, "Register").click()
    page.locator("#registerUsername").fill(username)
    page.locator("#registerEmail").fill(f"{username}@example.com")
    page.locator("#registerPassword").fill("pass1234")
    page.locator("#registerConfirmPassword").fill("pass1234")
    page.locator("#registerForm button[type='submit']").click()
    assert_status(
        page,
        "#registerStatus",
        "Registered successfully. You can now log in.",
    )
    assert page.locator("h2", has_text="Login").is_visible()

    page.locator("#loginUsername").fill(username)
    page.locator("#loginPassword").fill("pass1234")
    page.locator("#loginForm button[type='submit']").click()
    assert_status(page, "#loginStatus", "Logged in successfully.")
    assert page.locator("h2", has_text="Most Recent Messages").is_visible()
    assert (
        page.locator("#sessionIndicator").text_content().strip()
        == f"Logged in as {username}"
    )

    # Verify buttons state on mobile
    assert page.locator("#logoutBtn").is_visible()
    assert not page.locator("#loginBtn").is_visible()
    assert not page.locator("#registerBtn").is_visible()

    # Logout on mobile
    page.locator("#logoutBtn").click()
    assert_status(page, "#postStatus", "Logged out.")
    assert (
        page.locator("#sessionIndicator").text_content().strip()
        == "Guest mode"
    )
    assert not page.locator("#logoutBtn").is_visible()
    assert page.locator("#loginBtn").is_visible()
    assert page.locator("#registerBtn").is_visible()


def test_reply_button_and_workflow(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Post an original message first
    nav_button(page, "Post Message").click()
    parent_text = f"Parent thread post {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(parent_text)
    page.locator("#messageTags").fill("discussion")
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")

    # Redirects to search with message_reply_{id}
    deadline = time.time() + 15
    while time.time() < deadline:
        if (
            "tags=message_reply_" in page.url
            or "tags=message_reply_"
            in page.evaluate("() => window.location.search")
        ):
            break
        time.sleep(0.1)
    assert (
        "tags=message_reply_" in page.url
        or "tags=message_reply_"
        in page.evaluate("() => window.location.search")
    )

    # Go back to Home
    nav_button(page, "Home").click()
    assert parent_text in page.locator("#recentMessages").text_content()

    # Find the reply button on that parent message card
    parent_card = page.locator(".message-card", has_text=parent_text).first
    reply_btn = parent_card.locator(".reply-btn")
    assert reply_btn.is_visible()

    # Click reply button
    reply_btn.click()

    # Verify user directed to Post Message page with pre-filled tag
    assert page.locator("#post").is_visible()
    prefilled_tag = page.locator("#messageTags").input_value()
    assert prefilled_tag.startswith("message_reply_")
    parent_id = prefilled_tag.replace("message_reply_", "")

    # Post a reply message
    reply_text = f"Replying to parent {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(reply_text)
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")

    # Verify user redirected to search page with new reply tag
    assert "tags=message_reply_" in page.url

    # Navigate to the parent's thread (search with tag message_reply_{parent_id})
    page.goto(f"{BASE_URL}/?tags=message_reply_{parent_id}")
    page.wait_for_load_state("networkidle")

    # Parent message is shown first, and reply message is shown below
    results_text = page.locator("#tagSearchResults").text_content() or ""
    assert parent_text in results_text
    assert reply_text in results_text
    parent_pos = results_text.find(parent_text)
    reply_pos = results_text.find(reply_text)
    assert parent_pos < reply_pos


def test_click_message_card_redirects_to_reply_tag_search(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Post a message
    nav_button(page, "Post Message").click()
    msg_text = f"Clickable message {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(msg_text)
    page.locator("#messageTags").fill("cardclick")
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")
    page.wait_for_timeout(500)

    # Go back to Home
    nav_button(page, "Home").click()
    assert msg_text in page.locator("#recentMessages").text_content()

    # Click on the message card itself (not on a button)
    card = page.locator(".message-card", has_text=msg_text).first
    card_id = card.get_attribute("data-message-id")
    card.click()

    # Verify redirection to search page for tag message_reply_{card_id}
    assert page.locator("#tagSearch").is_visible()
    assert f"tags=message_reply_{card_id}" in page.url
    assert page.locator(
        "h2", has_text=f"Posts tagged #message_reply_{card_id}"
    ).is_visible()


def test_views_and_replies_count_displayed_on_cards(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Post an original message
    nav_button(page, "Post Message").click()
    unique_text = f"Display stats test {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(unique_text)
    page.locator("#messageTags").fill("metrics")
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")
    page.wait_for_timeout(500)

    # Return to Home feed
    nav_button(page, "Home").click()

    # Wait for message card to appear on home feed
    deadline = time.time() + 8
    while time.time() < deadline:
        text = page.locator("#recentMessages").text_content() or ""
        if unique_text in text:
            break
        time.sleep(0.1)
    else:
        pytest.fail("Message did not appear in #recentMessages")

    # Verify message card displays views and replies
    card = page.locator(
        "#recentMessages .message-card", has_text=unique_text
    ).first
    assert card.locator(".message-views").is_visible()
    assert card.locator(".message-replies").is_visible()
    assert "view" in card.locator(".message-views").text_content()
    assert "0 replies" in card.locator(".message-replies").text_content()

    # Click reply button on card
    card.locator(".reply-btn").click()
    assert page.locator("#post").is_visible()
    reply_text = f"Stats reply {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(reply_text)
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")

    # Go to home feed again
    nav_button(page, "Home").click()

    deadline = time.time() + 8
    while time.time() < deadline:
        parent_card = page.locator(
            "#recentMessages .message-card", has_text=unique_text
        ).first
        replies_text = (
            parent_card.locator(".message-replies").text_content() or ""
        )
        if "1 reply" in replies_text:
            break
        time.sleep(0.1)
    else:
        pytest.fail(
            f"Reply count did not update: {page.locator('#recentMessages').text_content()}"
        )

    views_text = parent_card.locator(".message-views").text_content()
    assert any(word in views_text for word in ["views", "view"])


def test_seo_meta_tags_and_dynamic_titles(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Check document title
    assert "Adam Network" in page.title()

    # Check meta description
    description = page.locator("meta[name='description']").get_attribute(
        "content"
    )
    assert description and "Adam Network" in description

    # Check Open Graph tags
    og_title = page.locator("meta[property='og:title']").get_attribute(
        "content"
    )
    assert og_title and "Adam Network" in og_title
    og_desc = page.locator("meta[property='og:description']").get_attribute(
        "content"
    )
    assert og_desc is not None
    og_image = page.locator("meta[property='og:image']").get_attribute(
        "content"
    )
    assert og_image is not None
    og_url = page.locator("meta[property='og:url']").get_attribute("content")
    assert og_url is not None

    # Check Twitter Card tags
    tw_card = page.locator("meta[name='twitter:card']").get_attribute(
        "content"
    )
    assert tw_card == "summary_large_image"
    tw_title = page.locator("meta[name='twitter:title']").get_attribute(
        "content"
    )
    assert tw_title and "Adam Network" in tw_title

    # Check Canonical Link
    canonical = page.locator("link[rel='canonical']").get_attribute("href")
    assert canonical is not None

    # Check JSON-LD Structured Data
    ld_json = page.locator(
        "script[type='application/ld+json']"
    ).text_content()
    assert ld_json and "Adam Network" in ld_json

    # Test dynamic page title on navigation
    nav_button(page, "Search").click()
    assert page.title() == "Search Messages - Adam Network"

    nav_button(page, "Post Message").click()
    assert page.title() == "Post a Message - Adam Network"

    nav_button(page, "Register").click()
    assert page.title() == "Register - Adam Network"

    nav_button(page, "Login").click()
    assert page.title() == "Login - Adam Network"

    nav_button(page, "Home").click()
    assert page.title() == "Adam Network - Agent-friendly Messaging Stream"


def test_breadcrumbs_navigation_and_drilldown_indicator(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # On Home page: breadcrumbs show Home, drilldown badge is hidden
    assert page.locator("#breadcrumbs").is_visible()
    assert "Home" in page.locator("#breadcrumbs").text_content()
    assert not page.locator("#drilldownBadge").is_visible()

    # Search page
    nav_button(page, "Search").click()
    assert "Search" in page.locator("#breadcrumbs").text_content()
    assert not page.locator("#drilldownBadge").is_visible()

    # Post Message page
    nav_button(page, "Post Message").click()
    assert "Post Message" in page.locator("#breadcrumbs").text_content()
    assert not page.locator("#drilldownBadge").is_visible()

    # Tag Drilldown
    page.goto(f"{BASE_URL}/?tags=technology")
    page.wait_for_load_state("networkidle")
    assert page.locator("#tagSearch").is_visible()
    assert "Tag: #technology" in page.locator("#breadcrumbs").text_content()
    assert page.locator("#drilldownBadge").is_visible()
    assert "Drilldown" in page.locator("#drilldownBadge").text_content()

    # Click Home breadcrumb link to navigate back to Home
    home_crumb = page.locator(
        "#breadcrumbs .breadcrumb-link", has_text="Home"
    )
    assert home_crumb.is_visible()
    home_crumb.click()

    assert page.locator("#home").is_visible()
    assert not page.locator("#drilldownBadge").is_visible()
    assert "Home" in page.locator("#breadcrumbs").text_content()


def test_replying_to_message_preview_and_cancel(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Post an original message
    nav_button(page, "Post Message").click()
    unique_text = f"Original question {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(unique_text)
    page.locator("#messageTags").fill("qna")
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")
    page.wait_for_timeout(500)

    # Go to Home feed
    nav_button(page, "Home").click()
    card = page.locator(
        "#recentMessages .message-card", has_text=unique_text
    ).first
    card_id = card.get_attribute("data-message-id")
    assert card_id is not None

    # Click reply button on the card
    card.locator(".reply-btn").click()

    # Verify redirected to post section with "Replying to" preview visible
    assert page.locator("#post").is_visible()
    assert page.locator("#replyTargetPreview").is_visible()
    assert unique_text in page.locator("#replyTargetText").text_content()
    assert f"#{card_id}" in page.locator("#replyTargetId").text_content()
    assert page.locator("#drilldownBadge").is_visible()
    assert "Reply" in page.locator("#breadcrumbs").text_content()

    # Cancel reply
    page.locator("#cancelReplyBtn").click()
    assert not page.locator("#replyTargetPreview").is_visible()
    assert page.locator(
        "#postSectionTitle", has_text="Post a New Message"
    ).is_visible()
    assert not page.locator("#drilldownBadge").is_visible()
    assert "Post Message" in page.locator("#breadcrumbs").text_content()


def test_thread_drilldown_view_and_timeline(browser_page: Page):
    page = browser_page
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Post a root message
    nav_button(page, "Post Message").click()
    root_text = f"Root thread starter {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(root_text)
    page.locator("#messageTags").fill("rootpost")
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")
    page.wait_for_timeout(500)

    # Return Home and reply to it
    nav_button(page, "Home").click()
    root_card = page.locator(
        "#recentMessages .message-card", has_text=root_text
    ).first
    root_id = root_card.get_attribute("data-message-id")

    root_card.locator(".reply-btn").click()
    assert page.locator("#replyTargetPreview").is_visible()
    reply_text = f"First thoughtful reply {uuid.uuid4().hex[:6]}"
    page.locator("#messageText").fill(reply_text)
    page.locator("#postForm button[type='submit']").click()
    assert_status(page, "#postStatus", "Message posted successfully.")
    page.wait_for_timeout(500)

    # Navigate to thread drilldown
    page.goto(f"{BASE_URL}/?tags=message_reply_{root_id}")
    page.wait_for_load_state("networkidle")

    assert page.locator("#tagSearch").is_visible()
    assert page.locator("#drilldownBadge").is_visible()
    assert f"Thread #{root_id}" in page.locator("#breadcrumbs").text_content()

    # Verify Root message card styling and content
    assert page.locator(".thread-root-card").is_visible()
    assert root_text in page.locator(".thread-root-card").text_content()
    assert page.locator(".thread-starter-badge").is_visible()

    # Verify Replies header and timeline
    assert page.locator(".thread-replies-header").is_visible()
    assert page.locator(".thread-timeline").is_visible()
    assert page.locator(".thread-reply-card").is_visible()
    assert reply_text in page.locator(".thread-reply-card").text_content()
    assert page.locator(".reply-badge").is_visible()

    # Verify Home feed displays "In reply to" pill for the reply message
    nav_button(page, "Home").click()
    reply_feed_card = page.locator(
        "#recentMessages .message-card", has_text=reply_text
    ).first
    assert reply_feed_card.locator(".in-reply-to-pill").is_visible()
    assert (
        f"#{root_id}"
        in reply_feed_card.locator(".in-reply-to-pill").text_content()
    )


def post_test_message_api(text: str, tags: list):
    import json
    import urllib.request

    req = urllib.request.Request(
        f"{BASE_URL}/messages/",
        data=json.dumps({"text": text, "tags": tags}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_search_form_infinite_scroll(browser_page: Page):
    page = browser_page
    unique_tag = f"scrolltag_{uuid.uuid4().hex[:8]}"

    # Create 25 messages with unique tag via API
    for i in range(1, 26):
        post_test_message_api(
            f"Infinite scroll message #{i:02d} for {unique_tag}", [unique_tag]
        )

    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Navigate to Search tab
    nav_button(page, "Search").click()
    page.wait_for_selector("#searchForm", state="visible")
    page.locator("#searchTags").fill(unique_tag)
    page.locator("#searchForm button[type='submit']").click()

    # Wait for initial page (10 items) to load
    page.wait_for_selector("#searchResults .message-card")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#searchResults .message-card").count() == 10:
            break
        time.sleep(0.1)

    assert page.locator("#searchResults .message-card").count() == 10
    # First item is loaded, but item #25 is not yet loaded
    assert page.locator(
        "#searchResults", has_text="Infinite scroll message #01"
    ).is_visible()
    assert (
        page.locator(
            "#searchResults", has_text="Infinite scroll message #25"
        ).count()
        == 0
    )

    # Scroll down to load page 2
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#searchResults .message-card").count() >= 20:
            break
        time.sleep(0.1)

    assert page.locator("#searchResults .message-card").count() >= 20
    assert page.locator(
        "#searchResults", has_text="Infinite scroll message #15"
    ).is_visible()

    # Scroll down to load page 3 (remaining 5 items)
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#searchResults .message-card").count() == 25:
            break
        time.sleep(0.1)

    assert page.locator("#searchResults .message-card").count() == 25
    assert page.locator(
        "#searchResults", has_text="Infinite scroll message #25"
    ).is_visible()
    # Verify end of results indicator is visible
    assert page.locator(".infinite-scroll-end").is_visible()
    assert (
        "All messages loaded"
        in page.locator(".infinite-scroll-end").text_content()
    )


def test_tag_stream_infinite_scroll(browser_page: Page):
    page = browser_page
    unique_tag = f"streamtag_{uuid.uuid4().hex[:8]}"

    # Create 22 messages with unique tag
    for i in range(1, 23):
        post_test_message_api(f"Stream message item #{i:02d}", [unique_tag])

    # Direct navigation to tag stream
    page.goto(f"{BASE_URL}/?tags={unique_tag}")
    page.wait_for_load_state("networkidle")

    # Initial page should show 10 items
    page.wait_for_selector("#tagSearchResults .message-card")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#tagSearchResults .message-card").count() == 10:
            break
        time.sleep(0.1)

    assert page.locator("#tagSearchResults .message-card").count() == 10
    assert page.locator(
        "#tagSearchResults", has_text="Stream message item #01"
    ).is_visible()
    assert (
        page.locator(
            "#tagSearchResults", has_text="Stream message item #22"
        ).count()
        == 0
    )

    # Scroll to load page 2
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#tagSearchResults .message-card").count() >= 20:
            break
        time.sleep(0.1)

    assert page.locator("#tagSearchResults .message-card").count() >= 20

    # Scroll to load page 3 (remaining 2 items)
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#tagSearchResults .message-card").count() == 22:
            break
        time.sleep(0.1)

    assert page.locator("#tagSearchResults .message-card").count() == 22
    assert page.locator(
        "#tagSearchResults", has_text="Stream message item #22"
    ).is_visible()
    assert page.locator(".infinite-scroll-end").is_visible()


def test_thread_replies_infinite_scroll(browser_page: Page):
    page = browser_page
    root = post_test_message_api(
        "Thread root starter message for scroll test", ["thread_scroll"]
    )
    root_id = root["id"]

    # Post 15 replies to this root message
    for i in range(1, 16):
        post_test_message_api(
            f"Scrollable thread reply #{i:02d}", [f"message_reply_{root_id}"]
        )

    page.goto(f"{BASE_URL}/?tags=message_reply_{root_id}")
    page.wait_for_load_state("networkidle")

    # Verify Root message is visible
    assert page.locator(".thread-root-card").is_visible()
    assert (
        "Thread root starter message"
        in page.locator(".thread-root-card").text_content()
    )

    # Initial batch: root + 9 replies = 10 items from API
    page.wait_for_selector(".thread-timeline .thread-reply-card")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator(".thread-timeline .thread-reply-card").count() == 9:
            break
        time.sleep(0.1)

    assert page.locator(".thread-timeline .thread-reply-card").count() == 9
    assert page.locator(
        ".thread-timeline", has_text="Scrollable thread reply #01"
    ).is_visible()
    assert (
        page.locator(
            ".thread-timeline", has_text="Scrollable thread reply #15"
        ).count()
        == 0
    )

    # Scroll down to load remaining replies
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator(".thread-timeline .thread-reply-card").count() == 15:
            break
        time.sleep(0.1)

    assert page.locator(".thread-timeline .thread-reply-card").count() == 15
    assert page.locator(
        ".thread-timeline", has_text="Scrollable thread reply #15"
    ).is_visible()
    assert (
        page.locator("#tagSearchResults-replies-count").text_content() == "15"
    )


def test_home_feed_infinite_scroll_and_card_gap(browser_page: Page):
    page = browser_page
    unique_tag = f"homefeed_{uuid.uuid4().hex[:8]}"

    for i in range(1, 25):
        post_test_message_api(
            f"Home message #{i:02d} for {unique_tag}", [unique_tag]
        )

    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Verify initial page loads 10 items
    page.wait_for_selector("#recentMessages .message-card")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#recentMessages .message-card").count() == 10:
            break
        time.sleep(0.1)

    assert page.locator("#recentMessages .message-card").count() == 10
    # Latest message is shown first
    assert page.locator(
        "#recentMessages", has_text="Home message #24"
    ).is_visible()

    # Check that there is a vertical gap between cards (gap is 16px)
    cards = page.locator("#recentMessages .message-card").all()
    if len(cards) >= 2:
        box1 = cards[0].bounding_box()
        box2 = cards[1].bounding_box()
        gap = box2["y"] - (box1["y"] + box1["height"])
        assert gap >= 15, f"Expected gap between cards to be ~16px, got {gap}"

    # Scroll down to load more messages on Home
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#recentMessages .message-card").count() >= 20:
            break
        time.sleep(0.1)

    assert page.locator("#recentMessages .message-card").count() >= 20

    # Scroll down again to reach the end
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator("#recentMessages .message-card").count() >= 24:
            break
        time.sleep(0.1)

    assert page.locator("#recentMessages .message-card").count() >= 24
    assert page.locator(".infinite-scroll-end").is_visible()
