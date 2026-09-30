"""Blocking, integration-friendly endpoints on top of the asynchronous run engine.

`/api/runs` is asynchronous: it returns a run id and the UI polls it. Agents, SDKs
and drop-in replacements for commercial APIs want one request -> one answer, so
these endpoints submit a normal run (same routing, cache, quotas and memory) and
wait for it to reach a terminal state.
"""

from __future__ import annotations

import asyncio
import time


from fastapi import APIRouter, HTTPException, Request
from typing import Literal

from pydantic import BaseModel, Field

router = APIRouter()

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
DEFAULT_TIMEOUT = 900


async def run_and_wait(request: Request, timeout: float = DEFAULT_TIMEOUT, **submit) -> dict:
    """Submit a run and block until it finishes, returning the stored run record."""
    state = request.app.state
    submit.setdefault("reflection_enabled", False)
    try:
        run = state.research.submit(**submit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    deadline = time.monotonic() + timeout
    while True:
        item = state.store.get("runs", run["id"]) or run
        if item.get("status") in TERMINAL:
            return item
        if time.monotonic() > deadline:
            raise HTTPException(504, f"Run {run['id']} is still running; poll /api/runs/{run['id']}")
        await asyncio.sleep(0.5)


def compact(run: dict) -> dict:
    """Public, stable shape of a finished run."""
    result = run.get("result") or {}
    sources = [
        {"url": s.get("url"), "title": s.get("title") or s.get("url"), "snippet": s.get("snippet", "")}
        for s in result.get("sources", [])
        if s.get("url")
    ]
    body = {
        "run_id": run["id"],
        "status": run.get("status"),
        "query": run.get("query"),
        "answer": result.get("answer", ""),
        "sources": sources,
        "provider": result.get("provider"),
        "cached": bool(run.get("cached")),
    }
    if result.get("content"):
        body.update(
            content=result["content"],
            final_url=result.get("final_url"),
            http_status=result.get("status"),
        )
    if result.get("error"):
        body["error"] = result["error"]
    if result.get("research_stats"):
        body["stats"] = result["research_stats"]
    return body


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=10)
    fresh: bool = False
    lang: Literal["en", "ru"] | None = None


class FetchInput(BaseModel):
    url: str = Field(min_length=8, max_length=4000)
    fresh: bool = False
    allow_archive: bool = False
    instruction: str = Field(default="", max_length=2000)
    lang: Literal["en", "ru"] | None = None


class ResearchInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    deep: bool = False
    instruction: str = Field(default="", max_length=2000)
    persistence_level: int = Field(default=2, ge=1, le=4)
    fresh: bool = False
    lang: Literal["en", "ru"] | None = None


@router.post("/api/search", tags=["integrations"])
async def search(payload: SearchInput, request: Request):
    """Web search: ranked free-first engines with fallback. Returns sources (+ short answer if an LLM is set)."""
    run = await run_and_wait(
        request,
        query=payload.query,
        mode="search",
        limit=payload.limit,
        fresh=payload.fresh,
        lang=payload.lang,
    )
    return compact(run)


@router.post("/api/fetch", tags=["integrations"])
async def fetch(payload: FetchInput, request: Request):
    """Read one URL through the fallback chain (official feeds -> HTTP -> TLS -> reader -> browser)."""
    if not payload.url.startswith(("http://", "https://")):
        raise HTTPException(422, "url must start with http:// or https://")
    run = await run_and_wait(
        request,
        query=payload.url,
        mode="fetch",
        fresh=payload.fresh,
        allow_archive=payload.allow_archive,
        instruction=payload.instruction,
        lang=payload.lang,
    )
    return compact(run)


@router.post("/api/research", tags=["integrations"])
async def research(payload: ResearchInput, request: Request):
    """Answer a question with sources. `deep=true` runs the multi-site agent (minutes, needs an LLM)."""
    run = await run_and_wait(
        request,
        query=payload.question,
        mode="search",
        deep=payload.deep,
        instruction=payload.instruction,
        persistence_level=payload.persistence_level,
        fresh=payload.fresh,
        limit=8,
        lang=payload.lang,
    )
    return compact(run)


# --- Drop-in compatibility -------------------------------------------------
# Many tools let you override the base URL of Tavily or Firecrawl. Pointing them
# at INET keeps their client code and removes the paid dependency. API keys sent
# by those clients are accepted and ignored: INET is a local single-user service.


class TavilySearch(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    max_results: int = Field(default=5, ge=1, le=10)
    include_answer: bool | str = False
    include_raw_content: bool | str = False
    search_depth: str = "basic"
    api_key: str | None = None


@router.post("/tavily/search", tags=["compatibility"])
async def tavily_search(payload: TavilySearch, request: Request):
    """Tavily `/search` compatible response."""
    started = time.monotonic()
    run = await run_and_wait(
        request,
        query=payload.query,
        mode="search",
        limit=payload.max_results,
        deep=payload.search_depth == "advanced",
    )
    body = compact(run)
    if body.get("error") and not body["sources"]:
        raise HTTPException(502, body["error"])
    results = [
        {"title": s["title"], "url": s["url"], "content": s["snippet"], "score": round(1 - i * 0.05, 2)}
        for i, s in enumerate(body["sources"][: payload.max_results])
    ]
    for item in results:
        item["raw_content"] = None
    return {
        "query": payload.query,
        "answer": body["answer"] if payload.include_answer else None,
        "images": [],
        "results": results,
        "response_time": round(time.monotonic() - started, 2),
        "request_id": body["run_id"],
    }


class FirecrawlScrape(BaseModel):
    url: str = Field(min_length=8, max_length=4000)
    formats: list[str] = Field(default_factory=lambda: ["markdown"])
    onlyMainContent: bool = True


@router.post("/firecrawl/v1/scrape", tags=["compatibility"])
@router.post("/firecrawl/v2/scrape", tags=["compatibility"], include_in_schema=False)
async def firecrawl_scrape(payload: FirecrawlScrape, request: Request):
    """Firecrawl `/v1/scrape` compatible response (markdown/text only)."""
    run = await run_and_wait(request, query=payload.url, mode="fetch")
    body = compact(run)
    if not body.get("content"):
        return {"success": False, "error": body.get("error") or "Page could not be read"}
    title = body["sources"][0]["title"] if body["sources"] else payload.url
    return {
        "success": True,
        "data": {
            "markdown": body["content"],
            "metadata": {
                "title": title,
                "sourceURL": payload.url,
                "url": body.get("final_url") or payload.url,
                "statusCode": body.get("http_status") or 200,
                "provider": body.get("provider"),
            },
        },
    }


@router.get("/api/runs/{id}/wait", tags=["integrations"])
async def wait_existing(id: str, request: Request, timeout: float = 60):
    """Long-poll an existing run until it finishes (or `timeout` seconds pass)."""
    deadline = time.monotonic() + min(timeout, DEFAULT_TIMEOUT)
    while True:
        item = request.app.state.store.get("runs", id)
        if not item:
            raise HTTPException(404, "Run not found")
        if item.get("status") in TERMINAL or time.monotonic() > deadline:
            return compact(item) | {"status": item.get("status")}
        await asyncio.sleep(0.5)
