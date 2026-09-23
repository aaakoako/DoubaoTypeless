"""Specified Windows paste surface for S2. Not Cursor. Records image-then-text order."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
from pathlib import Path

import tkinter as tk
import win32clipboard
import win32con
from PIL import Image


def dib_to_png(dib: bytes) -> bytes:
    info_size = int.from_bytes(dib[0:4], "little")
    bit_count = int.from_bytes(dib[14:16], "little") if len(dib) >= 16 else 24
    palette = 0
    if bit_count <= 8:
        colors = int.from_bytes(dib[32:36], "little") if len(dib) >= 36 else 0
        palette = (colors or (1 << bit_count)) * 4
    offset = 14 + info_size + palette
    bmp = b"BM" + (14 + len(dib)).to_bytes(4, "little") + b"\x00\x00\x00\x00" + offset.to_bytes(4, "little") + dib
    image = Image.open(io.BytesIO(bmp)).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def read_clipboard():
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
            dib = win32clipboard.GetClipboardData(win32con.CF_DIB)
            png = dib_to_png(dib)
            image = Image.open(io.BytesIO(png))
            return "image", png, image.size
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return "text", str(win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)), None
        return None, None, None
    except Exception:
        return None, None, None
    finally:
        win32clipboard.CloseClipboard()


def main() -> int:
    state_path = Path(sys.argv[1])
    image_dir = state_path.parent / "pasted"
    image_dir.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    images: list[dict] = []
    root = tk.Tk()
    root.title("DT-S2-PasteTarget")
    root.geometry("520x360")
    root.attributes("-topmost", True)
    status = tk.Label(root, text="等待先图后文", font=("Segoe UI", 12))
    status.pack(fill="x", padx=8, pady=6)
    box = tk.Text(root, wrap="word", font=("Segoe UI", 14), height=8)
    box.pack(fill="both", expand=True)
    box.focus_force()
    root.focus_force()

    def dump() -> None:
        payload = {
            "title": root.title(),
            "text": box.get("1.0", "end-1c"),
            "images": images,
            "events": events,
            "has_focus": root.focus_displayof() is not None,
        }
        state_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        root.after(50, dump)

    def on_paste(_event=None):
        kind, data, size = read_clipboard()
        now = time.time()
        if kind == "image" and data:
            digest = hashlib.sha256(data).hexdigest()
            path = image_dir / f"{len(images)+1}-{digest[:12]}.png"
            path.write_bytes(data)
            item = {"sha256": digest, "path": str(path), "width": size[0], "height": size[1], "bytes": len(data)}
            images.append(item)
            events.append({"kind": "image", "t": now, "sha256": digest, "width": size[0], "height": size[1]})
            status.config(text=f"已收图 {len(images)}")
            return "break"
        if kind == "text" and data:
            box.insert("end", data)
            events.append({"kind": "text", "t": now, "text": data})
            status.config(text="已收文字")
            return "break"
        return "break"

    root.bind_all("<Control-v>", on_paste)
    root.bind_all("<Control-V>", on_paste)
    box.bind("<<Paste>>", on_paste)
    root.after(50, dump)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
