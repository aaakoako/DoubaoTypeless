"""SQLite persistence for V3. Image bytes stay in AssetStore, not in this file."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS migrations (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    referenced INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    owner_session_id TEXT
);
CREATE TABLE IF NOT EXISTS bundles (
    bundle_id TEXT PRIMARY KEY,
    draft_id TEXT,
    epoch TEXT,
    revision INTEGER,
    manifest_hash TEXT,
    text TEXT,
    recorded_at REAL NOT NULL,
    attempt_result TEXT
);
CREATE TABLE IF NOT EXISTS bundle_assets (
    bundle_id TEXT,
    asset_id TEXT,
    ordinal INTEGER,
    PRIMARY KEY (bundle_id, ordinal)
);
CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    bundle_id TEXT,
    result TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS attempt_steps (
    attempt_id TEXT,
    idx INTEGER,
    kind TEXT,
    asset_id TEXT,
    state TEXT,
    evidence TEXT,
    PRIMARY KEY (attempt_id, idx)
);
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    session_id TEXT,
    last_seen REAL
);
"""


class V3DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.execute("INSERT OR IGNORE INTO migrations(id, name) VALUES (1, 'v3-init')")
            cols = {row[1] for row in self.conn.execute("PRAGMA table_info(assets)")}
            if "owner_session_id" not in cols:
                self.conn.execute("ALTER TABLE assets ADD COLUMN owner_session_id TEXT")
            self.conn.commit()

    def upsert_asset(
        self,
        asset_id: str,
        sha256: str,
        nbytes: int,
        *,
        referenced: bool = False,
        created_at: float | None = None,
        owner_session_id: str = "",
    ) -> None:
        with self._lock:
            self.conn.execute(
            "INSERT OR REPLACE INTO assets(asset_id, sha256, bytes, referenced, created_at, owner_session_id) VALUES (?,?,?,?,?,?)",
            (asset_id, sha256, nbytes, int(referenced), time.time() if created_at is None else created_at, owner_session_id or None),
        )
        self.conn.commit()

    def asset(self, sha256: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM assets WHERE sha256=?", (sha256,)).fetchone()
        return dict(row) if row else None

    def asset_by_id(self, asset_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
        return dict(row) if row else None

    def mark_referenced(self, asset_id: str, referenced: bool = True) -> None:
        self.conn.execute("UPDATE assets SET referenced=? WHERE asset_id=?", (int(referenced), asset_id))
        self.conn.commit()

    def gc_unreferenced(self, *, now: float, ttl_s: float, protected_ids: set[str]) -> list[str]:
        rows = self.conn.execute("SELECT asset_id, referenced, created_at FROM assets").fetchall()
        removed: list[str] = []
        for row in rows:
            asset_id = row["asset_id"]
            if asset_id in protected_ids or row["referenced"]:
                continue
            if now - float(row["created_at"]) <= ttl_s:
                continue
            self.conn.execute("DELETE FROM assets WHERE asset_id=?", (asset_id,))
            removed.append(asset_id)
        self.conn.commit()
        return removed

    def record_bundle(self, bundle: dict[str, Any], *, attempt_result: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO bundles(bundle_id, draft_id, epoch, revision, manifest_hash, text, recorded_at, attempt_result) VALUES (?,?,?,?,?,?,?,?)",
                (
                    bundle["bundle_id"],
                    bundle.get("draft_id"),
                    bundle.get("epoch"),
                    bundle.get("revision"),
                    bundle.get("manifest_hash"),
                    bundle.get("text", ""),
                    time.time(),
                    attempt_result,
                ),
            )
            self.conn.execute("DELETE FROM bundle_assets WHERE bundle_id=?", (bundle["bundle_id"],))
            for i, asset in enumerate(bundle.get("assets") or []):
                aid = asset.get("asset_id")
                self.conn.execute(
                    "INSERT INTO bundle_assets(bundle_id, asset_id, ordinal) VALUES (?,?,?)",
                    (bundle["bundle_id"], aid, i),
                )
                if aid:
                    self.mark_referenced(aid, True)
            self.conn.commit()

    def last_bundle(self) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM bundles ORDER BY recorded_at DESC LIMIT 1").fetchone()
        if not row:
            return None
        assets = [
            {"asset_id": r["asset_id"]}
            for r in self.conn.execute(
                "SELECT asset_id FROM bundle_assets WHERE bundle_id=? ORDER BY ordinal",
                (row["bundle_id"],),
            )
        ]
        return {
            "bundle_id": row["bundle_id"],
            "draft_id": row["draft_id"],
            "epoch": row["epoch"],
            "revision": row["revision"],
            "manifest_hash": row["manifest_hash"],
            "text": row["text"],
            "assets": assets,
        }

    def list_history(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM bundles ORDER BY recorded_at").fetchall()
        items = []
        for row in rows:
            items.append(
                {
                    "recorded_at": row["recorded_at"],
                    "attempt_result": row["attempt_result"],
                    "bundle": {
                        "bundle_id": row["bundle_id"],
                        "draft_id": row["draft_id"],
                        "epoch": row["epoch"],
                        "revision": row["revision"],
                        "manifest_hash": row["manifest_hash"],
                        "text": row["text"],
                        "assets": [
                            {"asset_id": r["asset_id"]}
                            for r in self.conn.execute(
                                "SELECT asset_id FROM bundle_assets WHERE bundle_id=? ORDER BY ordinal",
                                (row["bundle_id"],),
                            )
                        ],
                    },
                }
            )
        return items

    def record_attempt(self, attempt_id: str, bundle_id: str, result: str, steps: list[dict]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO attempts(attempt_id, bundle_id, result, created_at) VALUES (?,?,?,?)",
            (attempt_id, bundle_id, result, time.time()),
        )
        self.conn.execute("DELETE FROM attempt_steps WHERE attempt_id=?", (attempt_id,))
        for step in steps:
            self.conn.execute(
                "INSERT INTO attempt_steps(attempt_id, idx, kind, asset_id, state, evidence) VALUES (?,?,?,?,?,?)",
                (
                    attempt_id,
                    step.get("index", 0),
                    step.get("kind"),
                    step.get("asset_id"),
                    step.get("state"),
                    step.get("evidence"),
                ),
            )
        self.conn.commit()
