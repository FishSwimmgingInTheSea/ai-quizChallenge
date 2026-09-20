@echo off
chcp 65001 >nul
REM ============================================================
REM  Dev backend launcher  (workaround: stale DASHSCOPE_API_KEY)
REM ------------------------------------------------------------
REM  The key was deleted from the Windows registry (Machine/User
REM  = none), but the already-running IDE process still caches the
REM  OLD invalid value (sk-09...) and passes it to child terminals.
REM  Because pydantic-settings prefers os.environ over .env, the
REM  backend would read the stale key and fail with 401.
REM
REM  Clearing it for THIS process makes the backend fall back to
REM  the valid key in .env.  Permanent fix: reboot / sign out so
REM  every process rebuilds its environment block from registry.
REM ============================================================
set "DASHSCOPE_API_KEY="
cd /d "%~dp0"
echo [start_backend] launching uvicorn on http://127.0.0.1:8000 ...
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
