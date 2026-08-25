@echo off
rem One-click start for Tray Launcher (no console window; uses local .venv if present).
set "HERE=%~dp0"
set "PYW=%HERE%.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
start "" "%PYW%" "%HERE%tray_launcher.pyw"
