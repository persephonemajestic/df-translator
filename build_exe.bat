@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Сборка DFTranslator.exe. Нужен Python 3.10-3.12. Результат: dist\DFTranslator\DFTranslator.exe + DFTranslator.zip
rem  build_exe.bat           - папка (быстрый запуск, рекомендуется)
rem  build_exe.bat debug      - сборка с чёрным окном консоли (видно ошибки)
rem  build_exe.bat onefile   - один .exe (запускается дольше, весит больше)

if not exist .venv-build (
  py -3.12 -m venv .venv-build 2>nul || py -3.11 -m venv .venv-build 2>nul || py -3.10 -m venv .venv-build 2>nul
  if errorlevel 1 (echo Нужен Python 3.10-3.12 с python.org & pause & exit /b 1)
)
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip || goto :fail
pip install -r requirements.txt pyinstaller || goto :fail
python tools\make_icon.py

set MODE=--onedir
set WIN=--windowed
if /i "%1"=="onefile" set MODE=--onefile
if /i "%1"=="debug" set WIN=--console

pyinstaller --noconfirm --clean %WIN% %MODE% --name DFTranslator ^
  --icon assets\icon.ico ^
  --add-data "data;data" ^
  --add-data "assets\icon.png;assets" ^
  --collect-all rapidocr_onnxruntime ^
  --exclude-module tkinter --exclude-module matplotlib ^
  run_app.py || goto :fail

if /i not "%1"=="onefile" powershell -NoProfile -Command "Compress-Archive -Force -Path dist\DFTranslator -DestinationPath dist\DFTranslator.zip"
echo.
echo Готово: dist\DFTranslator\DFTranslator.exe  (или dist\DFTranslator.exe для onefile)
pause
exit /b 0
:fail
echo Сборка не удалась.
pause
exit /b 1
