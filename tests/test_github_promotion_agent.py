"""Unit tests for the GitHub Repository Scanner & PR Promotion Agent."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agents.add_comments_to_network.github_scanner import (
    GitHubClient,
    detect_agent_framework,
    generate_adam_integration,
    inspect_github_repository,
    search_github_ai_agent_repos,
    create_github_issue_or_discussion,
    submit_github_pr_or_fork,
    search_agent_repositories,
    inspect_agent_repository,
    generate_adam_integration_proposal,
    submit_github_integration_pr,
    submit_github_issue_or_discussion as submit_issue_tool,
)


def test_github_client_init():
    client = GitHubClient(token="test-token-123")
    assert client.token == "test-token-123"
    assert client.headers["Authorization"] == "Bearer test-token-123"
    assert "User-Agent" in client.headers


def test_detect_agent_framework():
    # LangChain detection
    assert (
        detect_agent_framework(
            description="Autonomous agent built with langchain",
            topics=["agents", "langchain"],
            dependency_text="langchain>=0.2.0\nlanggraph",
            language="Python",
        )
        == "langchain"
    )

    # CrewAI detection
    assert (
        detect_agent_framework(
            description="Multi-agent role-playing system",
            topics=["crewai", "multi-agent"],
            dependency_text="crewai>=0.50.0",
            language="Python",
        )
        == "crewai"
    )

    # AutoGen detection
    assert (
        detect_agent_framework(
            description="Multi-agent conversation framework",
            topics=["autogen", "llm"],
            dependency_text="pyautogen>=0.2.0",
            language="Python",
        )
        == "autogen"
    )

    # LlamaIndex detection
    assert (
        detect_agent_framework(
            description="Data framework for LLM applications",
            topics=["rag", "llama-index"],
            dependency_text="llama-index-core",
            language="Python",
        )
        == "llama-index"
    )

    # MCP detection
    assert (
        detect_agent_framework(
            description="MCP server implementation for tools",
            topics=["mcp-server", "model-context-protocol"],
            dependency_text="mcp>=1.0.0",
            language="Python",
        )
        == "mcp"
    )

    # ElizaOS detection
    assert (
        detect_agent_framework(
            description="Autonomous agent character runtime",
            topics=["eliza", "crypto-agents"],
            dependency_text="@elizaos/core",
            language="TypeScript",
        )
        == "elizaos"
    )

    # General fallback
    assert (
        detect_agent_framework(
            description="Generic script",
            topics=["bot"],
            dependency_text="",
            language="Python",
        )
        == "general_python"
    )


def test_generate_adam_integration_templates():
    frameworks = [
        "langchain",
        "crewai",
        "autogen",
        "llama-index",
        "mcp",
        "elizaos",
        "general_python",
    ]
    for fw in frameworks:
        proposal = generate_adam_integration(
            framework=fw, repo_name="example-org/sample-agent"
        )
        assert proposal["file_path"]
        assert proposal["file_content"]
        assert proposal["title"]
        assert proposal["body"]
        assert proposal["framework"] == fw
        assert "Adam Network" in proposal["body"]


def test_search_github_ai_agent_repos_mocked():
    mock_gh = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "items": [
            {
                "full_name": "test-org/ai-agent",
                "name": "ai-agent",
                "owner": {"login": "test-org"},
                "html_url": "https://github.com/test-org/ai-agent",
                "description": "An awesome LangChain agent",
                "stargazers_count": 120,
                "language": "Python",
                "topics": ["langchain", "agents"],
                "default_branch": "main",
            }
        ]
    }
    mock_gh.get.return_value = mock_response

    results = search_github_ai_agent_repos(limit=2, client=mock_gh)
    assert len(results) == 1
    assert results[0]["full_name"] == "test-org/ai-agent"
    assert results[0]["stars"] == 120


def test_inspect_github_repository_mocked():
    mock_gh = MagicMock()

    def mock_get(endpoint, params=None):
        res = MagicMock()
        if endpoint == "/repos/test-org/ai-agent":
            res.status_code = 200
            res.json.return_value = {
                "name": "ai-agent",
                "owner": {"login": "test-org"},
                "description": "LangChain autonomous agent",
                "topics": ["langchain", "agent"],
                "default_branch": "main",
                "language": "Python",
            }
        elif endpoint == "/repos/test-org/ai-agent/contents":
            res.status_code = 200
            res.json.return_value = [{"name": "requirements.txt"}]
        elif endpoint == "/repos/test-org/ai-agent/contents/requirements.txt":
            res.status_code = 200
            res.json.return_value = {
                "content": "bGFuZ2NoYWluPj0wLjIuMA=="  # base64 for "langchain>=0.2.0"
            }
        else:
            res.status_code = 404
        return res

    mock_gh.get.side_effect = mock_get

    info = inspect_github_repository(
        repo_full_name="test-org/ai-agent", client=mock_gh
    )
    assert info["full_name"] == "test-org/ai-agent"
    assert info["framework"] == "langchain"


def test_submit_github_pr_dry_run():
    res = submit_github_pr_or_fork(
        repo_full_name="test-org/sample-agent",
        file_path="examples/adam_network_integration.py",
        file_content="# Test integration",
        title="feat: test",
        body="Test body",
        dry_run=True,
    )
    assert res["success"] is True
    assert res["mode"] == "dry_run"
    assert "simulate" in res["pr_url"]


def test_submit_github_issue_dry_run():
    res = create_github_issue_or_discussion(
        repo_full_name="test-org/sample-agent",
        title="feat: proposal",
        body="Proposal body",
        dry_run=True,
    )
    assert res["success"] is True
    assert res["mode"] == "dry_run"
    assert "simulate" in res["issue_url"]

    # Test via tool
    tool_res = submit_issue_tool.invoke(
        {
            "repo_name": "test-org/sample-agent",
            "title": "feat: proposal",
            "body": "Proposal body",
            "dry_run": True,
        }
    )
    assert tool_res["success"] is True
    assert tool_res["mode"] == "dry_run"


def test_agent_prompt_and_memory_files_exist():
    base_dir = (
        Path(__file__).resolve().parent.parent
        / "agents"
        / "add_comments_to_network"
        / "prompts"
        / "github_pr_promotion_agent"
    )
    assert (base_dir / "sys_prompt.md").exists()
    assert (base_dir / "user_prompt.md").exists()
    assert (base_dir / "agent_memory" / "AGENTS.md").exists()

    sys_text = (base_dir / "sys_prompt.md").read_text()
    assert "Adam Network" in sys_text
    assert "search_agent_repositories" in sys_text


def test_langchain_tools_schema():
    assert search_agent_repositories.name == "search_agent_repositories"
    assert inspect_agent_repository.name == "inspect_agent_repository"
    assert (
        generate_adam_integration_proposal.name
        == "generate_adam_integration_proposal"
    )
    assert submit_github_integration_pr.name == "submit_github_integration_pr"
    assert submit_issue_tool.name == "submit_github_issue_or_discussion"


def test_promotion_agent_prompt_and_memory_files():
    base_dir = (
        Path(__file__).resolve().parent.parent
        / "agents"
        / "add_comments_to_network"
        / "prompts"
        / "promotion_agent"
    )
    assert (base_dir / "sys_prompt.md").exists()
    assert (base_dir / "user_prompt.md").exists()
    assert (base_dir / "agent_memory" / "AGENTS.md").exists()

    sys_text = (base_dir / "sys_prompt.md").read_text()
    assert "Adam Network" in sys_text
    assert "adam.ivansky@gmail.com" in sys_text
    assert "wait_for_verification_email" in sys_text
    assert "search_verification_emails" in sys_text

    user_text = (base_dir / "user_prompt.md").read_text()
    assert (
        "wait_for_verification_email" in user_text
        or "search_verification_emails" in user_text
    )


def test_navigate_page_tool_timeout_resilience():
    import asyncio
    from unittest.mock import AsyncMock
    from agents.add_comments_to_network.tasks import NavigatePageTool

    mock_page = AsyncMock()
    mock_page.goto.side_effect = Exception(
        "Page.goto: Timeout 30000ms exceeded."
    )
    mock_page.url = "https://mcphub.com/"
    mock_page.title.return_value = "MCPHub - MCP Server Directory"

    mock_browser = AsyncMock()
    with patch(
        "agents.add_comments_to_network.tasks._safe_get_current_page",
        new=AsyncMock(return_value=mock_page),
    ):
        tool = NavigatePageTool(async_browser=mock_browser)
        result = asyncio.run(tool._arun(url="https://mcphub.com/"))
        assert "mcphub.com" in result
        assert "MCPHub - MCP Server Directory" in result


def test_click_element_tool_resilience():
    import asyncio
    from unittest.mock import AsyncMock
    from agents.add_comments_to_network.tasks import ClickElementTool

    mock_page = AsyncMock()
    mock_page.click.side_effect = Exception("Timeout waiting for selector")
    mock_locator = AsyncMock()
    mock_locator.first.click.side_effect = Exception("Element not found")
    mock_page.get_by_text.return_value = mock_locator
    mock_page.evaluate.side_effect = Exception("Evaluation failed")

    mock_browser = AsyncMock()
    with patch(
        "agents.add_comments_to_network.tasks._safe_get_current_page",
        new=AsyncMock(return_value=mock_page),
    ):
        tool = ClickElementTool(async_browser=mock_browser)
        result = asyncio.run(tool._arun(selector="#non-existent"))
        assert "Failed to click element" in result


def test_make_tool_safe_wrapper():
    import asyncio
    from agents.add_comments_to_network.tasks import _make_tool_safe

    class FlakyTool:
        name = "test_flaky_tool"

        async def _arun(self, *args, **kwargs):
            raise RuntimeError("Connection timeout")

    mock_tool = FlakyTool()
    safe_tool = _make_tool_safe(mock_tool)
    assert safe_tool.handle_tool_error is True

    result = asyncio.run(safe_tool._arun(param="value"))
    assert "test_flaky_tool" in result
    assert "Connection timeout" in result
