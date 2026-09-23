"""Windows startup quoting and preview identity; never writes the user's registry."""
import ctypes
import sys
import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows command-line parser')
def test_autostart_keeps_current_data_and_instance_after_environment_is_gone(tmp_path, monkeypatch):
    from doubao_typeless.ui.v3_startup import startup_command
    from doubao_typeless.runtime import configure_launch, v3_data_dir
    from doubao_typeless.ui.single_instance import pipe_name
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path/'软件 预览'/'client.exe'))
    monkeypatch.setenv('DT_V3_PIPE', 'UsabilityPreview')
    monkeypatch.setenv('DT_V3_DATA_DIR', str(tmp_path/'irrelevant'))
    actual_data = tmp_path/'这份预览 数据'
    command = startup_command(data_dir=actual_data)
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    ptr = shell.CommandLineToArgvW(command, ctypes.byref(count))
    assert ptr
    try: argv = [ptr[i] for i in range(count.value)]
    finally: kernel.LocalFree(ptr)
    monkeypatch.delenv('DT_V3_PIPE')
    monkeypatch.delenv('DT_V3_DATA_DIR')
    configure_launch(argv)
    assert v3_data_dir() == actual_data.resolve()
    assert pipe_name() == 'UsabilityPreview'
    assert '--minimized' in argv
    assert not actual_data.exists(), 'Building the command does not migrate or create data'
