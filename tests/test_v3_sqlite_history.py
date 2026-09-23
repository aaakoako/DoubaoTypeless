"""SQLite history is the durable store when a db is attached."""
from __future__ import annotations

from doubao_typeless.services.history import HistoryService
from doubao_typeless.storage.db import V3DB


def test_history_records_into_sqlite_not_json(tmp_path):
    db = V3DB(tmp_path / "v3.sqlite")
    json_path = tmp_path / "history.json"
    hist = HistoryService(json_path, persist=True, db=db)
    hist.record(
        {
            "bundle_id": "b1",
            "draft_id": "d",
            "epoch": "e",
            "revision": 1,
            "manifest_hash": "h",
            "text": "hello sqlite",
            "assets": [{"asset_id": "a1"}],
        },
        attempt_result="CONFIRMED",
    )
    assert not json_path.exists()
    loaded = V3DB(tmp_path / "v3.sqlite").last_bundle()
    assert loaded["text"] == "hello sqlite"
    assert loaded["assets"][0]["asset_id"] == "a1"
    again = HistoryService(json_path, db=V3DB(tmp_path / "v3.sqlite"))
    assert again.last_bundle()["bundle_id"] == "b1"
