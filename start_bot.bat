@echo off
echo Starting Discord Music Bot...
echo.

REM Activate virtual environment
call discord_bot_env\Scripts\activate.bat

REM Check if required packages are installed
python -c "import discord, yt_dlp, spotipy" 2>nul
if errorlevel 1 (
    echo Installing required packages...
    pip install -r requirements.txt
)

REM Run the bot
python music_bot.py

pause