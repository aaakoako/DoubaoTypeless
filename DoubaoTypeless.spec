# PyInstaller — Windows 单文件 exe（需在项目根目录执行: pyinstaller DoubaoTypeless.spec）
# 依赖: pip install pyinstaller
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None

try:
    from PyInstaller.utils.hooks import collect_all

    ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")
except Exception:
    ctk_datas, ctk_binaries, ctk_hidden = [], [], []

icon_path = Path("assets/icon.ico")
icon_arg = str(icon_path) if icon_path.is_file() else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=ctk_binaries,
    datas=[
        ("phone.html", "."),
        ("providers.json", "."),
        ("assets", "assets"),
        ("data/dictionary.txt", "data"),
    ]
    + ctk_datas,
    hiddenimports=list(ctk_hidden)
    + [
        "PIL._tkinter_finder",
        "pystray._win32",
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "qrcode",
        "qrcode.image.pil",
        "term_bank",
        "app_version",
        "updater",
        "providers_registry",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DoubaoTypeless",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)
