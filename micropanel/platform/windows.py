"""Windows only: DPI awareness, the foreground program, the single instance lock.
Standard library only. Nothing here runs at import time: the Windows API is touched only inside functions,
so this module can be imported on any system. The DPI call itself is made by the start file, before the third-party packages are imported."""
import ctypes
import logging
from pathlib import Path

from micropanel.log import emit

RESOLVE_EXE = "resolve.exe"   # process name of the foreground window (case-insensitive)

DPI_NAMES = {0: "not DPI aware", 1: "system DPI aware", 2: "per monitor DPI aware"}


def set_dpi_awareness(shcore=None):
    """Asks Windows for per-monitor DPI awareness (2) and reads back what the process has afterwards.
    Returns (awareness, result code of the set call), or (None, None) if this is not possible (not Windows).
    The set call reports a refusal only through its return value, it raises no error: once a process has an
    awareness, Windows refuses every change. `shcore` is only passed in by the self-test."""
    try:
        if shcore is None:
            shcore = ctypes.windll.shcore
        code = shcore.SetProcessDpiAwareness(2)
        value = ctypes.c_int()
        if shcore.GetProcessDpiAwareness(None, ctypes.byref(value)) == 0:
            return value.value, code
    except Exception:  # noqa: BLE001
        pass
    return None, None


def dpi_warning_text(awareness, code):
    """Warning text if the awareness is not per monitor (2), otherwise None. Unknown (None) gives no text."""
    if awareness is None or awareness == 2:
        return None
    name = DPI_NAMES.get(awareness, f"unknown value {awareness}")
    return (f"DPI awareness is '{name}' ({awareness}) instead of per monitor (2), set call returned "
            f"{(code or 0) & 0xFFFFFFFF:#010x}: clicks can miss on monitors with different scaling")


# --------------------------------------------------------------------------
# Foreground window check
# --------------------------------------------------------------------------
_winapi = None


def foreground_process_name():
    """File name of the program in the foreground (e.g. 'Resolve.exe'), or None."""
    global _winapi
    if _winapi is None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.QueryFullProcessImageNameW.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        _winapi = (user32, kernel32)
    user32, kernel32 = _winapi

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    handle = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return Path(buf.value).name
    finally:
        kernel32.CloseHandle(handle)


def resolve_is_foreground():
    """Returns (True/False, name of the foreground program or None). The name is never written to the log."""
    try:
        name = foreground_process_name()
    except Exception as e:  # noqa: BLE001
        emit(logging.ERROR, "foreground_check_failed", "Foreground check failed: %r", e)
        return False, None
    return (name is not None and name.lower() == RESOLVE_EXE), name


# --------------------------------------------------------------------------
# Single instance lock
# --------------------------------------------------------------------------
_mutex_handle = None   # keep a reference as long as the script runs


def acquire_single_instance():
    """True if this is the only running instance. Uses a named Windows mutex."""
    global _mutex_handle
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        _mutex_handle = kernel32.CreateMutexW(None, False, "Local\\MicroColorPanelBindings")
        if not _mutex_handle:
            emit(logging.WARNING, "instance_check_warning", "Instance check not possible, starting anyway")
            return True
        return ctypes.get_last_error() != 183   # 183 = ERROR_ALREADY_EXISTS
    except Exception as e:  # noqa: BLE001
        emit(logging.WARNING, "instance_check_warning", "Instance check failed (%r), starting anyway", e)
        return True