"""Wake or stop the running desktop client. Same process never starts a second service."""
from __future__ import annotations

import os
import json

PIPE = "DoubaoTypelessV3Preview"


def pipe_name() -> str:
    override = os.environ.get("DT_V3_PIPE", "").strip()
    return override or PIPE


def request_command(command: str, timeout_ms: int = 800) -> bool:
    try:
        from PySide6.QtNetwork import QLocalSocket
    except ImportError:
        return False
    sock = QLocalSocket()
    sock.connectToServer(pipe_name())
    if not sock.waitForConnected(timeout_ms):
        sock.close()
        return False
    sock.write(f"{command}\n".encode("utf-8"))
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    sock.close()
    return True


def request_show(timeout_ms: int = 400) -> bool:
    return request_command("show", timeout_ms=timeout_ms)


def request_quit(timeout_ms: int = 800) -> bool:
    return request_command("quit", timeout_ms=timeout_ms)


def listen_for_commands(on_command, parent=None):
    try:
        from PySide6.QtNetwork import QLocalServer
    except ImportError:
        return None
    name = pipe_name()
    QLocalServer.removeServer(name)
    server = QLocalServer(parent)
    if not server.listen(name):
        return None

    def _incoming():
        sock = server.nextPendingConnection()
        if sock is None:
            return
        if sock.bytesAvailable() == 0:
            sock.waitForReadyRead(500)
        payload = bytes(sock.readAll()).decode("utf-8", errors="replace").strip().lower()
        if payload == "identify":
            from doubao_typeless.build_info import build_info
            import sys
            reply = {**build_info(), "pid":os.getpid(), "executable":sys.executable, "schema":1}
            sock.write((json.dumps(reply)+"\n").encode("utf-8"))
            sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        if payload in {"show", "quit"}:
            on_command(payload)

    server.newConnection.connect(_incoming)
    return server


def listen_for_show(on_show, parent=None):
    return listen_for_commands(lambda cmd: on_show() if cmd == "show" else None, parent=parent)


def identify_running(timeout_ms: int = 500) -> dict | None:
    """None是未运行，unknown是旧协议/失败；未知不能冒充新包已启动。"""
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    try:
        sock.connectToServer(pipe_name())
        if not sock.waitForConnected(timeout_ms):
            return None
        sock.write(b"identify\n")
        sock.waitForBytesWritten(timeout_ms)
        if not sock.waitForReadyRead(timeout_ms):
            return {"unknown": True}
        data = bytes(sock.readAll()).decode("utf-8")
        value = json.loads(data)
        return value if value.get("schema") == 1 else {"unknown": True}
    except Exception:
        return {"unknown": True}
    finally:
        sock.close()
