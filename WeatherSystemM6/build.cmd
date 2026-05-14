@echo off
if "%PATH_TO_FX%"=="" (
  echo ERROR: PATH_TO_FX is not set.
  echo Set PATH_TO_FX to your JavaFX SDK folder, for example:
  echo   set PATH_TO_FX=C:\javafx-sdk-25.0.3
  exit /b 1
)
if not exist "%PATH_TO_FX%\lib" (
  echo ERROR: Could not find JavaFX SDK lib folder at %PATH_TO_FX%\lib
  exit /b 1
)
set SRC_ROOT=src
set OUT_DIR=out
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"
if exist sources.txt del sources.txt
for /R "%SRC_ROOT%" %%f in (*.java) do @echo %%f >> sources.txt
javac --module-path "%PATH_TO_FX%\lib" --add-modules javafx.controls -d "%OUT_DIR%" @sources.txt
set ERR=%ERRORLEVEL%
del sources.txt
if %ERR% neq 0 exit /b %ERR%
echo Build complete.
