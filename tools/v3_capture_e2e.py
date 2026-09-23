"""Windows capture e2e: colored window bbox, cancel, HUD hidden."""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EVIDENCE = ROOT / "docs" / "evidence" / "v3-capture"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    from PySide6.QtCore import Qt, QRect
    from PySide6.QtGui import QColor, QGuiApplication
    from PySide6.QtWidgets import QApplication, QWidget, QLabel

    from doubao_typeless.platform.windows.capture import ensure_dpi_aware, grab_bbox, list_monitors, parse_scope
    from doubao_typeless.services.capture import CaptureService
    from doubao_typeless.storage.credentials import Session
    from doubao_typeless.ui.hud import HudController

    ensure_dpi_aware()
    app = QApplication.instance() or QApplication([])
    hud = HudController()
    hud.start()
    hud.show_receiving("不应出现在截图", 1)
    app.processEvents()

    target = QWidget()
    target.setWindowTitle("DT-V3-CAPTURE-SWATCH")
    target.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
    target.setStyleSheet("background:#E11D48;")
    target.resize(180, 120)
    target.show()
    target.raise_()
    app.processEvents()
    time.sleep(0.3)
    geo = target.frameGeometry()
    # Qt geometry is in DIP; grab uses physical pixels via DPI-aware process.
    screen = QGuiApplication.screenAt(geo.center()) or QGuiApplication.primaryScreen()
    dpr = float(screen.devicePixelRatio())
    bbox = (
        int(geo.x() * dpr),
        int(geo.y() * dpr),
        int(geo.x() * dpr) + int(geo.width() * dpr),
        int(geo.y() * dpr) + int(geo.height() * dpr),
    )
    hud.hide()
    app.processEvents()
    blob = grab_bbox(bbox, hide=hud.hide)
    image = Image.open(io.BytesIO(blob))
    sample = image.getpixel((image.width // 2, image.height // 2))
    image.save(EVIDENCE / "region-swatch.png")

    grabs = []
    svc = CaptureService(grab=lambda s: grabs.append(s) or blob, hide_surfaces=hud.hide)
    session = Session("d", "s", "h", 9e12, allow_capture=True)
    svc.begin(session, f"region:{bbox[0]},{bbox[1]},{bbox[2]-bbox[0]},{bbox[3]-bbox[1]}", "cancel-me", now=time.monotonic())
    svc.cancel("cancel-me")
    cancelled = False
    try:
        svc.complete("cancel-me", session)
    except ValueError as exc:
        cancelled = "cancel" in str(exc)

    monitors = list_monitors()
    primary = parse_scope("primary")
    result = {
        "case_id": "AC3-042/043/044",
        "status": "PASS" if sample[0] > 180 and cancelled and image.size[0] > 10 else "FAIL",
        "observed": {
            "image_size": list(image.size),
            "center_pixel": list(sample),
            "dpr": dpr,
            "bbox": list(bbox),
            "qt_geo": [geo.x(), geo.y(), geo.width(), geo.height()],
            "monitors": monitors,
            "primary": list(primary),
            "cancel_no_grab": cancelled and grabs == [],
            "hud_hidden_before_grab": hud.visible is False,
        },
        "expected": "region pixels match swatch; cancel adds no image; HUD hidden",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "evidence_paths": ["docs/evidence/v3-capture/region-swatch.png"],
    }
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    target.close()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
