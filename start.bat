@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
if not exist ".build\native-dev\Hascone.exe" (
  ".venv\Scripts\python.exe" tools/build_native.py --dev
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
start "" "%~dp0.build\native-dev\Hascone.exe" --backend-root "%~dp0." --data-dir "%~dp0."
