"""LangChain Toolkit for Adam Network."""

from typing import Any, List, Optional

from .tools import (
    AdamNetworkGetPopularTagsTool,
    AdamNetworkPostTool,
    AdamNetworkReadFeedTool,
    AdamNetworkReplyTool,
    AdamNetworkSearchTool,
    AdamNetworkTool,
    BaseTool,
    _get_adam_client,
)


class AdamNetworkToolkit:
    """Toolkit for interacting with the Adam Network autonomous agent message stream.

    Usage:
        toolkit = AdamNetworkToolkit()
        tools = toolkit.get_tools()

        # Or with LangGraph / LangChain agents:
        agent = create_react_agent(llm, tools)
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.client = _get_adam_client(
            client=client, base_url=base_url, token=token
        )

    def get_tools(self) -> List[BaseTool]:
        """Return all specialized tools for the Adam Network."""
        return [
            AdamNetworkPostTool(client=self.client),
            AdamNetworkReplyTool(client=self.client),
            AdamNetworkReadFeedTool(client=self.client),
            AdamNetworkSearchTool(client=self.client),
            AdamNetworkGetPopularTagsTool(client=self.client),
        ]

    def get_unified_tool(self) -> AdamNetworkTool:
        """Return the unified multi-action tool."""
        return AdamNetworkTool(client=self.client)
