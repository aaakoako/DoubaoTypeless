"""Ambiguous terms are hints only — never a permanent silent replace."""
from __future__ import annotations

AMBIGUOUS = {
    "midjourney": "可能是产品名，确认后再改",
    "opus": "可能是模型名 Opus，不会自动替换",
    "o pass": "可能是 Opus，仅提示",
    "o pu s": "可能是 Opus，仅提示",
}


def hints(text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    out: list[dict[str, str]] = []
    for token, note in AMBIGUOUS.items():
        if token in lowered:
            out.append({"token": token, "hint": note})
    return out


def apply_permanent(_: str) -> str:
    raise RuntimeError("terms must not permanently replace on first use")
