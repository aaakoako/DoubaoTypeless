"""只读比较当前进程和目标的完整性级别；不提权、不申请调试权限。"""
from __future__ import annotations
import ctypes
import os
import sys
from ctypes import wintypes as w


class PermissionProbeError(OSError):
    error_code = 'TARGET_PERMISSION_UNKNOWN'


def _integrity_rid(pid: int) -> int:
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    adv.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    adv.OpenProcessToken.restype = w.BOOL
    adv.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    adv.GetTokenInformation.restype = w.BOOL
    adv.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    adv.GetSidSubAuthority.argtypes = [ctypes.c_void_p, w.DWORD]
    adv.GetSidSubAuthority.restype = ctypes.POINTER(w.DWORD)
    process = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not process:
        raise PermissionProbeError('TARGET_PERMISSION_UNKNOWN')
    token = w.HANDLE()
    try:
        if not adv.OpenProcessToken(process, 0x0008, ctypes.byref(token)):
            raise PermissionProbeError('TARGET_PERMISSION_UNKNOWN')
        size = w.DWORD()
        adv.GetTokenInformation(token, 25, None, 0, ctypes.byref(size))
        if not 0 < size.value <= 65536:
            raise PermissionProbeError('TARGET_PERMISSION_UNKNOWN')
        buffer = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token, 25, buffer, size.value, ctypes.byref(size)):
            raise PermissionProbeError('TARGET_PERMISSION_UNKNOWN')
        # TOKEN_MANDATORY_LABEL begins with SID_AND_ATTRIBUTES; its first field is PSID.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        count = adv.GetSidSubAuthorityCount(sid)
        if not count or count[0] == 0:
            raise PermissionProbeError('TARGET_PERMISSION_UNKNOWN')
        return int(adv.GetSidSubAuthority(sid, count[0] - 1)[0])
    finally:
        if token:
            kernel.CloseHandle(token)
        kernel.CloseHandle(process)


def target_above_ours(*, get_pid=None, read_rid=None) -> bool:
    if get_pid is None:
        if sys.platform != 'win32':
            return False
        import win32gui, win32process
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise PermissionProbeError('TARGET_PERMISSION_UNKNOWN')
        get_pid = lambda: win32process.GetWindowThreadProcessId(hwnd)[1]
    pid = int(get_pid())
    if pid == os.getpid():
        return False
    reader = read_rid or _integrity_rid
    return reader(pid) > reader(os.getpid())
