@echo off
cd /d "%~dp0"
echo ========================================================
echo   Auphonic AI Upscaler - Pushing to GitHub...
echo ========================================================
echo.
git branch -M main
git push -u origin main --force
echo.
echo ========================================================
echo Finished! Press any key to close.
echo ========================================================
pause
