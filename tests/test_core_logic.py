from __future__ import annotations

import json
import socket

import pytest

import updater
from config import api_key_for_http_header
from diagnostics import (
    export_diagnostics_json,
    redact_log_line,
    safe_recent_log_lines,
    tcp_connects,
)
from polish import (
    LearnJsonError,
    build_compact_learn_item,
    effective_chat_temperature,
    load_dict_suggestions_pending,
    parse_learn_model_json,
    save_dict_suggestions_pending,
    split_dictionary_file,
    write_dictionary_file,
    zhipu_coding_openai_model_id,
)
from providers_registry import detect_provider_name
from updater import (
    _write_update_task_wrapper,
    apply_mirror_prefix,
    compare_version_tags,
    pick_exe_asset,
    remote_is_newer,
)


def test_api_key_sanitizer_removes_wrappers_and_bad_pastes():
    assert api_key_for_http_header("  Bearer sk-test123\n") == "sk-test123"
    assert api_key_for_http_header("\ufeff\u200babc\r\n") == "abc"
    assert api_key_for_http_header("Traceback ModuleNotFoundError: bad paste") == ""


def test_provider_and_model_helpers():
    assert detect_provider_name("https://api.deepseek.com/v1") == "DeepSeek"
    assert detect_provider_name("https://example.test/v1") == "自定义"
    assert zhipu_coding_openai_model_id(
        "GLM-5.1", "https://open.bigmodel.cn/api/coding/paas/v4"
    ) == "glm-5.1"
    assert effective_chat_temperature("https://api.minimaxi.com/v1", 2.0) == 1.0
    assert effective_chat_temperature("https://api.minimaxi.com", 0.0) == 0.01


def test_updater_asset_and_version_helpers():
    assets = [
        {"name": "notes.txt", "browser_download_url": "https://x/notes.txt"},
        {"name": "DoubaoTypeless.exe", "browser_download_url": "https://x/app.exe"},
        {"name": "other.exe", "browser_download_url": "https://x/other.exe"},
    ]
    assert pick_exe_asset(assets)["name"] == "DoubaoTypeless.exe"
    assert remote_is_newer("v0.4.1", "0.4.0") is True
    assert remote_is_newer("v0.4.0", "0.4.0") is False
    assert remote_is_newer("v0.4.0", "0.4") is False
    assert compare_version_tags("v0.4", "0.4.0") == 0
    assert compare_version_tags("v0.4.10", "0.4.2") == 1
    assert (
        apply_mirror_prefix("https://github.com/a/b", "https://mirror.example/")
        == "https://mirror.example/https://github.com/a/b"
    )


def test_update_task_wrapper_contains_cleanup(tmp_path):
    bat = tmp_path / "_DoubaoTypeless_update.bat"
    bat.write_text("@echo off\n", encoding="utf-8")
    wrapper = _write_update_task_wrapper(bat, "DoubaoTypeless_Update_Test")
    text = wrapper.read_text(encoding="utf-8")
    assert str(bat.resolve()) in text
    assert 'schtasks.exe /Delete /TN "%DT_UPDATE_TASK%" /F' in text
    assert 'del "%~f0"' in text


def test_update_bat_uses_no_console_safe_sleep(tmp_path, monkeypatch):
    current = tmp_path / "DoubaoTypeless.exe"
    downloaded = tmp_path / "DoubaoTypeless.new.exe"
    current.write_bytes(b"old exe placeholder")
    downloaded.write_bytes(b"new exe placeholder")
    monkeypatch.setattr(updater, "app_root", lambda: tmp_path)

    bat = updater.write_update_bat(current, downloaded, wait_pid=0)
    text = bat.read_text(encoding="utf-8")

    assert "timeout /t" not in text.lower()
    assert "Start-Sleep" in text
    assert "call :sleep_sec 10" in text
    assert "call :sleep_sec 4" in text


def test_learn_json_parser_chooses_result_over_echo():
    logs: list[str] = []
    raw = (
        '{"items":[{"mode":"no_diff","text":"用户正文"}]}\n'
        '说明\n```json\n{"notes":["n"],"candidate_pairs":[{"wrong":"豆包","correct":"Doubao","confidence":0.8}],"domain_terms":["Doubao"]}\n```'
    )
    parsed = parse_learn_model_json(raw, logs.append)
    assert parsed["domain_terms"] == ["Doubao"]
    assert parsed["candidate_pairs"][0]["correct"] == "Doubao"


def test_learn_json_parser_rejects_echo_only():
    with pytest.raises(LearnJsonError):
        parse_learn_model_json('{"items":[]}', lambda _m: None, quiet_failure=True)


def test_compact_learn_item_shapes():
    assert build_compact_learn_item("a", "a", "a", []) == {"mode": "no_diff", "text": "a"}
    changed = build_compact_learn_item("raw", "raw", "final", [{"id": "s1"}])
    assert changed["llm_same_as_raw"] is True
    assert changed["final_text"] == "final"
    assert changed["accepted_suggestions"] == [{"id": "s1"}]


def test_dictionary_and_pending_files_roundtrip(tmp_path):
    dict_path = tmp_path / "dictionary.txt"
    write_dictionary_file(dict_path, [("错词", "正词")], header_lines=["# header"])
    header, pairs = split_dictionary_file(dict_path)
    assert header == ["# header"]
    assert pairs == [("错词", "正词")]

    pending_path = tmp_path / "pending.json"
    save_dict_suggestions_pending(
        pending_path,
        [
            {"wrong": "a", "correct": "b", "confidence": 0.7},
            {"wrong": "", "correct": "ignored"},
        ],
    )
    assert load_dict_suggestions_pending(pending_path) == [
        {"wrong": "a", "correct": "b", "confidence": 0.7}
    ]


def test_diagnostics_log_redaction_and_export(tmp_path):
    line = "[suggest.result] before='用户正文' after='修正正文' api_key: sk-secret12345"
    redacted = redact_log_line(line)
    assert "用户正文" not in redacted
    assert "修正正文" not in redacted
    assert "sk-secret" not in redacted

    log_path = tmp_path / "debug.log"
    log_path.write_text(line + "\n[bridge] 手机已连接\n", encoding="utf-8")
    recent = safe_recent_log_lines(log_path)
    assert any("[bridge]" in x for x in recent)
    assert all("用户正文" not in x for x in recent)

    out = export_diagnostics_json({"hello": "world"}, tmp_path)
    assert json.loads(out.read_text(encoding="utf-8")) == {"hello": "world"}


def test_tcp_connects_detects_local_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert tcp_connects("127.0.0.1", port, timeout=0.2) is True
    finally:
        sock.close()
