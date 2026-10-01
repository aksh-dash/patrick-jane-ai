@echo off
REM J.A.N.E. — double-click launcher.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python is not on PATH. Install Python 3.11+ and try again.
  pause
  exit /b 1
)

if not exist ".env" (
  echo No .env found. Copying .env.example — add your ANTHROPIC_API_KEY to it.
  copy /y ".env.example" ".env" >nul
)

python -c "import anthropic, psutil" 2>nul
if errorlevel 1 (
  echo Installing dependencies...
  python -m pip install -r requirements.txt || (pause & exit /b 1)
)

python -m jane
pause
