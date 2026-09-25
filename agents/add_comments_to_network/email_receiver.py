"""IMAP Email Receiver and Verification Tools for Adam Network Promotion Agent.

This module provides tools for accessing the Gmail account via IMAP (SSL)
to read recent emails, fetch verification links, and extract OTP/confirmation codes
when registering the Adam Network on external directories, registries, or platforms.
"""

from __future__ import annotations

import email
import email.header
import email.utils
from html.parser import HTMLParser
import imaplib
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

try:
    from langchain_core.tools import tool
except ImportError:
    # Graceful fallback decorator when langchain_core is not installed in the environment
    def tool(*d_args, **d_kwargs):
        def decorator(fn):
            fn.name = fn.__name__
            fn.description = fn.__doc__ or ""
            if "args_schema" in d_kwargs:
                fn.args_schema = d_kwargs["args_schema"]
            fn.invoke = lambda input_dict, **kw: fn(**input_dict)
            return fn

        if d_args and callable(d_args[0]):
            return decorator(d_args[0])
        return decorator


logger = logging.getLogger(__name__)

DEFAULT_IMAP_SERVER = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_EMAIL_USER = (
    os.getenv("GMAIL_EMAIL")
    or os.getenv("EMAIL_USER")
    or "adam.ivansky@gmail.com"
)

URL_REGEX = re.compile(
    r"https?://[^\s<>'\"{}|\\^`]+[^\s<>'\"{}|\\^`.,;:!?)\]]"
)
OTP_CODE_PATTERNS = [
    re.compile(
        r"(?:verification\s+code|confirmation\s+code|security\s+code|otp|passcode|pin|code)\s*(?:is|:|=|-)?\s*([A-Za-z0-9]{4,10})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b([0-9]{6})\b"),  # standard 6-digit OTP
    re.compile(r"\b([0-9]{4,8})\b"),  # 4-8 digit numeric codes
]

VERIFICATION_URL_KEYWORDS = [
    "verify",
    "verification",
    "confirm",
    "confirmation",
    "activate",
    "activation",
    "validate",
    "validation",
    "token=",
    "auth",
    "signup",
    "register",
    "approve",
    "magic",
    "login",
]


# ---------------------------------------------------------------------------
# HTML Parsing & Link Extraction
# ---------------------------------------------------------------------------


class _HtmlLinkExtractor(HTMLParser):
    """HTML parser to extract <a> tags with href and anchor text."""

    def __init__(self) -> None:
        super().__init__()
        self.links: List[Dict[str, str]] = []
        self._current_href: Optional[str] = None
        self._current_text: List[str] = []

    def handle_starttag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        if tag.lower() == "a":
            for attr, val in attrs:
                if attr.lower() == "href" and val:
                    self._current_href = val
                    self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href is not None:
            anchor_text = " ".join(self._current_text).strip()
            self.links.append(
                {"url": self._current_href, "text": anchor_text}
            )
            self._current_href = None
            self._current_text = []


def decode_header_value(header_val: Optional[str]) -> str:
    """Decode RFC 2047 encoded email headers."""
    if not header_val:
        return ""
    try:
        decoded_parts = email.header.decode_header(header_val)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(
                    part.decode(charset or "utf-8", errors="replace")
                )
            else:
                result.append(str(part))
        return " ".join(result).strip()
    except Exception:
        return str(header_val).strip()


def extract_email_bodies(msg: email.message.Message) -> Tuple[str, str]:
    """Extract plain text and HTML bodies from an email Message object."""
    plain_parts: List[str] = []
    html_parts: List[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

    return "\n".join(plain_parts), "\n".join(html_parts)


def extract_links(plain_text: str, html_text: str) -> List[Dict[str, Any]]:
    """Extract and prioritize URLs and verification links from email content."""
    links_seen = set()
    all_links: List[Dict[str, Any]] = []

    # 1. Parse HTML links
    if html_text:
        try:
            parser = _HtmlLinkExtractor()
            parser.feed(html_text)
            for item in parser.links:
                url = item["url"]
                if url not in links_seen and url.startswith(
                    ("http://", "https://")
                ):
                    links_seen.add(url)
                    text = item["text"]
                    is_verification = any(
                        kw in url.lower() or kw in text.lower()
                        for kw in VERIFICATION_URL_KEYWORDS
                    )
                    all_links.append(
                        {
                            "url": url,
                            "anchor_text": text,
                            "is_verification_link": is_verification,
                        }
                    )
        except Exception as exc:
            logger.debug("Failed parsing HTML links: %s", exc)

    # 2. Extract plain text links
    for url in URL_REGEX.findall(plain_text + " " + html_text):
        if url not in links_seen:
            links_seen.add(url)
            is_verification = any(
                kw in url.lower() for kw in VERIFICATION_URL_KEYWORDS
            )
            all_links.append(
                {
                    "url": url,
                    "anchor_text": "",
                    "is_verification_link": is_verification,
                }
            )

    # Sort so verification links appear first
    all_links.sort(key=lambda x: not x["is_verification_link"])
    return all_links


def extract_codes(plain_text: str, html_text: str) -> List[str]:
    """Extract potential OTP / verification codes from text."""
    combined = plain_text + "\n" + re.sub(r"<[^>]+>", " ", html_text)
    codes_found: List[str] = []
    seen = set()

    for pattern in OTP_CODE_PATTERNS:
        for match in pattern.finditer(combined):
            code = match.group(1) if match.groups() else match.group(0)
            code = code.strip()
            # Ignore common false positive numbers like 2024, 2025, 2026 (years)
            if (
                code not in seen
                and len(code) >= 4
                and not (len(code) == 4 and code.startswith("202"))
            ):
                seen.add(code)
                codes_found.append(code)

    return codes_found


# ---------------------------------------------------------------------------
# IMAP Client & Email Retrieval
# ---------------------------------------------------------------------------


class IMAPEmailClient:
    """Client for connecting to Gmail via IMAP SSL and retrieving emails."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.host = (
            host
            or os.getenv("GMAIL_IMAP_SERVER")
            or os.getenv("IMAP_SERVER")
            or DEFAULT_IMAP_SERVER
        )
        self.port = int(
            port
            or os.getenv("GMAIL_IMAP_PORT")
            or os.getenv("IMAP_PORT")
            or DEFAULT_IMAP_PORT
        )
        self.user = (
            user
            or os.getenv("GMAIL_EMAIL")
            or os.getenv("GMAIL_USER")
            or os.getenv("IMAP_USER")
            or os.getenv("EMAIL_USER")
            or DEFAULT_EMAIL_USER
        )
        self.password = (
            password
            or os.getenv("GMAIL_APP_PASSWORD")
            or os.getenv("GMAIL_PASSWORD")
            or os.getenv("IMAP_PASSWORD")
            or os.getenv("EMAIL_PASSWORD")
        )

    def is_configured(self) -> bool:
        """Check if IMAP credentials are present."""
        return bool(self.user and self.password)

    def _connect(self) -> imaplib.IMAP4_SSL:
        """Create an authenticated IMAP4_SSL connection."""
        if not self.password:
            raise ValueError(
                "IMAP password not configured. Set GMAIL_APP_PASSWORD or IMAP_PASSWORD."
            )
        imap = imaplib.IMAP4_SSL(self.host, self.port)
        imap.login(self.user, self.password)
        return imap

    def fetch_recent_emails(
        self,
        folder: str = "INBOX",
        limit: int = 5,
        max_age_minutes: Optional[int] = 30,
        query: Optional[str] = None,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch recent emails matching criteria."""
        if not self.is_configured():
            logger.warning("IMAP credentials not configured.")
            return []

        imap = self._connect()
        try:
            status, _ = imap.select(folder, readonly=True)
            if status != "OK":
                logger.error("Failed to select IMAP folder %s", folder)
                return []

            # Build search criteria
            criteria_parts = ["ALL"]
            if sender:
                criteria_parts.extend(["FROM", f'"{sender}"'])
            if subject:
                criteria_parts.extend(["SUBJECT", f'"{subject}"'])
            if query:
                criteria_parts.extend(["TEXT", f'"{query}"'])

            search_query = " ".join(criteria_parts)
            status, data = imap.search(None, search_query)
            if status != "OK" or not data or not data[0]:
                # Fallback to ALL if specific search fails
                status, data = imap.search(None, "ALL")
                if status != "OK" or not data or not data[0]:
                    return []

            msg_ids = data[0].split()
            # Most recent first
            msg_ids = msg_ids[::-1]

            results: List[Dict[str, Any]] = []
            now = datetime.now(timezone.utc)

            for mid in msg_ids:
                if len(results) >= limit:
                    break

                res, msg_data = imap.fetch(mid, "(RFC822)")
                if res != "OK" or not msg_data:
                    continue

                raw_email = None
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        raw_email = response_part[1]
                        break

                if not raw_email:
                    continue

                msg = email.message_from_bytes(raw_email)
                email_date_str = msg.get("Date", "")
                parsed_date = None
                if email_date_str:
                    try:
                        parsed_date = email.utils.parsedate_to_datetime(
                            email_date_str
                        )
                        if parsed_date.tzinfo is None:
                            parsed_date = parsed_date.replace(
                                tzinfo=timezone.utc
                            )
                    except Exception:
                        parsed_date = None

                # Check age if max_age_minutes specified
                if max_age_minutes is not None and parsed_date is not None:
                    age_seconds = (now - parsed_date).total_seconds()
                    if age_seconds > max_age_minutes * 60:
                        continue

                sub = decode_header_value(msg.get("Subject", ""))
                frm = decode_header_value(msg.get("From", ""))
                to_hdr = decode_header_value(msg.get("To", ""))
                plain, html = extract_email_bodies(msg)

                links = extract_links(plain, html)
                verification_links = [
                    l["url"] for l in links if l["is_verification_link"]
                ]
                codes = extract_codes(plain, html)

                snippet = (plain or html)[:400].replace("\n", " ").strip()

                results.append(
                    {
                        "id": mid.decode("utf-8", errors="replace"),
                        "subject": sub,
                        "from": frm,
                        "to": to_hdr,
                        "date": email_date_str,
                        "verification_links": verification_links,
                        "all_links": [l["url"] for l in links],
                        "verification_codes": codes,
                        "body_preview": snippet,
                    }
                )

            return results
        finally:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass

    def wait_for_verification_email(
        self,
        query: Optional[str] = None,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
        max_wait_seconds: int = 60,
        poll_interval: int = 5,
        max_age_minutes: int = 15,
    ) -> Optional[Dict[str, Any]]:
        """Poll IMAP inbox until a matching verification email arrives or timeout."""
        start_time = time.time()
        while time.time() - start_time < max_wait_seconds:
            emails = self.fetch_recent_emails(
                limit=5,
                max_age_minutes=max_age_minutes,
                query=query,
                sender=sender,
                subject=subject,
            )
            for em in emails:
                # If we have verification links or verification codes, or it matches the sender/query
                if em.get("verification_links") or em.get(
                    "verification_codes"
                ):
                    return em
                if query and (
                    query.lower() in em.get("subject", "").lower()
                    or query.lower() in em.get("from", "").lower()
                    or query.lower() in em.get("body_preview", "").lower()
                ):
                    return em
                if sender and sender.lower() in em.get("from", "").lower():
                    return em
            time.sleep(poll_interval)
        return None


# ---------------------------------------------------------------------------
# LangChain Tools for Agents
# ---------------------------------------------------------------------------


class SearchVerificationEmailsSchema(BaseModel):
    query: Optional[str] = Field(
        None,
        description="Search keyword to match against email body/subject (e.g. directory name like 'Smithery' or 'ProductHunt').",
    )
    sender: Optional[str] = Field(
        None,
        description="Optional sender email or domain filter (e.g. 'no-reply@smithery.ai' or 'smithery.ai').",
    )
    subject: Optional[str] = Field(
        None,
        description="Optional subject filter keyword (e.g. 'Verify', 'Confirm', 'Activation').",
    )
    max_age_minutes: int = Field(
        15,
        description="Only look for emails received within the last N minutes (default 15).",
    )


@tool(args_schema=SearchVerificationEmailsSchema)
def search_verification_emails(
    query: Optional[str] = None,
    sender: Optional[str] = None,
    subject: Optional[str] = None,
    max_age_minutes: int = 15,
) -> Dict[str, Any]:
    """Search recent emails in the Gmail account via IMAP for verification emails.

    Extracts verification/confirmation URLs, one-time passwords (OTP/codes),
    subject, sender, and snippet. Use this after submitting a registration or
    directory listing form that requires email confirmation.
    """
    client = IMAPEmailClient()
    if not client.is_configured():
        return {
            "success": False,
            "error": "IMAP credentials not configured. Please ensure GMAIL_APP_PASSWORD or IMAP_PASSWORD is set.",
            "emails": [],
        }

    try:
        results = client.fetch_recent_emails(
            limit=5,
            max_age_minutes=max_age_minutes,
            query=query,
            sender=sender,
            subject=subject,
        )
        return {
            "success": True,
            "count": len(results),
            "emails": results,
        }
    except Exception as exc:
        logger.error("Error searching verification emails: %s", exc)
        return {
            "success": False,
            "error": f"Failed to fetch emails via IMAP: {exc}",
            "emails": [],
        }


class FetchLatestEmailsSchema(BaseModel):
    limit: int = Field(
        5,
        description="Maximum number of recent emails to return (default 5).",
    )
    folder: str = Field(
        "INBOX",
        description="IMAP mailbox folder to inspect (default 'INBOX').",
    )


@tool(args_schema=FetchLatestEmailsSchema)
def fetch_latest_emails(
    limit: int = 5,
    folder: str = "INBOX",
) -> Dict[str, Any]:
    """Fetch the latest emails from the Gmail inbox via IMAP.

    Returns sender, subject, date, text snippet, extracted links, and codes for each email.
    """
    client = IMAPEmailClient()
    if not client.is_configured():
        return {
            "success": False,
            "error": "IMAP credentials not configured. Please ensure GMAIL_APP_PASSWORD or IMAP_PASSWORD is set.",
            "emails": [],
        }

    try:
        results = client.fetch_recent_emails(
            folder=folder,
            limit=limit,
            max_age_minutes=None,
        )
        return {
            "success": True,
            "count": len(results),
            "emails": results,
        }
    except Exception as exc:
        logger.error("Error fetching latest emails: %s", exc)
        return {
            "success": False,
            "error": f"Failed to fetch emails via IMAP: {exc}",
            "emails": [],
        }


class WaitForVerificationEmailSchema(BaseModel):
    query: Optional[str] = Field(
        None,
        description="Directory name or keyword to look for in the verification email (e.g. 'Glama', 'Smithery', 'verify').",
    )
    sender: Optional[str] = Field(
        None,
        description="Sender email or domain to wait for (e.g. 'glama.ai', 'noreply@').",
    )
    subject: Optional[str] = Field(
        None,
        description="Subject keyword (e.g. 'Confirm', 'Verify').",
    )
    max_wait_seconds: int = Field(
        60,
        description="Maximum seconds to poll for the email (default 60, polls every 5 seconds).",
    )


@tool(args_schema=WaitForVerificationEmailSchema)
def wait_for_verification_email(
    query: Optional[str] = None,
    sender: Optional[str] = None,
    subject: Optional[str] = None,
    max_wait_seconds: int = 60,
) -> Dict[str, Any]:
    """Poll Gmail via IMAP until a verification or confirmation email arrives.

    Use this tool right after submitting a registration or project listing form on a directory
    that sends an email confirmation. Automatically extracts confirmation URLs and OTP codes.
    """
    client = IMAPEmailClient()
    if not client.is_configured():
        return {
            "success": False,
            "error": "IMAP credentials not configured. Please ensure GMAIL_APP_PASSWORD or IMAP_PASSWORD is set.",
            "email": None,
        }

    try:
        result = client.wait_for_verification_email(
            query=query,
            sender=sender,
            subject=subject,
            max_wait_seconds=max_wait_seconds,
            poll_interval=5,
        )
        if result:
            return {
                "success": True,
                "found": True,
                "email": result,
            }
        return {
            "success": True,
            "found": False,
            "message": f"No matching verification email arrived within {max_wait_seconds} seconds.",
            "email": None,
        }
    except Exception as exc:
        logger.error("Error waiting for verification email: %s", exc)
        return {
            "success": False,
            "error": f"Failed during IMAP polling: {exc}",
            "email": None,
        }
