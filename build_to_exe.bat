@echo off
echo Cleaning old build files...
if exist build rd /s /q build
if exist dist rd /s /q dist
echo Starting PyInstaller build process for Jai Agency with OCR...
pyinstaller --noconfirm Jai_Agency.spec
echo.
if %ERRORLEVEL% EQU 0 (
    echo Build successful! Check the 'dist' folder for Jai_Agency.exe
) else (
    echo Build failed! Please check the error messages above.
)
pause
