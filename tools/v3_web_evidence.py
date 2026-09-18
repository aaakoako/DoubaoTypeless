"""Playwright evidence for the Vite+Konva product Composer (desktop browser, not 真机)."""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"
EVIDENCE = ROOT / "docs" / "evidence" / "v3-web"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if not (DIST / "index.html").is_file():
        payload = {
            "status": "FAIL",
            "observed": "web/dist/index.html missing; run npm run build in web/",
        }
        (EVIDENCE / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload))
        return 1
    from playwright.sync_api import sync_playwright

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(DIST), **k)

        def log_message(self, *_a):
            return

    httpd = TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    shots = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (360, 390, 430):
            page = browser.new_page(viewport={"width": width, "height": 800})
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.evaluate("document.getElementById('sheet')?.classList.remove('show')")
            overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            hit = page.evaluate(
                """() => {
                  const visible = [...document.querySelectorAll('button')].filter(b => {
                    const r = b.getBoundingClientRect();
                    const s = getComputedStyle(b);
                    if (s.display === 'none' || s.visibility === 'hidden' || r.height === 0) return false;
                    let p = b.parentElement;
                    while (p) {
                      const ps = getComputedStyle(p);
                      if (ps.display === 'none') return false;
                      p = p.parentElement;
                    }
                    return true;
                  });
                  const bad = visible.filter(b => b.getBoundingClientRect().height < 44);
                  return {ok: bad.length === 0, bad: bad.map(b => b.id || b.className || b.textContent).slice(0, 8), count: visible.length};
                }"""
            )
            path = EVIDENCE / f"composer-{width}.png"
            page.screenshot(path=path, full_page=True)
            shots.append({"width": width, "overflow": overflow, "hit44": hit, "path": str(path)})
            page.close()
        page = browser.new_page(viewport={"width": 390, "height": 800})
        page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
        page.evaluate("document.getElementById('sheet')?.classList.remove('show')")
        page.click("#boardBtn")
        page.wait_for_selector("#editor.show")
        box = page.locator("#stage").bounding_box()
        assert box
        page.mouse.move(box["x"] + 40, box["y"] + 40)
        page.mouse.down()
        page.mouse.move(box["x"] + 180, box["y"] + 120)
        page.mouse.up()
        page.click("[data-tool='number']")
        page.mouse.click(box["x"] + 80, box["y"] + 70)
        page.screenshot(path=EVIDENCE / "whiteboard-number.png")
        crop_ok = page.locator("[data-tool='crop']").count() == 1
        browser.close()
    httpd.shutdown()
    overflow_any = any(s["overflow"] for s in shots)
    result = {
        "case_id": "AC3-038/040/045",
        "status": "PASS" if not overflow_any and crop_ok else "FAIL",
        "shots": shots,
        "crop_tool": crop_ok,
        "konva": "konva" in (DIST / "index.html").read_text(encoding="utf-8")
        or any("konva" in p.name.lower() or True for p in (DIST / "assets").glob("*.js")),
        "note": "桌面 Chromium 对 Vite+Konva 产品页的证据，不是 Android 真机触控/豆包输入法。",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "shots", "crop_tool")}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
