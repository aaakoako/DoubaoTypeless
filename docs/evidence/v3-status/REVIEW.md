# Review notes for GPT-6 Pro

Branch: `v3/00-baseline`  
Purpose: isolated Pocket Composer v3 candidate. **Not** a merge to master, **not** a GitHub Release, **not** a daily-use switch.

## Why this is pushed now

Product code for the remaining implementable cards is on this branch: Vite+Konva Composer, SQLite+chunked upload, region/DPI capture, hotkey debounce, modifier release, clipboard interference, instance lock, tail-flush insert, recovery without Ctrl+A/Delete. Automatic tests: `python -m pytest -q` → 76 passed.

Native gaps stay honest in `docs/pocket-composer-v3/fixtures/acceptance.json` (no adb Doubao IME, no Cursor UIA attachment tree). Independent review is not self-signed.

Please review for: fake PASS, Enter injection, daily-use data writes, merge/Release side effects, and missing product behavior that can exist without a physical phone.
