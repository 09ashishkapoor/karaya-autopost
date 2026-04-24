@echo off
setlocal

cd /d "%~dp0"

echo Generating Kalabhairava tweets...
python generate_tweets.py --config tweet_config.json
if errorlevel 1 goto error

echo.
echo Generating Adya Mahakali tweets...
python generate_tweets.py --config tweet_config_mahakali.json
if errorlevel 1 goto error

echo.
echo Done. Generated files are in the output folder.
pause
exit /b 0

:error
echo.
echo Tweet generation failed.
pause
exit /b 1
