# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

DoubaoTypeless is a Windows desktop tool that bridges mobile phone voice input to PC text insertion over WiFi. Users speak into their phone browser, text syncs to a PC review window, and after optional AI-powered correction, inserts at the system cursor position. Built with Python 3.11+, CustomTkinter, and aiohttp.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
# or use: scripts/启动.bat

# Build single-file exe
pyinstaller --noconfirm DoubaoTypeless.spec

# Build portable directory (onedir)
pyinstaller --noconfirm DoubaoTypeless_portable.spec

# Unit tests (what CI does before syntax check)
python -m pytest -q

# Local release preflight
python scripts/preflight_release.py

# Syntax check (what CI does)
python -m py_compile main.py paths.py bridge.py gui.py gui_vocab.py polish.py config.py hotkeys.py typer.py app_icon.py app_version.py windows_startup.py term_bank.py providers_registry.py updater.py diagnostics.py scripts/preflight_release.py

# Verbose logging (shows user text in debug.log)
set DT_VERBOSE_LOG=1 && python main.py
# PowerShell: $env:DT_VERBOSE_LOG=1; python main.py
```

## Architecture

Single-process application with cooperating loops/threads:
- **Main thread asyncio loop** (`App._loop`) — bridge server, LLM calls, background learning, runs via `loop.run_forever()`
- **CustomTkinter GUI thread** (`GUIManager._thread`) — owns Tk widgets and `root.mainloop()`; Tk operations must be scheduled through `gui._schedule()`
- **pystray tray thread** — system tray menu/state icon callbacks
- **pynput listener thread** — global hotkeys, dispatches to asyncio via `call_soon_threadsafe` / `run_coroutine_threadsafe`

### Core Data Flow

```
Phone browser (phone.html)
  → HTTP/WebSocket (bridge.py, port 8765)
  → App._process_bridge_text (debounce + dedup)
  → TextPolisher.build_suggestions (polish.py, optional LLM call)
  → GUIManager review window (gui.py)
  → User confirms → Typer.paste_text (typer.py, clipboard + Ctrl+V)
  → Optional: background learning via learn_from_review (polish.py)
```

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `main.py` | `App` class — orchestrates all components, owns the lifecycle |
| `bridge.py` | `PhoneBridge` — aiohttp HTTP+WS server, serves `phone.html`, handles text relay |
| `gui.py` | `GUIManager` — CustomTkinter windows: review, settings, debug log, vocabulary |
| `tray.py` | `SystemTray` — pystray system tray icon with state indicators |
| `polish.py` | `TextPolisher` + `PolishConfig` — frontend AI correction and backend learning via OpenAI-compatible APIs |
| `config.py` | `Config` dataclass — persisted to `config.json`, holds all settings |
| `hotkeys.py` | `GlobalHotkeyService` — pynput-based global hotkey registration |
| `typer.py` | `Typer` — simulates keyboard input via clipboard paste, saves/restores focus |
| `term_bank.py` | Domain term extraction and storage (separate from correction dictionary) |
| `providers_registry.py` | LLM provider presets (DeepSeek, Codex, GLM, etc.) with recommended temperatures |
| `updater.py` | Auto-update: downloads new exe, spawns batch script for self-replacement |
| `diagnostics.py` | Safe diagnostics snapshot/export without API keys or user text |
| `scripts/preflight_release.py` | Local pre-release check: pytest, py_compile, version, release files, ignore rules |

### Configuration

`Config` dataclass in `config.py` with two independent LLM channels:
- **Foreground (suggest)**: `llm_*` fields — text correction with inline suggestions shown in review window
- **Background (learn)**: `learn_*` fields — extracts domain terms and correction patterns from review history

Both use OpenAI-compatible chat completion APIs. Provider presets in `providers.json`.

### Data Files (all in `data/`)

- `dictionary.txt` — correction lookup table (misheard → correct, one mapping per line)
- `domain_terms.json` — specialized vocabulary extracted by backend learning
- `learning_samples.jsonl` — raw learning records
- `review_history.json` — persisted review/insertion history
- `learn_pending.json` — queued records waiting for batch learning

### UI Structure

- **Review window**: shows interim text (while typing on phone), final corrected text with inline suggestions, accepts/edits before insert
- **Settings window**: all config fields, model health probes, QR code for phone access, connection diagnostics/export, one-click bridge self-check
- **Vocabulary manager** (`gui_vocab.py`): edit dictionary and domain terms
- **System tray**: status (ready/recording/processing), access to settings/vocabulary/debug log/quit

## Build & Release

- PyInstaller spec files: `DoubaoTypeless.spec` (onefile) and `DoubaoTypeless_portable.spec` (onedir)
- Release triggered by pushing `v*` tags → GitHub Actions builds on Windows, creates Release with exe + portable zip
- `app_version.py` contains `APP_VERSION` string

## Conventions

- Language: UI text, log messages, and comments are in Chinese
- Logging: custom `_log()` function writes to `debug.log` and stdout; user text is redacted by default (`DT_VERBOSE_LOG=1` to disable)
- Threading: Tkinter operations must go through `gui._schedule()` or already be on the GUI thread; asyncio coroutines are dispatched via `asyncio.run_coroutine_threadsafe()` from non-async contexts
- Diagnostics: exported diagnostic JSON must not include API keys or user text; keep new diagnostic fields to booleans, counts, timestamps, paths, status strings, and redacted log excerpts
- Bridge protocol tests live in `tests/test_bridge.py`; keep them independent of GUI and real LAN networking by using localhost + random free ports
- The app is Windows-only — uses `pywin32`, registry for startup, `chcp 65001` for UTF-8 console
