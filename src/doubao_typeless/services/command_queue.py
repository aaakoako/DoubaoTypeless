"""串行用户操作队列。热键/GUI 只投递任务，不等待剪贴板或目标程序。

不积压插入命令：正在执行时再次点击得到 BUSY，绝不在用户切窗后补贴。
纯 Python 服务可直接同步调用，正式桌面和网络入口走此队列。
"""
from __future__ import annotations

from concurrent.futures import Future
import queue
import threading
from typing import Callable, Any


class CommandQueue:
    def __init__(self, *, on_error: Callable[[BaseException], None] | None = None):
        self._queue: queue.Queue = queue.Queue()
        self._guard = threading.Lock()
        self._active = False
        self._closed = False
        self._thread: threading.Thread | None = None
        self._on_error = on_error

    def submit(self, callback: Callable[..., Any], *args, **kwargs) -> Future:
        future: Future = Future()
        with self._guard:
            if self._closed or self._active:
                future.set_result({"result": "BUSY", "error_code": "SHUTTING_DOWN" if self._closed else "BUSY"})
                return future
            self._active = True
            if self._thread is None:
                self._thread = threading.Thread(target=self._work, name="DT-delivery", daemon=True)
                self._thread.start()
            self._queue.put_nowait((future, callback, args, kwargs))
        return future

    def _work(self):
        while True:
            job = self._queue.get()
            if job is None:
                self._queue.task_done()
                return
            future, callback, args, kwargs = job
            value: Any = {"result": "CANCELLED"}
            if future.set_running_or_notify_cancel():
                try:
                    value = callback(*args, **kwargs)
                except Exception as exc:
                    if self._on_error:
                        try:
                            self._on_error(exc)
                        except Exception:
                            pass
                    value = {"result": "UNKNOWN", "error_code": "COMMAND_FAILED"}
                finally:
                    with self._guard:
                        self._active = False
                future.set_result(value)
            else:
                with self._guard:
                    self._active = False
            self._queue.task_done()

    def close(self, timeout: float = 5.0) -> bool:
        """停止接收新操作；仅等待已开始的操作，不强杀、不自动重放。"""
        with self._guard:
            first_close = not self._closed
            self._closed = True
            thread = self._thread
            if thread is None:
                return True
            if first_close:
                # 哨兵排在已接收任务之后，不遗弃 Future；新的 submit 已被拒绝。
                self._queue.put_nowait(None)
        if thread is not threading.current_thread():
            thread.join(timeout)
        return not thread.is_alive()
