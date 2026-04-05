@echo off
chcp 65001 >nul 2>&1
title DoubaoTypeless
cd /d "%~dp0\.."
REM 避免「一个 Python 装了包、另一个没装」导致缺 aiohttp 等
python -c "import aiohttp" 1>nul 2>nul
if errorlevel 1 (
  echo [DoubaoTypeless] 正在安装依赖 requirements.txt ...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo pip 失败，请检查 python 是否在 PATH 中，或与手动执行 python 的解释器一致。
    pause
    exit /b 1
  )
)
python -u main.py
pause
