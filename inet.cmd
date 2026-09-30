@echo off
setlocal
set "INET_ROOT=%~dp0"
if exist "%INET_ROOT%.venv\Scripts\python.exe" (
  "%INET_ROOT%.venv\Scripts\python.exe" "%INET_ROOT%backend\cli.py" %*
) else (
  echo INET is not installed yet. Run install.ps1 first. 1>&2
  exit /b 1
)
