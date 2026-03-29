"""
DoubaoTypeless — 局域网手机网页与 Windows PC 的语音文本桥接。

同 WiFi 下用手机浏览器访问本机页面，通过输入法语音录入，
文本同步至 PC，在审阅窗口确认后插入当前系统焦点处。
"""

import asyncio
import atexit
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from bridge import PhoneBridge
from config import Config
from paths import app_root
from gui import GUIManager
from hotkeys import GlobalHotkeyService, build_bindings
from polish import PolishConfig, TextPolisher
from tray import STATE_PROCESSING, STATE_READY, STATE_RECORDING, SystemTray
from typer import Typer

if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if getattr(sys, "frozen", False):
    os.chdir(app_root())

_LOG_PATH = app_root() / "debug.log"
_log_file = None


def _log(msg: str):
    global _log_file
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line)
    try:
        if _log_file is None:
            _log_file = open(_LOG_PATH, "a", encoding="utf-8")
        _log_file.write(line + "\n")
        _log_file.flush()
    except Exception:
        pass


def _close_log():
    global _log_file
    if _log_file is not None:
        try:
            _log_file.flush()
            _log_file.close()
        except Exception:
            pass
        _log_file = None


atexit.register(_close_log)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _redact_logs_by_default() -> bool:
    """默认不向 debug.log 写入用户输入/纠错正文；需要完整片段时设 DT_VERBOSE_LOG=1。"""
    return not _env_truthy("DT_VERBOSE_LOG")


class App:
    def __init__(self):
        self.config = Config.load()
        self._redact_logs = _redact_logs_by_default()
        self.typer = Typer(clipboard_protection=self.config.clipboard_protection)
        self.gui = GUIManager(
            logger=_log,
            history_path=self.config.review_history_path,
        )
        self.gui.set_on_insert(self._on_insert)
        self.gui.set_on_batch_learn(self._on_batch_learn)
        self.gui.set_learn_when_no_diff_getter(
            lambda: bool(getattr(self.config, "learn_when_no_diff", False))
        )
        self.gui.set_on_model_probe(self._queue_model_probe)
        self._learn_pending: list[dict] = self._load_learn_pending()
        self.tray = SystemTray(
            on_settings=self._open_settings,
            on_quit=self._quit,
            on_debug_log=self._open_debug_log,
        )
        if sys.platform == "win32":
            from windows_startup import apply_start_with_windows

            ok, err = apply_start_with_windows(self.config.start_with_windows)
            if not ok and err:
                _log(f"开机自启注册表: {err}")
        self.polisher = self._make_polisher()
        self.bridge = PhoneBridge(
            port=self.config.bridge_port,
            on_text=self._on_bridge_text,
            on_update=self._on_bridge_update,
            logger=_log,
            redact_text_in_logs=self._redact_logs,
        )
        self._hotkeys = GlobalHotkeyService(logger=_log)

        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_raw = ""
        self._pending_llm_text = ""
        self._pending_llm_api_text = ""
        self._pending_suggestions = []
        self._preview_text = ""
        self._bridge_job_seq = 0
        self._active_bridge_job_seq = 0
        self._bridge_llm_task: asyncio.Task | None = None
        self._stable_dispatch_task: asyncio.Task | None = None
        self._last_suggest_started_at = 0.0
        self._last_suggest_source_text = ""
        self._dup_stable_guard_text = ""
        self._dup_stable_guard_at = 0.0

    def _load_review_history(self) -> list[dict]:
        p = Path(self.config.review_history_path)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception as e:
            _log(f"[history] 加载失败: {e}")
        return []

    def _load_learn_pending(self) -> list[dict]:
        p = Path(self.config.learn_pending_path)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            out = []
            for x in data:
                if not isinstance(x, dict):
                    continue
                if not (x.get("raw_text") and x.get("llm_text") and x.get("final_text")):
                    continue
                out.append(
                    {
                        "raw_text": x["raw_text"],
                        "llm_text": x["llm_text"],
                        "final_text": x["final_text"],
                        "accepted_suggestions": x.get("accepted_suggestions") or [],
                    }
                )
            return out
        except Exception as e:
            _log(f"[learn.pending] 加载失败: {e}")
        return []

    def _save_learn_pending(self) -> None:
        p = Path(self.config.learn_pending_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                json.dumps(self._learn_pending, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            _log(f"[learn.pending] 保存失败: {e}")

    @staticmethod
    def _looks_sentence_finished(text: str) -> bool:
        stripped = text.rstrip()
        return bool(stripped) and stripped[-1] in "。！？!?；;：:\n"

    def _make_polisher(self) -> TextPolisher:
        return TextPolisher(
            PolishConfig(
                enabled=self.config.llm_enabled,
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key,
                model=self.config.llm_model,
                timeout=self.config.llm_timeout,
                dictionary_path=self.config.dictionary_path,
                llm_system_prompt=self.config.llm_system_prompt,
                suggest_domain_terms=self.config.suggest_domain_terms,
                domain_terms_path=self.config.domain_terms_path,
                review_history_path=self.config.review_history_path,
                domain_term_topic_window=self.config.domain_term_topic_window,
                domain_terms_prompt_cap=self.config.domain_terms_prompt_cap,
                domain_terms_max_store=self.config.domain_terms_max_store,
                learn_enabled=self.config.learn_enabled,
                learn_base_url=self.config.learn_base_url,
                learn_api_key=self.config.learn_api_key,
                learn_model=self.config.learn_model,
                learn_timeout=self.config.learn_timeout,
                learning_samples_path=self.config.learning_samples_path,
                learn_system_prompt=self.config.learn_system_prompt,
                learn_user_prompt=self.config.learn_user_prompt,
                dict_write_mode=self.config.dict_write_mode,
                dict_auto_min_confidence=self.config.dict_auto_min_confidence,
                dict_auto_max_pairs=self.config.dict_auto_max_pairs,
                dict_block_regexes=self.config.dict_block_regexes,
            ),
            logger=_log,
            redact_user_logs=self._redact_logs,
        )

    def _on_hotkey_toggle_review(self):
        self.gui.bring_review_to_front()

    def _on_hotkey_insert(self):
        self.gui.trigger_review_insert()

    def _refresh_hotkeys(self):
        bindings = build_bindings(
            self.config.hotkey_toggle_review,
            self.config.hotkey_insert,
            self._on_hotkey_toggle_review,
            self._on_hotkey_insert,
        )
        self._hotkeys.start(bindings)

    def _queue_model_probe(self, target: str, cfg: dict):
        if not self._loop:
            self.gui.set_model_health(target, False, "程序未完全启动")
            return
        asyncio.run_coroutine_threadsafe(
            self._run_model_probe(target, cfg), self._loop
        )

    async def _run_model_probe(self, target: str, cfg: dict):
        import httpx

        url = (cfg.get("base_url") or "").strip()
        key = (cfg.get("api_key") or "").strip()
        model = (cfg.get("model") or "").strip()
        if not url or not key or not model:
            self.gui.set_model_health(target, False, "请填写 Base URL、Key、Model")
            return
        base = url.rstrip("/") + "/"
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ok"}],
                "max_tokens": 2,
                "temperature": 0,
            }
            # 与 polish 学习请求一致：ASCII 转义 JSON + UTF-8 字节体，避免部分环境下非 ASCII 触发 ascii codec
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            async with httpx.AsyncClient(
                base_url=base,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                timeout=httpx.Timeout(20.0, connect=12.0),
            ) as client:
                r = await client.post(
                    "chat/completions",
                    content=body,
                )
                r.raise_for_status()
            self.gui.set_model_health(target, True, "探测成功")
            _log(f"[probe.{target}] 模型探测成功")
        except Exception as e:
            self.gui.set_model_health(target, False, str(e))
            _log(f"[probe.{target}] 失败: {e}")

    def _open_settings(self):
        self.gui.open_settings(
            self.config,
            on_save=self._on_config_saved,
            get_runtime_bridge_port=lambda: self.config.bridge_port,
            on_bridge_rebind=self._on_bridge_port_rebind,
        )

    def _open_debug_log(self):
        self.gui.show_debug_log()

    def _on_bridge_port_rebind(self, new_port: int):
        if new_port == self.config.bridge_port:
            return
        self.config.bridge_port = new_port
        self.config.save()
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._restart_bridge(), self._loop)
        _log(f"[bridge] 端口冲突已处理，切换为 {new_port} 并重启桥接")

    def _on_config_saved(self, new_config: Config):
        restart_bridge = new_config.bridge_port != self.config.bridge_port
        self.config = new_config
        self.typer.clipboard_protection = new_config.clipboard_protection
        self.polisher = self._make_polisher()
        self.gui.set_model_health("suggest", None, "")
        self.gui.set_model_health("learn", None, "")
        _hk_n = sum(
            1
            for x in (new_config.hotkey_toggle_review, new_config.hotkey_insert)
            if (x or "").strip()
        )
        _log(
            "[config] "
            f"bridge_port={new_config.bridge_port} "
            f"hotkeys={_hk_n} "
            f"前台建议={'开' if new_config.llm_enabled else '关'} "
            f"后台学习={'开' if new_config.learn_enabled else '关'} "
            f"dict_write={new_config.dict_write_mode}（对照表） "
            f"learn_batch_interval={new_config.learn_batch_interval}"
        )
        self.gui.set_history_path(new_config.review_history_path)
        if restart_bridge and self._loop:
            asyncio.run_coroutine_threadsafe(self._restart_bridge(), self._loop)
        self._refresh_hotkeys()

    def _on_bridge_update(self, text: str, meta: dict | None = None):
        if not self._loop:
            return
        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._apply_bridge_preview(text))
        )

    async def _apply_bridge_preview(self, text: str):
        previous = self._preview_text
        if text == previous:
            return
        self._preview_text = text
        if not text.strip():
            self.tray.set_state(STATE_READY)
            return
        self.tray.set_state(STATE_RECORDING)
        if not previous.strip():
            self.gui.show_recording()
        self.gui.update_interim(text)

    def _on_bridge_text(self, text: str, meta: dict | None = None):
        if not self._loop:
            return
        self._loop.call_soon_threadsafe(lambda: self._schedule_stable_text(text))

    def _schedule_stable_text(self, text: str):
        if self._stable_dispatch_task and not self._stable_dispatch_task.done():
            self._stable_dispatch_task.cancel()
        self._stable_dispatch_task = asyncio.create_task(self._dispatch_stable_text(text))

    async def _dispatch_stable_text(self, text: str):
        try:
            await asyncio.sleep(0.3)
            await self._process_bridge_text(text)
        except asyncio.CancelledError:
            return

    async def _process_bridge_text(self, text: str):
        text = text.strip()
        if not text:
            return
        # 注意：防抖分支会更新 _pending_raw 但不跑纠错；stable 再次带上同一段正文时
        # 必须与 _pending_raw 相等才能进入下面的 LLM 流程，故不能在此处因相等而 return。
        now = time.monotonic()
        if (
            self._pending_raw
            and text.startswith(self._pending_raw)
            and (len(text) - len(self._pending_raw)) < 28
            and (now - self._last_suggest_started_at) < 5.5
        ):
            self._preview_text = text
            self._pending_raw = text
            self.gui.update_interim(text)
            return
        if (
            self._last_suggest_source_text
            and text.startswith(self._last_suggest_source_text)
            and not self._looks_sentence_finished(text)
            and (len(text) - len(self._last_suggest_source_text)) < 80
            and (now - self._last_suggest_started_at) < 12.0
        ):
            self._preview_text = text
            self._pending_raw = text
            self.gui.update_interim(text)
            return

        if (
            text == self._dup_stable_guard_text
            and (now - self._dup_stable_guard_at) < 0.5
        ):
            return

        self._bridge_job_seq += 1
        job_seq = self._bridge_job_seq
        self._active_bridge_job_seq = job_seq
        self._preview_text = text
        self._pending_raw = text
        self._last_suggest_started_at = now
        self._last_suggest_source_text = text
        self._dup_stable_guard_text = text
        self._dup_stable_guard_at = now

        self.typer.save_focus()
        self.tray.set_state(STATE_PROCESSING)
        self.gui.show_recording()
        self.gui.update_interim(text)
        self.gui.show_processing()

        self._bridge_llm_task = asyncio.create_task(self.polisher.build_suggestions(text))
        try:
            batch = await self._bridge_llm_task
        except asyncio.CancelledError:
            _log("[审阅] 纠错任务已取消（跳过）")
            self.tray.set_state(STATE_READY)
            return
        finally:
            self._bridge_llm_task = None

        if job_seq != self._active_bridge_job_seq:
            return

        self._pending_llm_text = batch.llm_text
        self._pending_llm_api_text = (batch.api_llm_text or "").strip() or batch.llm_text
        self._pending_suggestions = batch.suggestions
        if batch.suggestions or batch.llm_text != text:
            _log(
                f"[审阅] seq={job_seq} suggestions={len(batch.suggestions)} "
                f"llm_changed={'yes' if batch.llm_text != text else 'no'} len={len(text)}"
            )
        if self.config.llm_enabled and batch.api_called:
            self.gui.set_model_health(
                "suggest",
                batch.api_ok,
                "纠错 API 失败" if not batch.api_ok else "纠错调用成功",
            )
        self.gui.show_final(text, batch.suggestions, batch.llm_text)
        self.tray.set_state(STATE_READY)

    def _on_batch_learn(self, records: list[dict]):
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._do_batch_learn(records), self._loop)

    async def _do_batch_learn(self, records: list[dict]):
        if not records:
            return
        if not self.config.learn_enabled:
            _log("[learn.batch] 跳过：后台学习未启用")
            return
        if not (
            self.config.learn_base_url
            and self.config.learn_api_key
            and self.config.learn_model
        ):
            _log("[learn.batch] 跳过：后台 Base URL / Key / Model 未配齐")
            return
        self.polisher = self._make_polisher()
        chunk_size = max(1, int(self.config.learn_batch_interval or 0))
        n_batch = (len(records) + chunk_size - 1) // chunk_size
        _log(
            f"[learn.batch] 共 {len(records)} 条，分 {n_batch} 次请求（每批最多 {chunk_size} 条合并为一次 API）"
        )
        ok_marked = 0
        for off in range(0, len(records), chunk_size):
            chunk = records[off : off + chunk_size]
            bi = off // chunk_size + 1
            try:
                if await self.polisher.learn_from_review_batch(chunk):
                    ok_marked += len(chunk)
                    for r in chunk:
                        self.gui.mark_history_learn_ok(
                            r["raw_text"], r["llm_text"], r["final_text"]
                        )
                    self.gui.set_model_health("learn", True, "学习调用成功")
            except Exception as e:
                _log(f"[learn.batch] 第 {bi}/{n_batch} 批失败（{len(chunk)} 条）: {e}")
                self.gui.set_model_health("learn", False, str(e))
            if off + chunk_size < len(records):
                await asyncio.sleep(0.35)
        _log(f"[learn.batch] 结束 已标记={ok_marked}/{len(records)}")

    def _on_insert(self, payload: dict):
        final_text = payload.get("final_text", "")
        accepted = payload.get("accepted_suggestions", [])
        if payload.get("skip_llm"):
            _log(f"[插入] 跳过纠错 final_len={len(final_text)}")
        else:
            _log(f"[插入] final_len={len(final_text)} accepted={len(accepted)}")
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._do_insert(payload), self._loop)

    async def _do_insert(self, payload: dict):
        edited_text = payload.get("final_text", "")
        accepted = payload.get("accepted_suggestions", [])
        skip_llm = bool(payload.get("skip_llm"))
        if skip_llm:
            self._active_bridge_job_seq = -999999
            t = self._bridge_llm_task
            if t and not t.done():
                t.cancel()
            self.tray.set_state(STATE_READY)
        await asyncio.sleep(0.15)
        paste_result = self.typer.paste_text(edited_text, keep_in_clipboard=True)
        _log(
            "[插入结果] "
            f"attempted={paste_result.get('attempted')} "
            f"focus_restored={paste_result.get('focus_restored')} "
            f"paste_sent={paste_result.get('paste_sent')} "
            f"clipboard_kept={paste_result.get('clipboard_kept')}"
        )
        if skip_llm:
            raw = edited_text
            llm_text = edited_text
            learn_llm = edited_text
        else:
            # 插入在 GUI 线程投递，_do_insert 异步晚于若干毫秒执行；若此时下一段语音已到，
            # _pending_* 可能已被覆盖。审阅窗口 payload 与当前终稿一致，应优先使用。
            pr = (payload.get("raw_text") or "").strip()
            pllm = (payload.get("llm_text") or "").strip()
            raw = pr or (self._pending_raw or "").strip()
            pend_llm = (self._pending_llm_text or "").strip()
            api_llm = (self._pending_llm_api_text or "").strip()
            llm_text = pllm or pend_llm
            learn_llm = pllm if pllm else (api_llm if api_llm else pend_llm)
        self.gui.add_history(
            {
                "final_text": edited_text,
                "raw_text": raw or "",
                "llm_text": llm_text or "",
                "accepted_suggestions": accepted,
            }
        )
        learn_gate = not skip_llm and bool(
            (raw or "").strip() and (learn_llm or "").strip() and self.config.learn_enabled
        )
        # 前台纠错结果与 ASR 原文不一致（用户未改终稿时也算「有可学信号」）
        api_delta = (
            not skip_llm
            and bool((llm_text or "").strip())
            and (llm_text or "").strip() != (raw or "").strip()
        )
        has_edit_signal = edited_text != raw or bool(accepted) or api_delta
        allow_no_diff_learn = bool(getattr(self.config, "learn_when_no_diff", False))
        if learn_gate and not has_edit_signal and not allow_no_diff_learn:
            _log(
                "[自学习] 跳过：终稿与语音原文相同、未采纳替换，且前台模型返回与原文一致（无可学差异）。"
                "若仍希望沉淀术语到学习样本的 notes，可在设置中开启「无差异仍学习」。"
            )
        if (
            not skip_llm
            and self.config.learn_enabled
            and not learn_gate
            and (not (raw or "").strip() or not (learn_llm or "").strip())
        ):
            _log(
                "[自学习] 跳过：原文或纠错文本为空，无法调用学习。"
                f" raw_len={len(raw or '')} learn_llm_len={len(learn_llm or '')}"
            )
        eligible_learn = bool(learn_gate and (has_edit_signal or allow_no_diff_learn))
        if eligible_learn:
            rec = {
                "raw_text": raw,
                "llm_text": learn_llm,
                "final_text": edited_text,
                "accepted_suggestions": accepted,
            }
            interval = max(0, int(self.config.learn_batch_interval or 0))
            if interval <= 0:
                try:
                    _log(
                        "[learn.invoke] "
                        f"raw_len={len(raw)} learn_llm_len={len(learn_llm)} "
                        f"final_len={len(edited_text)} accepted={len(accepted)}"
                        + (" no_diff_terms=1" if not has_edit_signal else "")
                    )
                    if await self.polisher.learn_from_review(
                        raw_text=raw,
                        llm_text=learn_llm,
                        final_text=edited_text,
                        accepted_suggestions=accepted,
                    ):
                        self.gui.mark_history_learn_ok(raw, learn_llm, edited_text)
                        self.gui.set_model_health("learn", True, "学习调用成功")
                except Exception as e:
                    _log(f"[自学习] 错误: {e}")
                    self.gui.set_model_health("learn", False, str(e))
            else:
                self._learn_pending.append(rec)
                self._save_learn_pending()
                _log(
                    f"[learn.defer] 待批量学习 {len(self._learn_pending)}/{interval} 条"
                )
                while len(self._learn_pending) >= interval:
                    batch = self._learn_pending[:interval]
                    self._learn_pending = self._learn_pending[interval:]
                    self._save_learn_pending()
                    await self._do_batch_learn(batch)

        self._pending_raw = ""
        self._pending_llm_text = ""
        self._pending_llm_api_text = ""
        self._pending_suggestions = []
        self._preview_text = ""
        self._last_suggest_source_text = ""
        try:
            await self.bridge.notify_cleared()
        except Exception as e:
            _log(f"[bridge] 清空手机页面失败: {e}")

    async def _restart_bridge(self):
        try:
            await self.bridge.stop()
        except Exception:
            pass
        self.bridge = PhoneBridge(
            port=self.config.bridge_port,
            on_text=self._on_bridge_text,
            on_update=self._on_bridge_update,
            logger=_log,
            redact_text_in_logs=self._redact_logs,
        )
        await self.bridge.start(self._loop)
        _log(f"[bridge] 已切换到新端口: {self.bridge.url}")

    def _quit(self):
        self._save_learn_pending()
        self._hotkeys.stop()
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.bridge.stop(), self._loop).result(timeout=2)
        except Exception:
            pass
        self.gui.stop()
        self.tray.stop()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        _close_log()
        os._exit(0)

    def run(self):
        _log("DoubaoTypeless 启动中...")
        _log(f"  手机桥接端口: {self.config.bridge_port}")
        _hk_n = sum(
            1
            for x in (self.config.hotkey_toggle_review, self.config.hotkey_insert)
            if (x or "").strip()
        )
        _log(f"  全局快捷键: {_hk_n} 个已配置")
        _log(f"  前台建议: {'开 (' + self.config.llm_model + ')' if self.config.llm_enabled else '关'}")
        _nodiff = " 无差异仍学=开" if getattr(self.config, "learn_when_no_diff", False) else ""
        _log(
            f"  后台学习: {'开 (' + self.config.learn_model + ')' if self.config.learn_enabled else '关'}"
            f"{_nodiff if self.config.learn_enabled else ''}"
        )
        _log(
            f"  纠错对照表: {self.config.dictionary_path} ({len(self.polisher.dictionary._mappings)} 条) "
            f"学习后自动追加={'开' if (self.config.dict_write_mode or '').lower() == 'auto' else '关'}"
        )
        _log(f"  日志文件: {_LOG_PATH}")
        if self._redact_logs:
            _log("  日志默认脱敏（不写输入正文）；调试请设环境变量 DT_VERBOSE_LOG=1")
        _log(
            f"  审阅历史文件: {self.config.review_history_path} "
            f"学习队列: {self.config.learn_pending_path} "
            f"批量间隔: {self.config.learn_batch_interval or '立即'}"
        )
        _log("")

        self.gui.start()
        hist = self._load_review_history()
        if hist:
            self.gui.import_history(hist)
            _log(f"[history] 已加载 {len(hist)} 条审阅历史")
        if self._learn_pending:
            _log(f"[learn.pending] 已从磁盘恢复 {len(self._learn_pending)} 条待批量学习")
        self._refresh_hotkeys()
        self.tray.start()

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.bridge.start(self._loop))
        _log(f"  手机页面: {self.bridge.url}")
        _log("  手机浏览器打开上面的地址即可")
        _log("  手机端输入会自动同步到 PC，稳定后自动进入审阅")
        _log("")
        _log("就绪！")

        try:
            self._loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            try:
                self._loop.run_until_complete(self.bridge.stop())
            except Exception:
                pass
            self._quit()


if __name__ == "__main__":
    app = App()
    app.run()
