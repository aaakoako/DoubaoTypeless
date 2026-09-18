"""Real Windows text box for S1. Not Cursor, not a file-backed fake Composer."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import tkinter as tk


def main() -> int:
    state_path = Path(sys.argv[1])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.title("DT-S1-TextTarget")
    root.geometry("480x220")
    root.attributes("-topmost", True)
    box = tk.Text(root, wrap="word", font=("Segoe UI", 14))
    box.pack(fill="both", expand=True)
    box.insert("1.0", "")
    box.focus_force()
    root.focus_force()

    def dump() -> None:
        payload = {
            "title": root.title(),
            "text": box.get("1.0", "end-1c"),
            "has_focus": root.focus_displayof() is not None,
        }
        state_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        root.after(50, dump)

    root.after(50, dump)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
