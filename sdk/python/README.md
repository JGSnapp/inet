# inet-client

Client, MCP server and LangChain tools for [INET](https://github.com/JGSnapp/inet).

```bash
pip install "inet-client[mcp] @ git+https://github.com/JGSnapp/inet#subdirectory=sdk/python"
```

```python
from inet_client import Inet

with Inet() as inet:  # $INET_URL or http://127.0.0.1:8000
    print(inet.search("free-threaded CPython status")["sources"])
    print(inet.fetch("https://peps.python.org/pep-0703/")["content"][:500])
    print(inet.research("SQLite vs DuckDB for analytics")["answer"])
```

`inet-mcp` starts a stdio MCP server with `web_search`, `fetch_url` and `research` tools.
See the main README for Claude Code / Cursor configuration.
