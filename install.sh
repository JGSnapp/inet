#!/usr/bin/env sh
# INET installer for Linux and macOS.
#   curl -fsSL https://raw.githubusercontent.com/JGSnapp/inet/main/install.sh | sh
# Options (environment): INET_DIR=~/inet  INET_NO_BROWSER=1  INET_NO_UI=1
set -eu

REPO="https://github.com/JGSnapp/inet"
say() { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1" >&2; }

# 1. Source: use the checkout this script lives in, otherwise clone.
SCRIPT_DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd -P || pwd)
if [ -f "$SCRIPT_DIR/backend/cli.py" ]; then
  ROOT="$SCRIPT_DIR"
else
  ROOT="${INET_DIR:-$HOME/inet}"
  if [ -d "$ROOT/.git" ]; then
    say "Updating $ROOT"
    git -C "$ROOT" pull --ff-only
  else
    command -v git >/dev/null || { warn "git is required"; exit 1; }
    say "Cloning INET into $ROOT"
    git clone --depth 1 "$REPO" "$ROOT"
  fi
fi
cd "$ROOT"

# 2. uv manages Python itself, so no system Python is required.
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (Python package manager)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

say "Creating Python environment"
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -r backend/requirements-browser.txt -e "sdk/python[mcp]"

if [ "${INET_NO_BROWSER:-0}" != "1" ]; then
  say "Installing Chromium for the browser fallback"
  # On Linux Chromium also needs system libraries; install them when we are allowed to.
  DEPS=""
  if [ "$(uname -s)" = "Linux" ] && { [ "$(id -u)" = "0" ] || sudo -n true 2>/dev/null; }; then
    DEPS="--with-deps"
  fi
  # Large downloads from the Playwright CDN can time out; retry once before giving up.
  if ! .venv/bin/python -m playwright install $DEPS chromium && ! .venv/bin/python -m playwright install $DEPS chromium; then
    warn "Chromium install failed; rerun .venv/bin/python -m playwright install chromium or set ENABLE_BROWSER=false in .env"
  fi
  if [ "$(uname -s)" = "Linux" ] && [ -z "$DEPS" ]; then
    warn "If the browser fallback fails, run: sudo $ROOT/.venv/bin/python -m playwright install-deps chromium"
  fi
fi

# 3. Web UI: build with Node if present, otherwise download the prebuilt release asset.
if [ "${INET_NO_UI:-0}" != "1" ] && [ ! -f frontend/build/index.html ]; then
  if command -v npm >/dev/null 2>&1; then
    say "Building web UI"
    npm --prefix frontend ci --no-audit --no-fund && npm --prefix frontend run build
  else
    say "Downloading prebuilt web UI"
    ARCHIVE=$(mktemp)
    if curl -fsSL -o "$ARCHIVE" "$REPO/releases/latest/download/inet-ui.tar.gz" 2>/dev/null; then
      mkdir -p frontend/build && tar -xzf "$ARCHIVE" -C frontend/build
    else
      warn "No prebuilt UI found. API, CLI and MCP work; install Node.js to build the UI."
    fi
    rm -f "$ARCHIVE"
  fi
fi

# 4. Configuration.
if [ ! -f .env ]; then
  cp .env.example .env
  TOKEN=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))")
  sed -i.bak "s|^SANDBOX_TOKEN=.*|SANDBOX_TOKEN=$TOKEN|" .env && rm -f .env.bak
fi
chmod +x inet

say "Done. Next steps:"
cat <<EOF

  cd $ROOT
  ./inet setup          # optional: connect an LLM (Ollama, OpenAI-compatible, Claude, ...)
  ./inet serve --open   # web UI + API on http://127.0.0.1:8000
  ./inet search "your question"

  Add to your PATH:  export PATH="$ROOT:\$PATH"
EOF
