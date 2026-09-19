"""Isolated V3 vocabulary. Never reads or writes daily-use data/dictionary.txt."""
from __future__ import annotations

from pathlib import Path


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
