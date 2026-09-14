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

import nest_asyncio
from prefect import task

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langchain_core.callbacks import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from langchain_community.agent_toolkits.playwright.toolkit import (
    PlayWrightBrowserToolkit,
)
from langchain_community.tools.playwright.base import BaseBrowserTool
from langchain_community.tools.playwright.utils import (
    aget_current_page,
    create_async_playwright_browser,
)

from agents.add_comments_to_network.run_comfy_graph import (
    generate_image_from_prompt,
)

nest_asyncio.apply()

DEFAULT_MCP_URL = "https://adam-network.up.railway.app/mcp/sse"


# ---------------------------------------------------------------------------
# Custom Playwright Browser Form Interaction Tools
# ---------------------------------------------------------------------------


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
        FillInputTool(async_browser=async_browser),
        SelectOptionTool(async_browser=async_browser),
        CheckElementTool(async_browser=async_browser),
        PressKeyTool(async_browser=async_browser),
    ]

    browser_tools = [*toolkit.get_tools(), *custom_browser_tools]

    model = ChatOllama(
        model=model_name,
        temperature=0,
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

    # Add local PoW helper so the agent can solve challenges after calling get_challenge.
    tools = [
        *mcp_tools,
        *browser_tools,
        solve_pow_challenge,
        generate_and_post_image_message,
    ]

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
