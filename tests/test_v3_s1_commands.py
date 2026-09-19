"""Command layer: current insert is not last history."""
from __future__ import annotations

from doubao_typeless.app import V3App
from doubao_typeless.core.policy import is_own_window
from doubao_typeless.ui.hud import TOKENS
from doubao_typeless.ui.tokens import TEXT_SIZE


def _stub_delivery(app, pasted, focus=("DT-S2-PasteTarget", "chatinput")):
    app._read_focus = lambda: focus
    app._saved_target = focus
    app.delivery._read_focus = lambda: focus
    app.delivery._paste = lambda: pasted.append("paste")
    app.delivery._set_text = lambda text: pasted.append(f"text:{text}")
    app.delivery._set_image = lambda _b: pasted.append("image")
    app.delivery._read_clipboard_text = None
    app.delivery._wait_modifiers = lambda: True
    app.delivery._is_locked = lambda: False
    app.delivery._observe_text = lambda: "unknown"
    app._set_text = lambda text: pasted.append(f"copy:{text}")


def test_insert_current_uses_draft_not_last_bundle(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_delivery(app, pasted)
    app.draft.text = "当前B"
    app.draft.revision = 2
    app.bridge.last_bundle = {"bundle_id": "old-a", "text": "上次A", "assets": []}
    out = app.insert_current()
    assert out is not None
    assert any(item == "text:当前B" for item in pasted)
    assert "上次A" not in "".join(pasted)
    assert app.bridge.last_bundle["text"] == "当前B"
    assert app.draft.text == ""
    assert app._copied_text == "当前B"
    assert app.hud.visible is False


def test_insert_last_does_not_steal_current_draft(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_delivery(app, pasted)
    app.draft.text = "当前B"
    app.bridge.last_bundle = None
    assert app.insert_last() is None
    assert app.draft.text == "当前B"
    assert pasted == []


def test_copy_text_does_not_clear_draft(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    copied: list[str] = []
    app._set_text = lambda text: copied.append(text)
    app.draft.text = "只复制不清稿"
    assert app.copy_text() == "只复制不清稿"
    assert app.draft.text == "只复制不清稿"
    assert copied == ["只复制不清稿"]


def test_restore_history_asks_when_current_draft_exists(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.draft.text = "电脑正在改"
    old = {"bundle_id": "hist", "text": "上次图文", "assets": []}
    assert app.restore_history(old) == "ask"
    assert app.draft.text == "电脑正在改"
    assert app.restore_history(old, replace=True) == "restored"
    assert app.draft.text == "上次图文"


def test_own_window_is_never_a_paste_target(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_delivery(app, pasted, focus=("Qt662QWindowIcon", "DoubaoTypeless"))
    app._saved_target = None
    app.draft.text = "不能贴进自己的窗"
    out = app.insert_current()
    assert out["result"] == "NO_STEPS"
    assert out["error_code"] == "OWN_WINDOW"
    assert "paste" not in pasted
    assert is_own_window("Qt662QWindowIcon", "当前图文")
    assert is_own_window("Tool", "DT-V3-HUD")
    assert not is_own_window("Notepad", "notes.txt")


def test_hud_tokens_follow_readable_long_text():
    assert TEXT_SIZE[0] == 400
    assert TOKENS["width"] == 400
    assert TOKENS["max_h"] == 300
    assert TOKENS["text_size"] == (400, 88)
