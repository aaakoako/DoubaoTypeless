"""Recent bundles. Last delivered is not the current draft."""
from __future__ import annotations

import json
import copy
import threading
import time
from pathlib import Path
from typing import Any

MAX_ITEMS = 20
TTL_S = 24 * 3600
MAX_BYTES = 256 * 1024 * 1024


class HistoryService:
    def __init__(self, path: Path, *, persist: bool = True, db=None):
        self.path = Path(path)
        self.persist = persist
        self.db = db
        self.items: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        if db is not None:
            self.items = db.list_history()
        elif persist and self.path.is_file():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = list(raw.get("items") or [])
        self.gc()

    def record(self, bundle: dict[str, Any], *, attempt_result: str) -> None:
        with self._lock:
            safe = copy.deepcopy(bundle)
            safe["assets"] = [{k: v for k, v in a.items() if k != "bytes_data"}
                              for a in safe.get("assets", [])]
            previous = list(self.items)
            try:
                entry = {"recorded_at": time.time(), "attempt_result": attempt_result, "bundle": safe}
                self.items = [i for i in self.items if i["bundle"]["bundle_id"] != bundle["bundle_id"]] + [entry]
                if self.db is not None:
                    self.db.record_bundle(safe, attempt_result=attempt_result)
                self.gc(protected_ids={bundle["bundle_id"]})
                if self.db is None:
                    self._flush()
            except Exception:
                self.items = previous
                raise

    def last_bundle(self) -> dict[str, Any] | None:
        if not self.items:
            return None
        return copy.deepcopy(self.items[-1]["bundle"])

    def copy_to_new_draft(self, bundle: dict[str, Any]) -> dict[str, Any]:
        return {
            "text": bundle.get("source_text", bundle.get("text", "")),
            "assets": copy.deepcopy(bundle.get("assets") or []),
            "source_bundle_id": bundle.get("bundle_id"),
            "action": "copy_to_new_draft",
        }

    def replay_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        out = copy.deepcopy(bundle)
        out["action"] = "replay_bundle"
        return out

    def delete(self, bundle_id: str) -> None:
        with self._lock:
            keep = [i for i in self.items if i["bundle"]["bundle_id"] != bundle_id]
            if self.db is not None:
                self.db.retain_history({i["bundle"]["bundle_id"] for i in keep})
            self.items = keep
            if self.db is None:
                self._flush()

    def gc(self, *, now: float | None = None, protected_ids: set[str] | None = None) -> None:
        now = time.time() if now is None else now
        protected_ids = protected_ids or set()
        kept: list[dict[str, Any]] = []
        total = 0
        for item in reversed(self.items):
            bid = item["bundle"]["bundle_id"]
            age = now - float(item["recorded_at"])
            size = sum(int(a.get("bytes") or 0) for a in item["bundle"].get("assets") or [])
            size += len((item["bundle"].get("text") or "").encode("utf-8"))
            if bid not in protected_ids:
                if age > TTL_S:
                    continue
                if len(kept) >= MAX_ITEMS:
                    continue
                if total + size > MAX_BYTES:
                    continue
            kept.append(item)
            total += size
        kept.reverse()
        if self.db is not None and len(kept) != len(self.items):
            self.db.retain_history({i["bundle"]["bundle_id"] for i in kept})
        self.items = kept

    def can_accept_bytes(self, extra: int) -> bool:
        used = sum(
            sum(int(a.get("bytes") or 0) for a in i["bundle"].get("assets") or [])
            for i in self.items
        )
        return used + extra <= MAX_BYTES

    def diagnostics(self) -> dict[str, Any]:
        return {
            "persist": self.persist,
            "count": len(self.items),
            "oldest_age_s": (
                time.time() - float(self.items[0]["recorded_at"]) if self.items else 0
            ),
        }

    def _flush(self) -> None:
        if not self.persist:
            return
        from doubao_typeless.storage.draft_snapshot import write_json_atomic
        write_json_atomic(self.path, {"items": self.items})
