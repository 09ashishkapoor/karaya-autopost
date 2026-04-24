@echo off
setlocal

cd /d "%~dp0"

echo Generating Kalabhairava posts...
python generate_posts.py --config post_config.json
if errorlevel 1 goto error

echo.
echo Generating Adya Mahakali posts...
python generate_posts.py --config post_config_mahakali.json
if errorlevel 1 goto error

echo.
echo Done. Generated files are in the output folder.
pause
exit /b 0

:error
echo.
echo Post generation failed.
pause
exit /b 1
