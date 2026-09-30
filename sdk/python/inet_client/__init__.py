"""Tiny client for a running INET server (local install or Docker).

from inet_client import Inet
inet = Inet()                       # http://127.0.0.1:8000 or $INET_URL
inet.search("free-threaded CPython status")
inet.fetch("https://peps.python.org/pep-0703/")
inet.research("SQLite vs DuckDB for analytics", deep=True)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

__all__ = ["Inet", "AsyncInet", "InetError", "DEFAULT_URL", "ensure_server"]
__version__ = "0.3.0"

DEFAULT_URL = "http://127.0.0.1:8000"
# Deep research can legitimately take several minutes.
DEFAULT_TIMEOUT = float(os.getenv("INET_TIMEOUT", "960"))


class InetError(RuntimeError):
    pass


def _base_url(url: str | None) -> str:
    return (url or os.getenv("INET_URL") or DEFAULT_URL).rstrip("/")


def _raise_for(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise InetError(f"INET {response.status_code}: {detail}")
    return response.json()


def _healthy(url: str) -> bool:
    try:
        return httpx.get(url + "/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def ensure_server(url: str | None = None, home: str | None = None, wait: float = 90) -> str:
    """Return a reachable INET URL, starting `inet serve` from $INET_HOME if needed."""
    url = _base_url(url)
    if _healthy(url):
        return url
    home = home or os.getenv("INET_HOME")
    if not home or not (Path(home) / "backend" / "cli.py").is_file():
        raise InetError(
            f"INET is not reachable at {url}. Start it with `inet serve` (or `docker compose up`), "
            "or set INET_HOME to the repository so it can be started automatically."
        )
    python = Path(home) / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    port = url.rsplit(":", 1)[-1].split("/")[0]
    (Path(home) / "runtime").mkdir(exist_ok=True)
    log = open(Path(home) / "runtime" / "server.log", "ab")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(
        [
            str(python if python.exists() else sys.executable),
            str(Path(home) / "backend" / "cli.py"),
            "serve",
            "--port",
            port,
        ],
        cwd=home,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        creationflags=flags,
        start_new_session=os.name != "nt",
    )
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if _healthy(url):
            return url
        time.sleep(1)
    raise InetError(f"INET did not become healthy at {url} within {wait:.0f}s")


class Inet:
    """Synchronous client."""

    def __init__(self, url: str | None = None, timeout: float = DEFAULT_TIMEOUT, autostart: bool = False):
        self.url = ensure_server(url) if autostart else _base_url(url)
        self._http = httpx.Client(base_url=self.url, timeout=timeout)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return _raise_for(self._http.post(path, json=body))

    def search(self, query: str, limit: int = 5, fresh: bool = False) -> dict[str, Any]:
        return self._post("/api/search", {"query": query, "limit": limit, "fresh": fresh})

    def fetch(self, url: str, fresh: bool = False, instruction: str = "") -> dict[str, Any]:
        return self._post("/api/fetch", {"url": url, "fresh": fresh, "instruction": instruction})

    def research(
        self, question: str, deep: bool = False, instruction: str = "", persistence_level: int = 2
    ) -> dict[str, Any]:
        return self._post(
            "/api/research",
            {
                "question": question,
                "deep": deep,
                "instruction": instruction,
                "persistence_level": persistence_level,
            },
        )

    def system(self) -> dict[str, Any]:
        return _raise_for(self._http.get("/api/system"))

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Inet":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncInet:
    """Asynchronous client with the same methods as `Inet`."""

    def __init__(self, url: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.url = _base_url(url)
        self._http = httpx.AsyncClient(base_url=self.url, timeout=timeout)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return _raise_for(await self._http.post(path, json=body))

    async def search(self, query: str, limit: int = 5, fresh: bool = False) -> dict[str, Any]:
        return await self._post("/api/search", {"query": query, "limit": limit, "fresh": fresh})

    async def fetch(self, url: str, fresh: bool = False, instruction: str = "") -> dict[str, Any]:
        return await self._post("/api/fetch", {"url": url, "fresh": fresh, "instruction": instruction})

    async def research(
        self, question: str, deep: bool = False, instruction: str = "", persistence_level: int = 2
    ) -> dict[str, Any]:
        return await self._post(
            "/api/research",
            {
                "question": question,
                "deep": deep,
                "instruction": instruction,
                "persistence_level": persistence_level,
            },
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncInet":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
