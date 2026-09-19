"""A18: preview/test identity stays off the daily-use instance."""
from __future__ import annotations

from pathlib import Path

from doubao_typeless.app import V3App
from doubao_typeless.runtime import PREVIEW_NAME, daily_use_config_candidates, pick_port, v3_data_dir
from doubao_typeless.ui.desktop import RESULT_LABELS, _result_label
from doubao_typeless.ui.single_instance import PIPE, pipe_name
from doubao_typeless.ui.v3_startup import DAILY_RUN_NAME, V3_RUN_NAME


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


def test_preview_names_never_equal_daily_use():
    assert PIPE == "DoubaoTypelessV3Preview"
    assert V3_RUN_NAME == "DoubaoTypelessV3Preview"
    assert V3_RUN_NAME != DAILY_RUN_NAME
    assert DAILY_RUN_NAME == "DoubaoTypeless"
    assert pipe_name() != DAILY_RUN_NAME


def test_pick_port_skips_occupied_wildcard():
    import socket

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("0.0.0.0", 0))
    occupied = holder.getsockname()[1]
    try:
        chosen = pick_port(occupied)
        assert chosen != occupied
        assert occupied < chosen <= occupied + 16
    finally:
        holder.close()


def test_pipe_override_does_not_touch_live_preview(monkeypatch):
    monkeypatch.setenv("DT_V3_PIPE", "DoubaoTypelessV3Preview-pytest")
    assert pipe_name() == "DoubaoTypelessV3Preview-pytest"
    assert PIPE == "DoubaoTypelessV3Preview"


def test_default_data_dir_is_not_daily_config(tmp_path, monkeypatch):
    monkeypatch.delenv("DT_V3_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    path = v3_data_dir()
    assert path.name == PREVIEW_NAME
    daily = daily_use_config_candidates()
    assert all(item != path / "config.json" for item in daily)
    assert all(item.parent != path for item in daily)
    assert Path(tmp_path / "local" / "DoubaoTypeless" / "config.json") in daily


def test_v3_app_does_not_write_repo_or_daily_config(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    daily = tmp_path / "roaming" / "DoubaoTypeless" / "config.json"
    daily.parent.mkdir(parents=True)
    daily.write_text('{"keep": true}', encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = V3App(data_dir=tmp_path / "preview", port=0)
    app.draft.text = "隔离"
    app._save_draft()
    assert not (repo / "config.json").exists() or "隔离" not in (repo / "config.json").read_text(encoding="utf-8", errors="replace")
    assert daily.read_text(encoding="utf-8") == '{"keep": true}'
    assert app.data_dir == tmp_path / "preview"


def test_insert_current_abc_is_per_round(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_delivery(app, pasted)
    rounds = ("A短句", "B这是一段更长的说明用来确认当轮不是累加", "C第一行\n第二行")
    for text in rounds:
        pasted.clear()
        app.draft.text = text
        app.draft.revision += 1
        out = app.insert_current()
        assert out is not None
        assert f"text:{text}" in pasted
        assert app._copied_text == text
        assert app.draft.text == ""
        assert app.hud.visible is False
    last = app.history.last_bundle()
    assert last is not None
    assert last["text"] == rounds[-1]
    app.draft.text = "新稿B"
    app.recall_last()
    assert app.draft.text == "新稿B"


def test_copy_then_new_draft_keeps_last(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_delivery(app, pasted)
    app.draft.text = "先插入A"
    app.insert_current()
    app.draft.text = "只复制B"
    assert app.copy_text() == "只复制B"
    assert app.draft.text == "只复制B"
    app.start_new_draft()
    assert app.draft.text == ""
    last = app.history.last_bundle()
    assert last is not None
    assert last["text"] == "先插入A"


def test_recent_result_labels_are_human():
    assert _result_label("CONFIRMED") == "已插入"
    assert _result_label("UNKNOWN") == "上次结果未知"
    assert "CONFIRMED" not in RESULT_LABELS.values()


def test_hud_copy_is_wired(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    copied: list[str] = []
    app._set_text = lambda text: copied.append(text)
    app.draft.text = "HUD复制"
    assert app.hud._on_copy is not None
    app.hud._on_copy()
    assert copied == ["HUD复制"]
    assert app.draft.text == "HUD复制"
