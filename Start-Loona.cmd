@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Loona Python environment was not found. Open this file from the project folder.
  pause
  exit /b 1
)
if /i "%~1"=="--check" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0main.py" --smoke-test
  if errorlevel 1 exit /b 1
  exit /b 0
)
start "" /d "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
