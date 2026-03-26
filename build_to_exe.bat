@echo off
echo Cleaning old build files...
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist Jai_Agency.spec del Jai_Agency.spec

echo Starting PyInstaller build process...
echo This may take a few minutes...

pyinstaller --noconfirm --onefile --windowed ^
    --name "Jai_Agency" ^
    --icon "static/css/images/logo.ico" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --hidden-import webview ^
    --hidden-import waitress ^
    --hidden-import flask ^
    app.py

echo.
if %ERRORLEVEL% EQU 0 (
    echo Build successful! Check the 'dist' folder for Jai_Agency.exe
) else (
    echo Build failed! Please check the error messages above.
)
pause
