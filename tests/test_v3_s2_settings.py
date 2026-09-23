"""BYOK uses the selected model; keys stay out of settings.json."""
from __future__ import annotations

from doubao_typeless.services.byok import ByokService, chat_url
from doubao_typeless.services.v3_diagnostics import snapshot
from doubao_typeless.app import V3App
from doubao_typeless.storage.credentials import AuthService, pairing_page_url
from doubao_typeless.storage.settings_store import load_settings, save_settings
from doubao_typeless.storage.vocab_store import load_vocab, parse_mappings, save_vocab


def test_byok_sends_selected_model_and_keeps_original_on_empty_reply():
    seen = {}

    def post(url, body, headers):
        seen["url"] = url
        seen["body"] = body
        return {"choices": [{"message": {"content": ""}}]}

    svc = ByokService(
        endpoint="https://example.invalid/v1",
        api_key="sk-test",
        model="deepseek-chat",
        post=post,
    )
    out = svc.polish("原文可插入", draft_id="d", revision=1, current_draft_id="d", current_revision=1)
    assert seen["body"]["model"] == "deepseek-chat"
    assert seen["url"] == chat_url("https://example.invalid/v1")
    assert out["status"] == "error"
    assert out["text"] == "原文可插入"


def test_settings_json_does_not_keep_plaintext_key(tmp_path):
    save_settings(tmp_path, {"byok_api_key": "sk-plain", "byok_model": "glm-4-flash"})
    assert load_settings(tmp_path)["byok_api_key"] == "sk-plain"
    raw = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "sk-plain" not in raw
    assert "glm-4-flash" in raw


def test_short_pairing_code_is_backup(tmp_path):
    auth = AuthService()
    long = auth.new_pairing_challenge()
    short = auth.current_short_code()
    assert short is not None and len(short) == 4
    url = pairing_page_url("http://192.168.1.8:8766", long)
    assert url.endswith(f"/?pair={long}")
    session = auth.complete_pairing(short)
    assert session.session_id


def test_vocab_and_diagnostics_stay_isolated(tmp_path):
    daily = tmp_path / "repo" / "data" / "dictionary.txt"
    daily.parent.mkdir(parents=True)
    daily.write_text("daily -> keep\n", encoding="utf-8")
    data = tmp_path / "preview-v3"
    save_vocab(data, "豆包 -> Doubao\n")
    assert parse_mappings(load_vocab(data)) == [("豆包", "Doubao")]
    assert daily.read_text(encoding="utf-8") == "daily -> keep\n"
    app = V3App(data_dir=data, port=0)
    app.draft.text = "用户正文不应进诊断"
    app.byok.api_key = "sk-should-hide"
    snap = snapshot(app)
    blob = str(snap)
    assert "用户正文不应进诊断" not in blob
    assert "sk-should-hide" not in blob
    assert snap["has_text"] is True
    assert snap["vocab_lines"] == 1
