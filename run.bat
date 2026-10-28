@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo Создаю окружение...
  py -3.12 -m venv .venv 2>nul || py -3.11 -m venv .venv 2>nul || py -3.10 -m venv .venv 2>nul || py -3 -m venv .venv
  if errorlevel 1 (echo Нужен Python 3.10-3.12 с python.org & pause & exit /b 1)
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt || (echo Ошибка установки & pause & exit /b 1)
) else (
  call .venv\Scripts\activate.bat
)
start "" pythonw -m dftranslator
