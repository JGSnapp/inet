"""INET command line.

inet setup                 create .env interactively (LLM provider, key)
inet serve [--open]        API + web UI on http://127.0.0.1:8000
inet search "query"        quick search (starts the server if needed)
inet fetch https://...     read one page
inet ask "question" [--deep]
inet mcp                   stdio MCP server for Claude Code / Cursor / Cline
inet doctor                check the installation
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
ENV_FILE = ROOT / ".env"
sys.path.insert(0, str(ROOT / "sdk" / "python"))


def load_env() -> None:
    """Load .env without overriding variables that are already set."""
    if not ENV_FILE.is_file():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    os.environ.setdefault("RUNTIME_DB", str(ROOT / "runtime" / "state.sqlite3"))
    os.environ.setdefault("INET_HOME", str(ROOT))


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    (ROOT / "runtime").mkdir(exist_ok=True)
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    url = f"http://{args.host}:{args.port}"
    ui = (ROOT / "frontend" / "build" / "index.html").is_file()
    print(f"INET  ->  {url}" + ("" if ui else "   (web UI not built: API only, see /docs)"))
    if args.open and ui:
        import threading
        import webbrowser

        threading.Timer(2.5, webbrowser.open, [url]).start()
    uvicorn.run("api:app", host=args.host, port=args.port, log_level=args.log_level)


def _client():
    from inet_client import Inet, InetError, ensure_server

    try:
        return Inet(ensure_server())
    except InetError as exc:
        sys.exit(str(exc))


def _print(body: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return
    from inet_client.mcp_server import _format

    print(_format(body, content_limit=4000))


def cmd_search(args: argparse.Namespace) -> None:
    with _client() as inet:
        _print(inet.search(args.query, limit=args.limit, fresh=args.fresh), args.json)


def cmd_fetch(args: argparse.Namespace) -> None:
    with _client() as inet:
        _print(inet.fetch(args.url, fresh=args.fresh), args.json)


def cmd_ask(args: argparse.Namespace) -> None:
    if args.deep:
        print(
            "Deep research: planning queries and reading many sites, this takes a few minutes...",
            file=sys.stderr,
        )
    with _client() as inet:
        _print(inet.research(args.question, deep=args.deep), args.json)


def cmd_mcp(args: argparse.Namespace) -> None:
    from inet_client.mcp_server import main

    main()


PROVIDERS = {
    "1": ("none", "No LLM: search and fetch only"),
    "2": ("ollama", "Ollama on this machine (free, local)"),
    "3": ("openai_compatible", "Any OpenAI-compatible API (OpenRouter, ProxyAPI, LM Studio, vLLM...)"),
    "4": ("openai", "OpenAI"),
    "5": ("anthropic", "Anthropic Claude"),
    "6": ("google", "Google Gemini"),
    "7": ("groq", "Groq"),
    "8": ("deepseek", "DeepSeek"),
}
KEY_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai_compatible": "AI_API_KEY",
}


def set_env_values(values: dict[str, str]) -> None:
    import re

    template = ROOT / ".env.example"
    text = (
        ENV_FILE.read_text(encoding="utf-8-sig")
        if ENV_FILE.exists()
        else template.read_text(encoding="utf-8-sig")
    )
    for key, value in values.items():
        if re.search(rf"(?m)^{key}=", text):
            text = re.sub(rf"(?m)^{key}=.*$", lambda _: f"{key}={value}", text, count=1)
        else:
            text += f"\n{key}={value}"
    ENV_FILE.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def cmd_setup(args: argparse.Namespace) -> None:
    import secrets

    print("INET setup. Search and page reading work without an LLM;")
    print("an LLM adds answers, deep research and self-repair.\n")
    for number, (_, label) in PROVIDERS.items():
        print(f"  {number}. {label}")
    choice = PROVIDERS.get(input("\nChoose [1-8, default 1]: ").strip() or "1", PROVIDERS["1"])[0]
    values = {"ENABLE_LLM": "false"}
    if choice != "none":
        values.update(ENABLE_LLM="true", AI_PROVIDER=choice)
        if choice == "ollama":
            values["OLLAMA_BASE_URL"] = (
                input("Ollama URL [http://localhost:11434]: ").strip() or "http://localhost:11434"
            )
        if choice == "openai_compatible":
            values["AI_BASE_URL"] = input("Base URL (e.g. https://openrouter.ai/api/v1): ").strip()
        model = input("Model name [provider default]: ").strip()
        if model:
            values["AI_MODEL"] = model
        if choice in KEY_VARS:
            values[KEY_VARS[choice]] = input("API key: ").strip()
    if not os.getenv("SANDBOX_TOKEN") or "replace-with" in os.getenv("SANDBOX_TOKEN", ""):
        values["SANDBOX_TOKEN"] = secrets.token_urlsafe(32)
    set_env_values(values)
    print(f"\nSaved {ENV_FILE}. Start with:  inet serve --open")


def cmd_doctor(args: argparse.Namespace) -> None:
    import importlib.util
    import shutil

    ok = True

    def check(name: str, passed: bool, hint: str = "") -> None:
        nonlocal ok
        ok &= passed or hint.startswith("optional")
        print(f"  [{'x' if passed else ' '}] {name}" + ("" if passed or not hint else f"  ->  {hint}"))

    print("INET doctor")
    check("Python >= 3.11", sys.version_info >= (3, 11), "install Python 3.11+")
    for module in ("fastapi", "langgraph", "httpx", "bs4"):
        check(f"package {module}", importlib.util.find_spec(module) is not None, "run the installer again")
    check(
        "curl_cffi (browser TLS)",
        importlib.util.find_spec("curl_cffi") is not None,
        "optional: pip install curl-cffi",
    )
    check("mcp (MCP server)", importlib.util.find_spec("mcp") is not None, "optional: pip install mcp")
    browsers = Path(
        os.getenv("PLAYWRIGHT_BROWSERS_PATH")
        or Path.home() / ("AppData/Local/ms-playwright" if os.name == "nt" else ".cache/ms-playwright")
    )
    check(
        "Chromium for Playwright",
        browsers.exists() and any(browsers.glob("chromium*")),
        "optional: python -m playwright install chromium",
    )
    check(
        "web UI built",
        (ROOT / "frontend" / "build" / "index.html").is_file(),
        "optional: npm --prefix frontend ci && npm --prefix frontend run build",
    )
    check(".env present", ENV_FILE.is_file(), "run: inet setup")
    check(
        "Docker (sandbox, optional)",
        shutil.which("docker") is not None,
        "optional: needed only for the adapter sandbox",
    )
    if os.getenv("ENABLE_LLM", "false").lower() == "true":
        sys.path.insert(0, str(BACKEND))
        try:
            from models import create_chat_model

            reply = create_chat_model().invoke("Reply with the single word: ready")
            check(
                f"LLM {os.getenv('AI_PROVIDER')} / {os.getenv('AI_MODEL') or 'default'}",
                bool(str(reply.content).strip()),
            )
        except Exception as exc:  # noqa: BLE001 - report any provider failure
            check(f"LLM {os.getenv('AI_PROVIDER')}", False, f"{type(exc).__name__}: {str(exc)[:160]}")
    else:
        print("  [-] LLM disabled (ENABLE_LLM=false): search/fetch only")
    sys.exit(0 if ok else 1)


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    load_env()
    parser = argparse.ArgumentParser(prog="inet", description="Free-first, self-healing web research engine")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the API and web UI")
    serve.add_argument("--host", default=os.getenv("INET_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.getenv("BACKEND_PORT", "8000")))
    serve.add_argument("--open", action="store_true", help="open the UI in a browser")
    serve.add_argument("--log-level", default="info")
    serve.set_defaults(func=cmd_serve)

    search = sub.add_parser("search", help="web search")
    search.add_argument("query")
    search.add_argument("-n", "--limit", type=int, default=5)
    search.add_argument("--fresh", action="store_true", help="ignore cache")
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=cmd_search)

    fetch = sub.add_parser("fetch", help="read a web page")
    fetch.add_argument("url")
    fetch.add_argument("--fresh", action="store_true")
    fetch.add_argument("--json", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    ask = sub.add_parser("ask", help="answer a question with sources")
    ask.add_argument("question")
    ask.add_argument("--deep", action="store_true", help="multi-site agentic research (needs an LLM)")
    ask.add_argument("--json", action="store_true")
    ask.set_defaults(func=cmd_ask)

    sub.add_parser("mcp", help="run the MCP server over stdio").set_defaults(func=cmd_mcp)
    sub.add_parser("setup", help="configure .env interactively").set_defaults(func=cmd_setup)
    sub.add_parser("doctor", help="check the installation").set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
