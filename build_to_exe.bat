@echo off
title Jai Agency - EXE Builder
echo ====================================================
echo   JAI AGENCY - DESKTOP EXE BUILDER (WITH OCR)
echo ====================================================
echo.
echo Cleaning previous build artifacts...
if exist build rd /s /q build
if exist dist rd /s /q dist

echo.
echo Starting PyInstaller build process...
echo This will package OCR models, PyWebView, and all assets.
echo Please wait...
echo.

if exist .venv\Scripts\python.exe (
    call .venv\Scripts\python.exe -m PyInstaller --noconfirm Jai_Agency.spec
) else (
    pyinstaller --noconfirm Jai_Agency.spec
)

echo.
if %ERRORLEVEL% EQU 0 (
    echo ====================================================
    echo SUCCESS: Build complete!
    echo Executable created: dist\Jai_Agency.exe
    echo ====================================================
) else (
    echo ====================================================
    echo ERROR: Build failed! Please check messages above.
    echo ====================================================
)
echo.
pause
