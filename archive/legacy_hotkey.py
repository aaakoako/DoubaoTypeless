from pynput import keyboard
from typing import Callable, Optional


class HotkeyListener:
    """Legacy global hotkey listener for the retired PC direct-ASR path."""

    def __init__(self, hotkey_str: str, on_press: Callable, on_release: Callable):
        self.hotkey_str = hotkey_str
        self.on_press = on_press
        self.on_release = on_release
        self._pressed = False
        self._listener: Optional[keyboard.Listener] = None
        self._target_key = self._parse_key(hotkey_str)

    @staticmethod
    def _parse_key(key_str: str):
        if key_str.startswith("Key."):
            return getattr(keyboard.Key, key_str[4:], None)
        if len(key_str) == 1:
            return keyboard.KeyCode.from_char(key_str)
        return None

    @staticmethod
    def key_to_str(key) -> Optional[str]:
        if isinstance(key, keyboard.Key):
            return f"Key.{key.name}"
        if isinstance(key, keyboard.KeyCode) and key.char:
            return key.char
        return None

    def _matches(self, key) -> bool:
        if self._target_key is None:
            return False
        if isinstance(self._target_key, keyboard.Key):
            return key == self._target_key
        if isinstance(self._target_key, keyboard.KeyCode):
            if isinstance(key, keyboard.KeyCode):
                return key.char == self._target_key.char
        return False

    def _handle_press(self, key):
        if self._matches(key) and not self._pressed:
            self._pressed = True
            try:
                self.on_press()
            except Exception as e:
                print(f"[hotkey] on_press error: {e}")

    def _handle_release(self, key):
        if self._matches(key) and self._pressed:
            self._pressed = False
            try:
                self.on_release()
            except Exception as e:
                print(f"[hotkey] on_release error: {e}")

    def update_hotkey(self, hotkey_str: str):
        self.hotkey_str = hotkey_str
        self._target_key = self._parse_key(hotkey_str)

    def start(self):
        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
