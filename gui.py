import json
import sys
import tkinter as tk
import threading
import queue
import traceback
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Tuple

import customtkinter as ctk

from app_icon import apply_tk_window_icon
from config import DICT_WRITE_MODES, Config
from paths import app_root, resource_dir
from hotkeys import validate_all_for_save
from polish import LEARN_PROMPT, LEARN_SYSTEM_DEFAULT, SYSTEM_PROMPT, Suggestion

_external_logger: Optional[Callable[[str], None]] = None


def _gui_log(msg: str):
    if _external_logger:
        _external_logger(f"[gui] {msg}")


class DebugLogWindow:
    """只读 tail debug.log，定时刷新；不占用前台控制台。"""

    _TAIL = 120_000

    def __init__(self, root: ctk.CTk):
        self._root = root
        self._win: Optional[ctk.CTkToplevel] = None
        self._tb: Optional[ctk.CTkTextbox] = None
        self._after_id: Optional[str] = None

    def toggle(self):
        if self._win is not None and self._win.winfo_exists():
            self._close()
        else:
            self._open()

    def _close(self):
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
        self._win = None
        self._tb = None

    def _open(self):
        self._win = ctk.CTkToplevel(self._root)
        self._win.title("调试日志 (debug.log)")
        self._win.geometry("760x520")
        icon = getattr(self._root, "_doubao_icon_photo", None)
        if icon is not None:
            self._win.iconphoto(True, icon)
        self._win.protocol("WM_DELETE_WINDOW", self._close)
        p = app_root() / "debug.log"
        ctk.CTkLabel(
            self._win,
            text=f"路径: {p}",
            anchor="w",
            text_color="#888888",
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", padx=10, pady=(8, 4))
        self._tb = ctk.CTkTextbox(
            self._win,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
            fg_color="#1E1E1E",
            text_color="#D4D4D4",
        )
        self._tb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        bf = ctk.CTkFrame(self._win, fg_color="transparent")
        bf.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(bf, text="立即刷新", width=88, command=self._load_once).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="关闭", width=72, command=self._close).pack(side="left")
        self._load_once()
        self._schedule_tick()

    def _load_once(self):
        if self._tb is None:
            return
        path = app_root() / "debug.log"
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            if len(raw) > self._TAIL:
                raw = raw[-self._TAIL :]
            self._tb.delete("1.0", "end")
            self._tb.insert("1.0", raw)
            self._tb.see("end")
        except FileNotFoundError:
            self._tb.delete("1.0", "end")
            self._tb.insert("1.0", "（尚无 debug.log，运行后自动生成）")
        except Exception as e:
            self._tb.delete("1.0", "end")
            self._tb.insert("1.0", f"读取失败: {e}")

    def _schedule_tick(self):
        if self._win is None or not self._win.winfo_exists():
            return
        self._load_once()
        self._after_id = self._root.after(2500, self._schedule_tick)


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def pick_random_free_port() -> int:
    """取一个当前可用的监听端口：让操作系统分配（bind 0），不扫描、不遍历端口表。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 0))
        return int(s.getsockname()[1])


def bridge_port_in_use_by_others(port: int, active_listening_port: Optional[int]) -> bool:
    """除本程序当前桥接端口外，port 是否已被占用（无法由我们新绑定）。"""
    if not (1 <= port <= 65535):
        return True
    if active_listening_port is not None and port == active_listening_port:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
        return False
    except OSError:
        return True


class ReviewWindow:
    """审阅窗口：可编辑终稿、展示替换建议并接受或拒绝。"""

    MAX_HISTORY = 100

    def __init__(
        self,
        root: ctk.CTk,
        on_insert: Optional[Callable] = None,
        on_batch_learn: Optional[Callable[[list[dict]], None]] = None,
        on_history_persist: Optional[Callable[[list[dict]], None]] = None,
    ):
        self._root = root
        self._on_insert = on_insert
        self._on_batch_learn = on_batch_learn
        self._on_history_persist = on_history_persist
        self._get_learn_when_no_diff: Optional[Callable[[], bool]] = None
        self._window: Optional[ctk.CTkToplevel] = None
        self._status_label: Optional[ctk.CTkLabel] = None
        self._final_box: Optional[ctk.CTkTextbox] = None
        self._insert_btn: Optional[ctk.CTkButton] = None
        self._history_btn: Optional[ctk.CTkButton] = None
        self._suggestions_frame: Optional[ctk.CTkScrollableFrame] = None
        # 每条: ts, final_text, raw_text, llm_text, accepted_suggestions
        self._history: list[dict] = []
        self._raw_text: str = ""
        self._llm_text: str = ""
        self._suggestions: list[Suggestion] = []
        self._accepted_ids: set[str] = set()

    def set_learn_when_no_diff_getter(self, fn: Optional[Callable[[], bool]]) -> None:
        """与 main 侧 learn_when_no_diff 同步，用于历史菜单批量学习的筛选条件。"""
        self._get_learn_when_no_diff = fn

    def _learn_when_no_diff_enabled(self) -> bool:
        fn = self._get_learn_when_no_diff
        if not fn:
            return False
        try:
            return bool(fn())
        except Exception:
            return False

    @staticmethod
    def _history_row_eligible_for_batch_learn(h: dict, allow_no_diff: bool) -> bool:
        """与 main._do_insert 中 eligible 判定对齐（无 skip_llm 语义，仅已落盘的历史行）。"""
        if h.get("learn_processed_ok"):
            return False
        raw = (h.get("raw_text") or "").strip()
        llm = (h.get("llm_text") or "").strip()
        fin = (h.get("final_text") or "").strip()
        if not (raw and llm and fin):
            return False
        if allow_no_diff:
            return True
        acc = h.get("accepted_suggestions") or []
        if fin != raw or bool(acc) or llm != raw:
            return True
        return False

    def _create_window(self):
        if self._window and self._window.winfo_exists():
            return

        self._window = ctk.CTkToplevel(self._root)
        self._window.title("DoubaoTypeless")
        self._window.attributes("-topmost", True)
        self._window.configure(fg_color="#F5F7FA")

        screen_w = self._window.winfo_screenwidth()
        screen_h = self._window.winfo_screenheight()
        w, h = 560, 380
        x = screen_w - w - 30
        y = screen_h - h - 80
        self._window.geometry(f"{w}x{h}+{x}+{y}")
        self._window.resizable(True, True)
        self._window.minsize(460, 340)

        self._window.protocol("WM_DELETE_WINDOW", self.hide)
        self._window.bind("<Escape>", lambda _: self.hide())
        self._window.bind("<Alt-i>", lambda _: self._do_insert())
        self._window.bind("<Alt-I>", lambda _: self._do_insert())
        self._window.bind("<Alt-Shift-I>", lambda _: self._skip_llm_insert())
        self._window.bind("<Alt-Shift-i>", lambda _: self._skip_llm_insert())
        icon = getattr(self._root, "_doubao_icon_photo", None)
        if icon is not None:
            self._window.iconphoto(True, icon)

        self._status_label = ctk.CTkLabel(
            self._window,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            text_color="#3370FF",
        )
        self._status_label.pack(pady=(10, 4), padx=14, fill="x")

        ctk.CTkLabel(
            self._window,
            text="待插入文本",
            anchor="w",
            text_color="#86909C",
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", padx=12)

        self._final_box = ctk.CTkTextbox(
            self._window,
            font=ctk.CTkFont(size=14),
            wrap="word",
            height=150,
            fg_color="#FFFFFF",
            text_color="#1D2129",
            border_width=1,
            border_color="#E5E6EB",
            corner_radius=8,
        )
        self._final_box.pack(fill="x", padx=12, pady=(2, 8))

        btn_frame = ctk.CTkFrame(self._window, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(0, 8))

        self._insert_btn = ctk.CTkButton(
            btn_frame, text="插入并复制 (Alt+I)", width=160,
            command=self._do_insert,
            fg_color="#3370FF", hover_color="#2860E0",
            text_color="#FFFFFF", corner_radius=8,
        )
        self._insert_btn.pack(side="left", padx=(0, 6))

        self._skip_llm_btn = ctk.CTkButton(
            btn_frame,
            text="跳过纠错并插入",
            width=130,
            command=self._skip_llm_insert,
            fg_color="#FF7D00",
            hover_color="#E56D00",
            text_color="#FFFFFF",
            corner_radius=8,
            state="disabled",
        )
        self._skip_llm_btn.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="复制", width=60, command=self._do_copy,
            fg_color="#F2F3F5", hover_color="#E5E6EB",
            text_color="#1D2129", corner_radius=8,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="清空", width=60, command=self._do_clear,
            fg_color="#F2F3F5", hover_color="#E5E6EB",
            text_color="#1D2129", corner_radius=8,
        ).pack(side="left", padx=(0, 6))

        self._history_btn = ctk.CTkButton(
            btn_frame, text="历史", width=60, command=self._show_history,
            fg_color="#F2F3F5", hover_color="#E5E6EB",
            text_color="#1D2129", corner_radius=8,
        )
        self._history_btn.pack(side="right")

        ctk.CTkLabel(
            self._window,
            text="替换建议",
            anchor="w",
            text_color="#86909C",
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", padx=12)

        self._suggestions_frame = ctk.CTkScrollableFrame(
            self._window,
            height=80,
            fg_color="#FFFFFF",
            corner_radius=8,
            border_width=1,
            border_color="#E5E6EB",
        )
        self._suggestions_frame.pack(fill="x", expand=False, padx=12, pady=(2, 10))

    # 以下接口由 GUIManager 在 GUI 线程调用

    def show_recording(self):
        self._create_window()
        self._window.deiconify()
        self._window.lift()
        self._window.focus_force()
        self._status_label.configure(text="正在听...", text_color="#FF4D4F")
        self._raw_text = ""
        self._llm_text = ""
        self._suggestions = []
        self._accepted_ids.clear()
        self._set_box_text(self._final_box, "", editable=False)
        self._clear_suggestions()
        self._insert_btn.configure(state="disabled")
        self._skip_llm_btn.configure(state="disabled")

    def update_interim(self, text: str):
        if not self._final_box or not self._window or not self._window.winfo_exists():
            return
        self._status_label.configure(text="手机输入中...", text_color="#3370FF")
        self._set_box_text(self._final_box, text, editable=False)

    def show_processing(self):
        if not self._status_label or not self._window or not self._window.winfo_exists():
            return
        self._status_label.configure(text="正在纠错...", text_color="#FF7D00")
        self._skip_llm_btn.configure(state="normal")

    def show_final(self, raw_text: str, suggestions: list[Suggestion], llm_text: str):
        if not self._final_box or not self._window or not self._window.winfo_exists():
            return
        self._raw_text = raw_text
        self._llm_text = llm_text
        self._suggestions = suggestions
        self._accepted_ids.clear()
        self._status_label.configure(
            text=f"已同步到电脑 — {len(suggestions)} 条替换建议",
            text_color="#00B578",
        )
        self._set_box_text(self._final_box, raw_text, editable=True)
        self._render_suggestions()
        self._apply_suggestion_tags()
        self._insert_btn.configure(state="normal")
        self._skip_llm_btn.configure(state="disabled")
        self._window.deiconify()
        self._window.lift()
        self._window.focus_force()
        self._final_box.focus_set()

    def hide(self):
        if self._window and self._window.winfo_exists():
            self._window.withdraw()

    def bring_to_front(self):
        self._create_window()
        if self._window and self._window.winfo_exists():
            self._window.deiconify()
            self._window.lift()
            self._window.focus_force()

    def trigger_insert(self):
        if not self._window or not self._window.winfo_exists():
            return
        if not self._final_box:
            return
        text = self._final_box.get("1.0", "end").strip()
        if not text:
            return
        self._do_insert()

    def add_history(self, record: dict):
        ts = datetime.now().strftime("%H:%M:%S")
        rec = {
            "ts": ts,
            "final_text": (record.get("final_text") or "").strip(),
            "raw_text": (record.get("raw_text") or "").strip(),
            "llm_text": (record.get("llm_text") or "").strip(),
            "accepted_suggestions": record.get("accepted_suggestions") or [],
            "learn_processed_ok": False,
        }
        self._history.insert(0, rec)
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[: self.MAX_HISTORY]
        if self._on_history_persist:
            try:
                self._on_history_persist(list(self._history))
            except Exception:
                pass

    def import_history(self, items: list[dict]):
        out: list[dict] = []
        for x in items:
            if not isinstance(x, dict):
                continue
            acc = x.get("accepted_suggestions")
            if not isinstance(acc, list):
                acc = []
            out.append(
                {
                    "ts": str(x.get("ts", "")),
                    "final_text": str(x.get("final_text", "")),
                    "raw_text": str(x.get("raw_text", "")),
                    "llm_text": str(x.get("llm_text", "")),
                    "accepted_suggestions": acc,
                    "learn_processed_ok": bool(x.get("learn_processed_ok")),
                }
            )
        self._history = out[: self.MAX_HISTORY]

    # 按钮与快捷键

    def _skip_llm_insert(self):
        if not self._final_box or not self._on_insert:
            return
        text = self._final_box.get("1.0", "end").strip()
        if not text:
            return
        self.hide()
        self._on_insert(
            {
                "final_text": text,
                "raw_text": self._raw_text,
                "llm_text": self._llm_text,
                "accepted_suggestions": [],
                "skip_llm": True,
            }
        )

    def _do_insert(self):
        if not self._final_box:
            return
        text = self._final_box.get("1.0", "end").strip()
        if not text:
            return
        self.hide()
        if self._on_insert:
            accepted = [s for s in self._suggestions if s.id in self._accepted_ids]
            self._on_insert({
                "final_text": text,
                "raw_text": self._raw_text,
                "llm_text": self._llm_text,
                "accepted_suggestions": [s.__dict__ for s in accepted],
            })

    def _do_copy(self):
        if not self._final_box:
            return
        text = self._final_box.get("1.0", "end").strip()
        if text:
            self._root.clipboard_clear()
            self._root.clipboard_append(text)

    def _do_clear(self):
        if self._final_box:
            self._set_box_text(self._final_box, "", editable=True)

    def _show_history(self):
        if not self._history:
            return
        menu = tk.Menu(self._window, tearoff=0)
        nodiff = self._learn_when_no_diff_enabled()
        n_learn = sum(
            1
            for h in self._history
            if self._history_row_eligible_for_batch_learn(h, nodiff)
        )
        menu.add_command(
            label=f"批量后台学习（未处理 {n_learn} 条）",
            command=self._submit_batch_learn,
            state="normal" if n_learn and self._on_batch_learn else "disabled",
        )
        menu.add_separator()
        for h in self._history:
            ts = h.get("ts", "")
            text = h.get("final_text", "")
            display = f"[{ts}] {text[:35]}..." if len(text) > 35 else f"[{ts}] {text}"
            menu.add_command(
                label=display,
                command=lambda t=text: self._fill_from_history(t),
            )
        try:
            x = self._history_btn.winfo_rootx()
            y = self._history_btn.winfo_rooty()
            menu.post(x, y - min(len(self._history) + 2, 12) * 22)
        except Exception:
            pass

    def _submit_batch_learn(self):
        eligible: list[dict] = []
        nodiff = self._learn_when_no_diff_enabled()
        for h in self._history:
            if not self._history_row_eligible_for_batch_learn(h, nodiff):
                continue
            raw = (h.get("raw_text") or "").strip()
            llm = (h.get("llm_text") or "").strip()
            fin = (h.get("final_text") or "").strip()
            eligible.append(
                {
                    "raw_text": raw,
                    "llm_text": llm,
                    "final_text": fin,
                    "accepted_suggestions": h.get("accepted_suggestions") or [],
                }
            )
        if not eligible or not self._on_batch_learn:
            return
        self._on_batch_learn(eligible)
        if self._status_label:
            self._status_label.configure(
                text=f"已提交 {len(eligible)} 条后台学习（异步执行，请看日志）",
                text_color="#FF7D00",
            )

    def _fill_from_history(self, text: str):
        if self._final_box:
            self._set_box_text(self._final_box, text, editable=True)
            self._status_label.configure(text="历史记录 — 可编辑后插入", text_color="#3370FF")
            self._insert_btn.configure(state="normal")

    def mark_learn_ok(self, raw_text: str, llm_text: str, final_text: str) -> bool:
        """后台学习成功后标记该条审阅历史，避免重复学习。"""
        r = (raw_text or "").strip()
        l = (llm_text or "").strip()
        f = (final_text or "").strip()
        for h in self._history:
            if (
                (h.get("raw_text") or "").strip() == r
                and (h.get("llm_text") or "").strip() == l
                and (h.get("final_text") or "").strip() == f
            ):
                h["learn_processed_ok"] = True
                if self._on_history_persist:
                    try:
                        self._on_history_persist(list(self._history))
                    except Exception:
                        pass
                return True
        _gui_log("[learn] 未匹配到审阅历史项，无法写入 learn_processed_ok（可能已超出历史条数上限）")
        return False

    def _set_box_text(self, box: ctk.CTkTextbox, text: str, editable: bool = False):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="normal" if editable else "disabled")

    def _apply_suggestion_tags(self):
        if not self._final_box:
            return
        text_widget = self._final_box._textbox
        for tag in list(text_widget.tag_names()):
            if tag.startswith("suggest_"):
                text_widget.tag_delete(tag)
        current = self._final_box.get("1.0", "end").strip()
        for suggestion in self._suggestions:
            if suggestion.id in self._accepted_ids:
                continue
            source = suggestion.source.strip()
            if not source:
                continue
            start_index = "1.0"
            while True:
                pos = text_widget.search(source, start_index, stopindex="end")
                if not pos:
                    break
                end = f"{pos}+{len(source)}c"
                tag = f"suggest_{suggestion.id}"
                text_widget.tag_add(tag, pos, end)
                text_widget.tag_config(tag, underline=True, foreground="#3370FF")
                start_index = end

    def _clear_suggestions(self):
        if not self._suggestions_frame:
            return
        for child in self._suggestions_frame.winfo_children():
            child.destroy()

    def _render_suggestions(self):
        self._clear_suggestions()
        if not self._suggestions_frame:
            return
        if not self._suggestions:
            ctk.CTkLabel(
                self._suggestions_frame,
                text="没有替换建议，确认后可直接插入。",
                text_color="#86909C",
                anchor="w",
            ).pack(fill="x", padx=4, pady=6)
            return

        for suggestion in self._suggestions:
            row = ctk.CTkFrame(self._suggestions_frame, fg_color="#F7F8FA", corner_radius=6)
            row.pack(fill="x", pady=3, padx=2)
            from_text = suggestion.source or "(空)"
            to_text = suggestion.target or "(删除)"

            ctk.CTkLabel(
                row,
                text=from_text,
                anchor="w",
                justify="left",
                text_color="#86909C",
                font=ctk.CTkFont(size=13),
            ).pack(side="left", fill="x", expand=True, padx=(8, 4), pady=6)
            ctk.CTkLabel(
                row,
                text="→",
                width=20,
                text_color="#C9CDD4",
            ).pack(side="left", padx=2)
            ctk.CTkLabel(
                row,
                text=to_text,
                anchor="w",
                justify="left",
                text_color="#00B578",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(side="left", fill="x", expand=True, padx=(4, 8), pady=6)

            btn = ctk.CTkButton(
                row,
                text="采纳",
                width=52,
                height=28,
                fg_color="#3370FF",
                hover_color="#2860E0",
                text_color="#FFFFFF",
                corner_radius=6,
                command=lambda s=suggestion: self._toggle_suggestion(s),
            )
            btn.pack(side="right", padx=6)
            if suggestion.id in self._accepted_ids:
                btn.configure(text="撤销", fg_color="#C9CDD4", hover_color="#A9AEB8", text_color="#4E5969")

    def _toggle_suggestion(self, suggestion: Suggestion):
        if not self._final_box:
            return
        current = self._final_box.get("1.0", "end").strip()
        if suggestion.id in self._accepted_ids:
            if suggestion.target and suggestion.target in current:
                current = current.replace(suggestion.target, suggestion.source, 1)
            self._accepted_ids.remove(suggestion.id)
        else:
            if suggestion.source and suggestion.source in current:
                current = current.replace(suggestion.source, suggestion.target, 1)
                self._accepted_ids.add(suggestion.id)
            elif not suggestion.source and suggestion.target:
                current += suggestion.target
                self._accepted_ids.add(suggestion.id)
        self._set_box_text(self._final_box, current, editable=True)
        self._apply_suggestion_tags()
        self._render_suggestions()


_PROVIDERS_PATH = resource_dir() / "providers.json"

# 与仓库内 providers.json 同类：厂商预设（url / models / 推荐 temperature）。
# 多厂商统一路由可参考 LiteLLM Proxy，本程序只直连 OpenAI 兼容 HTTP。
_DEFAULT_PROVIDERS: dict[str, dict] = {
    "DeepSeek": {
        "url": "https://api.deepseek.com/v1",
        "temperature": 0,
        "models": ["deepseek-chat"],
    },
    # Anthropic 官方 OpenAI 兼容层：https://docs.anthropic.com/en/api/openai-sdk
    "Claude (Anthropic)": {
        "url": "https://api.anthropic.com/v1",
        "temperature": 0,
        "models": [
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "claude-opus-4-5",
            "claude-3-5-sonnet-20241022",
        ],
    },
    "智谱 (GLM)": {
        "url": "https://open.bigmodel.cn/api/paas/v4",
        "temperature": 0,
        "models": ["glm-4-flash", "glm-4-flash-250414", "glm-4-air", "glm-5", "glm-5-turbo"],
    },
    "MiniMax": {
        "url": "https://api.minimaxi.com/v1",
        "temperature": 0.01,
        "models": ["MiniMax-M2.7-highspeed", "MiniMax-M2.7", "MiniMax-M2"],
    },
    "Qwen (阿里云)": {
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "temperature": 0,
        "models": ["qwen-turbo", "qwen-flash", "qwen-plus"],
    },
    "豆包 (火山引擎)": {
        "url": "https://ark.cn-beijing.volces.com/api/v3",
        "temperature": 0,
        "models": [],
    },
    "Moonshot (Kimi)": {
        "url": "https://api.moonshot.cn/v1",
        "temperature": 0,
        "models": ["kimi-k2-turbo-preview", "moonshot-v1-8k"],
    },
    "OpenAI": {
        "url": "https://api.openai.com/v1",
        "temperature": 0,
        "models": ["gpt-4o-mini", "gpt-4o"],
    },
}


def _load_providers() -> dict[str, dict]:
    import json
    providers = {name: dict(info) for name, info in _DEFAULT_PROVIDERS.items()}
    if _PROVIDERS_PATH.exists():
        try:
            with open(_PROVIDERS_PATH, "r", encoding="utf-8") as f:
                user_providers = json.load(f)
            for name, info in user_providers.items():
                base = dict(providers.get(name, {}))
                if isinstance(info, dict):
                    base.update(info)
                providers[name] = base
        except Exception:
            pass
    else:
        with open(_PROVIDERS_PATH, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_PROVIDERS, f, indent=2, ensure_ascii=False)
    providers["自定义"] = {"url": "", "models": []}
    return providers


LLM_PROVIDERS = _load_providers()


class SettingsWindow:
    """设置对话框（CustomTkinter）。"""

    def __init__(
        self,
        root: ctk.CTk,
        config: Config,
        on_save: Optional[Callable] = None,
        *,
        get_runtime_bridge_port: Optional[Callable[[], int]] = None,
        on_bridge_rebind: Optional[Callable[[int], None]] = None,
        on_toggle_debug_log: Optional[Callable[[], None]] = None,
        get_model_health: Optional[
            Callable[[], Tuple[Optional[bool], str, Optional[bool], str]]
        ] = None,
        on_model_probe: Optional[Callable[[str, dict], None]] = None,
    ):
        self._config = config
        self._on_save = on_save
        self._get_runtime_bridge_port = get_runtime_bridge_port
        self._on_bridge_rebind = on_bridge_rebind
        self._on_toggle_debug_log = on_toggle_debug_log
        self._get_model_health = get_model_health
        self._on_model_probe = on_model_probe
        self._probe_status_bullets: dict[str, ctk.CTkLabel] = {}
        self._probe_detail_vars: dict[str, tk.StringVar] = {}
        self._suggest_key_visible = False
        self._learn_key_visible = False
        self._win: Optional[ctk.CTkToplevel] = None
        self._root = root
        self._qr_ctk_image: Optional[ctk.CTkImage] = None

    @staticmethod
    def _make_copyable_line_entry(parent, textvariable: tk.StringVar) -> ctk.CTkEntry:
        """单行展示：可选中、Ctrl+C 复制，禁止键入修改。"""

        def _filter_key(ev):
            st = ev.state or 0
            if st & 0x4 and ev.keysym.lower() in ("c", "a"):
                return None
            if ev.keysym in (
                "Left",
                "Right",
                "Up",
                "Down",
                "Home",
                "End",
                "Prior",
                "Next",
                "Shift_L",
                "Shift_R",
                "Control_L",
                "Control_R",
                "Alt_L",
                "Alt_R",
            ):
                return None
            if len(ev.char) == 1 and ev.char.isprintable():
                return "break"
            if ev.keysym in ("BackSpace", "Delete", "Return", "Tab", "space"):
                return "break"
            return None

        e = ctk.CTkEntry(
            parent,
            textvariable=textvariable,
            height=28,
            font=ctk.CTkFont(size=12),
        )
        e.bind("<Key>", _filter_key)
        return e

    def _flash_settings_status(self, text: str, color: str = "#888888"):
        sl = getattr(self, "_status_label", None)
        if sl is not None:
            try:
                sl.configure(text=text, text_color=color)
            except tk.TclError:
                pass

    def _toggle_suggest_key_visibility(self):
        self._suggest_key_visible = not self._suggest_key_visible
        b = "\u2022"
        self._key_entry.configure(show="" if self._suggest_key_visible else b)
        self._suggest_key_toggle_btn.configure(
            text="隐藏" if self._suggest_key_visible else "显示"
        )

    def _toggle_learn_key_visibility(self):
        self._learn_key_visible = not self._learn_key_visible
        b = "\u2022"
        self._learn_key_entry.configure(show="" if self._learn_key_visible else b)
        self._learn_key_toggle_btn.configure(
            text="隐藏" if self._learn_key_visible else "显示"
        )

    def _copy_suggest_api_key(self):
        t = (self._key_var.get() or "").strip()
        if not t:
            self._flash_settings_status("前台 API Key 为空", "#C62828")
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(t)
        self._flash_settings_status("前台 API Key 已复制", "#2E7D32")

    def _copy_learn_api_key(self):
        t = (self._learn_key_var.get() or "").strip()
        if not t:
            self._flash_settings_status("后台 API Key 为空", "#C62828")
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(t)
        self._flash_settings_status("后台 API Key 已复制", "#2E7D32")

    def _copy_probe_line(self, target: str):
        bl = self._probe_status_bullets.get(target)
        dv = self._probe_detail_vars.get(target)
        parts = []
        if bl is not None:
            try:
                parts.append(bl.cget("text"))
            except tk.TclError:
                pass
        if dv is not None:
            parts.append(dv.get().strip())
        text = " ".join(p for p in parts if p).strip()
        if not text:
            self._flash_settings_status("没有可复制的状态文本", "#888888")
            return
        self._root.clipboard_clear()
        self._root.clipboard_append(text)
        self._flash_settings_status("状态已复制到剪贴板", "#2E7D32")

    def _current_listener_port(self) -> Optional[int]:
        if not self._get_runtime_bridge_port:
            return None
        try:
            return int(self._get_runtime_bridge_port())
        except Exception:
            return None

    @staticmethod
    def _fallback(primary: str, secondary: str) -> str:
        return primary.strip() or secondary.strip()

    def _get_provider_models(self, provider: str, current_value: str = "") -> list[str]:
        info = LLM_PROVIDERS.get(provider, {})
        models = list(info.get("models", []))
        current_value = current_value.strip()
        if current_value and current_value not in models:
            models.insert(0, current_value)
        return models

    @staticmethod
    def _get_model_placeholder(provider: str) -> str:
        if provider == "豆包 (火山引擎)":
            return "输入推理接入点 ID"
        if provider == "自定义":
            return "输入模型名"
        return "输入模型名或接入点 ID"

    def _current_bridge_url(self) -> str:
        try:
            port = int((self._bridge_port_var.get() or "").strip())
        except (ValueError, tk.TclError):
            port = self._config.bridge_port
        if not 1 <= port <= 65535:
            port = self._config.bridge_port
        return f"http://{_get_local_ip()}:{port}"

    def _refresh_bridge_url_label(self):
        lab = getattr(self, "_bridge_url_label", None)
        if lab is None:
            return
        try:
            if lab.winfo_exists():
                lab.configure(text=self._current_bridge_url())
        except tk.TclError:
            pass

    def _on_bridge_port_write(self, *_):
        self._refresh_bridge_url_label()
        self._refresh_qr_image()

    def _refresh_qr_image(self):
        lab = getattr(self, "_qr_label", None)
        if lab is None:
            return
        try:
            if not lab.winfo_exists():
                return
        except tk.TclError:
            return
        url = self._current_bridge_url()
        try:
            import qrcode
            from PIL import Image as PILImage
        except ImportError:
            lab.configure(image=None, text='扫码需安装：pip install "qrcode[pil]"')
            return
        qr = qrcode.QRCode(version=None, box_size=5, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        im = qr.make_image(fill_color="#1D2129", back_color="#FFFFFF").convert("RGBA")
        im2 = im.resize((160, 160), PILImage.Resampling.NEAREST)
        self._qr_ctk_image = ctk.CTkImage(light_image=im2, dark_image=im2, size=(160, 160))
        lab.configure(image=self._qr_ctk_image, text="")

    def _random_bridge_port(self):
        try:
            cur = int((self._bridge_port_var.get() or "").strip())
        except (ValueError, tk.TclError):
            cur = self._config.bridge_port
        if not bridge_port_in_use_by_others(cur, self._current_listener_port()):
            sl = getattr(self, "_status_label", None)
            if sl is not None:
                try:
                    sl.configure(
                        text="当前端口未被其他程序占用，无需更换",
                        text_color="#888888",
                    )
                except tk.TclError:
                    pass
            return
        p = pick_random_free_port()
        self._bridge_port_var.set(str(p))
        if self._on_bridge_rebind:
            self._on_bridge_rebind(p)
        sl = getattr(self, "_status_label", None)
        if sl is not None:
            try:
                sl.configure(
                    text=f"原端口被占用，已切换为 {p} 并重启桥接",
                    text_color="#4CAF50",
                )
            except tk.TclError:
                pass
        self._on_bridge_port_write()

    def _copy_bridge_url(self):
        url = self._current_bridge_url()
        try:
            self._root.clipboard_clear()
            self._root.clipboard_append(url)
            self._root.update()
        except tk.TclError:
            pass
        sl = getattr(self, "_status_label", None)
        if sl is not None:
            try:
                sl.configure(text=f"已复制: {url}", text_color="#4CAF50")
            except tk.TclError:
                pass

    def show(self):
        if self._win and self._win.winfo_exists():
            self._win.focus()
            return

        self._win = ctk.CTkToplevel(self._root)
        self._win.title("DoubaoTypeless 设置")
        self._win.geometry("620x820")
        self._win.resizable(True, True)
        self._win.attributes("-topmost", True)
        self._win.lift()
        self._win.focus_force()
        icon = getattr(self._root, "_doubao_icon_photo", None)
        if icon is not None:
            self._win.iconphoto(True, icon)

        container = ctk.CTkScrollableFrame(self._win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            container,
            text="DoubaoTypeless 设置",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(10, 12))

        ctk.CTkLabel(
            container,
            text="手机网页输入 -> 自动同步到电脑 -> 审阅后插入",
            text_color="#9aa0aa",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 8))

        # --- 桥接设置 ---
        ctk.CTkLabel(container, text="桥接设置", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#888888", anchor="w").pack(fill="x", padx=10, pady=(8, 2))

        clip_frame = ctk.CTkFrame(container)
        clip_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(clip_frame, text="剪贴板保护：").pack(side="left", padx=10)
        self._clip_var = ctk.BooleanVar(value=self._config.clipboard_protection)
        ctk.CTkSwitch(clip_frame, variable=self._clip_var, text="").pack(side="left", padx=5)

        app_frame = ctk.CTkFrame(container)
        app_frame.pack(fill="x", padx=10, pady=4)
        app_row = ctk.CTkFrame(app_frame, fg_color="transparent")
        app_row.pack(fill="x")
        if sys.platform == "win32":
            ctk.CTkLabel(app_row, text="开机自动启动：").pack(side="left", padx=10)
            self._start_win_var = tk.BooleanVar(value=self._config.start_with_windows)
            ctk.CTkSwitch(app_row, variable=self._start_win_var, text="").pack(side="left", padx=5)
        if self._on_toggle_debug_log:
            ctk.CTkButton(
                app_row,
                text="调试日志",
                width=100,
                command=self._on_toggle_debug_log,
            ).pack(side="left", padx=12)

        bridge_frame = ctk.CTkFrame(container)
        bridge_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(bridge_frame, text="手机桥接端口：").pack(side="left", padx=10)
        self._bridge_port_var = ctk.StringVar(value=str(self._config.bridge_port))
        ctk.CTkEntry(bridge_frame, textvariable=self._bridge_port_var, width=120).pack(side="left", padx=5)
        ctk.CTkButton(
            bridge_frame,
            text="随机端口",
            width=88,
            command=self._random_bridge_port,
        ).pack(side="left", padx=4)

        bridge_url_frame = ctk.CTkFrame(container)
        bridge_url_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(bridge_url_frame, text="当前访问地址：").pack(side="left", padx=10)
        self._bridge_url_label = ctk.CTkLabel(
            bridge_url_frame,
            text=f"http://{_get_local_ip()}:{self._config.bridge_port}",
            text_color="#aaaaaa",
            anchor="w",
        )
        self._bridge_url_label.pack(side="left", padx=5)
        ctk.CTkButton(
            bridge_url_frame,
            text="复制地址",
            width=88,
            command=self._copy_bridge_url,
        ).pack(side="left", padx=4)
        self._bridge_port_var.trace_add("write", lambda *_: self._on_bridge_port_write())

        ctk.CTkLabel(
            container,
            text="手机和电脑在同一个 WiFi 下，用浏览器打开上面的地址或扫码。",
            text_color="#777777",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 6))

        qr_wrap = ctk.CTkFrame(container, fg_color="transparent")
        qr_wrap.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkLabel(
            qr_wrap,
            text="手机扫码打开（需与电脑同 WiFi）",
            text_color="#888888",
            anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 4))
        self._qr_label = ctk.CTkLabel(qr_wrap, text="")
        self._qr_label.pack(padx=4, pady=2)
        self._refresh_qr_image()

        # --- 前台纠错建议 ---
        ctk.CTkLabel(container, text="前台纠错建议", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#888888", anchor="w").pack(fill="x", padx=10, pady=(12, 2))

        llm_toggle_frame = ctk.CTkFrame(container)
        llm_toggle_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(llm_toggle_frame, text="启用前台建议：").pack(side="left", padx=10)
        self._llm_enabled_var = ctk.BooleanVar(value=self._config.llm_enabled)
        ctk.CTkSwitch(llm_toggle_frame, variable=self._llm_enabled_var, text="").pack(side="left", padx=5)

        provider_frame = ctk.CTkFrame(container)
        provider_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(provider_frame, text="Provider：").pack(side="left", padx=10)
        self._provider_var = ctk.StringVar(value=self._detect_provider(self._config.llm_base_url))
        self._provider_menu = ctk.CTkOptionMenu(
            provider_frame,
            variable=self._provider_var,
            values=list(LLM_PROVIDERS.keys()),
            command=lambda choice: self._on_provider_changed(choice, "suggest"),
            width=180,
        )
        self._provider_menu.pack(side="left", padx=5)

        key_frame = ctk.CTkFrame(container)
        key_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(key_frame, text="API Key：").pack(side="left", padx=10)
        self._key_var = ctk.StringVar(value=self._config.llm_api_key)
        self._key_entry = ctk.CTkEntry(key_frame, textvariable=self._key_var, width=252, show="•")
        self._key_entry.pack(side="left", padx=5)
        self._suggest_key_toggle_btn = ctk.CTkButton(
            key_frame,
            text="显示",
            width=40,
            command=self._toggle_suggest_key_visibility,
        )
        self._suggest_key_toggle_btn.pack(side="left", padx=2)
        ctk.CTkButton(
            key_frame,
            text="复制",
            width=40,
            command=self._copy_suggest_api_key,
        ).pack(side="left", padx=2)

        model_frame = ctk.CTkFrame(container)
        model_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(model_frame, text="Model：").pack(side="left", padx=10)
        self._model_var = ctk.StringVar(value=self._config.llm_model)
        self._model_frame = model_frame

        url_frame = ctk.CTkFrame(container)
        url_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(url_frame, text="Base URL：", text_color="#666666").pack(side="left", padx=10)
        self._url_var = ctk.StringVar(value=self._config.llm_base_url)
        ctk.CTkEntry(url_frame, textvariable=self._url_var, width=340,
                     text_color="#888888").pack(side="left", padx=5)
        self._build_model_widget("suggest")

        self._suggest_probe_row = ctk.CTkFrame(container, fg_color="transparent")
        self._suggest_probe_row.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(
            self._suggest_probe_row,
            text="模型状态",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
            width=56,
            anchor="w",
        ).pack(side="left", padx=(10, 4))
        bl_s = ctk.CTkLabel(
            self._suggest_probe_row,
            text="— 未验证",
            text_color="#888888",
            font=ctk.CTkFont(size=12),
            width=76,
            anchor="w",
        )
        bl_s.pack(side="left", padx=2)
        self._probe_detail_vars["suggest"] = tk.StringVar(
            value="可点击「检测」或完成一次纠错后更新；下方文本可选中复制。"
        )
        pe_s = self._make_copyable_line_entry(self._suggest_probe_row, self._probe_detail_vars["suggest"])
        pe_s.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(
            self._suggest_probe_row,
            text="复制状态",
            width=72,
            command=lambda: self._copy_probe_line("suggest"),
        ).pack(side="left", padx=4)
        self._probe_status_bullets["suggest"] = bl_s

        domain_terms_frame = ctk.CTkFrame(container)
        domain_terms_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(domain_terms_frame, text="近期术语参考：").pack(side="left", padx=10)
        self._suggest_domain_terms_var = tk.BooleanVar(
            value=bool(getattr(self._config, "suggest_domain_terms", True))
        )
        ctk.CTkSwitch(domain_terms_frame, variable=self._suggest_domain_terms_var, text="").pack(
            side="left", padx=5
        )
        ctk.CTkLabel(
            domain_terms_frame,
            text="前台纠错时注入近窗审阅里出现过的采集术语（依赖后台学习与审阅历史）",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).pack(side="left", padx=(8, 10))

        # --- 后台学习模型 ---
        ctk.CTkLabel(container, text="后台学习模型", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#888888", anchor="w").pack(fill="x", padx=10, pady=(12, 2))

        learn_toggle_frame = ctk.CTkFrame(container)
        learn_toggle_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(learn_toggle_frame, text="启用后台学习：").pack(side="left", padx=10)
        self._learn_enabled_var = ctk.BooleanVar(value=self._config.learn_enabled)
        ctk.CTkSwitch(learn_toggle_frame, variable=self._learn_enabled_var, text="").pack(side="left", padx=5)

        learn_provider_frame = ctk.CTkFrame(container)
        learn_provider_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(learn_provider_frame, text="Provider：").pack(side="left", padx=10)
        self._learn_provider_var = ctk.StringVar(
            value=self._detect_provider(self._fallback(self._config.learn_base_url, self._config.llm_base_url))
        )
        ctk.CTkOptionMenu(
            learn_provider_frame,
            variable=self._learn_provider_var,
            values=list(LLM_PROVIDERS.keys()),
            command=lambda choice: self._on_provider_changed(choice, "learn"),
            width=180,
        ).pack(side="left", padx=5)

        learn_key_frame = ctk.CTkFrame(container)
        learn_key_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(learn_key_frame, text="API Key：").pack(side="left", padx=10)
        self._learn_key_var = ctk.StringVar(value=self._config.learn_api_key)
        self._learn_key_entry = ctk.CTkEntry(
            learn_key_frame, textvariable=self._learn_key_var, width=252, show="•"
        )
        self._learn_key_entry.pack(side="left", padx=5)
        self._learn_key_toggle_btn = ctk.CTkButton(
            learn_key_frame,
            text="显示",
            width=40,
            command=self._toggle_learn_key_visibility,
        )
        self._learn_key_toggle_btn.pack(side="left", padx=2)
        ctk.CTkButton(
            learn_key_frame,
            text="复制",
            width=40,
            command=self._copy_learn_api_key,
        ).pack(side="left", padx=2)

        learn_model_frame = ctk.CTkFrame(container)
        learn_model_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(learn_model_frame, text="Model：").pack(side="left", padx=10)
        self._learn_model_var = ctk.StringVar(
            value=self._fallback(self._config.learn_model, self._config.llm_model)
        )
        self._learn_model_frame = learn_model_frame

        learn_url_frame = ctk.CTkFrame(container)
        learn_url_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(learn_url_frame, text="Base URL：", text_color="#666666").pack(side="left", padx=10)
        self._learn_url_var = ctk.StringVar(
            value=self._fallback(self._config.learn_base_url, self._config.llm_base_url)
        )
        ctk.CTkEntry(learn_url_frame, textvariable=self._learn_url_var, width=340,
                     text_color="#888888").pack(side="left", padx=5)
        self._build_model_widget("learn")

        self._learn_probe_row = ctk.CTkFrame(container, fg_color="transparent")
        self._learn_probe_row.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(
            self._learn_probe_row,
            text="模型状态",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
            width=56,
            anchor="w",
        ).pack(side="left", padx=(10, 4))
        bl_l = ctk.CTkLabel(
            self._learn_probe_row,
            text="— 未验证",
            text_color="#888888",
            font=ctk.CTkFont(size=12),
            width=76,
            anchor="w",
        )
        bl_l.pack(side="left", padx=2)
        self._probe_detail_vars["learn"] = tk.StringVar(
            value="可点击「检测」或完成一次学习后更新；下方文本可选中复制。"
        )
        pe_l = self._make_copyable_line_entry(self._learn_probe_row, self._probe_detail_vars["learn"])
        pe_l.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(
            self._learn_probe_row,
            text="复制状态",
            width=72,
            command=lambda: self._copy_probe_line("learn"),
        ).pack(side="left", padx=4)
        self._probe_status_bullets["learn"] = bl_l

        learn_batch_frame = ctk.CTkFrame(container)
        learn_batch_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(learn_batch_frame, text="自动学习间隔：").pack(side="left", padx=10)
        self._learn_batch_interval_var = ctk.StringVar(
            value=str(int(getattr(self._config, "learn_batch_interval", 0)))
        )
        ctk.CTkEntry(learn_batch_frame, textvariable=self._learn_batch_interval_var, width=48).pack(
            side="left", padx=4
        )
        ctk.CTkLabel(
            learn_batch_frame,
            text="0=每条可学习插入单独 1 次 API（紧凑 payload）；N=每满 N 条合并为 1 次 API 一起提取术语（仅新插入入队，不自动扫历史文件）",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).pack(side="left", padx=(8, 10))

        learn_nodiff_frame = ctk.CTkFrame(container)
        learn_nodiff_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(learn_nodiff_frame, text="无差异仍学习：").pack(side="left", padx=10)
        self._learn_when_no_diff_var = tk.BooleanVar(
            value=bool(getattr(self._config, "learn_when_no_diff", False))
        )
        ctk.CTkSwitch(learn_nodiff_frame, variable=self._learn_when_no_diff_var, text="").pack(
            side="left", padx=5
        )
        ctk.CTkLabel(
            learn_nodiff_frame,
            text="放宽单次插入与历史「批量后台学习」：三者一致、无替换时也调用学习（沉淀术语 notes，更耗 API）；不表示启动时自动重学全部旧历史",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).pack(side="left", padx=(8, 10))

        # --- 纠错对照表（误听/误写 → 正确写法，供前台参考，非硬替换）---
        ctk.CTkLabel(container, text="纠错对照表", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#888888", anchor="w").pack(fill="x", padx=10, pady=(12, 2))

        dict_frame = ctk.CTkFrame(container)
        dict_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(dict_frame, text="对照表文件：").pack(side="left", padx=10)
        ctk.CTkLabel(dict_frame, text=self._config.dictionary_path,
                     text_color="#aaaaaa").pack(side="left", padx=5)
        ctk.CTkButton(dict_frame, text="编辑", width=60,
                      command=self._open_dictionary).pack(side="right", padx=10)

        # --- 全局快捷键 ---
        ctk.CTkLabel(container, text="全局快捷键", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#888888", anchor="w").pack(fill="x", padx=10, pady=(12, 2))
        ctk.CTkLabel(
            container,
            text="格式同 pynput，例如 <ctrl>+<shift>+u ；留空表示不注册。无法检测与系统/其他软件占用冲突。",
            text_color="#666666",
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=14, pady=(0, 4))
        hk1 = ctk.CTkFrame(container)
        hk1.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(hk1, text="唤起审阅窗口：").pack(side="left", padx=10)
        self._hotkey_toggle_var = ctk.StringVar(value=self._config.hotkey_toggle_review)
        ctk.CTkEntry(hk1, textvariable=self._hotkey_toggle_var, width=280,
                     placeholder_text="<ctrl>+<shift>+u").pack(side="left", padx=5)
        hk2 = ctk.CTkFrame(container)
        hk2.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(hk2, text="插入并复制：").pack(side="left", padx=10)
        self._hotkey_insert_var = ctk.StringVar(value=self._config.hotkey_insert)
        ctk.CTkEntry(hk2, textvariable=self._hotkey_insert_var, width=280,
                     placeholder_text="<alt>+<shift>+i").pack(side="left", padx=5)

        # --- 高级设置（可折叠）---
        ctk.CTkLabel(container, text="高级设置", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#888888", anchor="w").pack(fill="x", padx=10, pady=(12, 2))
        self._adv_expanded = ctk.BooleanVar(value=False)

        def _toggle_advanced():
            if self._adv_expanded.get():
                self._adv_frame.pack(fill="both", expand=True, padx=4, pady=(0, 8))
            else:
                self._adv_frame.pack_forget()

        ctk.CTkCheckBox(
            container, text="显示高级设置（提示词、超时、学习样本路径、自动写对照表）",
            variable=self._adv_expanded,
            command=_toggle_advanced,
        ).pack(anchor="w", padx=10, pady=(0, 4))

        self._adv_frame = ctk.CTkFrame(container, fg_color="transparent")

        to_frame = ctk.CTkFrame(self._adv_frame)
        to_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(to_frame, text="前台超时(s)：").pack(side="left", padx=8)
        self._llm_timeout_var = ctk.StringVar(value=str(self._config.llm_timeout))
        ctk.CTkEntry(to_frame, textvariable=self._llm_timeout_var, width=72).pack(side="left", padx=4)
        ctk.CTkLabel(to_frame, text="后台超时(s)：").pack(side="left", padx=(16, 0))
        self._learn_timeout_var = ctk.StringVar(value=str(self._config.learn_timeout))
        ctk.CTkEntry(to_frame, textvariable=self._learn_timeout_var, width=72).pack(side="left", padx=4)

        temp_frame = ctk.CTkFrame(self._adv_frame)
        temp_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(temp_frame, text="前台 temperature：").pack(side="left", padx=8)
        self._llm_temperature_var = tk.StringVar(
            value=""
            if getattr(self._config, "llm_temperature", None) is None
            else str(self._config.llm_temperature)
        )
        ctk.CTkEntry(
            temp_frame,
            textvariable=self._llm_temperature_var,
            width=72,
            placeholder_text="空=自动",
        ).pack(side="left", padx=4)
        ctk.CTkLabel(temp_frame, text="后台 temperature：").pack(side="left", padx=(16, 0))
        self._learn_temperature_var = tk.StringVar(
            value=""
            if getattr(self._config, "learn_temperature", None) is None
            else str(self._config.learn_temperature)
        )
        ctk.CTkEntry(
            temp_frame,
            textvariable=self._learn_temperature_var,
            width=72,
            placeholder_text="空=自动",
        ).pack(side="left", padx=4)
        ctk.CTkLabel(
            temp_frame,
            text="留空按 Base URL 自动；MiniMax 须 (0,1]",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(12, 8))

        sp_frame = ctk.CTkFrame(self._adv_frame)
        sp_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(sp_frame, text="学习样本 JSONL：").pack(side="left", padx=8)
        self._learn_samples_var = ctk.StringVar(value=self._config.learning_samples_path)
        ctk.CTkEntry(sp_frame, textvariable=self._learn_samples_var, width=360).pack(side="left", padx=4)

        hp_frame = ctk.CTkFrame(self._adv_frame)
        hp_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(hp_frame, text="审阅历史 JSON：").pack(side="left", padx=8)
        self._review_hist_path_var = ctk.StringVar(value=self._config.review_history_path)
        ctk.CTkEntry(hp_frame, textvariable=self._review_hist_path_var, width=360).pack(side="left", padx=4)

        dt_path_frame = ctk.CTkFrame(self._adv_frame)
        dt_path_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(dt_path_frame, text="专业术语库 JSON：").pack(side="left", padx=8)
        self._domain_terms_path_var = ctk.StringVar(
            value=getattr(self._config, "domain_terms_path", "./data/domain_terms.json")
        )
        ctk.CTkEntry(dt_path_frame, textvariable=self._domain_terms_path_var, width=360).pack(
            side="left", padx=4
        )

        dt_num_frame = ctk.CTkFrame(self._adv_frame)
        dt_num_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(dt_num_frame, text="术语近窗条数：").pack(side="left", padx=8)
        self._domain_topic_window_var = ctk.StringVar(
            value=str(int(getattr(self._config, "domain_term_topic_window", 50)))
        )
        ctk.CTkEntry(dt_num_frame, textvariable=self._domain_topic_window_var, width=56).pack(
            side="left", padx=4
        )
        ctk.CTkLabel(dt_num_frame, text="注入上限：").pack(side="left", padx=(16, 0))
        self._domain_terms_cap_var = ctk.StringVar(
            value=str(int(getattr(self._config, "domain_terms_prompt_cap", 80)))
        )
        ctk.CTkEntry(dt_num_frame, textvariable=self._domain_terms_cap_var, width=48).pack(
            side="left", padx=4
        )
        ctk.CTkLabel(dt_num_frame, text="词库最多条数：").pack(side="left", padx=(16, 0))
        self._domain_terms_max_store_var = ctk.StringVar(
            value=str(int(getattr(self._config, "domain_terms_max_store", 300)))
        )
        ctk.CTkEntry(dt_num_frame, textvariable=self._domain_terms_max_store_var, width=56).pack(
            side="left", padx=4
        )

        lp_frame = ctk.CTkFrame(self._adv_frame)
        lp_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(lp_frame, text="学习队列 JSON：").pack(side="left", padx=8)
        self._learn_pending_path_var = ctk.StringVar(value=self._config.learn_pending_path)
        ctk.CTkEntry(lp_frame, textvariable=self._learn_pending_path_var, width=360).pack(side="left", padx=4)

        ctk.CTkLabel(self._adv_frame, text="前台 system 提示词", anchor="w",
                     text_color="#777777").pack(fill="x", padx=10, pady=(6, 0))
        self._llm_prompt_box = ctk.CTkTextbox(self._adv_frame, height=90, font=ctk.CTkFont(size=12))
        self._llm_prompt_box.pack(fill="x", padx=10, pady=4)
        self._llm_prompt_box.insert("1.0", self._config.llm_system_prompt or SYSTEM_PROMPT)

        ctk.CTkLabel(self._adv_frame, text="后台学习 system 提示词", anchor="w",
                     text_color="#777777").pack(fill="x", padx=10, pady=(4, 0))
        self._learn_sys_box = ctk.CTkTextbox(self._adv_frame, height=56, font=ctk.CTkFont(size=12))
        self._learn_sys_box.pack(fill="x", padx=10, pady=4)
        self._learn_sys_box.insert("1.0", self._config.learn_system_prompt or LEARN_SYSTEM_DEFAULT)

        ctk.CTkLabel(self._adv_frame, text="后台学习 user 任务说明", anchor="w",
                     text_color="#777777").pack(fill="x", padx=10, pady=(4, 0))
        self._learn_user_box = ctk.CTkTextbox(self._adv_frame, height=120, font=ctk.CTkFont(size=12))
        self._learn_user_box.pack(fill="x", padx=10, pady=4)
        self._learn_user_box.insert("1.0", self._config.learn_user_prompt or LEARN_PROMPT)

        dict_adv = ctk.CTkFrame(self._adv_frame)
        dict_adv.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(dict_adv, text="学习后写对照表：").pack(side="left", padx=8)
        mode_vals = sorted(DICT_WRITE_MODES)
        self._dict_mode_var = ctk.StringVar(
            value=self._config.dict_write_mode if self._config.dict_write_mode in mode_vals else "off"
        )
        ctk.CTkOptionMenu(dict_adv, variable=self._dict_mode_var, values=list(mode_vals), width=100).pack(
            side="left", padx=4
        )
        ctk.CTkLabel(dict_adv, text="单次最多写入条数：").pack(side="left", padx=(12, 0))
        self._dict_max_pairs_var = ctk.StringVar(value=str(self._config.dict_auto_max_pairs))
        ctk.CTkEntry(dict_adv, textvariable=self._dict_max_pairs_var, width=48).pack(side="left", padx=4)
        ctk.CTkLabel(dict_adv, text="min置信度：").pack(side="left", padx=(8, 0))
        self._dict_min_conf_var = ctk.StringVar(value=str(self._config.dict_auto_min_confidence))
        ctk.CTkEntry(dict_adv, textvariable=self._dict_min_conf_var, width=48).pack(side="left", padx=4)

        ctk.CTkLabel(self._adv_frame, text="对照表过滤正则（每行一条，匹配 wrong 或 correct 则丢弃）", anchor="w",
                     text_color="#777777").pack(fill="x", padx=10, pady=(4, 0))
        self._dict_regex_box = ctk.CTkTextbox(self._adv_frame, height=64, font=ctk.CTkFont(size=11))
        self._dict_regex_box.pack(fill="x", padx=10, pady=4)
        self._dict_regex_box.insert("1.0", self._config.dict_block_regexes or "")

        # 保存
        ctk.CTkButton(
            container, text="保存", command=self._save, width=120
        ).pack(pady=16)

        self._status_label = ctk.CTkLabel(
            container, text="", font=ctk.CTkFont(size=12), text_color="#888888"
        )
        self._status_label.pack()

        self._llm_control_frames = [
            provider_frame,
            key_frame,
            model_frame,
            self._suggest_probe_row,
            url_frame,
            domain_terms_frame,
        ]
        self._learn_control_frames = [
            learn_provider_frame,
            learn_key_frame,
            learn_model_frame,
            self._learn_probe_row,
            learn_url_frame,
            learn_batch_frame,
        ]
        self._update_group_state("suggest")
        self._update_group_state("learn")
        self._llm_enabled_var.trace_add("write", lambda *_: self._update_group_state("suggest"))
        self._learn_enabled_var.trace_add("write", lambda *_: self._update_group_state("learn"))

    def _detect_provider(self, url: str) -> str:
        for name, info in LLM_PROVIDERS.items():
            preset_url = info.get("url", "")
            if preset_url and url and preset_url.rstrip("/") == url.rstrip("/"):
                return name
        return "自定义" if url else "DeepSeek"

    def _on_provider_changed(self, choice: str, target: str):
        info = LLM_PROVIDERS.get(choice, {})
        url = info.get("url", "")
        models = self._get_provider_models(choice)
        url_var = self._get_var(target, "url")
        model_var = self._get_var(target, "model")
        if url and url_var:
            url_var.set(url)
        if model_var:
            model_var.set(models[0] if models else "")
        if "temperature" in info and choice != "自定义":
            tv = (
                self._llm_temperature_var
                if target == "suggest"
                else self._learn_temperature_var
            )
            t = info.get("temperature")
            tv.set("" if t is None else str(t))
        self._build_model_widget(target)

    def _get_var(self, target: str, kind: str):
        attr_map = {
            ("suggest", "provider"): "_provider_var",
            ("suggest", "model"): "_model_var",
            ("suggest", "url"): "_url_var",
            ("suggest", "custom"): "_custom_model_var",
            ("learn", "provider"): "_learn_provider_var",
            ("learn", "model"): "_learn_model_var",
            ("learn", "url"): "_learn_url_var",
            ("learn", "custom"): "_learn_custom_model_var",
        }
        attr_name = attr_map.get((target, kind))
        return getattr(self, attr_name, None) if attr_name else None

    def _get_model_frame(self, target: str):
        return self._model_frame if target == "suggest" else self._learn_model_frame

    def _build_model_widget(self, target: str):
        model_frame = self._get_model_frame(target)
        for child in list(model_frame.winfo_children()):
            child.destroy()
        ctk.CTkLabel(model_frame, text="Model：").pack(side="left", padx=10)
        provider = self._get_var(target, "provider").get()
        model_var = self._get_var(target, "model")
        current_model = model_var.get().strip()
        models = self._get_provider_models(provider, current_model)
        if models:
            if not current_model:
                model_var.set(models[0])
            option_menu = ctk.CTkOptionMenu(
                model_frame, variable=self._get_var(target, "model"),
                values=models, width=180,
            )
            option_menu.pack(side="left", padx=5)
            option_menu.set(model_var.get())
        else:
            ctk.CTkEntry(
                model_frame, textvariable=model_var, width=180,
                placeholder_text=self._get_model_placeholder(provider),
            ).pack(side="left", padx=5)
        if target == "suggest":
            self._custom_model_var = ctk.StringVar()
            custom_var = self._custom_model_var
        else:
            self._learn_custom_model_var = ctk.StringVar()
            custom_var = self._learn_custom_model_var
        ctk.CTkEntry(
            model_frame, textvariable=custom_var, width=100,
            placeholder_text="新模型",
        ).pack(side="left", padx=(4, 0))
        ctk.CTkButton(
            model_frame, text="+", width=30,
            command=lambda: self._add_custom_model(target),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            model_frame,
            text="检测",
            width=44,
            command=lambda t=target: self._probe_model_clicked(t),
        ).pack(side="left", padx=(6, 4))
        self._update_group_state(target)
        self.refresh_model_probe_labels()

    def refresh_model_probe_labels(self):
        if not self._get_model_health:
            return
        try:
            s_ok, s_msg, l_ok, l_msg = self._get_model_health()
        except Exception:
            return
        self._paint_probe_status("suggest", s_ok, s_msg)
        self._paint_probe_status("learn", l_ok, l_msg)

    def _paint_probe_status(self, target: str, ok: Optional[bool], msg: str):
        bl = self._probe_status_bullets.get(target)
        dv = self._probe_detail_vars.get(target)
        if bl is None or dv is None:
            return
        msg = (msg or "").strip()
        try:
            bl.winfo_exists()
        except tk.TclError:
            return
        if ok is True:
            bl.configure(text="● 可用", text_color="#2E7D32")
            dv.set(("模型可用。" + (f" {msg}" if msg else "")).strip())
        elif ok is False:
            bl.configure(text="● 不可用", text_color="#C62828")
            dv.set(msg or "请求失败，请查看 debug.log。")
        else:
            bl.configure(text="— 未验证", text_color="#888888")
            dv.set(
                "可点击「检测」或完成一次纠错/学习后更新；完整报错在此，可选中复制。"
            )

    def _probe_model_clicked(self, target: str):
        if not self._on_model_probe:
            return
        if target == "suggest":
            url = (self._url_var.get() or "").strip()
            key = (self._key_var.get() or "").strip()
            model = (self._model_var.get() or "").strip()
        else:
            url = (self._learn_url_var.get() or "").strip()
            key = (self._learn_key_var.get() or "").strip()
            model = (self._learn_model_var.get() or "").strip()
        bl = self._probe_status_bullets.get(target)
        dv = self._probe_detail_vars.get(target)
        if bl is not None:
            try:
                bl.configure(text="…", text_color="#F57C00")
            except tk.TclError:
                pass
        if dv is not None:
            dv.set("正在探测…")
        cfg = {"base_url": url, "api_key": key, "model": model}
        raw_t = (
            (self._llm_temperature_var.get() or "").strip()
            if target == "suggest"
            else (self._learn_temperature_var.get() or "").strip()
        )
        if raw_t:
            try:
                cfg["temperature"] = float(raw_t)
            except ValueError:
                pass
        self._on_model_probe(target, cfg)

    def _update_group_state(self, target: str):
        if not hasattr(self, "_llm_control_frames") or not hasattr(self, "_learn_control_frames"):
            return
        enabled = self._llm_enabled_var.get() if target == "suggest" else self._learn_enabled_var.get()
        frames = self._llm_control_frames if target == "suggest" else self._learn_control_frames
        state = "normal" if enabled else "disabled"
        for frame in frames:
            for child in frame.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    child.configure(text_color="#bbbbbb" if enabled else "#666666")
                    continue
                try:
                    child.configure(state=state)
                except Exception:
                    pass

    def _add_custom_model(self, target: str):
        import json
        custom_var = self._custom_model_var if target == "suggest" else self._learn_custom_model_var
        model = custom_var.get().strip()
        if not model:
            return
        provider = self._get_var(target, "provider").get()
        if provider == "自定义":
            self._get_var(target, "model").set(model)
            return
        info = LLM_PROVIDERS.get(provider, {})
        models = info.get("models", [])
        if model not in models:
            models.append(model)
            info["models"] = models
            try:
                save_data = {k: v for k, v in LLM_PROVIDERS.items() if k != "自定义"}
                with open(_PROVIDERS_PATH, "w", encoding="utf-8") as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        self._get_var(target, "model").set(model)
        custom_var.set("")
        self._build_model_widget(target)

    def _open_dictionary(self):
        import subprocess
        dict_path = Path(self._config.dictionary_path).resolve()
        if not dict_path.exists():
            dict_path.write_text(
                "# 纠错对照表（误听/误写 → 正确写法）\n"
                "# 供前台 LLM 作参考，不是运行时硬替换。\n"
                "# 学习流水里筛选通过的 candidate_pairs 可自动追加到此文件。\n"
                "# 格式：左侧误识形式=右侧正确形式（每行一条）\n",
                encoding="utf-8",
            )
        subprocess.Popen(["notepad.exe", str(dict_path)])

    def _save(self):
        self._config.clipboard_protection = self._clip_var.get()
        if sys.platform == "win32" and hasattr(self, "_start_win_var"):
            self._config.start_with_windows = self._start_win_var.get()
        try:
            bridge_port = int(self._bridge_port_var.get().strip())
        except ValueError:
            self._status_label.configure(text="端口必须是数字", text_color="#F44336")
            return
        if not 1 <= bridge_port <= 65535:
            self._status_label.configure(text="端口必须在 1-65535 之间", text_color="#F44336")
            return
        self._config.bridge_port = bridge_port

        hk_ok, hk_err = validate_all_for_save(
            self._hotkey_toggle_var.get(),
            self._hotkey_insert_var.get(),
        )
        if not hk_ok:
            self._status_label.configure(text=f"快捷键: {hk_err}", text_color="#F44336")
            return
        self._config.hotkey_toggle_review = self._hotkey_toggle_var.get().strip()
        self._config.hotkey_insert = self._hotkey_insert_var.get().strip()

        if self._llm_enabled_var.get():
            if not self._url_var.get().strip():
                self._status_label.configure(text="前台建议 Base URL 不能为空", text_color="#F44336")
                return
            if not self._key_var.get().strip():
                self._status_label.configure(text="前台建议 API Key 不能为空", text_color="#F44336")
                return
            if not self._model_var.get().strip():
                self._status_label.configure(text="前台建议 Model 不能为空", text_color="#F44336")
                return
        self._config.llm_enabled = self._llm_enabled_var.get()
        self._config.suggest_domain_terms = self._suggest_domain_terms_var.get()
        self._config.llm_base_url = self._url_var.get().strip()
        self._config.llm_api_key = self._key_var.get().strip()
        self._config.llm_model = self._model_var.get().strip()
        if self._learn_enabled_var.get():
            if not self._learn_url_var.get().strip():
                self._status_label.configure(text="后台学习 Base URL 不能为空", text_color="#F44336")
                return
            if not self._learn_key_var.get().strip():
                self._status_label.configure(text="后台学习 API Key 不能为空", text_color="#F44336")
                return
            if not self._learn_model_var.get().strip():
                self._status_label.configure(text="后台学习 Model 不能为空", text_color="#F44336")
                return
        self._config.learn_enabled = self._learn_enabled_var.get()
        self._config.learn_base_url = self._learn_url_var.get().strip()
        self._config.learn_api_key = self._learn_key_var.get().strip()
        self._config.learn_model = self._learn_model_var.get().strip()

        try:
            lbi = int(self._learn_batch_interval_var.get().strip())
        except ValueError:
            self._status_label.configure(text="自动学习间隔须为整数", text_color="#F44336")
            return
        if not 0 <= lbi <= 50:
            self._status_label.configure(text="自动学习间隔须在 0～50（0=立即）", text_color="#F44336")
            return
        self._config.learn_batch_interval = lbi
        self._config.learn_when_no_diff = self._learn_when_no_diff_var.get()

        try:
            llm_to = float(self._llm_timeout_var.get().strip())
            learn_to = float(self._learn_timeout_var.get().strip())
        except ValueError:
            self._status_label.configure(text="高级设置里的超时必须是数字", text_color="#F44336")
            return
        if not 0.5 <= llm_to <= 120 or not 0.5 <= learn_to <= 120:
            self._status_label.configure(text="超时须在 0.5～120 秒之间", text_color="#F44336")
            return
        self._config.llm_timeout = llm_to
        self._config.learn_timeout = learn_to

        def _parse_opt_temperature(label: str, raw: str):
            s = (raw or "").strip()
            if not s:
                return None
            try:
                return float(s)
            except ValueError:
                raise ValueError(label)

        try:
            self._config.llm_temperature = _parse_opt_temperature(
                "前台 temperature", self._llm_temperature_var.get()
            )
            self._config.learn_temperature = _parse_opt_temperature(
                "后台 temperature", self._learn_temperature_var.get()
            )
        except ValueError as e:
            self._status_label.configure(text=str(e) + " 须为数字或留空", text_color="#F44336")
            return

        samples_path = self._learn_samples_var.get().strip()
        self._config.learning_samples_path = samples_path or "./learning_samples.jsonl"

        self._config.review_history_path = (
            self._review_hist_path_var.get().strip() or "./review_history.json"
        )
        self._config.learn_pending_path = (
            self._learn_pending_path_var.get().strip() or "./learn_pending.json"
        )
        self._config.domain_terms_path = (
            self._domain_terms_path_var.get().strip() or "./data/domain_terms.json"
        )
        try:
            dtw = int(self._domain_topic_window_var.get().strip())
            dcap = int(self._domain_terms_cap_var.get().strip())
            dmax = int(self._domain_terms_max_store_var.get().strip())
        except ValueError:
            self._status_label.configure(text="术语近窗/注入上限/词库条数须为整数", text_color="#F44336")
            return
        if not 5 <= dtw <= 200:
            self._status_label.configure(text="术语近窗条数须在 5～200", text_color="#F44336")
            return
        if not 10 <= dcap <= 120:
            self._status_label.configure(text="术语注入上限须在 10～120", text_color="#F44336")
            return
        if not 50 <= dmax <= 2000:
            self._status_label.configure(text="词库最多条数须在 50～2000", text_color="#F44336")
            return
        self._config.domain_term_topic_window = dtw
        self._config.domain_terms_prompt_cap = dcap
        self._config.domain_terms_max_store = dmax

        llm_prompt = self._llm_prompt_box.get("1.0", "end-1c").strip()
        self._config.llm_system_prompt = "" if llm_prompt == SYSTEM_PROMPT else llm_prompt
        learn_sys = self._learn_sys_box.get("1.0", "end-1c").strip()
        self._config.learn_system_prompt = "" if learn_sys == LEARN_SYSTEM_DEFAULT else learn_sys
        learn_user = self._learn_user_box.get("1.0", "end-1c").strip()
        self._config.learn_user_prompt = "" if learn_user == LEARN_PROMPT else learn_user

        dm = (self._dict_mode_var.get() or "off").strip().lower()
        if dm not in DICT_WRITE_MODES:
            self._status_label.configure(text="写对照表模式无效", text_color="#F44336")
            return
        self._config.dict_write_mode = dm

        try:
            max_pairs = int(self._dict_max_pairs_var.get().strip())
        except ValueError:
            self._status_label.configure(text="单次最多写入条数必须是整数", text_color="#F44336")
            return
        if not 1 <= max_pairs <= 50:
            self._status_label.configure(text="单次最多写入条数须在 1～50", text_color="#F44336")
            return
        self._config.dict_auto_max_pairs = max_pairs

        try:
            min_conf = float(self._dict_min_conf_var.get().strip())
        except ValueError:
            self._status_label.configure(text="min置信度必须是数字", text_color="#F44336")
            return
        if not 0.0 <= min_conf <= 1.0:
            self._status_label.configure(text="min置信度须在 0～1", text_color="#F44336")
            return
        self._config.dict_auto_min_confidence = min_conf

        self._config.dict_block_regexes = self._dict_regex_box.get("1.0", "end-1c").strip()

        self._config.save()
        self._refresh_bridge_url_label()
        self._refresh_qr_image()
        startup_warn = ""
        if sys.platform == "win32" and hasattr(self, "_start_win_var"):
            from windows_startup import apply_start_with_windows

            ok, err = apply_start_with_windows(self._config.start_with_windows)
            if not ok and err:
                startup_warn = f" 开机自启未生效: {err}"
        if startup_warn:
            self._status_label.configure(
                text="已保存，但" + startup_warn.strip(),
                text_color="#FF9800",
            )
        else:
            self._status_label.configure(text="已保存！", text_color="#4CAF50")
        if self._on_save:
            self._on_save(self._config)


class GUIManager:
    """在独立线程中运行 CustomTkinter 主循环并调度界面更新。"""

    def __init__(
        self,
        logger: Optional[Callable[[str], None]] = None,
        history_path: str = "",
    ):
        global _external_logger
        if logger:
            _external_logger = logger
        self._history_path = (history_path or "").strip()
        self._root: Optional[ctk.CTk] = None
        self._review: Optional[ReviewWindow] = None
        self._settings: Optional[SettingsWindow] = None
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._on_insert: Optional[Callable] = None
        self._on_batch_learn: Optional[Callable[[list[dict]], None]] = None
        self._debug_log: Optional[DebugLogWindow] = None
        self._on_model_probe: Optional[Callable[[str, dict], None]] = None
        self._suggest_model_ok: Optional[bool] = None
        self._suggest_model_msg: str = ""
        self._learn_model_ok: Optional[bool] = None
        self._learn_model_msg: str = ""

    def set_history_path(self, path: str):
        self._history_path = (path or "").strip()

    def _persist_review_history(self, items: list[dict]):
        if not self._history_path:
            return
        try:
            p = Path(self._history_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            _gui_log(f"review_history write: {e}")

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self._root = ctk.CTk()
        self._root.withdraw()
        ph = apply_tk_window_icon(self._root)
        if ph is not None:
            self._root._doubao_icon_photo = ph
        self._review = ReviewWindow(
            self._root,
            on_insert=self._handle_insert,
            on_batch_learn=self._handle_batch_learn,
            on_history_persist=self._persist_review_history,
        )
        self._ready.set()
        self._poll_queue()
        self._root.mainloop()

    def _handle_insert(self, payload: dict):
        if self._on_insert:
            self._on_insert(payload)

    def _handle_batch_learn(self, records: list[dict]):
        if self._on_batch_learn:
            self._on_batch_learn(records)

    def _poll_queue(self):
        try:
            while True:
                func, args = self._queue.get_nowait()
                try:
                    func(*args)
                except Exception:
                    _gui_log(traceback.format_exc().strip())
        except queue.Empty:
            pass
        if self._root:
            self._root.after(50, self._poll_queue)

    def _schedule(self, func, *args):
        self._queue.put((func, args))

    def set_on_insert(self, callback: Callable):
        self._on_insert = callback

    def set_on_batch_learn(self, callback: Optional[Callable[[list[dict]], None]]):
        self._on_batch_learn = callback

    def set_learn_when_no_diff_getter(self, fn: Optional[Callable[[], bool]]):
        """由 Main 注册，供审阅窗口历史菜单与自动学习开关对齐（读取当前 config）。"""
        self._schedule(self._apply_learn_when_no_diff_getter, fn)

    def _apply_learn_when_no_diff_getter(self, fn: Optional[Callable[[], bool]]):
        if self._review:
            self._review.set_learn_when_no_diff_getter(fn)

    def set_on_model_probe(self, callback: Optional[Callable[[str, dict], None]]):
        self._on_model_probe = callback

    def set_model_health(self, target: str, ok: Optional[bool], msg: str = ""):
        """target: suggest | learn；ok None=未验证"""
        t = (target or "").strip().lower()
        if t == "suggest":
            self._suggest_model_ok = ok
            self._suggest_model_msg = (msg or "").strip()
        elif t == "learn":
            self._learn_model_ok = ok
            self._learn_model_msg = (msg or "").strip()
        else:
            return
        self._schedule(self._sync_settings_probe_labels)

    def _sync_settings_probe_labels(self):
        if self._settings and getattr(self._settings, "refresh_model_probe_labels", None):
            try:
                self._settings.refresh_model_probe_labels()
            except Exception:
                pass

    def _model_health_tuple(self) -> Tuple[Optional[bool], str, Optional[bool], str]:
        return (
            self._suggest_model_ok,
            self._suggest_model_msg,
            self._learn_model_ok,
            self._learn_model_msg,
        )

    def show_recording(self):
        self._schedule(self._review.show_recording)

    def update_interim(self, text: str):
        self._schedule(self._review.update_interim, text)

    def show_processing(self):
        self._schedule(self._review.show_processing)

    def show_final(self, raw_text: str, suggestions: list[Suggestion], llm_text: str):
        self._schedule(self._review.show_final, raw_text, suggestions, llm_text)

    def hide(self):
        self._schedule(self._review.hide)

    def add_history(self, record: dict):
        self._schedule(self._review.add_history, record)

    def mark_history_learn_ok(self, raw_text: str, llm_text: str, final_text: str):
        self._schedule(self._review.mark_learn_ok, raw_text, llm_text, final_text)

    def import_history(self, items: list[dict]):
        self._schedule(self._review.import_history, items)

    def bring_review_to_front(self):
        self._schedule(self._review.bring_to_front)

    def trigger_review_insert(self):
        self._schedule(self._review.trigger_insert)

    def open_settings(
        self,
        config: Config,
        on_save: Optional[Callable] = None,
        *,
        get_runtime_bridge_port: Optional[Callable[[], int]] = None,
        on_bridge_rebind: Optional[Callable[[int], None]] = None,
    ):
        self._schedule(
            self._open_settings_impl,
            config,
            on_save,
            get_runtime_bridge_port,
            on_bridge_rebind,
        )

    def _open_settings_impl(
        self,
        config: Config,
        on_save: Optional[Callable] = None,
        get_runtime_bridge_port: Optional[Callable[[], int]] = None,
        on_bridge_rebind: Optional[Callable[[int], None]] = None,
    ):
        if self._settings and self._settings._win and self._settings._win.winfo_exists():
            self._settings._win.lift()
            self._settings._win.focus_force()
            self._schedule(self._sync_settings_probe_labels)
            return
        self._settings = SettingsWindow(
            self._root,
            config,
            on_save,
            get_runtime_bridge_port=get_runtime_bridge_port,
            on_bridge_rebind=on_bridge_rebind,
            on_toggle_debug_log=self._toggle_debug_log_impl,
            get_model_health=self._model_health_tuple,
            on_model_probe=self._forward_model_probe,
        )
        self._settings.show()

    def _forward_model_probe(self, target: str, cfg: dict):
        if self._on_model_probe:
            self._on_model_probe(target, cfg)

    def _toggle_debug_log_impl(self):
        if self._root is None:
            return
        if self._debug_log is None:
            self._debug_log = DebugLogWindow(self._root)
        self._debug_log.toggle()

    def show_debug_log(self):
        self._schedule(self._toggle_debug_log_impl)

    def stop(self):
        if self._root:
            self._schedule(self._root.quit)
