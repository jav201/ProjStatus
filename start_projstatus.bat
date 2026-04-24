@echo off
setlocal

cd /d "%~dp0"

set "APP_URL=http://127.0.0.1:8000"
set "VENV_DIR=%CD%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "PYTHON_CMD="

if not exist "%VENV_PYTHON%" (
  echo [ProjStatus] Local virtual environment not found. Creating .venv...
  call :resolve_python
  if errorlevel 1 goto :python_missing
  %PYTHON_CMD% -m venv "%VENV_DIR%"
  if errorlevel 1 goto :venv_failed
)

echo [ProjStatus] Checking application install...
"%VENV_PYTHON%" -c "import fastapi, uvicorn, app.main" >nul 2>&1
if errorlevel 1 (
  echo [ProjStatus] Installing required dependencies...
  "%VENV_PYTHON%" -m pip install -e .
  if errorlevel 1 goto :install_failed
)

echo [ProjStatus] Starting browser when the server is ready...
start "" powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='%APP_URL%'; for ($i=0; $i -lt 30; $i++) { try { Invoke-WebRequest -UseBasicParsing $url | Out-Null; Start-Process $url; exit 0 } catch { Start-Sleep -Seconds 1 } }; Start-Process $url"

echo [ProjStatus] Launching server at %APP_URL%
"%VENV_PYTHON%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
goto :eof

:resolve_python
where python >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  exit /b 0
)

where py >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
  exit /b 0
)

exit /b 1

:python_missing
echo [ProjStatus] Python was not found on PATH.
echo [ProjStatus] Install Python 3.12+ and then run this file again.
exit /b 1

:venv_failed
echo [ProjStatus] Failed to create the local virtual environment.
exit /b 1

:install_failed
echo [ProjStatus] Dependency installation failed.
echo [ProjStatus] Try running: python -m pip install -e .
exit /b 1
