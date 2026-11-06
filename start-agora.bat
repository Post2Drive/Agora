@echo off
rem Double-click to install (first time) and open Agora in your browser.
cd /d "%~dp0"
where python >nul 2>nul || (
  echo Python is not installed. Install it with:  winget install Python.Python.3.12
  echo then open a new window and run this file again.
  pause & exit /b 1
)
if not exist .venv (
  echo First run: setting up Agora, this takes a minute...
  python -m venv .venv || (pause & exit /b 1)
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -e . || (pause & exit /b 1)
)
where ollama >nul 2>nul || echo Note: Ollama not found. Install it from https://ollama.com and run:  ollama pull llama3.2:3b
.venv\Scripts\agora web
pause
