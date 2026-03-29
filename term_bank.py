"""
近窗话题内的专业术语库：与 dictionary.txt「误听→正确」错题集分离。
术语来自后台学习 JSON 的 domain_terms 与 candidate_pairs 的 correct；
前台纠错仅在「最近 N 条审阅终稿」正文中出现过的术语才会注入 system，控制 token 与噪声。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_key(term: str) -> str:
    t = (term or "").strip()
    if not t:
        return ""
    letters = [c for c in t if c.isalpha()]
    if letters and all(ord(c) < 128 for c in letters):
        return t.lower()
    return t


def _term_ok(term: str) -> bool:
    t = term.strip()
    if len(t) < 2 or len(t) > 28:
        return False
    if "\n" in t or "\r" in t or "=" in t:
        return False
    if re.fullmatch(r"[\s\W_]+", t):
        return False
    return True


def load_recent_final_texts(history_path: str | Path, n: int) -> list[str]:
    """审阅历史文件为「新在前」的列表，取最近 n 条 final_text。"""
    p = Path(history_path)
    if not p.exists() or n <= 0:
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data[:n]:
        if not isinstance(item, dict):
            continue
        ft = (item.get("final_text") or "").strip()
        if ft:
            out.append(ft)
    return out


@dataclass
class TermEntry:
    display: str
    hits: int = 1
    last_ts: str = ""

    def to_json(self) -> dict:
        return {"display": self.display, "hits": self.hits, "last_ts": self.last_ts}

    @classmethod
    def from_json(cls, d: Any) -> Optional["TermEntry"]:
        if not isinstance(d, dict):
            return None
        disp = str(d.get("display", "")).strip()
        if not _term_ok(disp):
            return None
        try:
            hits = int(d.get("hits", 1))
        except (TypeError, ValueError):
            hits = 1
        hits = max(1, min(9999, hits))
        ts = str(d.get("last_ts", "")).strip() or _utc_now_iso()
        return cls(display=disp, hits=hits, last_ts=ts)


class TermBank:
    def __init__(
        self,
        path: str | Path,
        *,
        max_store: int = 300,
        log: Optional[Callable[[str], None]] = None,
    ):
        self.path = Path(path)
        self.max_store = max(20, min(2000, int(max_store)))
        self._log = log
        self._by_key: dict[str, TermEntry] = {}

    def __len__(self) -> int:
        return len(self._by_key)

    def load(self):
        self._by_key.clear()
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            if self._log:
                self._log(f"[terms] 加载失败，将使用空库: {e}")
            return
        if isinstance(data, dict) and isinstance(data.get("terms"), list):
            for item in data["terms"]:
                ent = TermEntry.from_json(item)
                if ent is None:
                    continue
                k = _normalize_key(ent.display)
                if not k:
                    continue
                self._by_key[k] = ent
        elif isinstance(data, list):
            for item in data:
                ent = TermEntry.from_json(item)
                if ent is None:
                    continue
                k = _normalize_key(ent.display)
                if not k:
                    continue
                self._by_key[k] = ent

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        terms = sorted(
            (e.to_json() for e in self._by_key.values()),
            key=lambda x: (-int(x.get("hits", 1)), x.get("last_ts", "")),
        )
        payload = {"version": 1, "updated": _utc_now_iso(), "terms": terms}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _prune(self):
        if len(self._by_key) <= self.max_store:
            return
        # 按 last_ts 最旧淘汰（解析失败放最前）
        def sort_key(kv: tuple[str, TermEntry]):
            ts = kv[1].last_ts
            return ts

        items = sorted(self._by_key.items(), key=sort_key)
        overflow = len(self._by_key) - self.max_store
        for i in range(overflow):
            k, _ = items[i]
            self._by_key.pop(k, None)

    def _bump(self, display: str):
        if not _term_ok(display):
            return
        k = _normalize_key(display)
        if not k:
            return
        now = _utc_now_iso()
        if k in self._by_key:
            e = self._by_key[k]
            e.hits = min(9999, e.hits + 1)
            e.last_ts = now
            if len(display) >= len(e.display):
                e.display = display.strip()
        else:
            self._by_key[k] = TermEntry(display=display.strip(), hits=1, last_ts=now)
        self._prune()

    def merge_from_learn_parsed(self, parsed: dict, *, log_hint: str = ""):
        if not isinstance(parsed, dict):
            return
        n0 = len(self._by_key)
        for t in parsed.get("domain_terms") or []:
            if isinstance(t, str) and _term_ok(t):
                self._bump(t)
        for p in parsed.get("candidate_pairs") or []:
            if not isinstance(p, dict):
                continue
            c = str(p.get("correct", "")).strip()
            if _term_ok(c):
                self._bump(c)
        n1 = len(self._by_key)
        if self._log and n1 != n0:
            self._log(
                f"[terms] 已合并学习结果中的术语 累计={n1} (Δ{n1 - n0}){log_hint}"
            )
        try:
            self.save()
        except Exception as e:
            if self._log:
                self._log(f"[terms] 保存失败: {e}")

    @staticmethod
    def _appears_in_finals(display: str, finals: list[str]) -> bool:
        if not display or not finals:
            return False
        for f in finals:
            if display in f:
                return True
        letters = [c for c in display if c.isalpha()]
        if letters and all(ord(c) < 128 for c in letters):
            dl = display.lower()
            for f in finals:
                if dl in f.lower():
                    return True
        return False

    def as_suggest_hint(self, recent_finals: list[str], cap: int) -> str:
        """仅包含在最近审阅终稿正文中出现过的术语（近窗话题）。"""
        cap = max(5, min(120, int(cap)))
        if not recent_finals or not self._by_key:
            return ""
        scored: list[tuple[int, str, str]] = []
        for e in self._by_key.values():
            if not self._appears_in_finals(e.display, recent_finals):
                continue
            scored.append((e.hits, e.last_ts, e.display))
        scored.sort(key=lambda x: (-x[0], x[1]))
        terms = [t for *_, t in scored[:cap]]
        if not terms:
            return ""
        return (
            "【近期审阅话题中出现的专业术语（仅作拼写与专名参考，不是误听对照表；"
            "不确定时保持 ASR 原文）】\n"
            + "、".join(terms)
        )
