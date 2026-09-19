"""启动/退出与未处理异常取证；不重试输入、不改变退出码、不上传任何内容。

普通记录只写异常类型和文件/函数/行号，不写异常消息、源码行或局部变量。
faulthandler 的独立文件包含线程栈和本机路径，仅保留本地；它不是内存转储，
也不保证捕获所有操作系统故障。此前已有故障处理器时不抢占它。
"""
from __future__ import annotations

import faulthandler
import json
import os
import sys
import threading
import traceback
import uuid
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

from doubao_typeless.ui.filelog import FileLogger


def _exception_fields(exc_type: type[BaseException], value: BaseException,
                      tb: TracebackType | None) -> dict:
    # 禁止 format_exception / str(value)：错误消息可能回显用户原文或 API Key。
    frames = []
    for frame, lineno in traceback.walk_tb(tb):
        frames.append({"file": Path(frame.f_code.co_filename).name,
                       "function": frame.f_code.co_name, "line": lineno})
    out: dict = {"exception_type": exc_type.__name__, "frames": frames[-32:]}
    for name in ("errno", "winerror"):
        code = getattr(value, name, None)
        if isinstance(code, int) and not isinstance(code, bool):
            out[name] = code
    return out


def _exit_code(value: object) -> int:
    # SystemExit 的字符串可能含敏感数据，不记录其内容。
    if value is None:
        return 0
    return int(value) if isinstance(value, int) else 1


class RuntimeDiagnostics:
    """单个进程的可关闭取证会话。失败降级，不承担业务异常恢复职责。"""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.run_id = uuid.uuid4().hex
        self.pid = os.getpid()
        self.logger = FileLogger(self.data_dir / "logs" / "runtime.log", also_print=False)
        self._closed = False
        self._old_sys_hook = None
        self._old_thread_hook = None
        self._sys_hook = self._on_sys_exception
        self._thread_hook = self._on_thread_exception
        self._fault_file: BinaryIO | None = None
        self._owns_fault_handler = False
        self._local = threading.local()
        self.fault_path: Path | None = None

    def event(self, kind: str, **fields: object) -> None:
        if self._closed:
            return
        try:
            payload = {**fields, "event": kind, "pid": self.pid, "run_id": self.run_id}
            self.logger(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        except Exception:
            # 取证失败不得成为第二次事故。
            pass

    def install(self) -> "RuntimeDiagnostics":
        if self._old_sys_hook is not None or self._closed:
            return self
        self._old_sys_hook = sys.excepthook
        self._old_thread_hook = threading.excepthook
        sys.excepthook = self._sys_hook
        threading.excepthook = self._thread_hook
        self.event("process_start", executable=str(Path(sys.executable).resolve()),
                   frozen=bool(getattr(sys, "frozen", False)),
                   python=sys.version.split()[0], data_dir=str(self.data_dir.resolve()),
                   stdout_available=sys.stdout is not None, stderr_available=sys.stderr is not None)
        self._enable_fault_handler()
        return self

    def _enable_fault_handler(self) -> None:
        try:
            if faulthandler.is_enabled():
                self.event("fault_handler_existing")
                return
            # 不轮换活动文件，始终保持文件描述符有效。每个进程单独命名。
            self.fault_path = self.data_dir / "logs" / f"fault-{self.pid}-{self.run_id[:12]}.log"
            self.fault_path.parent.mkdir(parents=True, exist_ok=True)
            self._fault_file = self.fault_path.open("ab", buffering=0)
            faulthandler.enable(file=self._fault_file, all_threads=True)
            self._owns_fault_handler = True
            self.event("fault_handler_enabled", file=self.fault_path.name)
        except Exception as exc:
            self.event("fault_handler_unavailable", exception_type=type(exc).__name__)
            if self._fault_file is not None and not self._owns_fault_handler:
                self._fault_file.close()
                self._fault_file = None

    def exception(self, channel: str, exc_type: type[BaseException], value: BaseException,
                  tb: TracebackType | None) -> None:
        if self._closed or getattr(self._local, "reporting", False):
            return
        self._local.reporting = True
        try:
            self.event("exception", channel=channel, thread_id=threading.get_ident(),
                       **_exception_fields(exc_type, value, tb))
        except Exception:
            pass
        finally:
            self._local.reporting = False

    def _on_sys_exception(self, exc_type, value, tb) -> None:
        self.exception("sys", exc_type, value, tb)
        # 保留既有处理器语义；没有控制台时仍以本地文件为取证来源。
        try:
            if self._old_sys_hook is not None:
                self._old_sys_hook(exc_type, value, tb)
        except Exception:
            pass

    def _on_thread_exception(self, args) -> None:
        if args.exc_type is not SystemExit:
            self.exception("thread", args.exc_type, args.exc_value, args.exc_traceback)
        try:
            if self._old_thread_hook is not None:
                self._old_thread_hook(args)
        except Exception:
            pass

    def run(self, entry) -> object:
        """从启动入口包围整个程序；只取证，绝不把非零退出改成成功。"""
        try:
            result = entry()
        except SystemExit as exc:
            self.event("process_exit", exit_code=_exit_code(exc.code), reason="system_exit")
            raise
        except BaseException as exc:
            self.exception("entry", type(exc), exc, exc.__traceback__)
            self.event("process_exit", exit_code=130 if isinstance(exc, KeyboardInterrupt) else 1,
                       reason="unhandled_exception")
            raise
        else:
            self.event("process_exit", exit_code=0, reason="entry_returned")
            return result
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        if sys.excepthook is self._sys_hook and self._old_sys_hook is not None:
            sys.excepthook = self._old_sys_hook
        if threading.excepthook is self._thread_hook and self._old_thread_hook is not None:
            threading.excepthook = self._old_thread_hook
        if self._owns_fault_handler:
            # 先禁用再关闭描述符，不让处理器以后写进其他文件。
            try:
                faulthandler.disable()
                self._owns_fault_handler = False
            except Exception:
                # 无法禁用时故意保留描述符到进程退出，而不是关闭后误写别的文件。
                self.event("fault_handler_disable_failed")
        if self._fault_file is not None and not self._owns_fault_handler:
            try:
                self._fault_file.close()
            except Exception:
                pass
            self._fault_file = None
        self._closed = True


def run_application() -> None:
    """PyInstaller/源码共用入口，早于 GUI 和平台模块导入安装取证。"""
    from doubao_typeless.runtime import v3_data_dir

    diagnostics = RuntimeDiagnostics(v3_data_dir()).install()

    def entry() -> None:
        from doubao_typeless.app import main
        main()

    diagnostics.run(entry)
