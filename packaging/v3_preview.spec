# V3 preview onedir — does NOT publish a GitHub Release.
# python -m PyInstaller --noconfirm packaging/v3_preview.spec
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).resolve().parent
icon_path = ROOT / "assets" / "icon.ico"
icon_arg = str(icon_path) if icon_path.is_file() else None
web_dist = ROOT / "web" / "dist"
asset_dir = ROOT / "assets"

datas = [
    (str(ROOT / "src/doubao_typeless/static/composer.html"), "doubao_typeless/static"),
    (str(ROOT / "src/doubao_typeless/static/pc.html"), "doubao_typeless/static"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "docs/release/preview-notes.md"), "docs/release"),
]
if web_dist.is_dir():
    datas.append((str(web_dist), "web/dist"))
if asset_dir.is_dir():
    datas.append((str(asset_dir), "assets"))

a = Analysis(
    [str(ROOT / "tools/run_v3.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "doubao_typeless",
        "aiohttp",
        "PIL",
        "PySide6",
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
