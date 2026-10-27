"""Shows the process name of the program in the foreground.

Purpose: find out what Resolve is called on your system (expected: Resolve.exe)
if the foreground check (micropanel/platform/windows.py) does not work as expected.
If the name differs, change RESOLVE_EXE at the top of micropanel/platform/windows.py.

Start: python tools\\window_name.py
Then click the window you want to check (e.g. Resolve) within 5 seconds.
"""
import ctypes
import time
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


def name_of_foreground():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "(no foreground window)"
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return f"(access denied, PID {pid.value})"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return f"(name not readable, PID {pid.value})"
        return f"{Path(buf.value).name}   [{buf.value}]"
    finally:
        kernel32.CloseHandle(handle)


print("Bring the window to the foreground, output follows in 5 s ...")
for i in range(5, 0, -1):
    print(i, end=" ", flush=True)
    time.sleep(1)
print("\nForeground:", name_of_foreground())
