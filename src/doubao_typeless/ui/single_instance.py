"""Local show/quit commands: bounded connection, framed input, explicit acceptance."""
from __future__ import annotations
import os
import json
import time

PIPE = "DoubaoTypelessV3Preview"


def pipe_name() -> str:
    return os.environ.get("DT_V3_PIPE", "").strip() or PIPE


def _read_reply(sock, deadline: float) -> dict | None:
    data = bytearray()
    while time.monotonic() < deadline:
        data.extend(bytes(sock.readAll()))
        if len(data) > 4096:
            return None
        if b"\n" in data:
            try:
                value = json.loads(data.split(b"\n", 1)[0])
                return value if isinstance(value, dict) else None
            except (ValueError, UnicodeError):
                return None
        remaining = max(1, int((deadline - time.monotonic()) * 1000))
        if not sock.waitForReadyRead(remaining) and not sock.bytesAvailable():
            return None
    return None


def request_command(command: str, timeout_ms: int = 2000) -> bool:
    """Retry only a connection not yet established. Never re-send command bytes."""
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
            reply = _read_reply(sock, deadline)
            return bool(reply and reply.get("accepted") == command)
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
        from PySide6.QtCore import QTimer
    except ImportError:
        return None
    name = pipe_name()
    QLocalServer.removeServer(name)
    server = QLocalServer(parent)
    if not server.listen(name):
        return None

    def accept(sock):
        # Never block the GUI thread waiting for a client to produce Python bytes.
        # Qt can announce a new connection before its first command chunk arrives.
        state = {"buffer": bytearray(), "done": False}
        timeout = QTimer(sock)
        timeout.setSingleShot(True)
        timeout.timeout.connect(sock.abort)
        timeout.start(2000)
        sock.disconnected.connect(sock.deleteLater)

        def read():
            if state["done"]:
                return
            state["buffer"].extend(bytes(sock.readAll()))
            if len(state["buffer"]) > 1024:
                state["done"] = True
                sock.abort()
                return
            if b"\n" not in state["buffer"]:
                return
            state["done"] = True
            timeout.stop()
            line, tail = state["buffer"].split(b"\n", 1)
            payload = line.decode("utf-8", errors="replace").strip().lower()
            reply = {"accepted": None}
            if not tail.strip() and payload == "identify":
                from doubao_typeless.build_info import build_info
                import sys
                reply = {**build_info(), "pid": os.getpid(), "executable": sys.executable,
                         "schema": 1, "command_ack": True}
            elif not tail.strip() and payload in {"show", "quit"}:
                try:
                    on_command(payload)
                    reply = {"accepted": payload}
                except Exception:
                    reply = {"accepted": None, "error": "COMMAND_FAILED"}
            sock.write((json.dumps(reply) + "\n").encode("utf-8"))
            sock.flush()
            sock.disconnectFromServer()

        sock.readyRead.connect(read)
        read()

    def incoming():
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            if sock is not None:
                accept(sock)

    server.newConnection.connect(incoming)
    return server


def listen_for_show(on_show, parent=None):
    return listen_for_commands(lambda cmd: on_show() if cmd == "show" else None, parent=parent)


def identify_running(timeout_ms: int = 500) -> dict | None:
    """None means no listener; unknown must never be treated as the new build."""
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    try:
        sock.connectToServer(pipe_name())
        if not sock.waitForConnected(timeout_ms):
            return None
        sock.write(b"identify\n")
        if sock.bytesToWrite() > 0:
            sock.waitForBytesWritten(timeout_ms)
        value = _read_reply(sock, deadline)
        return value if value and value.get("schema") == 1 else {"unknown": True}
    except Exception:
        return {"unknown": True}
    finally:
        sock.close()
