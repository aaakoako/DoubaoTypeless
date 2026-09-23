"""Isolated V3 vocabulary. Never writes daily-use data/dictionary.txt."""
from __future__ import annotations

import os
from pathlib import Path

from doubao_typeless.runtime import PREVIEW_NAME


def vocab_path(data_dir: Path) -> Path:
    return Path(data_dir) / "vocabulary.txt"


def load_vocab(data_dir: Path) -> str:
    path = vocab_path(data_dir)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def save_vocab(data_dir: Path, text: str) -> Path:
    path = vocab_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((text or "").replace("\r\n", "\n"), encoding="utf-8")
    return path


def parse_mappings(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "->" in line:
            left, right = line.split("->", 1)
        elif "=" in line:
            left, right = line.split("=", 1)
        else:
            continue
        src, dst = left.strip(), right.strip()
        if src and dst:
            out.append((src, dst))
    return out


def daily_vocab_candidates() -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    roots: list[Path] = []
    for env in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            roots.append(Path(base) / "DoubaoTypeless")
    for root in roots:
        if PREVIEW_NAME in root.parts:
            continue
        for rel in ("data/dictionary.txt", "dictionary.txt"):
            path = root / rel
            resolved = path.resolve() if path.exists() else path
            if PREVIEW_NAME in resolved.parts or resolved in seen:
                continue
            seen.add(resolved)
            found.append(path)
    return found


def inspect_vocab_file(path: Path) -> dict:
    target = Path(path)
    if not target.is_file():
        return {"present": False, "path": str(target), "text": "", "mappings": 0}
    before = target.read_bytes()
    text = before.decode("utf-8", errors="replace")
    after = target.read_bytes()
    if after != before:
        raise RuntimeError("import must not write the source vocab")
    return {
        "present": True,
        "path": str(target),
        "text": text,
        "mappings": len(parse_mappings(text)),
    }


def import_vocab_preview(data_dir: Path, source: Path) -> dict:
    info = inspect_vocab_file(source)
    if not info["present"]:
        return {"imported": 0, "source": str(source), "ok": False}
    before = Path(source).read_bytes()
    current = load_vocab(data_dir)
    existing = {(src, dst) for src, dst in parse_mappings(current)}
    added = [f"{src} -> {dst}" for src, dst in parse_mappings(info["text"]) if (src, dst) not in existing]
    merged = current.rstrip()
    if added:
        merged = (merged + "\n" if merged else "") + "\n".join(added) + "\n"
        save_vocab(data_dir, merged)
    after = Path(source).read_bytes()
    if after != before:
        raise RuntimeError("import must not write the source vocab")
    return {"imported": len(added), "source": str(source), "ok": True}
