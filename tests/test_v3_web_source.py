"""Product Composer is TypeScript + Vite + Konva, not only the HTML fallback."""
import subprocess
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
    assert "applyCrop" in canvas
    assert "addMask" in canvas
    assert "addStroke" in canvas
    assert "exportScene" in canvas
    app = (WEB / "src" / "app.ts").read_text(encoding="utf-8")
    assert "uploadPng" in app
    assert "插入电脑" in app
    assert "白板" in app
    assert "captionHint" in app
    assert "captionDrawer" in app
    assert "openNextQueued" in app
    assert "dt.v3.device" in app
    assert "resumeRemembered" in app
    # Scratch edits take precedence without replacing the saved scene until commit.
    # Production-page cancellation tests also verify the restored pixel/scene identity.
    assert "asset.edit_scene || asset.scene" in app
    assert "editor.importScene(asset.edit_scene || asset.scene!)" in app
    assert "rebindSource" in app
    assert "applyRotated" in app
    assert "applyReady" in app
    assert "device.remembered" in app
    assert "recall.last" in app
    assert "rebindSource" in canvas
    assert "midX" in canvas
    upload = (WEB / "src" / "transport" / "upload.ts").read_text(encoding="utf-8")
    assert "/v3/assets/init" in upload
    assert "chunks" in upload
    protocol = (WEB / "src" / "transport" / "protocol.ts").read_text(encoding="utf-8")
    assert "sha256Bytes" in protocol
    assert "settingsStatus" in app


def test_image_queue_and_finish_policy_scripts():
    root = Path(__file__).resolve().parents[1]
    for name in ("test_v3_image_queue.mjs", "test_v3_finish_editor.mjs", "test_v3_phone_events.mjs"):
        out = subprocess.check_output(["node", str(root / "tests" / name)], text=True)
        assert "ok" in out
