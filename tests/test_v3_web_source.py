"""Product Composer is TypeScript + Vite + Konva, not only the HTML fallback."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_vite_konva_sources_exist():
    pkg = (WEB / "package.json").read_text(encoding="utf-8")
    assert '"konva"' in pkg
    assert '"vite"' in pkg
    canvas = (WEB / "src" / "editor" / "canvas.ts").read_text(encoding="utf-8")
    assert "import Konva from" in canvas
    assert "crop" in canvas
    app = (WEB / "src" / "app.ts").read_text(encoding="utf-8")
    assert "uploadPng" in app
    assert "插入电脑" in app
    assert "白板" in app
    upload = (WEB / "src" / "transport" / "upload.ts").read_text(encoding="utf-8")
    assert "/v3/assets/init" in upload
    assert "chunks" in upload
