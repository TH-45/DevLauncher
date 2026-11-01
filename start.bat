@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

rem Minimum Python version. Below it, keep the cmd window and ask to upgrade.
set "MIN_MAJOR=3"
set "MIN_MINOR=8"
set "PYVER="
set "PYW="

if defined PYENV_VERSION set "PYVER=%PYENV_VERSION%"
if not defined PYVER call :read_local "%CD%"
if not defined PYVER if exist "%USERPROFILE%\.python-version" call :read_file "%USERPROFILE%\.python-version"

set "PYENV_ROOT=%USERPROFILE%\.pyenv\pyenv-win"
if not defined PYVER if exist "!PYENV_ROOT!\version" call :read_file "!PYENV_ROOT!\version"

if not defined PYVER goto :nopyenv
if not exist "!PYENV_ROOT!\versions\!PYVER!\pythonw.exe" goto :missing
set "PYW=!PYENV_ROOT!\versions\!PYVER!\pythonw.exe"
call :check_ver
if errorlevel 1 exit /b 1
goto :launch

:nopyenv
call :find_pythonw
if not defined PYW goto :missing
call :version_from_exe
if errorlevel 1 exit /b 1
call :check_ver
if errorlevel 1 exit /b 1

:launch
start "" "!PYW!" "%~dp0start.py" --launched
exit /b 0

:read_file
for /f "usebackq tokens=1" %%v in ("%~1") do (
  set "PYVER=%%v"
  exit /b 0
)
exit /b 0

:read_local
if exist "%~1\.python-version" (
  call :read_file "%~1\.python-version"
  exit /b 0
)
for %%I in ("%~1\..") do set "PARENT=%%~fI"
if /i "!PARENT!"=="%~1" exit /b 0
call :read_local "!PARENT!"
exit /b 0

:consider
set "CAND=%~1"
echo !CAND! | findstr /i "shims WindowsApps" >nul
if errorlevel 1 (
  if /i "!CAND:~-11!"=="pythonw.exe" set "PYW=!CAND!"
)
exit /b 0

:find_pythonw
for /f "delims=" %%i in ('where pythonw 2^>nul') do (
  call :consider "%%i"
  if defined PYW exit /b 0
)
exit /b 0

:version_from_exe
set "PYEXE=!PYW:pythonw.exe=python.exe!"
if not exist "!PYEXE!" (
  echo Python 不存在。
  pause
  exit /b 1
)
set "PYFILE=%TEMP%\launcher-pyver.txt"
del "%PYFILE%" >nul 2>&1
"!PYEXE!" -c "import sys; open(r'%PYFILE%','w').write(str(sys.version_info[0])+'.'+str(sys.version_info[1]))"
if not exist "%PYFILE%" goto :missing
set /p PYVER=<"%PYFILE%"
del "%PYFILE%" >nul 2>&1
exit /b 0

:missing
echo Python 不存在。
pause
exit /b 1

:check_ver
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
  set "MAJOR=%%a"
  set "MINOR=%%b"
)
if not defined MINOR set "MINOR=0"
echo !MAJOR!| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 (
  echo Python 版本无法识别：!PYVER!
  pause
  exit /b 1
)
echo !MINOR!| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 set "MINOR=0"
set "TOO=0"
if !MAJOR! LSS %MIN_MAJOR% set "TOO=1"
if !MAJOR! EQU %MIN_MAJOR% if !MINOR! LSS %MIN_MINOR% set "TOO=1"
if "!TOO!"=="1" (
  echo 请升级 Python 版本，当前 !PYVER!，需要 %MIN_MAJOR%.%MIN_MINOR% 或更高。
  pause
  exit /b 1
)
exit /b 0
