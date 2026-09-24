"""Cross-platform safety contracts; no native user input on developer machines."""
from types import SimpleNamespace
import sys
import pytest

from doubao_typeless.platform.accessible import input_kind
from doubao_typeless.platform import desktop
from doubao_typeless.storage import secret_store


@pytest.mark.parametrize('role,description,editable,kind', [
    ('AXTextArea', 'chatinput', True, 'composer'),
    ('text', 'promptinput', True, 'composer'),
    ('text', 'editor', True, 'edit'),
    ('password text', 'chatinput', True, 'password'),
    ('AXSecureTextField', 'chatinput', True, 'password'),
    ('text', 'monaco chatinput', True, 'code'),
    ('text', 'terminal', True, 'terminal'),
    ('label', 'chatinput', False, 'readonly'),
    ('text', 'Codex', True, 'edit'),
    ('text', 'Ask anything', True, 'composer'),
    ('text', 'Search chatinput', True, 'edit'),
])
def test_accessible_policy(role, description, editable, kind):
    assert input_kind(role, description, editable=editable) == kind


def test_wayland_never_registers_shortcuts_or_injects(monkeypatch):
    monkeypatch.setattr(desktop, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setenv('XDG_SESSION_TYPE', 'wayland')
    monkeypatch.delenv('DT_V3_DISABLE_HOTKEYS', raising=False)
    assert desktop.start_hotkeys()['failures']
    with pytest.raises(RuntimeError, match='X11'):
        desktop.send_paste()


def test_failed_os_keyring_keeps_latest_only_in_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(secret_store, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.delenv('DT_V3_SECRET_FILE', raising=False)
    def failed():
        raise RuntimeError('locked')
    monkeypatch.setattr(secret_store, '_native_keyring', failed)
    assert secret_store.put_secret(tmp_path, 'test', 'example') == 'memory'
    assert secret_store.get_secret(tmp_path, 'test') == 'example'
    assert not (tmp_path / 'secrets').exists()
    secret_store.delete_secret(tmp_path, 'test')
    assert secret_store.get_secret(tmp_path, 'test') == ''


def test_os_keyring_roundtrip(tmp_path, monkeypatch):
    values = {}
    keyring = SimpleNamespace(set_password=lambda s, k, v: values.update({k: v}),
                              get_password=lambda s, k: values.get(k),
                              delete_password=lambda s, k: values.pop(k, None))
    monkeypatch.setattr(secret_store, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.delenv('DT_V3_SECRET_FILE', raising=False)
    monkeypatch.setattr(secret_store, '_native_keyring', lambda: keyring)
    assert secret_store.put_secret(tmp_path, 'test', 'example') == 'os'
    assert secret_store.get_secret(tmp_path, 'test') == 'example'
    secret_store.delete_secret(tmp_path, 'test')
    assert secret_store.get_secret(tmp_path, 'test') == ''


def test_posix_update_does_not_offer_windows_executable(monkeypatch):
    from doubao_typeless.services import v3_update
    from doubao_typeless import build_info
    monkeypatch.setattr(v3_update, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(build_info, 'build_info', lambda: {
        'version': '0.5.5', 'channel': 'release-candidate', 'source_sha': 'a' * 40})
    def invalid(_):
        pytest.fail('Windows package selector called on macOS')
    monkeypatch.setattr(v3_update, 'release_package', invalid)
    result = v3_update.check_preview_update(get_json=lambda _: {'tag_name': 'v0.5.6'})
    assert result['update_available'] and result['package'] is None


def test_macos_and_linux_exclude_unused_qt_modules():
    from tools.collect_runtime_notices import qt_binary_allowed
    assert qt_binary_allowed('PySide6/Qt/lib/libQt6Core.so.6')
    assert qt_binary_allowed('PySide6/Qt/lib/QtGui.framework/Versions/A/QtGui')
    assert not qt_binary_allowed('PySide6/Qt/lib/libQt6VirtualKeyboard.so.6')
    assert not qt_binary_allowed('PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so')
    assert not qt_binary_allowed('PySide6/Qt/lib/QtQuick.framework/Versions/A/QtQuick')


@pytest.mark.skipif(sys.platform != 'darwin', reason='Native macOS frameworks')
def test_macos_native_framework_exports_without_injecting():
    import ApplicationServices as AX
    import Quartz as Q
    from CoreFoundation import CFHash
    from doubao_typeless.platform import macos
    for name in ('AXUIElementCreateApplication', 'AXUIElementSetMessagingTimeout',
                 'AXUIElementCopyAttributeValue', 'AXUIElementIsAttributeSettable',
                 'AXUIElementSetAttributeValue'):
        assert callable(getattr(AX, name))
    assert callable(Q.CGPreflightScreenCaptureAccess)
    assert callable(Q.CGEventCreateKeyboardEvent)
    assert callable(CFHash)
    assert isinstance(macos.trusted(), bool)
    assert isinstance(macos.modifiers_down(), bool)


def test_timed_out_gui_request_cannot_later_change_clipboard():
    from concurrent.futures import Future
    from doubao_typeless.platform.qt_bridge import Dispatcher
    future = Future()
    future.cancel()
    called = []
    Dispatcher.execute(None, future, lambda: called.append('write'))
    assert called == []


def test_locate_never_switches_away_from_another_application(monkeypatch):
    from doubao_typeless.platform.windows.focus import FocusSnapshot
    monkeypatch.setattr(desktop, 'sys', SimpleNamespace(platform='linux'))
    current = FocusSnapshot('button', '', 10, 20, 30, (20, 30), 'readonly')
    saved = FocusSnapshot('text', '', 11, 21, 31, (21, 31), 'composer')
    monkeypatch.setattr(desktop, 'read_target', lambda: current)
    monkeypatch.setattr(desktop, 'restore_target', lambda _: pytest.fail('must not steal focus'))
    assert desktop.locate_current(saved)['status'] == 'not_found'
