"""GitHub Repository Scanner & PR Agent for Adam Network.

This module searches GitHub for open-source AI agent projects (MCP, LangChain,
CrewAI, AutoGen, LlamaIndex, ElizaOS, etc.), analyzes their repository structure,
and automatically generates and proposes example integrations showing how their
agents can interact on the Adam Network.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx
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

GITHUB_API_URL = "https://api.github.com"
DEFAULT_ADAM_BASE_URL = "https://adam-network.up.railway.app"
DEFAULT_ADAM_MCP_URL = "https://adam-network.up.railway.app/mcp/sse"
ADAM_GITHUB_REPO = "https://github.com/snow884/adam-network"


# ---------------------------------------------------------------------------
# GitHub REST API Helper
# ---------------------------------------------------------------------------


class GitHubClient:
    """Lightweight GitHub API client using httpx."""

    def __init__(self, token: Optional[str] = None):
        self.token = (
            token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        )
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Adam-Network-Promotion-Agent/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        url = (
            f"{GITHUB_API_URL}{endpoint}"
            if endpoint.startswith("/")
            else endpoint
        )
        with httpx.Client(timeout=30.0) as client:
            return client.get(url, headers=self.headers, params=params)

    def post(
        self, endpoint: str, json_data: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        url = (
            f"{GITHUB_API_URL}{endpoint}"
            if endpoint.startswith("/")
            else endpoint
        )
        with httpx.Client(timeout=30.0) as client:
            return client.post(url, headers=self.headers, json=json_data)

    def put(
        self, endpoint: str, json_data: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        url = (
            f"{GITHUB_API_URL}{endpoint}"
            if endpoint.startswith("/")
            else endpoint
        )
        with httpx.Client(timeout=30.0) as client:
            return client.put(url, headers=self.headers, json=json_data)

    def get_authenticated_user(self) -> Optional[str]:
        if not self.token:
            return None
        res = self.get("/user")
        if res.status_code == 200:
            return res.json().get("login")
        return None


# ---------------------------------------------------------------------------
# Repository Scanner & Analyzer
# ---------------------------------------------------------------------------


def search_github_ai_agent_repos(
    query: Optional[str] = None,
    limit: int = 5,
    client: Optional[GitHubClient] = None,
) -> List[Dict[str, Any]]:
    """Search GitHub for active open-source AI agent repositories."""
    gh = client or GitHubClient()

    search_queries = [
        query
        or "topic:mcp-server OR topic:model-context-protocol language:python",
        "topic:langchain agent language:python",
        "topic:autogen OR topic:crewai language:python",
        "topic:ai-agents agent framework stars:>10",
        "mcp client agent language:python",
    ]

    selected_query = query or search_queries[0]
    params = {
        "q": f"{selected_query} is:public archived:false",
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 30),
    }

    try:
        res = gh.get("/search/repositories", params=params)
        if res.status_code != 200:
            return []

        data = res.json()
        items = data.get("items", [])
        results = []
        for item in items[:limit]:
            results.append(
                {
                    "full_name": item.get("full_name"),
                    "name": item.get("name"),
                    "owner": item.get("owner", {}).get("login"),
                    "html_url": item.get("html_url"),
                    "description": item.get("description") or "",
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language") or "Python",
                    "topics": item.get("topics", []),
                    "default_branch": item.get("default_branch", "main"),
                }
            )
        return results
    except Exception as exc:
        logger.warning(f"Error searching GitHub repos: {exc}")
        return []


def inspect_github_repository(
    repo_full_name: str,
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Inspect repository files and topics to determine its framework and architecture."""
    gh = client or GitHubClient()

    repo_res = gh.get(f"/repos/{repo_full_name}")
    if repo_res.status_code != 200:
        return {
            "error": f"Repository '{repo_full_name}' not found or inaccessible (HTTP {repo_res.status_code})"
        }

    repo_data = repo_res.json()
    description = repo_data.get("description") or ""
    topics = repo_data.get("topics", [])
    default_branch = repo_data.get("default_branch", "main")
    language = repo_data.get("language") or "Python"

    # Inspect file tree root
    contents_res = gh.get(f"/repos/{repo_full_name}/contents")
    file_names = []
    if contents_res.status_code == 200 and isinstance(
        contents_res.json(), list
    ):
        file_names = [f.get("name", "") for f in contents_res.json()]

    # Fetch dependency files if present
    dependency_text = ""
    for dep_file in [
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "setup.py",
        "Pipfile",
    ]:
        if dep_file in file_names:
            file_res = gh.get(f"/repos/{repo_full_name}/contents/{dep_file}")
            if file_res.status_code == 200:
                content_b64 = file_res.json().get("content", "")
                try:
                    dependency_text += "\n" + base64.b64decode(
                        content_b64
                    ).decode("utf-8", errors="ignore")
                except Exception:
                    pass

    # Detect framework
    framework = detect_agent_framework(
        description=description,
        topics=topics,
        dependency_text=dependency_text,
        language=language,
    )

    return {
        "full_name": repo_full_name,
        "name": repo_data.get("name"),
        "owner": repo_data.get("owner", {}).get("login"),
        "description": description,
        "topics": topics,
        "language": language,
        "default_branch": default_branch,
        "files": file_names,
        "framework": framework,
    }


def detect_agent_framework(
    description: str,
    topics: List[str],
    dependency_text: str,
    language: str = "Python",
) -> str:
    """Infer framework (langchain, crewai, autogen, llama-index, mcp, eliza, general)."""
    text_corpus = (
        f"{description} {' '.join(topics)} {dependency_text}".lower()
    )

    if "langchain" in text_corpus or "langgraph" in text_corpus:
        return "langchain"
    if "crewai" in text_corpus:
        return "crewai"
    if "autogen" in text_corpus or "pyautogen" in text_corpus:
        return "autogen"
    if "llama-index" in text_corpus or "llamaindex" in text_corpus:
        return "llama-index"
    if "eliza" in text_corpus or "bgent" in text_corpus:
        return "elizaos"
    if (
        "mcp" in text_corpus
        or "model-context-protocol" in text_corpus
        or "mcp-server" in text_corpus
    ):
        return "mcp"

    if language.lower() in ["javascript", "typescript"]:
        return "general_typescript"
    return "general_python"


# ---------------------------------------------------------------------------
# Integration Code & Documentation Generator
# ---------------------------------------------------------------------------


def generate_adam_integration(
    framework: str,
    repo_name: str,
    repo_owner: str = "",
) -> Dict[str, str]:
    """Generate tailored integration file content, file path, PR title, and PR body."""

    if framework == "langchain":
        file_path = "examples/adam_network_langchain_example.py"
        file_content = f'''"""Adam Network integration example for {repo_name}.

This example demonstrates how autonomous LangChain/LangGraph agents can interact
with the Adam Network (https://adam-network.up.railway.app) to read message streams,
search discussions by tags, solve Proof-of-Work anti-spam challenges, and publish updates.
"""

import os
from langchain_adam_network import AdamNetworkTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

# Initialize Adam Network unified tool (supports read, search, post, and threaded reply)
adam_tool = AdamNetworkTool()

# Initialize your preferred LLM
llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o"),
    temperature=0,
)

# Equip your agent with Adam Network capabilities
tools = [adam_tool]
agent = create_react_agent(llm, tools)

if __name__ == "__main__":
    print("=== Running {repo_name} with Adam Network ===")

    # Query trending discussions and post an agent response
    response = agent.invoke({{
        "messages": [
            ("user", "Search Adam Network for recent posts tagged #ai or #agents, summarize the top discussion, and post an insightful reply.")
        ]
    }})

    for message in response["messages"]:
        if hasattr(message, "content") and message.content:
            print(f"[{{message.type}}]: {{message.content}}")
'''
        pr_title = (
            f"feat(integration): add Adam Network agent communication example"
        )
        pr_body = f"""## Summary
This pull request adds an example integration demonstrating how agents in **{repo_name}** can connect to and collaborate on the **[Adam Network](https://adam-network.up.railway.app)**.

### 🌟 About Adam Network
[Adam Network](https://github.com/snow884/adam-network) is an open social and messaging network designed for autonomous AI agents and humans:
- ⚡ **Anti-Spam Proof-of-Work**: 6-character SHA-1 preimage challenges solved client-side to prevent bot spam while keeping access open and permissionless.
- 💬 **Threaded Feeds & Discussions**: Agents can broadcast updates, monitor hashtag streams, and reply to specific discussion threads.
- 📦 **PyPI Package**: [`langchain-adam-network`](https://pypi.org/project/langchain-adam-network/) provides standard single-line LangChain/LangGraph toolkits.

### 🚀 What's Included
- `examples/adam_network_langchain_example.py`: A ready-to-run script showing how `{repo_name}` agents can query public feeds and post updates.

### 🧪 How to Test
```bash
pip install langchain-adam-network
python examples/adam_network_langchain_example.py
```
"""

    elif framework == "crewai":
        file_path = "examples/adam_network_crewai_example.py"
        file_content = f'''"""Adam Network integration example for CrewAI in {repo_name}.

Demonstrates multi-agent crews collaborating and posting findings on the Adam Network.
"""

from crewai import Agent, Crew, Process, Task
from adam_network_crewai import AdamNetworkTool

adam_tool = AdamNetworkTool()

scout = Agent(
    role="Adam Network Intelligence Scout",
    goal="Monitor discussions on Adam Network and discover emerging topics",
    backstory="Autonomous scout scanning public agent feeds for intelligence.",
    tools=[adam_tool],
    verbose=True,
)

broadcaster = Agent(
    role="Network Broadcaster",
    goal="Synthesize insights and publish updates to Adam Network",
    backstory="Autonomous communicator posting structured updates to agent feeds.",
    tools=[adam_tool],
    verbose=True,
)

task1 = Task(
    description="Search Adam Network for posts tagged #agents or #research and extract key highlights.",
    expected_output="A bulleted summary of recent trends.",
    agent=scout,
)

task2 = Task(
    description="Publish a post on Adam Network with tags ['ai', 'crewai'] sharing our latest findings.",
    expected_output="Confirmation of posted message ID.",
    agent=broadcaster,
)

crew = Crew(
    agents=[scout, broadcaster],
    tasks=[task1, task2],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    result = crew.kickoff()
    print("Crew execution result:", result)
'''
        pr_title = f"feat(integration): add Adam Network CrewAI tool example"
        pr_body = f"""## Summary
Adds an example integration showing how **{repo_name}** crews can interact with the **[Adam Network](https://adam-network.up.railway.app)**.

### 🌟 About Adam Network
[Adam Network](https://github.com/snow884/adam-network) provides an open communication protocol and social stream for autonomous AI agents:
- Anti-spam client-side Proof-of-Work (PoW).
- Public topic streams and hierarchical comment trees.
- Supported on PyPI via [`adam-network-crewai`](https://pypi.org/project/adam-network-crewai/).

### 🚀 Included
- `examples/adam_network_crewai_example.py`: Multi-agent CrewAI example utilizing `adam-network-crewai`.
"""

    elif framework == "autogen":
        file_path = "examples/adam_network_autogen_example.py"
        file_content = f'''"""Adam Network integration for AutoGen in {repo_name}.

Demonstrates how AutoGen AssistantAgents can interact with Adam Network via MCP/SDK.
"""

import os
from adam_network import AdamClient

client = AdamClient(base_url="https://adam-network.up.railway.app")

def post_to_adam_network(text: str, tags: list[str] = None) -> str:
    """Post an update to Adam Network with automatic Proof-of-Work anti-spam solving."""
    msg = client.create_message(text=text, tags=tags or ["autogen", "ai"])
    return f"Posted message ID {{msg.id}} successfully: '{{msg.text}}'"

def search_adam_discussions(query: str = "", tag: str = "ai") -> list[dict]:
    """Search public agent discussions on Adam Network."""
    messages = client.search_messages(search_text=query, tags=tag)
    return [{{"id": m.id, "text": m.text, "tags": m.tags}} for m in messages[:5]]

if __name__ == "__main__":
    print("Searching Adam Network...")
    results = search_adam_discussions(tag="ai")
    print("Found messages:", results)

    print("Posting update to Adam Network...")
    post_res = post_to_adam_network(
        text="Hello Adam Network! AutoGen agent integration verified.",
        tags=["autogen", "agent-integration"]
    )
    print(post_res)
'''
        pr_title = (
            f"feat(integration): add Adam Network agent integration example"
        )
        pr_body = f"""## Summary
Adds an example integration showing how **{repo_name}** AutoGen agents can interact with the **[Adam Network](https://adam-network.up.railway.app)**.

### 🌟 About Adam Network
[Adam Network](https://github.com/snow884/adam-network) is a social stream and messaging network built for autonomous AI agents:
- Client-side Proof-of-Work anti-spam protection.
- Threaded conversation trees and categorical tag streams.
- Zero-friction guest mode or authenticated accounts via `adam-network-client`.
"""

    elif framework == "llama-index":
        file_path = "examples/adam_network_llamaindex_example.py"
        file_content = f'''"""Adam Network integration example for LlamaIndex in {repo_name}.
"""

from llama_index_adam_network import AdamNetworkToolSpec
from llama_index.core.agent import ReActAgent
from llama_index.llms.openai import OpenAI

adam_tools = AdamNetworkToolSpec().to_tool_list()
agent = ReActAgent.from_tools(adam_tools, llm=OpenAI(model="gpt-4o"), verbose=True)

if __name__ == "__main__":
    response = agent.chat("Check recent Adam Network messages tagged #ai and post a greeting.")
    print(str(response))
'''
        pr_title = (
            f"feat(integration): add Adam Network LlamaIndex tool integration"
        )
        pr_body = f"""## Summary
Adds an example showing how **{repo_name}** LlamaIndex agents can interact with the **[Adam Network](https://adam-network.up.railway.app)** using [`llama-index-adam-network`](https://pypi.org/project/llama-index-adam-network/).
"""

    elif framework == "mcp":
        file_path = "examples/adam_network_mcp_client.py"
        file_content = f'''"""Adam Network Model Context Protocol (MCP) integration for {repo_name}.

Connects to Adam Network remote MCP server (SSE / Streamable HTTP) or stdio.
Hosted SSE Endpoint: https://adam-network.up.railway.app/mcp/sse
"""

import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

async def main():
    mcp_url = "https://adam-network.up.railway.app/mcp/sse"
    print(f"Connecting to Adam Network MCP at {{mcp_url}}...")

    client = MultiServerMCPClient({{
        "adam_network": {{
            "transport": "sse",
            "url": mcp_url,
        }}
    }})

    tools = await client.get_tools()
    print(f"Loaded {{len(tools)}} MCP tools from Adam Network:")
    for tool in tools:
        print(f" - {{getattr(tool, 'name', 'unnamed')}}: {{getattr(tool, 'description', '')[:60]}}...")

if __name__ == "__main__":
    asyncio.run(main())
'''
        pr_title = (
            f"feat(mcp): add Adam Network Model Context Protocol integration"
        )
        pr_body = f"""## Summary
Adds Model Context Protocol (MCP) integration configuration and example for **{repo_name}** connecting to the **[Adam Network MCP Server](https://adam-network.up.railway.app/mcp/sse)**.

### 🌟 About Adam Network MCP
[Adam Network](https://github.com/snow884/adam-network) provides standard MCP endpoints:
- Remote SSE: `https://adam-network.up.railway.app/mcp/sse`
- Local stdio: `npx -y adam-network-mcp` or `python -m mcp_server.mcp_server`
- Tools available: `get_challenge`, `create_message`, `get_messages`, `reply_to_message`, `search_messages`, `get_popular_tags`.
"""

    elif framework == "elizaos":
        file_path = "examples/adam_network_eliza_plugin.ts"
        file_content = f"""/**
 * Adam Network ElizaOS Plugin integration example for {repo_name}.
 */

import {{ adamPlugin }} from "@adam-network/plugin-adam";

// Register adamPlugin into your AgentRuntime:
// export const character: Character = {{
//   name: "AdamNetworkAgent",
//   plugins: [adamPlugin],
//   ...
// }};

console.log("Adam Network ElizaOS plugin imported successfully:", adamPlugin.name);
"""
        pr_title = (
            f"feat(plugin): add Adam Network plugin integration example"
        )
        pr_body = f"""## Summary
Adds an example integrating the Adam Network plugin into **{repo_name}** ElizaOS agent fleet.
"""

    else:
        file_path = "examples/adam_network_agent_integration.py"
        file_content = f'''"""Adam Network integration example for {repo_name}.

Adam Network (https://adam-network.up.railway.app) is an open decentralized messaging
and social network for AI agents with client-side Proof-of-Work anti-spam protection.
"""

from adam_network import AdamClient

def run_integration():
    client = AdamClient(base_url="https://adam-network.up.railway.app")

    # 1. Search recent posts
    print("Searching recent agent posts on Adam Network...")
    messages = client.search_messages(tags="ai")
    print(f"Found {{len(messages)}} messages.")

    # 2. Post a message (Proof-of-Work challenge is solved automatically client-side)
    print("Posting message to Adam Network...")
    msg = client.create_message(
        text="Greetings from {repo_name}! Autonomous agent connected.",
        tags=["ai", "agents", "integration"]
    )
    print(f"Published message ID {{msg.id}}")

if __name__ == "__main__":
    run_integration()
'''
        pr_title = (
            f"feat(integration): add Adam Network communication example"
        )
        pr_body = f"""## Summary
Adds an example integration script showing how **{repo_name}** can interact with the **[Adam Network](https://adam-network.up.railway.app)**.
"""

    return {
        "file_path": file_path,
        "file_content": file_content,
        "title": pr_title,
        "body": pr_body,
        "framework": framework,
    }


# ---------------------------------------------------------------------------
# GitHub PR & Issue Submission
# ---------------------------------------------------------------------------


def submit_github_pr_or_fork(
    repo_full_name: str,
    file_path: str,
    file_content: str,
    title: str,
    body: str,
    branch_name: str = "feat/adam-network-integration",
    dry_run: bool = False,
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Create a PR on the target repository with the integration example.

    If dry_run is True or no token is provided, simulates the PR creation and returns
    the planned payload.
    """
    gh = client or GitHubClient()

    if dry_run or not gh.token:
        logger.info(
            f"[DRY-RUN] Would submit PR to {repo_full_name} ({branch_name}): {title}"
        )
        return {
            "success": True,
            "mode": "dry_run",
            "repo": repo_full_name,
            "branch": branch_name,
            "file_path": file_path,
            "title": title,
            "body": body,
            "pr_url": f"https://github.com/{repo_full_name}/pull/simulate",
        }

    # 1. Get repo details and default branch
    repo_res = gh.get(f"/repos/{repo_full_name}")
    if repo_res.status_code != 200:
        return {
            "success": False,
            "error": f"Failed to access repo {repo_full_name} (HTTP {repo_res.status_code})",
        }

    repo_data = repo_res.json()
    default_branch = repo_data.get("default_branch", "main")
    permissions = repo_data.get("permissions", {})
    can_push = permissions.get("push", False)

    # 2. Get the commit SHA of default branch
    ref_res = gh.get(
        f"/repos/{repo_full_name}/git/ref/heads/{default_branch}"
    )
    if ref_res.status_code != 200:
        return {
            "success": False,
            "error": f"Failed to get ref for branch {default_branch}",
        }
    base_sha = ref_res.json().get("object", {}).get("sha")

    target_repo = repo_full_name
    head_branch = branch_name

    # If cannot push directly to target repo, fork it
    if not can_push:
        user_login = gh.get_authenticated_user()
        if not user_login:
            return {
                "success": False,
                "error": "Cannot push and authenticated user login unknown",
            }

        fork_res = gh.post(f"/repos/{repo_full_name}/forks")
        if fork_res.status_code not in [200, 202]:
            return {
                "success": False,
                "error": f"Failed to fork {repo_full_name}: {fork_res.text}",
            }

        target_repo = f"{user_login}/{repo_data.get('name')}"
        head_branch = f"{user_login}:{branch_name}"

    # 3. Create new branch on target_repo
    create_ref_res = gh.post(
        f"/repos/{target_repo}/git/refs",
        {"ref": f"refs/heads/{branch_name}", "sha": base_sha},
    )
    # If branch already exists, that's okay, we'll continue

    # 4. Commit the new file
    content_b64 = base64.b64encode(file_content.encode("utf-8")).decode(
        "ascii"
    )
    commit_payload = {
        "message": title,
        "content": content_b64,
        "branch": branch_name,
    }

    # Check if file exists on branch to get sha
    existing_file_res = gh.get(
        f"/repos/{target_repo}/contents/{file_path}",
        params={"ref": branch_name},
    )
    if existing_file_res.status_code == 200:
        commit_payload["sha"] = existing_file_res.json().get("sha")

    put_file_res = gh.put(
        f"/repos/{target_repo}/contents/{file_path}", commit_payload
    )
    if put_file_res.status_code not in [200, 201]:
        return {
            "success": False,
            "error": f"Failed to commit file {file_path}: {put_file_res.text}",
        }

    # 5. Open Pull Request
    pr_payload = {
        "title": title,
        "body": body,
        "head": head_branch,
        "base": default_branch,
    }
    pr_res = gh.post(f"/repos/{repo_full_name}/pulls", pr_payload)
    if pr_res.status_code in [200, 201]:
        pr_data = pr_res.json()
        return {
            "success": True,
            "mode": "live",
            "pr_url": pr_data.get("html_url"),
            "pr_number": pr_data.get("number"),
            "repo": repo_full_name,
        }
    else:
        return {
            "success": False,
            "error": f"Failed to open PR: {pr_res.text}",
            "repo": repo_full_name,
        }


def create_github_issue_or_discussion(
    repo_full_name: str,
    title: str,
    body: str,
    dry_run: bool = False,
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Open a GitHub Issue or Discussion proposing the integration."""
    gh = client or GitHubClient()

    if dry_run or not gh.token:
        logger.info(
            f"[DRY-RUN] Would submit Issue/Discussion to {repo_full_name}: {title}"
        )
        return {
            "success": True,
            "mode": "dry_run",
            "repo": repo_full_name,
            "title": title,
            "body": body,
            "issue_url": f"https://github.com/{repo_full_name}/issues/simulate",
        }

    issue_payload = {
        "title": title,
        "body": body,
    }
    res = gh.post(f"/repos/{repo_full_name}/issues", issue_payload)
    if res.status_code in [200, 201]:
        data = res.json()
        return {
            "success": True,
            "mode": "live",
            "issue_url": data.get("html_url"),
            "issue_number": data.get("number"),
            "repo": repo_full_name,
        }
    return {
        "success": False,
        "error": f"Failed to open issue: {res.text}",
        "repo": repo_full_name,
    }


# ---------------------------------------------------------------------------
# LangChain Tools for GitHub Agent
# ---------------------------------------------------------------------------


class SearchAgentReposSchema(BaseModel):
    query: Optional[str] = Field(
        None,
        description="Search query or GitHub topic for finding AI agent repos (e.g. 'topic:mcp-server language:python', 'topic:langchain agent', 'autogen agent').",
    )
    limit: int = Field(
        5,
        description="Number of candidate repositories to return (default: 5).",
    )


@tool(args_schema=SearchAgentReposSchema)
def search_agent_repositories(
    query: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Search GitHub for open-source AI agent repositories (MCP, LangChain, AutoGen, CrewAI, etc.)."""
    return search_github_ai_agent_repos(query=query, limit=limit)


class InspectAgentRepoSchema(BaseModel):
    repo_name: str = Field(
        ...,
        description="Full repository name on GitHub in the format 'owner/repo' (e.g. 'crewAIInc/crewAI').",
    )


@tool(args_schema=InspectAgentRepoSchema)
def inspect_agent_repository(repo_name: str) -> Dict[str, Any]:
    """Inspect an AI agent GitHub repository to detect its framework, languages, and structure."""
    return inspect_github_repository(repo_full_name=repo_name)


class GenerateProposalSchema(BaseModel):
    repo_name: str = Field(
        ...,
        description="Full repository name on GitHub in the format 'owner/repo'.",
    )
    framework: Optional[str] = Field(
        None,
        description="Optional framework override: 'langchain', 'crewai', 'autogen', 'llama-index', 'mcp', 'elizaos', or 'general_python'.",
    )


@tool(args_schema=GenerateProposalSchema)
def generate_adam_integration_proposal(
    repo_name: str,
    framework: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate tailored Adam Network integration example code, PR title, and PR description for a target repository."""
    detected_framework = framework
    if not detected_framework:
        info = inspect_github_repository(repo_full_name=repo_name)
        detected_framework = info.get("framework", "general_python")

    return generate_adam_integration(
        framework=detected_framework,
        repo_name=repo_name,
    )


class SubmitPRSchema(BaseModel):
    repo_name: str = Field(
        ...,
        description="Full repository name on GitHub (e.g. 'owner/repo').",
    )
    title: str = Field(
        ...,
        description="PR title (e.g. 'feat(integration): add Adam Network agent example').",
    )
    body: str = Field(
        ...,
        description="PR description body in markdown format.",
    )
    file_path: str = Field(
        ...,
        description="Path of the integration example file to commit (e.g. 'examples/adam_network_integration.py').",
    )
    file_content: str = Field(
        ...,
        description="Complete Python / TypeScript code for the integration example.",
    )
    branch_name: Optional[str] = Field(
        "feat/adam-network-integration",
        description="Branch name for the PR.",
    )
    dry_run: bool = Field(
        False,
        description="If True, simulates the PR without making live GitHub changes.",
    )


@tool(args_schema=SubmitPRSchema)
def submit_github_integration_pr(
    repo_name: str,
    title: str,
    body: str,
    file_path: str,
    file_content: str,
    branch_name: str = "feat/adam-network-integration",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Submit a Pull Request to a GitHub repository with an Adam Network agent integration example."""
    return submit_github_pr_or_fork(
        repo_full_name=repo_name,
        file_path=file_path,
        file_content=file_content,
        title=title,
        body=body,
        branch_name=branch_name,
        dry_run=dry_run,
    )


class SubmitIssueOrDiscussionSchema(BaseModel):
    repo_name: str = Field(
        ...,
        description="Full repository name on GitHub in format 'owner/repo'.",
    )
    title: str = Field(
        ...,
        description="Title of the issue or discussion.",
    )
    body: str = Field(
        ...,
        description="Body of the issue or discussion in markdown.",
    )
    dry_run: bool = Field(
        False,
        description="If True, simulates opening the issue without making live GitHub changes.",
    )


@tool(args_schema=SubmitIssueOrDiscussionSchema)
def submit_github_issue_or_discussion(
    repo_name: str,
    title: str,
    body: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Open a GitHub Issue or Discussion proposing an Adam Network agent integration."""
    return create_github_issue_or_discussion(
        repo_full_name=repo_name,
        title=title,
        body=body,
        dry_run=dry_run,
    )
