"""Wake or stop the running desktop client. Same process never starts a second service."""
from __future__ import annotations

import os
import json
import time

PIPE = "DoubaoTypelessV3Preview"


def pipe_name() -> str:
    override = os.environ.get("DT_V3_PIPE", "").strip()
    return override or PIPE


def request_command(command: str, timeout_ms: int = 2000) -> bool:
    """Wait within a bounded deadline for a client still creating its UI.

    Connection failure may be immediate on Windows named pipes. Retry only before
    connecting; once any command bytes were sent, never send the command again.
    """
    if command not in {"show", "quit"}:
        return False
    try:
        from PySide6.QtNetwork import QLocalSocket
    except ImportError:
        return False
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    while time.monotonic() < deadline:
        sock = QLocalSocket()
        try:
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            sock.connectToServer(pipe_name())
            if not sock.waitForConnected(min(remaining, 100)):
                time.sleep(min(.02, max(0, deadline - time.monotonic())))
                continue
            payload = f"{command}\n".encode("utf-8")
            if sock.write(payload) != len(payload):
                return False
            if sock.bytesToWrite() > 0:
                remaining = max(1, int((deadline - time.monotonic()) * 1000))
                if not sock.waitForBytesWritten(remaining):
                    return False
            sock.disconnectFromServer()
            return True
        finally:
            sock.close()
    return False


def request_show(timeout_ms: int = 2000) -> bool:
    return request_command("show", timeout_ms=timeout_ms)


def request_quit(timeout_ms: int = 2000) -> bool:
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
