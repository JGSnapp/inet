"""LangChain / LangGraph tools backed by INET.

from inet_client.langchain import inet_tools
agent = create_react_agent(model, inet_tools())
"""

from __future__ import annotations

from langchain_core.tools import tool

from . import AsyncInet
from .mcp_server import _format


def inet_tools(url: str | None = None) -> list:
    """Return `web_search`, `fetch_url` and `research` tools bound to one INET server."""

    @tool
    async def web_search(query: str, limit: int = 5) -> str:
        """Search the web. Returns titles, URLs and snippets."""
        async with AsyncInet(url) as inet:
            return _format(await inet.search(query, limit=limit))

    @tool
    async def fetch_url(url_to_read: str) -> str:
        """Read a web page as clean text, falling back through several fetchers."""
        async with AsyncInet(url) as inet:
            return _format(await inet.fetch(url_to_read))

    @tool
    async def research(question: str, deep: bool = False) -> str:
        """Answer a question with cited sources. deep=True reads dozens of sites (slow)."""
        async with AsyncInet(url) as inet:
            return _format(await inet.research(question, deep=deep))

    return [web_search, fetch_url, research]
