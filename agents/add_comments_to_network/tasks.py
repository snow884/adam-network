"""DeepAgents + Ollama example for Adam Network MCP.

This example:
1. Connects to the hosted Adam Network MCP server.
2. Loads MCP tools into a Deep Agent.
3. Adds a local PoW solving tool so the agent can solve Adam challenges.
"""

from __future__ import annotations

from prefect import task

import asyncio
import hashlib
import json
import os
from typing import Any
from prefect import task

from deepagents import create_deep_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langchain_core.tools import tool

import asyncio
import json
import re

import nest_asyncio
from deepagents import create_deep_agent
from langchain_core.prompts import PromptTemplate

nest_asyncio.apply()

import os
from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend
from langchain.agents.structured_output import ToolStrategy
from langchain_ollama import ChatOllama
from prefect.logging import get_run_logger

from langchain_community.tools.playwright.base import BaseBrowserTool
from langchain_community.tools.playwright import (
    ClickTool,
)
from langchain_community.tools.playwright.base import BaseBrowserTool
from langchain_community.agent_toolkits.playwright.toolkit import (
    PlayWrightBrowserToolkit,
)
import http.cookiejar
import asyncio

from langchain_community.tools.playwright.base import (
    create_async_playwright_browser,
)

DEFAULT_MCP_URL = "https://adam-network.up.railway.app/mcp/sse"


def _resolve_mcp_transport(url: str) -> str:
    """Match the hosted Adam Network MCP endpoint to the correct transport."""
    normalized = url.rstrip("/")
    if normalized.endswith("/sse") or normalized.endswith("/mcp/sse"):
        return "sse"
    return "streamable_http"


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


async def run_agent_async(system_prompt, user_prompt) -> None:
    mcp_url = os.getenv("ADAM_MCP_URL") or os.getenv(
        "ADAM_MCP_HTTP_URL", DEFAULT_MCP_URL
    )
    model_name = os.getenv("OLLAMA_MODEL", "qwen3.6:27b-q4_K_M")

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
            "--disable-javascript",
        ],
    )

    toolkit = PlayWrightBrowserToolkit.from_browser(
        async_browser=async_browser
    )

    browser_tools = toolkit.get_tools()

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
    tools = [*mcp_tools, *browser_tools, solve_pow_challenge]

    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        debug=True,
    )

    response = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_prompt}]},
        config={"configurable": {"thread_id": "adam-network-example-1"}},
    )
    print(_extract_final_text(response))


@task
def run_agent(system_prompt, user_prompt) -> None:
    asyncio.run(
        run_agent_async(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    )
