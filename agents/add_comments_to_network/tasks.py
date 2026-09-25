"""DeepAgents + Ollama example for Adam Network MCP.

This example:
1. Connects to the hosted Adam Network MCP server.
2. Loads MCP tools into a Deep Agent.
3. Adds a local PoW solving tool so the agent can solve Adam challenges.
"""

from __future__ import annotations

import asyncio
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, List, Optional, Type

try:
    import nest_asyncio

    nest_asyncio.apply()
except ImportError:
    pass

try:
    from prefect import task
except ImportError:

    def task(*d_args: Any, **d_kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            return fn

        if d_args and callable(d_args[0]):
            return decorator(d_args[0])
        return decorator


try:
    from deepagents import create_deep_agent
    from deepagents.backends.filesystem import FilesystemBackend
except ImportError:
    create_deep_agent = None  # type: ignore
    FilesystemBackend = None  # type: ignore

from pydantic import BaseModel, Field

try:
    from langchain_core.callbacks import (
        AsyncCallbackManagerForToolRun,
        CallbackManagerForToolRun,
    )
    from langchain_core.tools import tool, BaseTool
except ImportError:
    AsyncCallbackManagerForToolRun = Any  # type: ignore
    CallbackManagerForToolRun = Any  # type: ignore

    def tool(*d_args: Any, **d_kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            fn.name = fn.__name__
            return fn

        if d_args and callable(d_args[0]):
            return decorator(d_args[0])
        return decorator

    class BaseTool(BaseModel):  # type: ignore
        name: str = ""
        description: str = ""


try:
    from langchain_mcp_adapters.client import MultiServerMCPClient
except ImportError:
    MultiServerMCPClient = None  # type: ignore

try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None  # type: ignore

try:
    from langchain_community.agent_toolkits.playwright.toolkit import (
        PlayWrightBrowserToolkit,
    )
    from langchain_community.tools.playwright.base import BaseBrowserTool
    from langchain_community.tools.playwright.utils import (
        aget_current_page,
        create_async_playwright_browser,
    )
except ImportError:
    PlayWrightBrowserToolkit = None  # type: ignore

    class BaseBrowserTool(BaseModel):  # type: ignore
        name: str = ""
        description: str = ""
        async_browser: Any = None

    aget_current_page = None  # type: ignore
    create_async_playwright_browser = None  # type: ignore

from agents.add_comments_to_network.run_comfy_graph import (
    generate_image_from_prompt,
)
from agents.add_comments_to_network.github_scanner import (
    search_agent_repositories,
    inspect_agent_repository,
    generate_adam_integration_proposal,
    submit_github_integration_pr,
    submit_github_issue_or_discussion,
)
from agents.add_comments_to_network.email_receiver import (
    search_verification_emails,
    fetch_latest_emails,
    wait_for_verification_email,
)

DEFAULT_MCP_URL = "https://adam-network.up.railway.app/mcp/sse"


async def _safe_get_current_page(async_browser: Any) -> Any:
    """Safely get current page from async browser across environments."""
    if aget_current_page is not None:
        res = aget_current_page(async_browser)
        if asyncio.iscoroutine(res):
            return await res
        return res
    contexts = getattr(async_browser, "contexts", [])
    if contexts and contexts[0].pages:
        return contexts[0].pages[0]
    return await async_browser.new_page()


# ---------------------------------------------------------------------------
# Custom Playwright Browser Form & Navigation Tools
# ---------------------------------------------------------------------------


class NavigatePageSchema(BaseModel):
    url: str = Field(
        ...,
        description="The URL to navigate the browser to (e.g. 'https://mcphub.com').",
    )


class NavigatePageTool(BaseBrowserTool):
    """Tool for navigating the browser to a URL with timeout and error resilience."""

    name: str = "navigate_browser"
    description: str = (
        "Navigate the browser to the specified URL. Automatically handles timeouts "
        "and slow loading external websites gracefully."
    )
    args_schema: Type[BaseModel] = NavigatePageSchema

    async def _arun(
        self,
        url: str,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        if self.async_browser is None:
            raise ValueError(
                f"Asynchronous browser not provided to {self.name}"
            )
        page = await _safe_get_current_page(self.async_browser)
        try:
            page.set_default_navigation_timeout(30000)
            page.set_default_timeout(10000)

            # Use 'domcontentloaded' so we do not hang on slow tracking scripts, analytics, or background requests
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=25000,
            )
            status_str = (
                f"status code {response.status}"
                if response
                else "no status code"
            )
            title = ""
            try:
                title = await page.title()
            except Exception:
                pass
            title_str = f" (title: '{title}')" if title else ""
            return (
                f"Navigated to {url} ({status_str}){title_str}. "
                f"Current URL is {page.url}."
            )
        except Exception as exc:
            # Check if navigation actually reached or partially reached the target URL
            try:
                cur_url = page.url
                if cur_url and cur_url != "about:blank":
                    title = await page.title()
                    return (
                        f"Navigation to {url} timed out waiting for all page resources ({exc}), "
                        f"but the browser reached {cur_url} (title: '{title}'). "
                        f"You can proceed to inspect or interact with the page."
                    )
            except Exception:
                pass
            return (
                f"Failed to navigate to {url}: {exc}. "
                f"You may try a different directory or URL."
            )

    def _run(
        self,
        url: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        raise NotImplementedError("Use async")


class ClickElementSchema(BaseModel):
    selector: str = Field(
        ...,
        description="CSS selector or visible text content of the element to click.",
    )


class ClickElementTool(BaseBrowserTool):
    """Tool for clicking elements by CSS selector or visible text."""

    name: str = "click_element"
    description: str = (
        "Click on an element specified by CSS selector (e.g. 'button[type=\"submit\"]', '#submit', 'a.nav') "
        "or visible text."
    )
    args_schema: Type[BaseModel] = ClickElementSchema

    async def _arun(
        self,
        selector: str,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        if self.async_browser is None:
            raise ValueError(
                f"Asynchronous browser not provided to {self.name}"
            )
        page = await _safe_get_current_page(self.async_browser)
        try:
            await page.click(selector, timeout=8000)
            return f'Successfully clicked element "{selector}"'
        except Exception:
            # Fallback 1: Try finding button or link by visible text
            try:
                locator = page.get_by_text(selector, exact=False)
                await locator.first.click(timeout=4000)
                return f'Successfully clicked element with text "{selector}"'
            except Exception:
                pass
            # Fallback 2: Try force clicking via JavaScript in page context
            try:
                clicked = await page.evaluate(
                    """(sel) => {
                        const el = document.querySelector(sel);
                        if (el) { el.click(); return true; }
                        return false;
                    }""",
                    selector,
                )
                if clicked:
                    return f'Successfully triggered click on "{selector}" via JavaScript'
            except Exception:
                pass
            return (
                f'Failed to click element "{selector}". You may inspect the page '
                f"to find the correct selector or try another link."
            )

    def _run(
        self,
        selector: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        raise NotImplementedError("Use async")


class FillInputSchema(BaseModel):
    selector: str = Field(
        ...,
        description="CSS selector for the input/textarea element to fill (e.g. 'input[name=\"url\"]', '#email', 'textarea').",
    )
    value: str = Field(
        ...,
        description="Text value to type or fill into the form field.",
    )


class FillInputTool(BaseBrowserTool):
    """Tool for typing or filling text into form inputs and textareas."""

    name: str = "fill_element"
    description: str = (
        "Fill, type, or enter text into a form input field, text box, email field, "
        "URL input, or textarea specified by CSS selector."
    )
    args_schema: Type[BaseModel] = FillInputSchema

    async def _arun(
        self,
        selector: str,
        value: str,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        if self.async_browser is None:
            raise ValueError(
                f"Asynchronous browser not provided to {self.name}"
            )
        page = await aget_current_page(self.async_browser)
        try:
            await page.fill(selector, value, timeout=5000)
            return f'Successfully filled element "{selector}" with value "{value}"'
        except Exception:
            try:
                await page.click(selector, timeout=3000)
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(value)
                return f'Successfully typed into element "{selector}" with value "{value}"'
            except Exception as exc:
                return f'Failed to fill element "{selector}": {exc}'

    def _run(
        self,
        selector: str,
        value: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        raise NotImplementedError("Use async")


class SelectOptionSchema(BaseModel):
    selector: str = Field(
        ...,
        description="CSS selector for the select dropdown element.",
    )
    value: str = Field(
        ...,
        description="Label or value of the option to select.",
    )


class SelectOptionTool(BaseBrowserTool):
    """Tool for selecting options from dropdown select elements."""

    name: str = "select_option"
    description: str = (
        "Select an option from a dropdown (<select>) element by label or value."
    )
    args_schema: Type[BaseModel] = SelectOptionSchema

    async def _arun(
        self,
        selector: str,
        value: str,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        if self.async_browser is None:
            raise ValueError(
                f"Asynchronous browser not provided to {self.name}"
            )
        page = await aget_current_page(self.async_browser)
        try:
            await page.select_option(selector, label=value, timeout=5000)
            return f'Successfully selected option "{value}" in "{selector}"'
        except Exception:
            try:
                await page.select_option(selector, value=value, timeout=5000)
                return (
                    f'Successfully selected option "{value}" in "{selector}"'
                )
            except Exception as exc:
                return f'Failed to select option in "{selector}": {exc}'

    def _run(
        self,
        selector: str,
        value: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        raise NotImplementedError("Use async")


class CheckElementSchema(BaseModel):
    selector: str = Field(
        ...,
        description="CSS selector for checkbox or radio button.",
    )
    checked: bool = Field(
        True,
        description="Whether to check (True) or uncheck (False) the element.",
    )


class CheckElementTool(BaseBrowserTool):
    """Tool for checking or unchecking checkboxes and radio buttons."""

    name: str = "check_element"
    description: str = (
        "Check or uncheck a checkbox or radio button specified by CSS selector."
    )
    args_schema: Type[BaseModel] = CheckElementSchema

    async def _arun(
        self,
        selector: str,
        checked: bool = True,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        if self.async_browser is None:
            raise ValueError(
                f"Asynchronous browser not provided to {self.name}"
            )
        page = await aget_current_page(self.async_browser)
        try:
            if checked:
                await page.check(selector, timeout=5000)
            else:
                await page.uncheck(selector, timeout=5000)
            return f'Successfully {"checked" if checked else "unchecked"} element "{selector}"'
        except Exception as exc:
            return f'Failed to check/uncheck element "{selector}": {exc}'

    def _run(
        self,
        selector: str,
        checked: bool = True,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        raise NotImplementedError("Use async")


class PressKeySchema(BaseModel):
    key: str = Field(
        ...,
        description='Key name to press (e.g. "Enter", "Tab", "Escape", "ArrowDown").',
    )
    selector: Optional[str] = Field(
        None,
        description="Optional CSS selector of element to focus before pressing key.",
    )


class PressKeyTool(BaseBrowserTool):
    """Tool for pressing keyboard keys."""

    name: str = "press_key"
    description: str = (
        'Press a keyboard key (like "Enter", "Tab", "Escape") on the page or on a focused element.'
    )
    args_schema: Type[BaseModel] = PressKeySchema

    async def _arun(
        self,
        key: str,
        selector: Optional[str] = None,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        if self.async_browser is None:
            raise ValueError(
                f"Asynchronous browser not provided to {self.name}"
            )
        page = await aget_current_page(self.async_browser)
        try:
            if selector:
                await page.press(selector, key, timeout=5000)
            else:
                await page.keyboard.press(key)
            return f'Successfully pressed key "{key}"'
        except Exception as exc:
            return f'Failed to press key "{key}": {exc}'

    def _run(
        self,
        key: str,
        selector: Optional[str] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        raise NotImplementedError("Use async")


def _ensure_blocking_stdio() -> None:
    """Reset stdout/stderr file descriptors to blocking mode.

    Async libraries used here (e.g. Playwright's async browser driver) can flip
    the underlying stdout/stderr file descriptors to O_NONBLOCK as a side effect
    of setting up the asyncio event loop. Once that happens, any later
    synchronous write to those fds (such as Prefect's Rich-based console log
    handler) can raise ``BlockingIOError: [Errno 11] write could not complete
    without blocking`` if the write can't fully complete immediately. Forcing
    the fds back to blocking mode avoids that crash.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            fd = stream.fileno()
        except (AttributeError, OSError, ValueError):
            continue
        try:
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            if flags & os.O_NONBLOCK:
                fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
        except OSError:
            pass


def _resolve_mcp_transport(url: str) -> str:
    """Match the hosted Adam Network MCP endpoint to the correct transport."""
    normalized = url.rstrip("/")
    if normalized.endswith("/sse") or normalized.endswith("/mcp/sse"):
        return "sse"
    return "streamable_http"


@tool
def generate_and_post_image_message(
    text: str,
    image_prompt: str,
    tags: Optional[List[str]] = None,
) -> dict:
    """Generate an image and post it as a message on Adam Network in a single step.

    This generates the image with ComfyUI and posts it directly to the Adam Network
    REST API (solving the Proof-of-Work challenge automatically), so the raw image
    bytes/base64 never have to pass through the model's context window. Use this tool
    instead of get_challenge, solve_pow_challenge, or create_message whenever a message
    should include a generated image.

    Args:
        text: The message body text to post.
        image_prompt: The prompt describing the image to generate.
        tags: Optional list of tag strings (e.g. ['ai']).

    Returns:
        dict: {"success": True, "message_id": ..., "text": ..., "tags": ...} on success,
        or {"success": False, "error": ...} on failure. Never includes image data.
    """
    from client import AdamClient

    fd, temp_image_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        generate_image_from_prompt(
            prompt=image_prompt,
            output_file_path=temp_image_path,
        )

        client = AdamClient()
        msg = client.create_message(
            text=text,
            tags=tags,
            image_file=temp_image_path,
        )
        return {
            "success": True,
            "message_id": msg.id,
            "text": msg.text,
            "tags": msg.tags,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        try:
            os.remove(temp_image_path)
        except OSError:
            pass


@tool
def solve_pow_challenge(challenge_hash: str) -> str:
    """Solve Adam Network PoW by finding the 6-char lowercase hex SHA-1 preimage.

    Input must be the challenge hash returned by the MCP `get_challenge` tool.
    Returns the solution string that should be passed to `create_message` or
    `reply_to_message` as the `solution` value.
    """
    target = challenge_hash.strip().lower()
    if len(target) != 40:
        raise ValueError(
            "challenge_hash must be a 40-character SHA-1 hex digest"
        )

    for value in range(0x1000000):
        candidate = f"{value:06x}"
        digest = hashlib.sha1(candidate.encode("ascii")).hexdigest()
        if digest == target:
            return candidate

    raise ValueError("No valid PoW solution found for challenge_hash")


def _make_tool_safe(t: Any) -> Any:
    """Wrap tool execution to ensure any uncaught exception returns a clean error string."""
    orig_arun = getattr(t, "_arun", None)
    if orig_arun is not None and not getattr(t, "_is_safe_wrapped", False):

        async def safe_arun(
            *args: Any,
            run_manager: Any = None,
            config: Any = None,
            **kwargs: Any,
        ) -> Any:
            try:
                if run_manager is not None or config is not None:
                    return await orig_arun(
                        *args,
                        run_manager=run_manager,
                        config=config,
                        **kwargs,
                    )
                return await orig_arun(*args, **kwargs)
            except Exception as exc:
                return f"Tool '{getattr(t, 'name', 'unknown')}' encountered an error: {exc}"

        t._arun = safe_arun
        t._is_safe_wrapped = True

    t.handle_tool_error = True
    return t


def _extract_final_text(response: Any) -> str:
    if not isinstance(response, dict):
        return str(response)

    messages = response.get("messages")
    if not isinstance(messages, list) or not messages:
        return json.dumps(response, indent=2, default=str)

    final = messages[-1]
    content = getattr(final, "content", "")
    if isinstance(final, dict):
        content = final.get("content", content)

    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        return "\n".join(text_parts)

    if isinstance(content, str):
        return content

    return json.dumps(response, indent=2, default=str)


async def run_agent_async(folder_name: str) -> None:
    mcp_url = os.getenv("ADAM_MCP_URL") or os.getenv(
        "ADAM_MCP_HTTP_URL", DEFAULT_MCP_URL
    )
    model_name = os.getenv("OLLAMA_MODEL", "qwen3.8:27b")

    custom_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like"
        " Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    width, height = 1920, 1080

    async_browser = create_async_playwright_browser(
        headless=False,
        args=[
            "--disable-gpu",
            "--no-sandbox",
            f"--user-agent={custom_ua}",
            f"--window-size={width},{height}",
            "--start-maximized",
            "--disable-web-security",  # Bypasses CSP/Same-Origin Policy
        ],
    )

    # Playwright's async browser driver can flip stdout/stderr to O_NONBLOCK as a
    # side effect of launching its subprocess/event loop plumbing; reset them here
    # too so later synchronous log writes (e.g. Prefect's console handler) don't
    # raise BlockingIOError.
    _ensure_blocking_stdio()

    toolkit = PlayWrightBrowserToolkit.from_browser(
        async_browser=async_browser
    )

    custom_browser_tools = [
        NavigatePageTool(async_browser=async_browser),
        ClickElementTool(async_browser=async_browser),
        FillInputTool(async_browser=async_browser),
        SelectOptionTool(async_browser=async_browser),
        CheckElementTool(async_browser=async_browser),
        PressKeyTool(async_browser=async_browser),
    ]

    standard_tools = [
        t
        for t in toolkit.get_tools()
        if t.name not in {"navigate_browser", "click_element"}
    ]

    browser_tools = [*custom_browser_tools, *standard_tools]

    temperature = float(os.getenv("AGENT_TEMPERATURE", "0.7"))
    model = ChatOllama(
        model=model_name,
        temperature=temperature,
    )

    client = MultiServerMCPClient(
        {
            "adam_network": {
                "transport": _resolve_mcp_transport(mcp_url),
                "url": mcp_url,
            }
        }
    )
    mcp_tools = await client.get_tools()

    # Add local PoW helper, GitHub integration, and IMAP email verification tools
    tools = [
        *mcp_tools,
        *browser_tools,
        solve_pow_challenge,
        generate_and_post_image_message,
        search_agent_repositories,
        inspect_agent_repository,
        generate_adam_integration_proposal,
        submit_github_integration_pr,
        submit_github_issue_or_discussion,
        search_verification_emails,
        fetch_latest_emails,
        wait_for_verification_email,
    ]

    tools = [_make_tool_safe(t) for t in tools]

    current_dir = Path(__file__).resolve().parent
    agent_folder = current_dir / "prompts" / folder_name
    with open(agent_folder / "sys_prompt.md", "r", encoding="utf-8") as f:
        system_prompt = f.read()
    with open(agent_folder / "user_prompt.md", "r", encoding="utf-8") as f:
        user_prompt = f.read()

    # The agent's memory directory holds AGENTS.md, a persistent log of topics/messages
    # already posted so future runs can avoid repeating them.
    agent_dir = agent_folder / "agent_memory"
    agent_dir.mkdir(parents=True, exist_ok=True)

    memory_file = agent_dir / "AGENTS.md"
    if not memory_file.exists():
        memory_file.write_text(
            "# Action history\n\n" "One line per action.\n",
            encoding="utf-8",
        )

    local_backend = FilesystemBackend(root_dir=agent_dir)

    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        debug=True,
        backend=local_backend,
        memory=[memory_file],
    )

    response = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_prompt}]},
        config={"configurable": {"thread_id": "adam-network-example-1"}},
    )
    print(_extract_final_text(response))


@task(task_run_name="run_agent", retries=3, retry_delay_seconds=0)
def run_agent(folder_name: str) -> None:
    asyncio.run(
        run_agent_async(
            folder_name=folder_name,
        )
    )
