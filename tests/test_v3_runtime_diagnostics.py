"""真实日志/异常钩子测试；不启动 Windows 应用、不模拟成品验收。"""
from __future__ import annotations

import faulthandler
import json
import os
import runpy
import subprocess
import sys
import threading
from pathlib import Path
from types import ModuleType

import pytest

from doubao_typeless.runtime_diagnostics import RuntimeDiagnostics
from doubao_typeless.ui.filelog import FileLogger


def events(path):
    if not path.exists():
        return []
    return [json.loads(line.split(" ", 1)[1]) for line in path.read_text(encoding="utf-8").splitlines()]


class BrokenConsole:
    def write(self, _text):
        raise BrokenPipeError("closed console")

    def flush(self):
        raise BrokenPipeError("closed console")


@pytest.mark.parametrize("stream", [None, BrokenConsole()])
def test_console_failure_does_not_escape_or_lose_file(tmp_path, monkeypatch, stream):
    log = FileLogger(tmp_path / "logs" / "v3.log")
    with monkeypatch.context() as m:
        m.setattr(sys, "stdout", stream)
        log("可继续输入")
    assert "可继续输入" in log.path.read_text(encoding="utf-8")
    assert log.last_error is None


def test_file_failure_does_not_escape(tmp_path):
    blocked = tmp_path / "not_a_directory"
    blocked.write_text("unrelated")
    log = FileLogger(blocked / "v3.log", also_print=False)
    log("test")
    assert log.last_error is not None
    assert blocked.read_text() == "unrelated"


def test_file_recovers_after_temporary_error(tmp_path):
    blocked = tmp_path / "parent"
    blocked.write_text("test fixture")
    log = FileLogger(blocked / "v3.log", also_print=False)
    log("first")
    assert log.last_error
    blocked.unlink()  # 仅测试创建的占位文件。
    log("second")
    assert log.last_error is None
    assert "second" in log.path.read_text()


def test_secret_redaction_and_unicode(tmp_path):
    log = FileLogger(tmp_path / "v3.log", also_print=False)
    log("测试 sk-ABC_def-12345678 Bearer test-token")
    text = log.path.read_text(encoding="utf-8")
    assert "测试" in text and "ABC_def" not in text and "test-token" not in text


def test_long_lines_remain_size_capped(tmp_path):
    log = FileLogger(tmp_path / "v3.log", max_bytes=256, also_print=False)
    for _ in range(3):
        log("中文" * 1000)
    for path in [log.path, log.path.with_suffix(".old.log")]:
        assert path.stat().st_size <= 256
        assert "truncated" in path.read_text(encoding="utf-8")


def test_parallel_writes_are_complete_lines(tmp_path):
    log = FileLogger(tmp_path / "v3.log", also_print=False)
    workers = [threading.Thread(target=lambda n=i: [log(f"{n}:{j}") for j in range(20)])
               for i in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    lines = log.path.read_text().splitlines()
    assert len(lines) == 160
    assert len({line.split(" ", 1)[1] for line in lines}) == 160


def test_message_format_failure_is_contained(tmp_path):
    class BadMessage:
        def __str__(self):
            raise ValueError("do not expose")
    log = FileLogger(tmp_path / "v3.log", also_print=False)
    log(BadMessage())
    assert log.last_error == "ValueError"


def test_logs_written_before_broken_console(tmp_path, monkeypatch):
    log = FileLogger(tmp_path / "v3.log")
    class VerifyConsole:
        def write(self, _text):
            assert "already saved" in log.path.read_text()
            raise BrokenPipeError()
    with monkeypatch.context() as m:
        m.setattr(sys, "stdout", VerifyConsole())
        log("already saved")
    assert log.console_error == "BrokenPipeError"


@pytest.fixture
def diag(tmp_path, monkeypatch):
    # pytest可能已经安装自己的faulthandler；测试不能抢它的句柄。
    monkeypatch.setattr(faulthandler, "is_enabled", lambda: True)
    result = RuntimeDiagnostics(tmp_path).install()
    yield result
    result.close()


def test_exception_omits_message_source_and_locals(diag):
    try:
        private_draft = "PRIVATE-DRAFT-WORDS"
        raise OSError(5, private_draft + " secret-api-value")
    except OSError as exc:
        diag.exception("insert", type(exc), exc, exc.__traceback__)
    raw = diag.logger.path.read_text()
    assert "PRIVATE-DRAFT-WORDS" not in raw and "secret-api-value" not in raw
    record = [e for e in events(diag.logger.path) if e["event"] == "exception"][0]
    assert record["exception_type"] == "OSError" and record["errno"] == 5
    assert record["frames"][-1]["function"] == "test_exception_omits_message_source_and_locals"
    assert all(set(frame) == {"file", "function", "line"} for frame in record["frames"])


def test_startup_records_pid_and_actual_executable(diag):
    start = events(diag.logger.path)[0]
    assert start["event"] == "process_start"
    assert start["pid"] == os.getpid()
    assert start["executable"] == str(Path(sys.executable).resolve())
    assert start["run_id"] == diag.run_id


def test_exit_zero_not_reported_as_crash(diag):
    with pytest.raises(SystemExit) as out:
        diag.run(lambda: sys.exit(0))
    assert out.value.code == 0
    last = events(diag.logger.path)[-1]
    assert last["event"] == "process_exit" and last["exit_code"] == 0
    assert last["reason"] == "system_exit"


@pytest.mark.parametrize("code, expected", [(3, 3), (None, 0), ("PRIVATE EXIT MESSAGE", 1)])
def test_exit_code_preserved_without_string_contents(diag, code, expected):
    with pytest.raises(SystemExit) as out:
        diag.run(lambda: sys.exit(code))
    assert out.value.code == code
    assert events(diag.logger.path)[-1]["exit_code"] == expected
    assert "PRIVATE EXIT MESSAGE" not in diag.logger.path.read_text()


def test_normal_return_is_preserved(diag):
    assert diag.run(lambda: "return value") == "return value"
    assert events(diag.logger.path)[-1]["reason"] == "entry_returned"


def test_entry_error_still_raises_after_recording(diag):
    def bad_entry():
        raise RuntimeError("PRIVATE EXCEPTION MESSAGE")
    with pytest.raises(RuntimeError, match="PRIVATE"):
        diag.run(bad_entry)
    recorded = events(diag.logger.path)
    assert recorded[-2]["channel"] == "entry"
    assert recorded[-1]["exit_code"] == 1
    assert "PRIVATE EXCEPTION MESSAGE" not in diag.logger.path.read_text()


def test_keyboard_interrupt_is_not_swallowed(diag):
    with pytest.raises(KeyboardInterrupt):
        diag.run(lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert events(diag.logger.path)[-1]["exit_code"] == 130


def test_hooks_restore_and_install_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(faulthandler, "is_enabled", lambda: True)
    old_sys, old_thread = sys.excepthook, threading.excepthook
    d = RuntimeDiagnostics(tmp_path).install()
    hook = sys.excepthook
    assert d.install() is d and sys.excepthook is hook
    d.close()
    d.close()
    assert sys.excepthook is old_sys and threading.excepthook is old_thread


def test_close_does_not_replace_later_hook(diag, monkeypatch):
    replacement = lambda *_: None
    monkeypatch.setattr(sys, "excepthook", replacement)
    diag.close()
    assert sys.excepthook is replacement


def test_thread_hook_reports_and_calls_previous(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(faulthandler, "is_enabled", lambda: True)
    monkeypatch.setattr(threading, "excepthook", lambda args: called.append(args.exc_type))
    d = RuntimeDiagnostics(tmp_path).install()
    try:
        t = threading.Thread(target=lambda: (_ for _ in ()).throw(ValueError("PRIVATE THREAD")))
        t.start()
        t.join()
    finally:
        d.close()
    assert called == [ValueError]
    assert any(e.get("channel") == "thread" for e in events(d.logger.path))
    assert "PRIVATE THREAD" not in d.logger.path.read_text()


def test_fault_file_open_until_handler_disabled(tmp_path, monkeypatch):
    order = []
    handle = []
    monkeypatch.setattr(faulthandler, "is_enabled", lambda: False)
    def enable(*, file, all_threads):
        handle.append(file)
        order.append("enable")
        assert all_threads and not file.closed
    def disable():
        assert not handle[0].closed
        order.append("disable")
    monkeypatch.setattr(faulthandler, "enable", enable)
    monkeypatch.setattr(faulthandler, "disable", disable)
    d = RuntimeDiagnostics(tmp_path).install()
    assert not handle[0].closed
    d.close()
    assert handle[0].closed and order == ["enable", "disable"]


def test_existing_fault_handler_not_replaced(diag):
    assert diag._fault_file is None and not diag._owns_fault_handler
    assert any(e["event"] == "fault_handler_existing" for e in events(diag.logger.path))


def test_unwritable_directory_does_not_stop_entry(tmp_path, monkeypatch):
    blocked = tmp_path / "file"
    blocked.write_text("original")
    monkeypatch.setattr(faulthandler, "is_enabled", lambda: False)
    d = RuntimeDiagnostics(blocked).install()
    assert d.run(lambda: 42) == 42
    assert blocked.read_text() == "original"


def test_production_launcher_installs_before_app_main(tmp_path, monkeypatch):
    runtime = ModuleType("doubao_typeless.runtime")
    runtime.v3_data_dir = lambda: tmp_path
    configured = []
    runtime.configure_launch = lambda argv: configured.append(list(argv))
    app = ModuleType("doubao_typeless.app")
    checks = []
    def main():
        checks.append(bool(configured) and any(e["event"] == "process_start" for e in events(tmp_path / "logs/runtime.log")))
        raise SystemExit(0)
    app.main = main
    monkeypatch.setitem(sys.modules, "doubao_typeless.runtime", runtime)
    monkeypatch.setitem(sys.modules, "doubao_typeless.app", app)
    monkeypatch.setattr(faulthandler, "is_enabled", lambda: True)
    launcher = Path(__file__).resolve().parents[1] / "tools/run_v3.py"
    with pytest.raises(SystemExit) as out:
        runpy.run_path(str(launcher), run_name="__main__")
    assert out.value.code == 0 and checks == [True]


def test_real_subprocess_without_console_records_failure(tmp_path):
    source = Path(__file__).resolve().parents[1] / "src"
    program = '''
import sys
from pathlib import Path
from doubao_typeless.runtime_diagnostics import RuntimeDiagnostics
sys.stdout = None
sys.stderr = None
d = RuntimeDiagnostics(Path(sys.argv[1])).install()
def fail():
    raise RuntimeError("PRIVATE-SUBPROCESS-DRAFT")
d.run(fail)
'''
    env = {**os.environ, "PYTHONPATH": str(source)}
    child = subprocess.run([sys.executable, "-c", program, str(tmp_path)], env=env,
                           capture_output=True, timeout=10)
    assert child.returncode != 0
    records = events(tmp_path / "logs/runtime.log")
    assert records[0]["stdout_available"] is False
    assert records[-1]["reason"] == "unhandled_exception"
    assert "PRIVATE-SUBPROCESS-DRAFT" not in (tmp_path / "logs/runtime.log").read_text()
