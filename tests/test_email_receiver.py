"""Unit tests for IMAP Email Receiver and Verification Tools."""

from datetime import datetime, timezone
import email.message
import email.utils
import imaplib
import os
from unittest.mock import MagicMock, patch
import pytest

from agents.add_comments_to_network.email_receiver import (
    DEFAULT_EMAIL_USER,
    DEFAULT_IMAP_PORT,
    DEFAULT_IMAP_SERVER,
    IMAPEmailClient,
    decode_header_value,
    extract_codes,
    extract_email_bodies,
    extract_links,
    fetch_latest_emails,
    search_verification_emails,
    wait_for_verification_email,
)


def test_decode_header_value():
    # Plain text
    assert decode_header_value("Simple Subject") == "Simple Subject"
    # None or empty
    assert decode_header_value(None) == ""
    assert decode_header_value("") == ""
    # RFC 2047 utf-8 base64 encoded header
    # "=?utf-8?B?VmVyaWZ5IHlvdXIgZW1haWwgYWRkcmVzcw==?=" -> "Verify your email address"
    assert (
        decode_header_value(
            "=?utf-8?B?VmVyaWZ5IHlvdXIgZW1haWwgYWRkcmVzcw==?="
        )
        == "Verify your email address"
    )


def test_extract_email_bodies_single_part():
    msg = email.message.EmailMessage()
    msg.set_content("Welcome! Please confirm your registration.")
    plain, html = extract_email_bodies(msg)
    assert "Please confirm your registration." in plain
    assert html == ""


def test_extract_email_bodies_multipart():
    msg = email.message.EmailMessage()
    msg.set_content("Plain text body here.")
    msg.add_alternative(
        "<html><body><p>HTML body with <a href='https://example.com/verify?token=xyz123'>link</a></p></body></html>",
        subtype="html",
    )
    plain, html = extract_email_bodies(msg)
    assert "Plain text body here." in plain
    assert "https://example.com/verify?token=xyz123" in html


def test_extract_links():
    plain = "Click here to verify: https://example.com/verify?token=abc456 or visit https://example.com/home"
    html = """
    <html>
      <body>
        <p>Thanks for registering.</p>
        <a href="https://example.com/confirm?id=999">Confirm your account</a>
        <a href="https://example.com/privacy">Privacy Policy</a>
      </body>
    </html>
    """
    links = extract_links(plain, html)
    urls = [l["url"] for l in links]

    assert "https://example.com/verify?token=abc456" in urls
    assert "https://example.com/confirm?id=999" in urls
    assert "https://example.com/home" in urls
    assert "https://example.com/privacy" in urls

    # Verification links should be prioritized
    verification_links = [
        l["url"] for l in links if l["is_verification_link"]
    ]
    assert "https://example.com/verify?token=abc456" in verification_links
    assert "https://example.com/confirm?id=999" in verification_links


def test_extract_codes():
    plain = (
        "Your verification code is 849201. Please enter it within 10 minutes."
    )
    html = "<p>Your security code: <strong>392014</strong></p>"
    codes = extract_codes(plain, html)
    assert "849201" in codes
    assert "392014" in codes


def test_imap_client_init_defaults():
    with patch.dict(os.environ, {}, clear=True):
        client = IMAPEmailClient()
        assert client.host == DEFAULT_IMAP_SERVER
        assert client.port == DEFAULT_IMAP_PORT
        assert client.user == DEFAULT_EMAIL_USER
        assert client.password is None
        assert client.is_configured() is False


def test_imap_client_custom_env():
    env = {
        "GMAIL_IMAP_SERVER": "imap.custom.com",
        "GMAIL_IMAP_PORT": "9993",
        "GMAIL_EMAIL": "test@custom.com",
        "GMAIL_APP_PASSWORD": "app-secret-pwd",
    }
    with patch.dict(os.environ, env, clear=True):
        client = IMAPEmailClient()
        assert client.host == "imap.custom.com"
        assert client.port == 9993
        assert client.user == "test@custom.com"
        assert client.password == "app-secret-pwd"
        assert client.is_configured() is True


def test_imap_client_fetch_recent_emails_mocked():
    now_str = email.utils.format_datetime(datetime.now(timezone.utc))
    raw_msg_bytes = (
        f"From: no-reply@directory.ai\r\n"
        f"To: adam.ivansky@gmail.com\r\n"
        f"Subject: Confirm your AI Directory registration\r\n"
        f"Date: {now_str}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"Thank you for registering Adam Network. Please verify your account at https://directory.ai/verify?token=abc123token or enter code 729104."
    ).encode("utf-8")

    mock_imap = MagicMock()
    mock_imap.select.return_value = ("OK", [b"1"])
    mock_imap.search.return_value = ("OK", [b"1"])
    mock_imap.fetch.return_value = (
        "OK",
        [(b"1 (RFC822 {100}", raw_msg_bytes)],
    )

    with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
        client = IMAPEmailClient(
            host="imap.gmail.com",
            port=993,
            user="adam.ivansky@gmail.com",
            password="fake-password",
        )
        emails = client.fetch_recent_emails(
            limit=2,
            max_age_minutes=15,
            query="directory",
        )

        assert len(emails) == 1
        em = emails[0]
        assert em["subject"] == "Confirm your AI Directory registration"
        assert em["from"] == "no-reply@directory.ai"
        assert (
            "https://directory.ai/verify?token=abc123token"
            in em["verification_links"]
        )
        assert "729104" in em["verification_codes"]


def test_wait_for_verification_email_mocked():
    now_str = email.utils.format_datetime(datetime.now(timezone.utc))
    raw_msg_bytes = (
        f"From: notifications@smithery.ai\r\n"
        f"To: adam.ivansky@gmail.com\r\n"
        f"Subject: Verify your Smithery submission\r\n"
        f"Date: {now_str}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"Click to confirm: https://smithery.ai/auth/confirm?code=987654"
    ).encode("utf-8")

    mock_imap = MagicMock()
    mock_imap.select.return_value = ("OK", [b"1"])
    mock_imap.search.return_value = ("OK", [b"10"])
    mock_imap.fetch.return_value = (
        "OK",
        [(b"10 (RFC822 {100}", raw_msg_bytes)],
    )

    with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
        client = IMAPEmailClient(password="test-password")
        result = client.wait_for_verification_email(
            query="smithery",
            max_wait_seconds=5,
            poll_interval=1,
            max_age_minutes=15,
        )
        assert result is not None
        assert "smithery.ai" in result["from"]
        assert (
            "https://smithery.ai/auth/confirm?code=987654"
            in result["verification_links"]
        )


def test_langchain_email_tools_unconfigured():
    with patch.dict(os.environ, {}, clear=True):
        search_res = search_verification_emails.invoke({"query": "test"})
        assert search_res["success"] is False
        assert "IMAP credentials not configured" in search_res["error"]

        fetch_res = fetch_latest_emails.invoke({"limit": 2})
        assert fetch_res["success"] is False
        assert "IMAP credentials not configured" in fetch_res["error"]

        wait_res = wait_for_verification_email.invoke(
            {"query": "test", "max_wait_seconds": 1}
        )
        assert wait_res["success"] is False
        assert "IMAP credentials not configured" in wait_res["error"]


def test_langchain_email_tools_configured_mocked():
    now_str = email.utils.format_datetime(datetime.now(timezone.utc))
    raw_msg_bytes = (
        f"From: auth@platform.ai\r\n"
        f"To: adam.ivansky@gmail.com\r\n"
        f"Subject: Your verification pin\r\n"
        f"Date: {now_str}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"Your activation code is 554433."
    ).encode("utf-8")

    mock_imap = MagicMock()
    mock_imap.select.return_value = ("OK", [b"1"])
    mock_imap.search.return_value = ("OK", [b"42"])
    mock_imap.fetch.return_value = (
        "OK",
        [(b"42 (RFC822 {100}", raw_msg_bytes)],
    )

    with patch.dict(os.environ, {"GMAIL_APP_PASSWORD": "secret-pw"}):
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            # Test search_verification_emails
            s_res = search_verification_emails.invoke(
                {"query": "platform", "max_age_minutes": 15}
            )
            assert s_res["success"] is True
            assert s_res["count"] == 1
            assert "554433" in s_res["emails"][0]["verification_codes"]

            # Test wait_for_verification_email
            w_res = wait_for_verification_email.invoke(
                {"query": "platform", "max_wait_seconds": 5}
            )
            assert w_res["success"] is True
            assert w_res["found"] is True
            assert "554433" in w_res["email"]["verification_codes"]
