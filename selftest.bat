@echo off
title Tray Launcher self-test
echo Tray Launcher is working.
echo This window was opened by the tray menu.
echo Close it or use Running -^> Stop in the tray to kill it.
echo.
:loop
echo still running... %time%
timeout /t 5 /nobreak >nul
goto loop
