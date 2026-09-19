"""Recovery, capture policy, migration, intent idempotency, HUD wake rules."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from doubao_typeless.core.attempt import Attempt
from doubao_typeless.core.bundle import Draft, freeze_bundle
from doubao_typeless.core.intent import IntentLedger
from doubao_typeless.runtime import pick_port
from doubao_typeless.services.capture import CaptureService, REQUEST_TTL_S
from doubao_typeless.services.delivery import DeliveryService
from doubao_typeless.storage.credentials import Session
from doubao_typeless.storage.migration import inspect_legacy_config
from doubao_typeless.ui.recovery import plan_retry
from doubao_typeless.ui.tokens import TEXT_SIZE, IMAGE_SIZE, should_wake

COMPOSER = Path(__file__).resolve().parents[1] / "src/doubao_typeless/static/composer.html"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _session(**kwargs) -> Session:
    data = dict(device_id="d", session_id="s", token_hash="h", expires_at=9e12, allow_capture=True)
    data.update(kwargs)
    return Session(**data)


def test_ping_and_hello_do_not_wake_hud():
    assert should_wake("ping") is False
    assert should_wake("pong") is False
    assert should_wake("session.hello") is False
    assert should_wake("draft.update") is True
    assert TEXT_SIZE == (400, 88)
    assert IMAGE_SIZE == (400, 132)


def test_intent_duplicate_and_busy_do_not_double_paste():
    ledger = IntentLedger()
    assert ledger.begin("i1") == "accept"
    assert ledger.begin("i1") == "duplicate"
    assert ledger.begin("i2") == "busy"
    ledger.finish("i1", "UNKNOWN")
    assert ledger.begin("i2") == "accept"


def test_text_only_recovery_does_not_repeat_images():
    pasted = []
    svc = DeliveryService(
        paste=lambda: pasted.append("paste"),
        set_clipboard_image=lambda _b: pasted.append("image"),
        set_clipboard_text=lambda _t: pasted.append("text"),
        read_focus=lambda: ("ComposerPane", "chatinput"),
        observe_image=lambda: "observed",
        observe_text=lambda: "observed",
    )
    attempt = Attempt("a", "i", "b", "cursor_windows")
    bundle = {
        "text": "only text",
        "assets": [{"asset_id": "img-1", "bytes_data": PNG}],
    }
    out = svc.run(attempt, bundle, mode="text_only")
    assert "image" not in pasted
    assert "text" in pasted
    assert out.steps and out.steps[0].kind == "text"


def test_remaining_verified_skips_observed_images():
    pasted = []
    svc = DeliveryService(
        paste=lambda: pasted.append("paste"),
        set_clipboard_image=lambda _b: pasted.append(_b),
        set_clipboard_text=lambda _t: pasted.append("text"),
        read_focus=lambda: ("ComposerPane", "chatinput"),
        observe_image=lambda: "observed",
        observe_text=lambda: "observed",
    )
    bundle = {
        "text": "tail",
        "assets": [
            {"asset_id": "img-1", "bytes_data": b"one"},
            {"asset_id": "img-2", "bytes_data": b"two"},
        ],
    }
    svc.run(Attempt("a", "i", "b", "c"), bundle, mode="remaining_verified", skip_asset_ids={"img-1"})
    assert b"one" not in pasted
    assert b"two" in pasted


def test_unknown_recovery_asks_and_never_ctrl_a():
    plan = plan_retry(
        previous_result="UNKNOWN",
        same_target=True,
        images_observed=1,
        images_total=1,
        text_sent=False,
    )
    assert plan["mode"] == "ask"
    assert plan["auto_replay"] is False
    assert plan["ctrl_a_delete"] is False


def test_capture_expiry_cancel_rate_limit_and_hide():
    hidden = []
    grabs = []
    svc = CaptureService(grab=lambda scope: grabs.append(scope) or PNG, hide_surfaces=lambda: hidden.append("hide"))
    session = _session()
    svc.begin(session, "primary", "r1", now=0)
    with pytest.raises(ValueError, match="expired"):
        svc.complete("r1", session, now=REQUEST_TTL_S + 1)
    assert grabs == []
    svc.begin(session, "primary", "r2", now=100)
    svc.cancel("r2")
    with pytest.raises(ValueError, match="cancelled"):
        svc.complete("r2", session, now=101)
    first = svc.capture(session, "primary", now=200)
    assert first.startswith(b"\x89PNG")
    assert hidden == ["hide"]
    with pytest.raises(ValueError, match="rate limited"):
        svc.capture(session, "primary", now=200.2)
    with pytest.raises(ValueError, match="unknown capture scope"):
        svc.capture(session, "hwnd:1234", now=400)


def test_legacy_migration_does_not_write_or_start_learn(tmp_path):
    path = tmp_path / "config.json"
    payload = {
        "learn_enabled": True,
        "hotkey_insert": "<ctrl>+<alt>+v",
        "hotkey_toggle_review": "<ctrl>+<shift>+u",
        "llm_api_key": "",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    info = inspect_legacy_config(path)
    assert path.read_bytes() == before
    assert info["start_learn"] is False
    assert info["hotkeys"]["insert"] == "<ctrl>+<alt>+v"
    assert info["hotkeys"]["legacy_skip_polish_removed"] is True
    assert "召回" in info["hotkeys"]["note"]


def test_two_hundred_freeze_and_intent_rounds_do_not_double_send():
    ledger = IntentLedger()
    pastes = 0
    for i in range(200):
        draft = Draft("d", "e", i + 1, "phone", f"round-{i}")
        bundle = freeze_bundle(draft, bundle_id=f"b{i}")
        assert bundle["text"] == f"round-{i}"
        intent_id = f"intent-{i}"
        assert ledger.begin(intent_id) == "accept"
        pastes += 1
        ledger.finish(intent_id, "UNKNOWN")
        assert ledger.begin(intent_id) == "duplicate"
    assert pastes == 200


def test_pick_port_skips_occupied_without_killing():
    import socket

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    occupied = blocker.getsockname()[1]
    try:
        chosen = pick_port(occupied)
        assert chosen != occupied
    finally:
        blocker.close()


def test_composer_recovery_and_optional_capture_copy():
    html = COMPOSER.read_text(encoding="utf-8")
    assert "只补文字" in html
    assert "allowCapture" in html
    assert "不会在重连时重放" in html
    assert "拒绝截图仍可同步文字" in html
    assert "WebEngine" not in html
