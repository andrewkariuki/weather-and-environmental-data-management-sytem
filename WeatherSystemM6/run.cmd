@echo off
set OUT_DIR=out
if "%PATH_TO_FX%"=="" (
  if exist "C:\Users\andre\Desktop\MEDIA\RANDOM\openjfx-21.0.11-ea+4_windows-x64_bin-sdk\javafx-sdk-21.0.11\lib" (
    set "PATH_TO_FX=C:\Users\andre\Desktop\MEDIA\RANDOM\openjfx-21.0.11-ea+4_windows-x64_bin-sdk\javafx-sdk-21.0.11"
  ) else (
    echo ERROR: PATH_TO_FX is not set and default JavaFX SDK path was not found.
    echo Set PATH_TO_FX to your JavaFX SDK folder, for example:
    echo   set PATH_TO_FX=C:\javafx-sdk-25.0.3
    exit /b 1
  )
)
if not exist "%OUT_DIR%" (
  echo ERROR: Build output not found. Run build.cmd first.
  exit /b 1
)
java --module-path "%PATH_TO_FX%\lib" --add-modules javafx.controls -cp "%OUT_DIR%" jkuat.weather.ui.WeatherSystemM6
