@echo off
chcp 65001 >nul
set "DT_V3_DATA_DIR=%LOCALAPPDATA%\DoubaoTypeless\preview-v3"
echo Pocket Composer v3 使用独立数据目录:
echo %DT_V3_DATA_DIR%
python -m doubao_typeless
