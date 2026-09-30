# INET installer for Windows.
#   irm https://raw.githubusercontent.com/JGSnapp/inet/main/install.ps1 | iex
# Options (environment): $env:INET_DIR, $env:INET_NO_BROWSER=1, $env:INET_NO_UI=1
$ErrorActionPreference = 'Stop'
$Repo = 'https://github.com/JGSnapp/inet'
function Say($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Warn($text) { Write-Host "!! $text" -ForegroundColor Yellow }

# 1. Source: use the checkout this script lives in, otherwise clone.
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'backend\cli.py'))) {
    $Root = $PSScriptRoot
} else {
    $Root = if ($env:INET_DIR) { $env:INET_DIR } else { Join-Path $HOME 'inet' }
    if (Test-Path (Join-Path $Root '.git')) {
        Say "Updating $Root"; git -C $Root pull --ff-only
    } else {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git is required: https://git-scm.com/download/win' }
        Say "Cloning INET into $Root"; git clone --depth 1 $Repo $Root
    }
}
Set-Location $Root

# 2. uv manages Python itself, so no system Python is required.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Say 'Installing uv (Python package manager)'
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$HOME\.local\bin;$env:Path"
}

Say 'Creating Python environment'
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv\Scripts\python.exe -r backend\requirements-browser.txt -e "sdk/python[mcp]"
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }

if ($env:INET_NO_BROWSER -ne '1') {
    Say 'Installing Chromium for the browser fallback'
    .venv\Scripts\python.exe -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { Warn 'Chromium install failed; set ENABLE_BROWSER=false in .env' }
}

# 3. Web UI: build with Node if present, otherwise download the prebuilt release asset.
if ($env:INET_NO_UI -ne '1' -and -not (Test-Path 'frontend\build\index.html')) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Say 'Building web UI'
        npm.cmd --prefix frontend ci --no-audit --no-fund; npm.cmd --prefix frontend run build
    } else {
        Say 'Downloading prebuilt web UI'
        try {
            $archive = Join-Path $env:TEMP 'inet-ui.tar.gz'
            Invoke-WebRequest "$Repo/releases/latest/download/inet-ui.tar.gz" -OutFile $archive
            New-Item -ItemType Directory -Force 'frontend\build' | Out-Null
            tar -xzf $archive -C frontend\build
        } catch { Warn 'No prebuilt UI found. API, CLI and MCP work; install Node.js to build the UI.' }
    }
}

# 4. Configuration.
if (-not (Test-Path '.env')) {
    $token = .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
    (Get-Content '.env.example' -Encoding UTF8) -replace '^SANDBOX_TOKEN=.*', "SANDBOX_TOKEN=$token" |
        Set-Content '.env' -Encoding UTF8
}

Say 'Done. Next steps:'
Write-Host @"

  cd $Root
  .\inet setup          # optional: connect an LLM (Ollama, OpenAI-compatible, Claude, ...)
  .\inet serve --open   # web UI + API on http://127.0.0.1:8000
  .\inet search "your question"

  Add to PATH:  [Environment]::SetEnvironmentVariable('Path', "$Root;" + [Environment]::GetEnvironmentVariable('Path','User'), 'User')
"@
