"""Wake the running desktop client instead of starting a second service."""
from __future__ import annotations

PIPE = "DoubaoTypelessV3Preview"


def request_show(timeout_ms: int = 400) -> bool:
    try:
        from PySide6.QtNetwork import QLocalSocket
    except ImportError:
        return False
    sock = QLocalSocket()
    sock.connectToServer(PIPE)
    if not sock.waitForConnected(timeout_ms):
        sock.close()
        return False
    sock.write(b"show\n")
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    sock.close()
    return True


def listen_for_show(on_show, parent=None):
    try:
        from PySide6.QtNetwork import QLocalServer
    except ImportError:
        return None
    QLocalServer.removeServer(PIPE)
    server = QLocalServer(parent)
    if not server.listen(PIPE):
        return None

    def _incoming():
        sock = server.nextPendingConnection()
        if sock is None:
            return
        if sock.bytesAvailable() == 0:
            sock.waitForReadyRead(500)
        payload = bytes(sock.readAll()).decode("utf-8", errors="replace")
        sock.close()
        if "show" in payload:
            on_show()

    server.newConnection.connect(_incoming)
    return server
