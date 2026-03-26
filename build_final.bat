@echo off
echo ====================================================
echo   KOKKALATTY TEEA TRADERS - EXE BUILDER
echo ====================================================
echo.
echo Cleaning old build files...
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist Kokkalatty_Sales.spec del Kokkalatty_Sales.spec

echo.
echo Installing requirements to ensure everything is ready...
pip install -r requirements.txt

echo.
echo Starting PyInstaller build process...
echo This will take a few minutes. Please wait...
echo.

pyinstaller --noconfirm --onefile --windowed ^
    --name "Kokkalatty_Sales" ^
    --icon "static/css/images/logo.ico" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --hidden-import webview ^
    --hidden-import waitress ^
    --hidden-import flask ^
    --hidden-import jinja2 ^
    app.py

echo.
if %ERRORLEVEL% EQU 0 (
    echo ====================================================
    echo SUCCESS: Build complete!
    echo Your executable is in the 'dist' folder:
    echo d:\Homewoode small factory\dist\Kokkalatty_Sales.exe
    echo ====================================================
) else (
    echo ====================================================
    echo ERROR: Build failed! 
    echo Please check the error messages above.
    echo ====================================================
)
pause
