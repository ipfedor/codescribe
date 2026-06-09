@echo off
setlocal EnableExtensions

REM Called from codescribe (CODESYS) with UTF-8 path list file as %1.
REM %~dp0 resolves to the real codescribe repo directory (even via symlink).

set "INPUT_PATH_FILE=%~1"
if "%INPUT_PATH_FILE%"=="" exit /b 1

set "REPO=%~dp0"
set "SCRIPT="

if exist "%REPO%converter.path" (
  set /p SCRIPT=<"%REPO%converter.path"
)

if not defined SCRIPT if exist "%REPO%..\codesys-export-converter\codesys_export_to_st.py" (
  set "SCRIPT=%REPO%..\codesys-export-converter\codesys_export_to_st.py"
)

if not defined SCRIPT if exist "%REPO%vendor\codesys-export-converter\codesys_export_to_st.py" (
  set "SCRIPT=%REPO%vendor\codesys-export-converter\codesys_export_to_st.py"
)

if not defined SCRIPT exit /b 2

if exist "%WINDIR%\py.exe" (
  "%WINDIR%\py.exe" -3 "%SCRIPT%" --input-path-file "%INPUT_PATH_FILE%" --inplace --dst-suffix .xml.st
  exit /b %ERRORLEVEL%
)

for /f "delims=" %%P in ('where python 2^>nul') do (
  "%%P" "%SCRIPT%" --input-path-file "%INPUT_PATH_FILE%" --inplace --dst-suffix .xml.st
  exit /b %ERRORLEVEL%
)

exit /b 3
