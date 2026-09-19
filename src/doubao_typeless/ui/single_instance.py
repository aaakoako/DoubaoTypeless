"""Wake or stop the running desktop client. Same process never starts a second service."""
from __future__ import annotations

import os

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
        sock.close()
        if payload in {"show", "quit"}:
            on_command(payload)

    server.newConnection.connect(_incoming)
    return server


def listen_for_show(on_show, parent=None):
    return listen_for_commands(lambda cmd: on_show() if cmd == "show" else None, parent=parent)
