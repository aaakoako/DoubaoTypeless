"""目标绑定回归；平台发键为替身，不是第三方应用验收。"""
from doubao_typeless.core.attempt import Attempt, Step
from doubao_typeless.platform.windows.focus import FocusSnapshot
from doubao_typeless.services.delivery import DeliveryService


def test_starting_on_other_control_never_touches_clipboard_or_pastes():
    expected = FocusSnapshot("Chrome", "A", 7, 10, 0, (1, 2), "composer")
    changed = expected._replace(runtime_id=(1, 3))
    actions = []
    service = DeliveryService(read_focus=lambda: changed,
        paste=lambda: actions.append("paste"),
        set_clipboard_text=lambda text: actions.append(text),
        set_clipboard_image=lambda data: actions.append(data))
    for prior in ([], [Step(0, "image", "already", "observed", "target_attachment")]):
        attempt = Attempt("a", "i", "b", "test", steps=list(prior))
        result = service.run(attempt, {"text": "private draft"}, expected_focus=expected, remote=True)
        assert result.error_code == "TARGET_CHANGED"
        assert result.result == ("PARTIAL" if prior else "NO_STEPS")
        assert result.steps == prior
    assert actions == []


def test_dynamic_title_change_preserves_same_control_binding():
    expected = FocusSnapshot("Chrome", "A", 7, 10, 0, (1, 2), "composer")
    actions = []
    service = DeliveryService(read_focus=lambda: expected._replace(title="B"),
        paste=lambda: actions.append("paste"), set_clipboard_text=lambda text: actions.append(text),
        set_clipboard_image=lambda data: None)
    result = service.run(Attempt("a", "i", "b", "test"), {"text": "draft"},
                         expected_focus=expected, remote=True)
    assert actions == ["draft", "paste"]
    assert result.result == "UNKNOWN"


def test_app_passes_captured_target_and_correlates_failure_receipt(tmp_path):
    from doubao_typeless.app import V3App
    from doubao_typeless.core.bundle import freeze_bundle
    app = V3App(data_dir=tmp_path / "isolated", port=0)
    expected = FocusSnapshot("Chrome", "A", 7, 10, 0, (1, 2), "composer")
    actions = []
    try:
        app.draft.text = "private draft"
        app._read_focus = lambda: expected
        app.delivery._read_focus = lambda: expected._replace(runtime_id=(1, 3))
        app.delivery._paste = lambda: actions.append("paste")
        app.delivery._set_text = lambda text: actions.append(text)
        bundle = freeze_bundle(app.draft, bundle_id="bound-bundle")
        result = app.deliver_and_finish({"intent_id":"current-intent", "_source":"remote"}, bundle)
        assert result["error_code"] == "TARGET_CHANGED"
        assert result["intent_id"] == "current-intent"
        assert result["phone_event"]["intent_id"] == "current-intent"
        assert app.draft.text == "private draft" and actions == []
    finally:
        app._commands.close(3)
        app.db.conn.close()
        app._lock.release()
