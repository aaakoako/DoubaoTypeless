"""CustomTkinter 输入框：系统一致的快捷键与右键菜单（复制/粘贴/剪切/全选）。"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk


def _tk_widget_from_ctk_entry(widget: ctk.CTkEntry) -> tk.Entry:
    return getattr(widget, "_entry", None)


def _tk_widget_from_ctk_textbox(widget: ctk.CTkTextbox) -> tk.Text:
    return getattr(widget, "_textbox", None)


def _clipboard_copy(root: tk.Misc, text: str) -> None:
    if not text:
        return
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
    except tk.TclError:
        pass


def _entry_get_selection_or_all(entry: tk.Entry) -> tuple[str, bool]:
    try:
        if entry.selection_present():
            return entry.selection_get(), False
    except tk.TclError:
        pass
    return entry.get(), True


def _text_get_selection_or_all(tb: tk.Text) -> tuple[str, bool]:
    try:
        if tb.tag_ranges("sel"):
            return tb.get("sel.first", "sel.last"), False
    except tk.TclError:
        pass
    content = tb.get("1.0", "end-1c")
    return content, bool(content)


def _entry_select_all(entry: tk.Entry) -> str:
    entry.select_range(0, tk.END)
    entry.icursor(tk.END)
    return entry.get()


def _text_select_all(tb: tk.Text) -> str:
    tb.tag_add("sel", "1.0", "end-1c")
    tb.mark_set("insert", "end-1c")
    return tb.get("1.0", "end-1c")


def _build_edit_menu(
    root: tk.Misc,
    event,
    *,
    editable: bool,
    on_cut: Optional[Callable[[], None]] = None,
    on_copy: Optional[Callable[[], None]] = None,
    on_paste: Optional[Callable[[], None]] = None,
    on_select_all: Optional[Callable[[], None]] = None,
) -> None:
    menu = tk.Menu(root, tearoff=0)
    if editable and on_cut is not None:
        menu.add_command(label="剪切(T)", command=on_cut)
    if on_copy is not None:
        menu.add_command(label="复制(C)", command=on_copy)
    if on_paste is not None:
        menu.add_command(label="粘贴(P)", command=on_paste)
    if on_select_all is not None:
        menu.add_command(label="全选(A)", command=on_select_all)
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        try:
            menu.grab_release()
        except tk.TclError:
            pass


def bind_ctk_entry_standard(
    entry_widget: ctk.CTkEntry,
    clipboard_root: tk.Misc,
    *,
    read_only: bool = False,
) -> None:
    """为 CTkEntry 绑定 Ctrl+A/C/X/V 与右键菜单。
    read_only 时仍可用复制、粘贴、全选（及 Ctrl+V）；剪切由 editable 决定是否提供。
    若需禁止键盘逐字输入，由外层对 CTkEntry 另行 bind <Key>。"""
    e = _tk_widget_from_ctk_entry(entry_widget)
    if e is None:
        return

    def do_copy(_: tk.Event | None = None):
        txt, _ = _entry_get_selection_or_all(e)
        _clipboard_copy(clipboard_root, txt)
        return "break"

    def do_cut(_: tk.Event | None = None):
        if read_only:
            return "break"
        txt, took_all = _entry_get_selection_or_all(e)
        _clipboard_copy(clipboard_root, txt)
        if took_all:
            e.delete(0, tk.END)
        else:
            try:
                e.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
        return "break"

    def do_paste(_: tk.Event | None = None):
        try:
            clip = clipboard_root.clipboard_get()
        except tk.TclError:
            return "break"
        try:
            if e.selection_present():
                e.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        e.insert("insert", clip)
        return "break"

    def do_select_all(_: tk.Event | None = None):
        _entry_select_all(e)
        return "break"

    def on_button_3(ev: tk.Event):
        _build_edit_menu(
            clipboard_root,
            ev,
            editable=not read_only,
            on_cut=None if read_only else do_cut,
            on_copy=do_copy,
            on_paste=do_paste,
            on_select_all=do_select_all,
        )

    for seq, fn in (
        ("<Control-a>", do_select_all),
        ("<Control-A>", do_select_all),
        ("<Control-c>", do_copy),
        ("<Control-C>", do_copy),
        ("<Control-v>", do_paste),
        ("<Control-V>", do_paste),
    ):
        e.bind(seq, fn)
    if not read_only:
        for seq, fn in (
            ("<Control-x>", do_cut),
            ("<Control-X>", do_cut),
        ):
            e.bind(seq, fn)
    e.bind("<Button-3>", on_button_3)


def bind_ctk_textbox_standard(
    tb_widget: ctk.CTkTextbox,
    clipboard_root: tk.Misc,
    *,
    read_only: bool = False,
) -> None:
    tb = _tk_widget_from_ctk_textbox(tb_widget)
    if tb is None:
        return

    def do_copy(_: tk.Event | None = None):
        txt, _ = _text_get_selection_or_all(tb)
        _clipboard_copy(clipboard_root, txt)
        return "break"

    def do_cut(_: tk.Event | None = None):
        if read_only:
            return "break"
        txt, took_all = _text_get_selection_or_all(tb)
        _clipboard_copy(clipboard_root, txt)
        if took_all:
            tb.delete("1.0", "end")
        else:
            try:
                tb.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
        return "break"

    def do_paste(_: tk.Event | None = None):
        try:
            clip = clipboard_root.clipboard_get()
        except tk.TclError:
            return "break"
        try:
            if tb.tag_ranges("sel"):
                tb.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        tb.insert("insert", clip)
        return "break"

    def do_select_all(_: tk.Event | None = None):
        _text_select_all(tb)
        return "break"

    def on_button_3(ev: tk.Event):
        _build_edit_menu(
            clipboard_root,
            ev,
            editable=not read_only,
            on_cut=None if read_only else do_cut,
            on_copy=do_copy,
            on_paste=do_paste,
            on_select_all=do_select_all,
        )

    for seq, fn in (
        ("<Control-a>", do_select_all),
        ("<Control-A>", do_select_all),
        ("<Control-c>", do_copy),
        ("<Control-C>", do_copy),
        ("<Control-v>", do_paste),
        ("<Control-V>", do_paste),
    ):
        tb.bind(seq, fn)
    if not read_only:
        for seq, fn in (
            ("<Control-x>", do_cut),
            ("<Control-X>", do_cut),
        ):
            tb.bind(seq, fn)
    tb.bind("<Button-3>", on_button_3)


def bind_ctk_subtree_standard(parent: tk.Misc, clipboard_root: tk.Misc) -> None:
    """递归为子树中所有 CTkEntry / CTkTextbox 绑定标准编辑行为（可编辑）。"""
    stack = [parent]
    seen: set[int] = set()
    while stack:
        w = stack.pop()
        wid = id(w)
        if wid in seen:
            continue
        seen.add(wid)
        try:
            kids = w.winfo_children()
        except tk.TclError:
            continue
        for ch in kids:
            if isinstance(ch, ctk.CTkEntry):
                bind_ctk_entry_standard(ch, clipboard_root, read_only=False)
            elif isinstance(ch, ctk.CTkTextbox):
                try:
                    bind_ctk_textbox_standard(ch, clipboard_root, read_only=False)
                except Exception:
                    pass
            stack.append(ch)
