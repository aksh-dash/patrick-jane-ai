@echo off
rem  Double-click this to start J.A.N.E. as a desktop app.
rem  It launches the local server and opens Jane in her own window.
cd /d "%~dp0"
echo Starting J.A.N.E. ...
python -m jane --app
pause
