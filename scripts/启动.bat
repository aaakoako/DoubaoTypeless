@echo off
chcp 65001 >nul 2>&1
title DoubaoTypeless
cd /d "%~dp0\.."
python -u main.py
pause
