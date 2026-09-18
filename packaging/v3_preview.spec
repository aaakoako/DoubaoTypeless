# V3 preview onedir — does NOT publish a GitHub Release.
# pyinstaller --noconfirm packaging/v3_preview.spec
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
icon_path = Path("assets/icon.ico")
icon_arg = str(icon_path) if icon_path.is_file() else None

a = Analysis(
    ["tools/run_v3.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("src/doubao_typeless/static/composer.html", "doubao_typeless/static"),
        ("assets", "assets"),
    ],
    hiddenimports=[
        "doubao_typeless",
        "aiohttp",
        "PIL",
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["customtkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DoubaoTypelessV3Preview",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="DoubaoTypelessV3Preview",
)
