"""词库管理：专业术语（domain_terms.json）与误听对照表（dictionary.txt）。"""

from __future__ import annotations

import copy
import tkinter as tk
import tkinter.messagebox as tk_msg
from typing import Callable, Optional

import customtkinter as ctk

from config import Config
from gui_text_bindings import bind_ctk_subtree_standard
from polish import split_dictionary_file, write_dictionary_file
from term_bank import TermBank, TermEntry


class VocabularyManagerWindow:
    _UNDO_MAX = 30

    def __init__(
        self,
        root: ctk.CTk,
        config: Config,
        *,
        on_saved: Callable[[], None],
    ):
        self._root = root
        self._config = config
        self._on_saved = on_saved
        self._win: Optional[ctk.CTkToplevel] = None
        self._tabs: Optional[ctk.CTkTabview] = None
        self._terms_scroll: Optional[ctk.CTkScrollableFrame] = None
        self._pairs_scroll: Optional[ctk.CTkScrollableFrame] = None
        self._search_var = tk.StringVar(value="")
        self._undo_stack: list[dict] = []

        self._header_lines, self._pairs = split_dictionary_file(config.dictionary_path)
        self._tbank = TermBank(
            config.domain_terms_path,
            max_store=config.domain_terms_max_store,
            log=None,
        )
        self._tbank.load()

    def show(self):
        if self._win is not None and self._win.winfo_exists():
            self._win.lift()
            self._win.focus_force()
            return

        self._win = ctk.CTkToplevel(self._root)
        self._win.title("词库管理")
        self._win.geometry("640x560")
        self._win.minsize(520, 420)
        icon = getattr(self._root, "_doubao_icon_photo", None)
        if icon is not None:
            try:
                self._win.iconphoto(True, icon)
            except tk.TclError:
                pass

        top = ctk.CTkFrame(self._win, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(top, text="搜索：", text_color="#86909C").pack(side="left", padx=(0, 6))
        ctk.CTkEntry(top, textvariable=self._search_var, width=200, placeholder_text="过滤显示").pack(
            side="left", padx=(0, 8)
        )
        self._search_var.trace_add("write", lambda *_: self._refresh_lists())

        ctk.CTkButton(top, text="撤销", width=72, command=self._undo).pack(side="left", padx=4)
        ctk.CTkButton(
            top,
            text="保存并应用到当前会话",
            width=160,
            fg_color="#3370FF",
            hover_color="#2860E0",
            command=self._save_all,
        ).pack(side="right", padx=4)

        self._tabs = ctk.CTkTabview(self._win)
        self._tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._tabs.add("专业术语")
        self._tabs.add("误听对照表")

        terms_tab = self._tabs.tab("专业术语")
        tbar = ctk.CTkFrame(terms_tab, fg_color="transparent")
        tbar.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(tbar, text="+ 添加术语", width=110, command=self._add_term_dialog).pack(
            side="left"
        )
        ctk.CTkLabel(
            tbar,
            text="近窗话题术语，带命中次数；来源见 domain_terms 路径（设置-高级）。",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=12)

        self._terms_scroll = ctk.CTkScrollableFrame(terms_tab, fg_color="#F7F8FA", corner_radius=8)
        self._terms_scroll.pack(fill="both", expand=True)

        pairs_tab = self._tabs.tab("误听对照表")
        pbar = ctk.CTkFrame(pairs_tab, fg_color="transparent")
        pbar.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(pbar, text="+ 添加条目", width=110, command=self._add_pair_dialog).pack(side="left")
        ctk.CTkLabel(
            pbar,
            text="误听→正确；写入 dictionary 路径。命中数尚未统计，卡片显示为 —。",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=12)

        self._pairs_scroll = ctk.CTkScrollableFrame(pairs_tab, fg_color="#F7F8FA", corner_radius=8)
        self._pairs_scroll.pack(fill="both", expand=True)

        bind_ctk_subtree_standard(self._win, self._win)
        self._refresh_lists()

    def _push_undo(self):
        snap = {
            "terms": copy.deepcopy([e.to_json() for e in self._tbank.list_entries_sorted()]),
            "pairs": list(self._pairs),
            "header": list(self._header_lines),
        }
        self._undo_stack.append(snap)
        if len(self._undo_stack) > self._UNDO_MAX:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack or self._terms_scroll is None:
            return
        snap = self._undo_stack.pop()
        self._tbank.replace_from_json_terms(snap["terms"])
        self._pairs = list(snap["pairs"])
        self._header_lines = list(snap["header"])
        self._refresh_lists()

    def _search_q(self) -> str:
        return (self._search_var.get() or "").strip().lower()

    def _refresh_lists(self):
        q = self._search_q()

        if self._terms_scroll:
            for w in self._terms_scroll.winfo_children():
                w.destroy()
            for ent in self._tbank.list_entries_sorted():
                if q and q not in ent.display.lower():
                    continue
                self._term_card(ent)

        if self._pairs_scroll:
            for w in self._pairs_scroll.winfo_children():
                w.destroy()
            for i, (w, c) in enumerate(self._pairs):
                if q and q not in w.lower() and q not in c.lower():
                    continue
                self._pair_card(i, w, c)

    def _term_card(self, ent: TermEntry):
        row = ctk.CTkFrame(self._terms_scroll, fg_color="#FFFFFF", corner_radius=8)
        row.pack(fill="x", pady=4, padx=4)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        ctk.CTkLabel(
            left,
            text=ent.display,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#1D2129",
        ).pack(fill="x")
        ctk.CTkLabel(
            left,
            text=f"命中 {ent.hits}  ·  {ent.last_ts or '—'}",
            anchor="w",
            text_color="#86909C",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x")
        ctk.CTkButton(
            row,
            text="删除",
            width=64,
            fg_color="#FFECE8",
            hover_color="#FFD4CC",
            text_color="#D4380D",
            command=lambda d=ent.display: self._remove_term(d),
        ).pack(side="right", padx=10, pady=8)

    def _pair_card(self, index: int, wrong: str, correct: str):
        row = ctk.CTkFrame(self._pairs_scroll, fg_color="#FFFFFF", corner_radius=8)
        row.pack(fill="x", pady=4, padx=4)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        ctk.CTkLabel(
            left,
            text=f"{wrong}  →  {correct}",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color="#1D2129",
        ).pack(fill="x")
        ctk.CTkLabel(
            left,
            text="命中 —",
            anchor="w",
            text_color="#86909C",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x")
        bf = ctk.CTkFrame(row, fg_color="transparent")
        bf.pack(side="right", padx=8, pady=8)
        ctk.CTkButton(
            bf,
            text="编辑",
            width=52,
            fg_color="#F2F3F5",
            hover_color="#E5E6EB",
            text_color="#1D2129",
            command=lambda: self._edit_pair_dialog(index),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bf,
            text="删除",
            width=52,
            fg_color="#FFECE8",
            hover_color="#FFD4CC",
            text_color="#D4380D",
            command=lambda: self._remove_pair(index),
        ).pack(side="left", padx=2)

    def _remove_term(self, display: str):
        self._push_undo()
        if self._tbank.remove_display(display):
            self._refresh_lists()

    def _remove_pair(self, index: int):
        self._push_undo()
        flat = [p for p in self._pairs]
        if 0 <= index < len(flat):
            flat.pop(index)
            self._pairs = flat
            self._refresh_lists()

    def _add_term_dialog(self):
        d = ctk.CTkInputDialog(text="术语（2～28 字符，不可含 = 与换行）:", title="添加术语")
        text = (d.get_input() or "").strip()
        if not text:
            return
        self._push_undo()
        if self._tbank.upsert_manual(text):
            self._refresh_lists()
        else:
            if self._undo_stack:
                self._undo_stack.pop()
            tk_msg.showwarning("无法添加", "术语不合规（长度、=、换行等限制），请修改后重试。")

    def _add_pair_dialog(self):
        self._pair_form_dialog(None)

    def _edit_pair_dialog(self, index: int):
        if not (0 <= index < len(self._pairs)):
            return
        w, c = self._pairs[index]
        self._pair_form_dialog(index, w, c)

    def _pair_form_dialog(self, index: Optional[int], wrong: str = "", correct: str = ""):
        win = ctk.CTkToplevel(self._win or self._root)
        win.title("误听对照" if index is None else "编辑对照")
        win.geometry("420x200")
        win.attributes("-topmost", True)
        icon = getattr(self._root, "_doubao_icon_photo", None)
        if icon is not None:
            try:
                win.iconphoto(True, icon)
            except tk.TclError:
                pass
        w_var = tk.StringVar(value=wrong)
        c_var = tk.StringVar(value=correct)
        ctk.CTkLabel(win, text="误听 / 误写：").pack(anchor="w", padx=16, pady=(16, 4))
        ctk.CTkEntry(win, textvariable=w_var, width=360).pack(padx=16)
        ctk.CTkLabel(win, text="正确写法：").pack(anchor="w", padx=16, pady=(10, 4))
        ctk.CTkEntry(win, textvariable=c_var, width=360).pack(padx=16)

        def ok():
            wi = (w_var.get() or "").strip()
            co = (c_var.get() or "").strip()
            if not wi or not co or "=" in wi or "=" in co or "\n" in wi or "\n" in co:
                return
            self._push_undo()
            if index is None:
                self._pairs.append((wi, co))
            else:
                if 0 <= index < len(self._pairs):
                    self._pairs[index] = (wi, co)
            self._refresh_lists()
            win.destroy()

        bf = ctk.CTkFrame(win, fg_color="transparent")
        bf.pack(fill="x", padx=16, pady=16)
        ctk.CTkButton(bf, text="确定", command=ok, fg_color="#3370FF").pack(side="right", padx=4)
        ctk.CTkButton(bf, text="取消", command=win.destroy, fg_color="#F2F3F5", text_color="#1D2129").pack(
            side="right"
        )
        bind_ctk_subtree_standard(win, win)

    def _save_all(self):
        try:
            write_dictionary_file(
                self._config.dictionary_path,
                self._pairs,
                header_lines=self._header_lines,
            )
            self._tbank.save()
        except Exception as e:
            tk_msg.showerror("保存失败", str(e))
            return
        self._on_saved()
        if self._win:
            try:
                self._win.destroy()
            except Exception:
                pass
        self._win = None
