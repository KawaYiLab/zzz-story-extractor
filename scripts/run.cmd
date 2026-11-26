@echo off
setlocal
pushd "%~dp0.." || exit /b 1
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>&1
if errorlevel 1 goto use_python
py -3 -m venv .venv
if not errorlevel 1 goto dependencies
:use_python
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -c "import zzz_story.cli, ooz, xxhash, cryptography, UnityPy, requests; assert __import__('sys').version_info >= (3, 11)" >nul 2>&1
if not errorlevel 1 goto run
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
:run
".venv\Scripts\python.exe" -m zzz_story %1
if errorlevel 1 goto failed
if "%~1"=="upload" pause
popd
exit /b 0
:failed
popd
pause
exit /b 1
