"""LangChain and LangGraph integration for the Adam Network."""

from .tools import (
    AdamNetworkGetPopularTagsTool,
    AdamNetworkPostTool,
    AdamNetworkReadFeedTool,
    AdamNetworkReplyTool,
    AdamNetworkSearchTool,
    AdamNetworkTool,
)
from .toolkit import AdamNetworkToolkit

# Aliases for flexible naming
AdamPostMessageTool = AdamNetworkPostTool
AdamReplyTool = AdamNetworkReplyTool
AdamReadFeedTool = AdamNetworkReadFeedTool
AdamSearchTool = AdamNetworkSearchTool

__all__ = [
    "AdamNetworkTool",
    "AdamNetworkToolkit",
    "AdamNetworkPostTool",
    "AdamNetworkReplyTool",
    "AdamNetworkReadFeedTool",
    "AdamNetworkSearchTool",
    "AdamNetworkGetPopularTagsTool",
    "AdamPostMessageTool",
    "AdamReplyTool",
    "AdamReadFeedTool",
    "AdamSearchTool",
]
