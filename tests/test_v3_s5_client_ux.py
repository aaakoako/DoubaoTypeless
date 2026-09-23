"""Desktop image order, nicknames, and optional rewrite suggestions."""
from __future__ import annotations

from doubao_typeless.app import V3App
from doubao_typeless.services.byok import ByokService
from doubao_typeless.storage.credentials import device_label
from doubao_typeless.storage.settings_store import load_settings, save_settings
from doubao_typeless.ui.desktop import STYLESHEET


def test_device_label_uses_nickname_or_index():
    assert device_label("abc", {}, 1) == "手机 1"
    assert device_label("abc", {"abc": "客厅手机"}, 2) == "客厅手机"


def test_settings_keep_nickname_and_extra_hotkeys(tmp_path):
    save_settings(
        tmp_path,
        {
            "device_nicknames": {"dev1": "客厅手机"},
            "hotkey_expand": "<alt>+<shift>+e",
            "hotkey_capture": "<alt>+<shift>+s",
            "byok_prompt": "保持术语",
        },
    )
    stored = load_settings(tmp_path)
    assert stored["device_nicknames"]["dev1"] == "客厅手机"
    assert stored["hotkey_expand"] == "<alt>+<shift>+e"
    assert stored["byok_prompt"] == "保持术语"


def test_draft_image_previews_keep_order_and_missing(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    meta = app.store.put_png(png, width=1, height=1, role="photo")
    app.draft.assets = [meta, {"asset_id": "missing-id", "bytes": 0}]
    previews = app.draft_image_previews()
    assert [item["order"] for item in previews] == [1, 2]
    assert previews[0]["present"] is True
    assert previews[1]["present"] is False


def test_suggest_does_not_change_draft_until_applied(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.draft.text = "原文"
    app.byok = ByokService(
        endpoint="https://example.invalid/v1",
        api_key="k",
        model="m",
        post=lambda *_a, **_k: {"choices": [{"message": {"content": "建议稿"}}]},
    )
    out = app.suggest_text("原文")
    assert out["suggested"] == "建议稿"
    assert app.draft.text == "原文"
    assert app.apply_suggestion() is True
    assert app.draft.text == "建议稿"
    app.draft.text = "原文"
    app.suggest_text("原文")
    app.reject_suggestion()
    assert app.draft.text == "原文"
    assert app.apply_suggestion() is False


def test_byok_extra_prompt_enters_payload():
    seen: dict = {}

    def post(url, body, headers):
        seen.update(body)
        return {"choices": [{"message": {"content": "ok"}}]}

    svc = ByokService(
        endpoint="https://example.invalid/v1",
        api_key="k",
        model="chosen",
        extra_prompt="保持术语",
        temperature=0.2,
        post=post,
    )
    out = svc.polish("hi", draft_id="d", revision=1, current_draft_id="d", current_revision=1)
    assert out["status"] == "ok"
    assert seen["model"] == "chosen"
    assert seen["temperature"] == 0.2
    assert seen["messages"][0] == {"role": "system", "content": "保持术语"}


def test_native_stylesheet_covers_interactive_states():
    for token in (
        "QPushButton:hover",
        "QPushButton:pressed",
        "QPushButton:disabled",
        "QPushButton:focus",
        "QTabBar::tab:selected",
        "border-bottom: 2px solid",
        "QListWidget::item:selected",
    ):
        assert token in STYLESHEET
