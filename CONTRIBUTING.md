# Contributing to INET

Thanks for helping! Issues, fixes, new free tools for the catalog and translations are all welcome.

## Setup

```bash
./install.sh            # or .\install.ps1 on Windows
.venv/bin/pip install ruff
```

Run the backend with `./inet serve` and the UI with hot reload with `npm --prefix frontend run dev`
(http://localhost:3000, proxied to the backend on :8000).

## Before opening a pull request

```bash
.venv/bin/ruff check backend sandbox scripts sdk
.venv/bin/ruff format backend sandbox scripts sdk
.venv/bin/python -m pytest backend -q
npm --prefix frontend run format && npm --prefix frontend run build
```

CI runs the same checks.

## Guidelines

- **Free first.** A new search or fetch tool should work without payment. Paid APIs stay
  optional fallbacks with an explicit budget.
- **Do not execute untrusted code in the backend.** Generated adapters run only in the sandbox service.
- **Be honest in results.** Do not report success for CAPTCHA pages, empty pages or HTTP errors.
- **Respect sites.** No features for bypassing logins, paywalls or terms of service.
- Keep pull requests focused and add a test for behavior changes (`backend/test_*.py`).

## Adding a tool to the catalog

Add an entry to `backend/resources.json` with its URL, category, license and whether it is free,
free-trial or paid. Claims about quotas must link to a source.
