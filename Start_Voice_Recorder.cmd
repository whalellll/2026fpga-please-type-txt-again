@echo off
setlocal
set "VOICE_PYTHON=G:\py\ana\pythonw.exe"
if exist "%VOICE_PYTHON%" (
  start "" "%VOICE_PYTHON%" "%~dp0linux\voice\launch_recorder_pc.py" %*
  exit /b
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
  start "" pythonw.exe "%~dp0linux\voice\launch_recorder_pc.py" %*
  exit /b
)
echo Python with Tk and pyserial is required. See START_HERE.md or the capture guide.
pause
