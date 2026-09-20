"""把第三方 UI Automation 调用关在本程序自建的辅助进程内。

辅助进程没有窗口、热键、剪贴板或网络入口。IPC 只传数值身份和少量描述；
超时/本机辅助进程退出会终止本次检查，不重放粘贴、不结束任何目标应用。
"""
from __future__ import annotations

import atexit
import json
import multiprocessing as mp
import threading

MAX_MESSAGE = 256 * 1024


class TargetProbeError(OSError):
    def __init__(self, code: str):
        self.error_code = code
        super().__init__(code)


def _serve(pipe) -> None:
    # comtypes 第一次导入会初始化当前线程；此线程从始至终使用 MTA。
    import sys
    sys.coinit_flags = 0
    from doubao_typeless.platform.windows import focus
    focus._INSIDE_HELPER = True
    try:
        while True:
            request = json.loads(pipe.recv_bytes(MAX_MESSAGE))
            op, args = request.get('op'), request.get('args') or {}
            if op == 'close':
                break
            try:
                if op == 'ping':
                    result = {'ready': True}
                elif op == 'focus':
                    result = list(focus._read_target_direct())
                elif op == 'restore':
                    result = focus._restore_target_direct(args['saved'])
                elif op == 'find_composer':
                    from doubao_typeless.platform.windows.composer_locator import discover_direct
                    result = discover_direct(int(args['hwnd']), int(args['pid']), args.get('remembered'))
                elif op == 'resume_composer':
                    from doubao_typeless.adapters.cursor_windows import resume_composer_direct
                    result = resume_composer_direct(args.get("anchor"), args["expected"])
                elif op == 'attachments':
                    from doubao_typeless.adapters.cursor_windows import _probe_uia_direct
                    result = _probe_uia_direct(args.get("anchor"))
                else:
                    raise ValueError('unsupported query')
                response = {'ok': True, 'value': result}
            except Exception as exc:
                # 不在诊断返回里复制异常消息、目标正文或API密钥。
                response = {'ok': False, 'error': type(exc).__name__}
            payload = json.dumps(response, ensure_ascii=False).encode('utf-8')
            if len(payload) > MAX_MESSAGE:
                payload = b'{"ok":false,"error":"response_limit"}'
            pipe.send_bytes(payload)
    except (EOFError, OSError):
        pass
    finally:
        # 所有元素函数已返回、局部COM引用已释放后，最后释放根对象。
        focus._AUTOMATION_ROOT = None
        import gc
        gc.collect()
        pipe.close()


class AutomationHost:
    """懒启动、串行、限时。worker参数只用于隔离进程生命周期单元测试。"""
    def __init__(self, *, worker=None):
        self._worker = worker or _serve
        self._lock = threading.RLock()
        self._pipe = None
        self._process = None
        self._closed = False

    @property
    def pid(self):
        return self._process.pid if self._process is not None else None

    def _start(self) -> None:
        ctx = mp.get_context('spawn')
        parent, child = ctx.Pipe(duplex=True)
        process = ctx.Process(target=self._worker, args=(child,), name='DT-UIA', daemon=True)
        try:
            process.start()
        except Exception:
            parent.close(); child.close()
            raise
        child.close()
        self._pipe, self._process = parent, process

    def call(self, op: str, args: dict | None = None, *, timeout: float = 2.0):
        with self._lock:
            if self._closed:
                raise TargetProbeError('TARGET_INSPECTION_CLOSED')
            try:
                if self._process is None or not self._process.is_alive():
                    self._dispose()
                    self._start()
                data = json.dumps({'op': op, 'args': args or {}}).encode('utf-8')
                if len(data) > MAX_MESSAGE:
                    raise TargetProbeError('TARGET_QUERY_TOO_LARGE')
                self._pipe.send_bytes(data)
                if not self._pipe.poll(timeout):
                    raise TargetProbeError('TARGET_INSPECTION_TIMEOUT')
                result = json.loads(self._pipe.recv_bytes(MAX_MESSAGE))
                if not result.get('ok'):
                    raise TargetProbeError('TARGET_INSPECTION_FAILED')
                return result.get('value')
            except TargetProbeError:
                self._dispose()
                raise
            except (EOFError, OSError, ValueError) as exc:
                self._dispose()
                raise TargetProbeError('TARGET_INSPECTION_FAILED') from exc

    def _dispose(self) -> None:
        pipe, process = self._pipe, self._process
        self._pipe = self._process = None
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass
        if process is not None:
            # 只管理由本对象保存的Process句柄，不按名字或端口扫描/杀进程。
            if process.is_alive():
                process.terminate()
            process.join(1)
            if process.is_alive():
                process.kill(); process.join(1)
            process.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._pipe is not None and self._process is not None:
                try:
                    self._pipe.send_bytes(b'{"op":"close"}')
                    self._process.join(0.75)
                except (EOFError, OSError):
                    pass
            self._dispose()


_host = None
_host_lock = threading.Lock()


def host() -> AutomationHost:
    global _host
    with _host_lock:
        if _host is None or _host._closed:
            _host = AutomationHost()
        return _host


def close_host() -> None:
    global _host
    with _host_lock:
        old, _host = _host, None
    if old is not None:
        old.close()


atexit.register(close_host)
