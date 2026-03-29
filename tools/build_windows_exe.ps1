# 在项目根目录执行: powershell -ExecutionPolicy Bypass -File tools\build_windows_exe.ps1
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "Working directory: $(Get-Location)"

pip install pyinstaller pillow qrcode[pil] | Out-Null
if (-not (Test-Path "assets\icon.ico")) {
    python tools/gen_app_icon.py
}

pyinstaller --noconfirm DoubaoTypeless.spec
Write-Host "Output: dist\DoubaoTypeless.exe (config.json / data 与 exe 同目录生成)"
