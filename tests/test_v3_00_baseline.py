"""V3-00 基线冻结：先暴露隔离与证据缺口，再允许落地。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

import config as config_mod
from config import Config

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "legacy"
SANITIZED_CONFIG = FIXTURE_DIR / "config.sanitized.json"
DAILY_SNAPSHOT = ROOT / "docs" / "evidence" / "baseline" / "AC3-004" / "daily-use-snapshot.json"
REVIEW_SHA = "e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5"
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|Bearer\s+\S+|llm_api_key\"\s*:\s*\"(?!\"|REDACTED)[^\"]{8,})",
    re.I,
)
DAILY_PATHS = [
    ROOT / "config.json",
    ROOT / "debug.log",
    ROOT / "data" / "review_history.json",
    ROOT / "data" / "learn_pending.json",
    ROOT / "data" / "learning_samples.jsonl",
    ROOT / "data" / "domain_terms.json",
    ROOT / "data" / "dict_suggestions_pending.json",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_legacy_sanitized_config_fixture_exists_and_has_no_secrets():
    assert SANITIZED_CONFIG.is_file(), "缺少 tests/fixtures/legacy/config.sanitized.json"
    raw = SANITIZED_CONFIG.read_text(encoding="utf-8")
    assert SECRET_RE.search(raw) is None
    data = json.loads(raw)
    assert data["llm_enabled"] is False
    assert data["learn_enabled"] is False
    assert data["llm_api_key"] == ""
    assert data["learn_api_key"] == ""
    assert data["llm_api_keys_by_provider"] == {}
    assert data["learn_api_keys_by_provider"] == {}
    assert "v3-00" in json.dumps(data, ensure_ascii=False).lower()


def test_fixtures_directory_contains_no_user_body_or_keys():
    assert FIXTURE_DIR.is_dir()
    for path in FIXTURE_DIR.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert SECRET_RE.search(text) is None
        lowered = text.lower()
        assert "sk-proj-" not in lowered
        assert "BEGIN PRIVATE KEY" not in text


def test_config_from_sanitized_fixture_does_not_write_daily_use(tmp_path, monkeypatch):
    assert SANITIZED_CONFIG.is_file()
    isolated = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", isolated)
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    payload = json.loads(SANITIZED_CONFIG.read_text(encoding="utf-8"))
    known = {k: v for k, v in payload.items() if k in Config.__dataclass_fields__}
    cfg = Config(**known)
    dumped = asdict(cfg)
    assert dumped["llm_api_key"] == ""
    assert dumped["learn_api_key"] == ""
    assert not isolated.exists(), "读取脱敏样例不得隐式 save 到隔离路径以外的位置"
    assert not (ROOT / "config.json").exists()
    for path in DAILY_PATHS:
        if path.name == "dictionary.txt":
            continue
        assert not path.exists() or path.stat().st_size == 0 or path.name.endswith(".txt")


def test_daily_use_snapshot_matches_current_tree():
    assert DAILY_SNAPSHOT.is_file(), "缺少 AC3-004 日用目录指纹"
    snap = json.loads(DAILY_SNAPSHOT.read_text(encoding="utf-8"))
    assert snap["review_sha"] == REVIEW_SHA
    for rel, expected in snap["tracked_hashes"].items():
        path = ROOT / rel
        assert path.is_file(), f"快照后丢失 {rel}"
        assert _sha256(path) == expected, f"{rel} 已被改写"
    for rel in snap["must_remain_absent"]:
        assert not (ROOT / rel).exists(), f"禁止写入日用文件 {rel}"


@pytest.mark.parametrize("case_id", ["AC3-001", "AC3-002", "AC3-003", "AC3-004"])
def test_v3_00_case_evidence_exists(case_id: str):
    result = ROOT / "docs" / "evidence" / "baseline" / case_id / "result.json"
    assert result.is_file(), f"缺少 {result}"
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["case_id"] == case_id
    assert data["status"] in {"PASS", "FAIL", "BLOCKED_NATIVE", "NOT_RUN"}
    assert data["status"] != "NOT_RUN"
    assert isinstance(data.get("observed"), str) and data["observed"].strip()
    assert isinstance(data.get("expected"), str) and data["expected"].strip()
    assert data.get("commit_sha")
    assert data["commit_sha"] != "UNKNOWN"
    assert isinstance(data.get("evidence_paths"), list)
    env_path = result.parent / "environment.json"
    if data["status"] == "PASS" and case_id == "AC3-002":
        env = json.loads(env_path.read_text(encoding="utf-8"))
        assert env.get("real_windows") is True
        assert env.get("real_android_ime") is True
        assert env.get("html_prototype_used_as_product_pass") is not True
    if data["status"] == "PASS" and case_id == "AC3-003":
        env = json.loads(env_path.read_text(encoding="utf-8"))
        assert env.get("real_windows") is True
        assert (result.parent / "idle.png").is_file()
        assert (result.parent / "input.png").is_file()
        assert (result.parent / "hidden.png").is_file()


def test_alt_shift_i_skip_correction_is_recorded_for_migration():
    path = ROOT / "docs" / "evidence" / "baseline" / "AC3-003" / "hotkey-migration.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Alt+Shift+I" in text or "Alt-Shift-I" in text
    assert "跳过纠错" in text
    assert "召回" in text
    assert "不能双重执行" in text


def test_whiteboard_remains_in_v3_scope_not_deferred():
    readme = ROOT / "docs" / "pocket-composer-v3" / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "轻量白板" in text
    assert "不再把白板整体推迟" in text
    tasks = json.loads((ROOT / "docs" / "pocket-composer-v3" / "fixtures" / "tasks.json").read_text(encoding="utf-8"))
    v13 = next(t for t in tasks if t["id"] == "V3-13")
    assert v13["status"] == "NOT_STARTED"
    assert "白板" in v13["title"]
