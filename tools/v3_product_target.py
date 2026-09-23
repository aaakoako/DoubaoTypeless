"""Observable paste target for the product, not the design prototype."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageGrab, ImageTk

out = Path(sys.argv[1] if len(sys.argv) > 1 else "target-state.json")
out.parent.mkdir(parents=True, exist_ok=True)

root = tk.Tk()
root.title("V3ComposerTarget · chatinput")
root.geometry("640x420+60+60")
root.attributes("-topmost", True)

status = tk.Label(root, text="产品投递目标 · 等待图后文 · 不接收 Enter 作为成功", anchor="w")
status.pack(fill="x", padx=8, pady=4)
thumbs = tk.Frame(root)
thumbs.pack(fill="x", padx=8)
text = tk.Text(root, wrap="word", height=10)
text.pack(fill="both", expand=True, padx=8, pady=8)
text.insert("1.0", "BEFORE\n")
text.focus_set()

state = {"images": [], "text": "BEFORE\n", "enter_count": 0, "updated_at": time.time()}
previews: list[ImageTk.PhotoImage] = []


def dump() -> None:
    state["text"] = text.get("1.0", "end")
    state["updated_at"] = time.time()
    out.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    root.after(120, dump)


def add_image(image: Image.Image) -> None:
    rgb = image.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    digest = hashlib.sha256(buf.getvalue()).hexdigest()
    state["images"].append({"sha256": digest, "width": rgb.width, "height": rgb.height})
    thumb = rgb.copy()
    thumb.thumbnail((96, 72))
    photo = ImageTk.PhotoImage(thumb)
    previews.append(photo)
    lbl = tk.Label(thumbs, image=photo, bd=1, relief="solid")
    lbl.pack(side="left", padx=4, pady=4)


def on_paste(_event=None):
    grabbed = ImageGrab.grabclipboard()
    if isinstance(grabbed, Image.Image):
        add_image(grabbed)
        return "break"
    try:
        root.clipboard_get()
    except tk.TclError:
        return "break"
    return None


def on_return(_event=None):
    state["enter_count"] = int(state["enter_count"]) + 1
    return "break"


root.bind("<FocusIn>", lambda _e: text.focus_set())
text.bind("<<Paste>>", on_paste)
text.bind("<Control-v>", on_paste)
text.bind("<Control-V>", on_paste)
text.bind("<Return>", on_return)
root.bind("<Return>", on_return)
root.after(120, dump)
root.mainloop()
