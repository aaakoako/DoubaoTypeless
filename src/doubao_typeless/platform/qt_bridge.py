"""Run clipboard/screen work on Qt's owner thread, including delivery workers."""
from concurrent.futures import Future
from PySide6.QtCore import QObject, Signal, Qt, QThread
from PySide6.QtWidgets import QApplication

_dispatcher = None


class Dispatcher(QObject):
    requested = Signal(object, object)

    def __init__(self, parent):
        super().__init__(parent)
        self.requested.connect(self.execute, Qt.QueuedConnection)

    def execute(self, future, callback):
        # A timed-out request must never modify the clipboard later.
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(callback())
        except BaseException as exc:
            future.set_exception(exc)


def initialize():
    global _dispatcher
    app = QApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError('Qt bridge must be initialized on the GUI thread')
    if _dispatcher is None:
        _dispatcher = Dispatcher(app)


def call(callback):
    app = QApplication.instance()
    if app is None:
        raise RuntimeError('Desktop event loop is unavailable')
    if QThread.currentThread() == app.thread():
        return callback()
    if _dispatcher is None:
        raise RuntimeError('Desktop bridge is unavailable')
    future = Future()
    _dispatcher.requested.emit(future, callback)
    try:
        return future.result(timeout=3)
    except TimeoutError:
        if not future.cancel():
            # The short GUI operation already started; wait for its actual result.
            return future.result()
        raise
