"""Visible paste target for V3-00. Writes captured text for observation."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "captured.txt")
out.parent.mkdir(parents=True, exist_ok=True)
root = tk.Tk()
root.title("V3-00-TARGET")
root.geometry("520x240+80+80")
root.attributes("-topmost", True)
label = tk.Label(root, text="V3-00 paste target — do not type secrets", anchor="w")
label.pack(fill="x", padx=8, pady=4)
text = tk.Text(root, wrap="word")
text.pack(fill="both", expand=True, padx=8, pady=8)
text.insert("1.0", "BEFORE\n")
text.focus_set()


def on_focus(_event=None) -> None:
    text.focus_set()


root.bind("<FocusIn>", on_focus)


def dump() -> None:
    out.write_text(text.get("1.0", "end"), encoding="utf-8")
    root.after(200, dump)


root.after(200, dump)
root.mainloop()
