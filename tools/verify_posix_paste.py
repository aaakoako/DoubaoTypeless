"""Native X11 receiver test. Run only on a disposable CI desktop, never a user's."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def receiver(path):
    from PySide6.QtWidgets import QApplication, QTextEdit
    app = QApplication([])
    events = []
    class Receiver(QTextEdit):
        def insertFromMimeData(self, source):
            if source.hasImage():
                events.append({'kind': 'image'})
            elif source.hasText():
                events.append({'kind': 'text', 'text': source.text()})
            Path(path).write_text(json.dumps(events))
            super().insertFromMimeData(source)
    widget = Receiver()
    widget.setWindowTitle('Pocket Composer native test receiver')
    widget.setAccessibleName('promptinput')
    widget.resize(500, 300)
    widget.show()
    widget.activateWindow()
    widget.setFocus()
    app.exec()


def verify():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.platform != 'linux':
        raise RuntimeError('This test requires a disposable Linux GitHub runner')
    from PySide6.QtWidgets import QApplication
    from doubao_typeless.platform.qt_bridge import initialize
    from doubao_typeless.platform import desktop
    from doubao_typeless.services.delivery import DeliveryService
    from doubao_typeless.core.attempt import Attempt
    from PIL import Image
    app = QApplication([])
    initialize()
    manager = subprocess.Popen(['openbox'])
    try:
        from Xlib.display import Display
        display = Display()
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if manager.poll() is not None:
                    raise RuntimeError('X11 window manager exited')
                prop = display.screen().root.get_full_property(display.intern_atom('_NET_SUPPORTING_WM_CHECK'), 0)
                if prop is not None:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('X11 window manager not ready')
        finally:
            display.close()
        with tempfile.TemporaryDirectory() as temp:
            receipt = Path(temp) / 'receipt.json'
            child = subprocess.Popen([sys.executable, __file__, '--receiver', str(receipt)])
            try:
                errors = []
                evidence = {}
                def work():
                    try:
                        deadline = time.monotonic() + 25
                        focus = None
                        while time.monotonic() < deadline:
                            from doubao_typeless.platform.errors import PlatformUnavailable
                            try:
                                focus = desktop.read_target()
                            except PlatformUnavailable:
                                time.sleep(.25)
                                continue
                            if focus.pid == child.pid and focus.kind == 'composer':
                                break
                            time.sleep(.25)
                        else:
                            raise AssertionError(f'Could not identify focused accessible composer: {focus}')
                        image = io.BytesIO()
                        Image.new('RGB', (24, 24), '#4f63dd').save(image, 'PNG')
                        def paste():
                            desktop.send_paste()
                            time.sleep(.15)
                        delivery = DeliveryService(paste=paste, set_clipboard_image=desktop.set_clipboard_png,
                            set_clipboard_text=desktop.set_clipboard_text, read_focus=desktop.read_target,
                            read_clipboard_text=desktop.read_clipboard_text, wait_modifiers=desktop.wait_modifiers_up,
                            is_locked=desktop.session_locked)
                        attempt = Attempt('native-test', 'native-intent', 'native-bundle', 'x11')
                        result = delivery.run(attempt, {'text': '手机图文 native paste',
                            'assets': [{'asset_id': 'test-image', 'bytes_data': image.getvalue()}]},
                            remote=True, expected_focus=focus)
                        deadline = time.monotonic() + 5
                        events = []
                        while time.monotonic() < deadline:
                            if receipt.exists():
                                try:
                                    events = json.loads(receipt.read_text())
                                except ValueError:
                                    pass
                            if len(events) == 2:
                                break
                            time.sleep(.05)
                        assert events == [{'kind': 'image'}, {'kind': 'text', 'text': '手机图文 native paste'}], (events, result.to_dict())
                        assert result.error_code in {None, ''}, result.to_dict()
                        assert desktop.read_clipboard_text() == '手机图文 native paste'
                        assert desktop.grab_primary().startswith(b'\x89PNG')
                        evidence.update(native_x11_image_then_text=True, screenshot=True,
                                        target='Qt accessible receiver', codex_cursor_tested=False,
                                        delivery=result.to_dict())
                    except BaseException as exc:
                        errors.append(exc)
                worker = threading.Thread(target=work)
                worker.start()
                while worker.is_alive():
                    app.processEvents()
                    time.sleep(.005)
                worker.join()
                if errors:
                    raise errors[0]
                print(json.dumps(evidence))
            finally:
                child.terminate()
                child.wait(timeout=10)
    finally:
        manager.terminate()
        manager.wait(timeout=10)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--receiver':
        receiver(sys.argv[2])
    else:
        verify()
