"""MCP server exposing INET to Claude Code, Claude Desktop, Cursor, Cline, Windsurf, etc.

Run over stdio:  inet-mcp            (or: python -m inet_client.mcp_server)
Environment:     INET_URL   server address (default http://127.0.0.1:8000)
                 INET_HOME  repository path; lets the tool start `inet serve` on demand
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import AsyncInet, InetError, ensure_server

mcp = FastMCP(
    "inet",
    instructions=(
        "INET is a free-first web research engine. Use web_search for quick lookups, "
        "fetch_url to read a specific page (it falls back through HTTP, TLS impersonation, "
        "reader services and a headless browser), and research for a sourced answer. "
        "Set deep=true only for broad questions: it reads dozens of sites and takes minutes."
    ),
)


def _format(body: dict, content_limit: int = 20000) -> str:
    lines: list[str] = []
    if body.get("answer"):
        lines += [body["answer"].strip(), ""]
    if body.get("content"):
        content = body["content"]
        if len(content) > content_limit:
            content = (
                content[:content_limit] + f"\n\n[truncated {len(body['content']) - content_limit} chars]"
            )
        lines += [f"# {body.get('final_url') or body.get('query')}", "", content, ""]
    if body.get("sources"):
        lines.append("Sources:")
        for i, source in enumerate(body["sources"], 1):
            snippet = (source.get("snippet") or "").replace("\n", " ")[:300]
            lines.append(
                f"[{i}] {source['title']} - {source['url']}" + (f"\n    {snippet}" if snippet else "")
            )
    if body.get("error"):
        lines.append(f"Error: {body['error']}")
    meta = {k: body.get(k) for k in ("run_id", "provider", "cached") if body.get(k) is not None}
    lines.append("\n" + json.dumps(meta))
    return "\n".join(lines).strip()


async def _client() -> AsyncInet:
    try:
        return AsyncInet(ensure_server())
    except InetError as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
async def web_search(query: str, limit: int = 5) -> str:
    """Search the web through INET's free-first engine pool (SearXNG, DuckDuckGo, configured APIs).

    Returns ranked results with titles, URLs and snippets, plus a short synthesized answer
    when the server has an LLM configured. limit: 1-10.
    """
    async with await _client() as inet:
        return _format(await inet.search(query, limit=max(1, min(10, limit))))


@mcp.tool()
async def fetch_url(url: str, instruction: str = "", max_chars: int = 20000) -> str:
    """Read a web page as clean text.

    INET tries official feeds/JSON-LD, plain HTTP, browser-TLS HTTP, reader services and
    a headless browser until real content is obtained, and remembers what worked per domain.
    instruction: optional hint for what to extract. max_chars: truncate long pages.
    """
    async with await _client() as inet:
        return _format(await inet.fetch(url, instruction=instruction), content_limit=max(1000, max_chars))


@mcp.tool()
async def research(question: str, deep: bool = False, instruction: str = "") -> str:
    """Answer a question with citations.

    deep=false: one search round plus synthesis (seconds).
    deep=true: an agent plans queries, reads up to dozens of sites and writes a sourced
    report (minutes; requires the INET server to have an LLM configured).
    """
    async with await _client() as inet:
        return _format(await inet.research(question, deep=deep, instruction=instruction))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
