"""S5 review gates: observer must not fake CONFIRMED; update/vocab stay read-only."""
from __future__ import annotations

from pathlib import Path

from doubao_typeless.adapters.observable_target import from_env
from doubao_typeless.services.byok import chat_url, url_join_note
from doubao_typeless.services.v3_update import DOWNLOAD_PAGE, check_preview_update
from doubao_typeless.storage.vocab_store import daily_vocab_candidates, import_vocab_preview, inspect_vocab_file


def test_target_state_alone_does_not_enable_file_observer(tmp_path, monkeypatch):
    monkeypatch.setenv("DT_V3_TARGET_STATE", str(tmp_path / "target.json"))
    monkeypatch.delenv("DT_V3_ALLOW_FILE_OBSERVER", raising=False)
    assert from_env() is None


def test_file_observer_requires_explicit_allow(tmp_path, monkeypatch):
    path = tmp_path / "target.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DT_V3_TARGET_STATE", str(path))
    monkeypatch.setenv("DT_V3_ALLOW_FILE_OBSERVER", "1")
    observer = from_env()
    assert observer is not None
    assert observer.path == path


def test_check_update_never_writes_or_replaces(tmp_path):
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    info = check_preview_update(get_json=lambda _url: {"tag_name": "v0.9.9"})
    assert info["auto_replace"] is False
    assert info["writes_daily_use"] is False
    assert info["page"] == DOWNLOAD_PAGE
    assert info["latest"] == "0.9.9"
    assert "不会自动" in info["message"] or "不会覆盖" in info["message"]
    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_vocab_import_does_not_write_source(tmp_path):
    source = tmp_path / "daily" / "dictionary.txt"
    source.parent.mkdir()
    source.write_text("错 -> 对\n", encoding="utf-8")
    before = source.read_bytes()
    dest = tmp_path / "preview"
    out = import_vocab_preview(dest, source)
    assert out["ok"] is True
    assert out["imported"] == 1
    assert source.read_bytes() == before
    again = import_vocab_preview(dest, source)
    assert again["imported"] == 0
    assert source.read_bytes() == before


def test_daily_vocab_candidates_skip_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roam"))
    preview = tmp_path / "local" / "DoubaoTypeless" / "preview-v3" / "dictionary.txt"
    preview.parent.mkdir(parents=True)
    preview.write_text("x -> y\n", encoding="utf-8")
    daily = tmp_path / "roam" / "DoubaoTypeless" / "data" / "dictionary.txt"
    daily.parent.mkdir(parents=True)
    daily.write_text("a -> b\n", encoding="utf-8")
    found = [p for p in daily_vocab_candidates() if p.is_file()]
    assert daily in found
    assert preview not in found
    assert inspect_vocab_file(daily)["mappings"] == 1


def test_chat_url_does_not_double_complete():
    full = "https://api.example/v1/chat/completions"
    assert chat_url(full) == full
    assert chat_url("https://api.example/v1") == "https://api.example/v1/chat/completions"
    assert "不会再拼接" in url_join_note("")
    assert "chat/completions" in url_join_note("https://api.example/v1")
