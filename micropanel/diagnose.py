"""Assisted diagnose for the Micro Color Panel program (replaces the old self-test).

Start:  python panel_main.py --diagnose            automatic checks + assisted steps at the real panel
        python panel_main.py --diagnose --auto     automatic checks only, no questions
        python panel_main.py --diagnose --full     assisted run plus: press all 52 inputs one after the other
        python panel_main.py --diagnose --rotary   assisted run plus: turn every knob, ring and trackball once
        python panel_main.py --diagnose --action-test
                                                   assisted run plus: one real click/toggle binding in Resolve

Nothing is sent to the panel (the panel is only read). Nothing is executed in Resolve, except in part D
with --action-test, and only after you typed YES. The diagnose installs no keyboard or mouse listener.
Your own bindings.json and tabs.json are only read, never changed.

Part A  environment, configuration, screens, panel, Resolve   (automatic)
Part B  (removed: the checks of the program code with a simulated panel now run with `python -m pytest -q`)
Part C  steps at the real panel, you press keys / unplug      (assisted, skipped with --auto;
        --full adds a walk through all 52 inputs, --rotary a walk through the 18 knobs, rings and trackballs)
Part D  mouse move to every click point and DPI check          (assisted, skipped with --auto;
        --action-test adds one real click/toggle in Resolve)

The result is written to reports/diagnose_<date>_<time>.txt. Names of other programs, user name, computer name
and file paths are not part of the report.

Needs the third-party packages hid and pynput; they are imported inside the functions that use them.
"""
import logging
import os
import platform
import subprocess
import sys
import time
import traceback
from typing import Any
from datetime import datetime
from importlib import metadata
from pathlib import Path

from micropanel import BASE, __version__
from micropanel.actions import execute, to_pynput, toggle_state
from micropanel.app import python_version_note
from micropanel.config import BINDINGS_PATH, TABS_PATH, ConfigError, ConfigManager, as_point, load_profile, read_json
from micropanel.decoder import decode_held, decode_rotary, make_lookup, make_rotary_lookup, triggers_for_report
from micropanel.device import bus_name, open_panel
from micropanel.keys import NAMED_KEYS, parse_keys
from micropanel.log import anonymize, log
from micropanel.platform.windows import (DPI_NAMES, acquire_single_instance, foreground_process_name,
                                         resolve_is_foreground)

try:
    import msvcrt          # Windows only: lets the assisted steps be skipped with Enter
except ImportError:
    msvcrt = None

IS_WINDOWS = sys.platform == "win32"
STEP_SECONDS = 15


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
class Capture(logging.Handler):
    """Collects the program's log records so the checks can look at them."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def clear(self):
        self.records.clear()

    def fields(self, event):
        return [r.fields for r in self.records if getattr(r, "fields", {}).get("event") == event]


class Context:
    def __init__(self, auto, full=False, action_test=False, rotary=False):
        self.auto = auto
        self.full = full                    # --full: walk through all inputs (part C)
        self.rotary = rotary                # --rotary: walk through the rotary elements (part C)
        self.action_test = action_test      # --action-test: one real action (part D)
        self.rows = []              # (status, text) or ("SECTION", title)
        self.capture = Capture()
        self.profile: Any = None
        self.dev: Any = None             # panel opened read-only (part A), used by part C
        self.owns_lock = None       # True / False / None = not checked
        self.resolve_running = None
        self.bus: str | None = None

    def section(self, title):
        print(f"\n== {title} ==", flush=True)
        self.rows.append(("SECTION", title))

    def add(self, status, text):
        text = anonymize(text)
        self.rows.append((status, text))
        print(f"[{status}] {text}", flush=True)


def crash_location(error):
    """'function, file.py line N' of the place where an error happened (innermost frame inside the project files,
    otherwise the innermost frame). Only file names, never folders."""
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return "unknown place"
    ours = [f for f in frames if Path(f.filename).name == "panel_main.py"
            or Path(f.filename).parent.name in ("micropanel", "platform")]
    frame = (ours or frames)[-1]
    return f"in {frame.name}, {Path(frame.filename).name} line {frame.lineno}"


def short_text(text, limit=100):
    """One line, at most `limit` characters (for messages from other programs and libraries)."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def run_step(ctx, title, func):
    """Runs one check. A crash inside a check becomes a FAIL line and does not stop the diagnose."""
    try:
        func(ctx)
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001
        ctx.add("FAIL", f"{title}: the check itself crashed ({type(e).__name__}: {short_text(e, 120)}; "
                        f"{crash_location(e)})")


# --------------------------------------------------------------------------
# Part A: environment, configuration, screens, panel, Resolve
# --------------------------------------------------------------------------
def step_environment(ctx):
    bits = "64-bit" if sys.maxsize > 2 ** 32 else "32-bit"
    ctx.add("INFO", f"Program v{__version__}, Python {platform.python_version()} ({bits}), {platform.platform()}")
    note = python_version_note(sys.version_info)
    if note:
        ctx.add("INFO", note)


def step_packages(ctx):
    found, missing = [], []
    for dist in ("hidapi", "pynput"):
        try:
            found.append(f"{dist} {metadata.version(dist)}")
        except metadata.PackageNotFoundError:
            missing.append(dist)
    ctx.add("PASS" if not missing else "WARN",
            "Packages: " + ", ".join(found) + (f"; not found by name: {', '.join(missing)}" if missing else ""))


def step_profile(ctx):
    profile, errors = load_profile()
    if profile is None or errors:
        for message in errors:
            ctx.add("FAIL", f"Device profile: {message}")
        return
    ctx.profile = profile
    ctx.add("PASS", f"Device profile: {profile.name}, {len(profile.buttons)} buttons decoded, "
                    f"{len(profile.rotary_channels)} rotary elements decoded, "
                    f"{len(profile.free_bindings)} free bindings")


def step_config(ctx):
    profile = ctx.profile
    if profile is None:
        ctx.add("SKIP", "bindings.json / tabs.json: no valid device profile")
        return
    manager = ConfigManager(set(profile.buttons), profile.free_bindings)
    ctx.capture.clear()
    manager.load(initial=True)               # only reads the real files
    errors = [r.getMessage() for r in ctx.capture.records if r.levelno >= logging.ERROR]
    if errors:
        ctx.add("FAIL", f"bindings.json / tabs.json not loaded: {errors[0]}")
        return
    loaded = ctx.capture.fields("config_loaded")[-1]
    warnings = ctx.capture.fields("config_warning")
    detail = ", ".join(f"{w.get('entry', 'tabs.json')} ({w.get('reason')})" for w in warnings)
    ctx.add("WARN" if warnings else "PASS",
            f"bindings.json / tabs.json: {loaded['active']} active, {loaded['skipped']} empty, {len(warnings)} warning(s)"
            + (f": {detail}" if warnings else ""))


# ---- screens and click points (Windows) ----
def get_monitors():
    """List of monitors: position, size, scale, primary flag (Windows API through ctypes)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shcore = ctypes.WinDLL("shcore", use_last_error=True)

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    shcore.GetDpiForMonitor.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                        ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]

    monitors = []

    def callback(hmonitor, _hdc, _rect, _lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            r = info.rcMonitor
            scale = None
            try:
                dpi_x, dpi_y = ctypes.c_uint(), ctypes.c_uint()
                if shcore.GetDpiForMonitor(hmonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                    scale = round(dpi_x.value * 100 / 96)
            except Exception:  # noqa: BLE001
                pass
            monitors.append({"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom,
                             "primary": bool(info.dwFlags & 1), "scale": scale})
        return True

    user32.EnumDisplayMonitors(None, None, callback_type(callback), 0)
    return monitors


def collect_click_points():
    """Click points of tabs.json and of 'click' bindings with a fixed position (read only).
    A point counts only if the program itself would accept it (config.as_point)."""
    points = {}
    try:
        tabs = read_json(TABS_PATH, required=False)
        for name, pos in (tabs.items() if isinstance(tabs, dict) else []):
            point = as_point(pos)
            if point is not None:
                points[f"tab '{name}'"] = point
    except ConfigError:
        pass
    try:
        bindings = read_json(BINDINGS_PATH)
        for name, entry in (bindings.items() if isinstance(bindings, dict) else []):
            if not name.startswith("_") and isinstance(entry, dict) and entry.get("type") == "click":
                point = as_point(entry.get("pos"))
                if point is not None:
                    points[f"binding '{name}'"] = point
    except ConfigError:
        pass
    return points


def judge_click_points(monitors, points):
    """Rows (status, text) for the click points: inside a monitor or not. Pure function, no system access.
    A point outside every monitor usually means that tabs.json was calibrated on another computer."""
    rows, outside = [], 0
    for label, (x, y) in points.items():
        index = next((i for i, m in enumerate(monitors, start=1)
                      if m["left"] <= x < m["right"] and m["top"] <= y < m["bottom"]), None)
        if index:
            rows.append(("PASS", f"Click point {label} lies inside monitor {index}"))
        else:
            outside += 1
            rows.append(("FAIL", f"Click point {label} lies outside all monitors"))
    if outside:
        rows.append(("INFO", "tabs.json probably comes from another computer (different screens or scaling). "
                             "Calibrate again on this computer with: python tools\\calibration.py"))
    return rows


def step_screens(ctx):
    if not IS_WINDOWS:
        ctx.add("SKIP", "Screens and click points: Windows only")
        return
    monitors = get_monitors()
    if not monitors:
        ctx.add("FAIL", "Screens: the system reported no monitor")
        return
    left = min(m["left"] for m in monitors)
    top = min(m["top"] for m in monitors)
    right = max(m["right"] for m in monitors)
    bottom = max(m["bottom"] for m in monitors)
    ctx.add("INFO", f"Screens: {len(monitors)} (virtual area {right - left}x{bottom - top} pixels)")
    for i, m in enumerate(monitors, start=1):
        scale = f", scale {m['scale']}%" if m["scale"] else ""
        ctx.add("INFO", f"Monitor {i}{' (primary)' if m['primary'] else ''}: "
                        f"{m['right'] - m['left']}x{m['bottom'] - m['top']} at ({m['left']}, {m['top']}){scale}")
    points = collect_click_points()
    if not points:
        ctx.add("INFO", "No click points defined (tabs.json is empty or missing)")
    for status, text in judge_click_points(monitors, points):
        ctx.add(status, text)


def step_panel(ctx):
    import hid
    profile = ctx.profile
    if profile is None:
        ctx.add("SKIP", "Panel: no valid device profile")
        return
    entries = hid.enumerate(profile.vid, profile.pid)
    mine = [d for d in entries if d.get("usage_page") == profile.usage_page]
    if not mine:
        ctx.add("FAIL", "Panel not found (is it connected and switched on? is the Blackmagic panel driver installed?)")
        return
    d = mine[0]
    ctx.bus = bus_name(d.get("bus_type"))
    ctx.add("PASS", f"Panel found: {len(mine)} of {len(entries)} listed entry(ies) with usage page {profile.usage_page:#06x}")
    ctx.add("INFO", f"Panel: product '{d.get('product_string') or '?'}', manufacturer '{d.get('manufacturer_string') or '?'}'")
    ctx.add("INFO", f"Connection type reported by the hid library: {ctx.bus or 'not provided by this version of the library'}")
    try:
        ctx.dev = open_panel(profile)
    except OSError as e:
        ctx.add("FAIL", f"Panel found but cannot be opened: {e!r}")
        return
    ctx.add("PASS" if ctx.dev is not None else "FAIL",
            "Panel opened read-only" if ctx.dev is not None else "Panel disappeared while opening")


def step_instance(ctx):
    if not IS_WINDOWS:
        ctx.add("SKIP", "Instance check: Windows only")
        return
    ctx.owns_lock = acquire_single_instance()
    if ctx.owns_lock:
        ctx.add("PASS", "No other instance of the program is running")
    else:
        ctx.add("WARN", "Another instance of the program is running. The assisted steps and the second-instance "
                        "test are skipped. Close the program and run the diagnose again.")


def step_second_instance(ctx):
    if not IS_WINDOWS:
        ctx.add("SKIP", "Second instance is blocked: Windows only")
        return
    if not ctx.owns_lock:
        ctx.add("SKIP", "Second instance is blocked: another instance already runs, cannot test")
        return
    log_file = BASE / "panel.log"

    def log_state():
        try:
            st = log_file.stat()
            return st.st_size, st.st_mtime_ns
        except OSError:
            return None

    before = log_state()
    # --no-log-file keeps this test out of the real panel.log (in v0.3.1 the second instance wrote into it)
    result = subprocess.run([sys.executable, str(BASE / "panel_main.py"), "--no-log-file"], capture_output=True,
                            timeout=30, cwd=str(BASE))
    output = (result.stdout or b"").decode("utf-8", errors="replace")
    blocked = result.returncode == 1 and "already running" in output
    untouched = log_state() == before
    problems = []
    if not blocked:
        problems.append(f"the second instance was not blocked as expected (exit code {result.returncode})")
    if not untouched:
        problems.append("the test changed the real panel.log")
    ctx.add("PASS" if not problems else "FAIL",
            "Second instance is blocked (exit code 1, says so) and panel.log stays untouched" if not problems
            else "Second instance: " + "; ".join(problems))


# ---- Resolve ----
def listing_has_resolve(data):
    """True if the raw tasklist output (bytes) names Resolve.exe.
    The output is NOT decoded as text: on a German system tasklist prints an umlaut in the OEM code page
    when no process matches, and decoding that as text raised an error in v0.3.1."""
    return b"resolve.exe" in data.lower()


def resolve_process_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, timeout=15)
    return listing_has_resolve(out.stdout or b"")


def find_resolve_exe():
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base:
            candidate = Path(base) / "Blackmagic Design" / "DaVinci Resolve" / "Resolve.exe"
            if candidate.exists():
                return candidate
    return None


def read_version_info(path):
    """Text fields of the file's version resource (ProductName, ...). Windows only."""
    import ctypes
    import struct

    version = ctypes.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    version.GetFileVersionInfoSizeW.restype = ctypes.c_ulong
    version.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    version.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return {}
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return {}
    pointer, length = ctypes.c_void_p(), ctypes.c_uint()
    if not version.VerQueryValueW(buffer, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)) or not length.value:
        return {}
    address = pointer.value
    if not address:
        return {}
    language, codepage = struct.unpack("<HH", ctypes.string_at(address, 4))
    fields = {}
    for key in ("ProductName", "FileDescription", "FileVersion", "ProductVersion"):
        sub_block = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\{key}"
        found = version.VerQueryValueW(buffer, sub_block, ctypes.byref(pointer), ctypes.byref(length))
        address = pointer.value
        if found and length.value and address:
            fields[key] = ctypes.wstring_at(address, length.value).rstrip("\0")
    return fields


def installed_davinci_entries():
    """Names and versions of installed programs whose name contains 'DaVinci' (Windows registry)."""
    import winreg

    found = []
    for subkey in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                   r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as entry:
                        name = winreg.QueryValueEx(entry, "DisplayName")[0]
                        if "davinci" in str(name).lower():
                            try:
                                found.append(f"{name} {winreg.QueryValueEx(entry, 'DisplayVersion')[0]}")
                            except OSError:
                                found.append(str(name))
                except OSError:
                    continue
    return sorted(set(found))


def step_resolve(ctx):
    if not IS_WINDOWS:
        ctx.add("SKIP", "Resolve: Windows only")
        return
    try:
        ctx.resolve_running = resolve_process_running()
    except (OSError, subprocess.SubprocessError) as e:
        ctx.add("WARN", f"Could not check whether Resolve is running: {type(e).__name__}")
        ctx.resolve_running = None
    if ctx.resolve_running is not None:
        ctx.add("INFO", f"Resolve is running: {'yes' if ctx.resolve_running else 'no'}")

    exe = find_resolve_exe()
    if exe is None:
        ctx.add("INFO", "Resolve.exe not found in the standard install folder (file information not read)")
    else:
        try:
            info = read_version_info(exe)
            ctx.add("INFO", "Resolve.exe file information: " + (
                ", ".join(f"{k}='{v}'" for k, v in info.items()) if info else "none readable"))
        except Exception as e:  # noqa: BLE001
            ctx.add("INFO", f"Resolve.exe file information could not be read ({type(e).__name__})")
    try:
        entries = installed_davinci_entries()
        ctx.add("INFO", "Installed programs with 'DaVinci' in the name: " + ("; ".join(entries) if entries else "none"))
    except Exception as e:  # noqa: BLE001
        ctx.add("INFO", f"Installed programs could not be read ({type(e).__name__})")


def step_foreground_function(ctx):
    if not IS_WINDOWS:
        ctx.add("SKIP", "Foreground detection: Windows only")
        return
    name = foreground_process_name()
    ctx.add("PASS" if name else "WARN",
            "Foreground detection works (it returned a program name)" if name
            else "Foreground detection returned no program name")


def _known_here(name):
    """True if this system's pynput knows the key name."""
    try:
        to_pynput(parse_keys(name)[0])
        return True
    except (ValueError, AttributeError):
        return False


def step_documented_keys(ctx):
    """Which of the key names of keys.py does this system's key table not know? (Information, never a FAIL.)"""
    names = sorted(NAMED_KEYS)
    missing = [name for name in names if not _known_here(name)]
    if not missing:
        ctx.add("PASS", f"Documented key names: all {len(names)} exist in this system's key table")
    else:
        ctx.add("INFO", f"Documented key names missing on this system ({len(missing)} of {len(names)}): "
                        f"{', '.join(missing)}. A binding that uses one of them stays active and logs an action error when it fires.")


A_STEPS = [
    ("Environment", step_environment), ("Packages", step_packages), ("Device profile", step_profile),
    ("Configuration", step_config), ("Screens", step_screens), ("Panel", step_panel),
    ("Instance check", step_instance), ("Second instance", step_second_instance), ("Resolve", step_resolve),
    ("Foreground detection", step_foreground_function),
    ("Documented key names", step_documented_keys),
]


# --------------------------------------------------------------------------
# Part C: assisted steps at the real panel
# --------------------------------------------------------------------------
def key_action(allow_abort=False):
    """Looks at the keys typed so far: 'skip' for Enter, 'abort' for q (only if allowed), otherwise None."""
    if msvcrt is None:
        return None
    action = None
    while msvcrt.kbhit():
        char = msvcrt.getwch()
        if char in ("\r", "\n"):
            action = action or "skip"
        elif allow_abort and char.lower() == "q":
            action = "abort"
    return action


def enter_pressed():
    return key_action() == "skip"


def ask_text(prompt):
    """Reads one line for the assisted questions. Keys typed earlier are thrown away first."""
    if msvcrt is not None:
        while msvcrt.kbhit():
            msvcrt.getwch()
    try:
        return input(prompt)
    except EOFError:
        return ""


def wait_until(prompt, seconds, poll, allow_abort=False):
    """Shows the prompt and calls poll() until it returns something other than None.
    Returns ('ok', result), ('timeout', None), ('skipped', None) or, if allow_abort, ('aborted', None) for q."""
    hint = (", Enter = skip" + (", q = stop" if allow_abort else "")) if msvcrt else ""
    print(f"      -> {prompt} ({seconds} s{hint})", flush=True)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        action = key_action(allow_abort)
        if action == "skip":
            return "skipped", None
        if action == "abort":
            return "aborted", None
        result = poll()
        if result is not None:
            return "ok", result
    return "timeout", None


class Reader:
    """Reads button reports from the panel with the same decoding the program uses."""

    def __init__(self, profile, dev):
        self.profile, self.dev = profile, dev
        self.lookup, self.min_length = make_lookup(profile)

    def held(self):
        report = self.dev.read(64, 100)
        return decode_held(report, self.lookup, self.profile.report_id, self.min_length)


def collect_sequence(ctx, prompt, seconds=STEP_SECONDS, allow_abort=False):
    """Records the pressed-sets from the first key press until everything is released again."""
    reader = Reader(ctx.profile, ctx.dev)
    sequence = []

    def poll():
        held = reader.held()
        if held is None:
            return None
        if held or sequence:
            sequence.append(held)
        return True if (sequence and not held) else None

    status, _ = wait_until(prompt, seconds, poll, allow_abort)
    return status, sequence


def format_sequence(sequence):
    """The pressed keys of every report in order, repeats collapsed: 'shift_up > shift_up+undo > (released)'."""
    if not sequence:
        return "(no report)"
    shown = ["+".join(sorted(held)) if held else "(released)" for held in sequence]
    return " > ".join(text for i, text in enumerate(shown) if i == 0 or text != shown[i - 1])


def sequence_hint(sequence):
    """Extra hint if several keys arrived in the very first report (they were pressed at the same moment)."""
    first = next((held for held in sequence if held), set())
    if len(first) > 1:
        return (" Several keys arrived in the same report: press the first key, hold it, "
                "and press the second key a moment later.")
    return ""


def fired_by(sequence):
    prev, fired = set(), []
    for held in sequence:
        fired += triggers_for_report(prev, held)
        prev = held
    return fired


def step_press_user(ctx):
    status, sequence = collect_sequence(
        ctx, "Press the USER key once (left key in the row above the two triangle keys) and release it")
    if status == "skipped":
        ctx.add("SKIP", "Press USER: skipped")
        return
    names = set().union(*sequence) if sequence else set()
    if not sequence:
        ctx.add("WARN", "Press USER: no report received (key not pressed, or a quiet panel sends nothing)")
    elif names != {"user"}:
        ctx.add("FAIL", f"Press USER: recognized as {sorted(names)}, expected only ['user']; "
                        f"keys seen in order: {format_sequence(sequence)}")
    elif status == "timeout":
        ctx.add("WARN", "Press USER: 'user' recognized, but the release was not seen")
    else:
        ctx.add("PASS", "Press USER: recognized as 'user', release seen")


def make_combo_step(shift, label):
    def step(ctx):
        status, sequence = collect_sequence(
            ctx, f"Hold {label} and, while holding it, press UNDO; then release both")
        if status == "skipped":
            ctx.add("SKIP", f"{shift} + UNDO: skipped")
            return
        if not sequence:
            ctx.add("WARN", f"{shift} + UNDO: no report received")
            return
        fired = fired_by(sequence)
        expected = [f"{shift}+undo"]
        ctx.add("PASS" if fired == expected else "FAIL",
                f"{shift} + UNDO: the program computed {fired}"
                + ("" if fired == expected else f", expected {expected}; keys seen in order: {format_sequence(sequence)}."
                                                f"{sequence_hint(sequence)}"))
    return step


def step_order_rule(ctx):
    status, sequence = collect_sequence(
        ctx, "Press and HOLD UNDO first, then also press SHIFT UP (triangle upper left); release both")
    if status == "skipped":
        ctx.add("SKIP", "Order rule (button first, then shift): skipped")
        return
    if not sequence:
        ctx.add("WARN", "Order rule: no report received")
        return
    fired = fired_by(sequence)
    ctx.add("PASS" if fired == ["undo"] else "FAIL",
            f"Order rule (button first, then shift): the program computed {fired}"
            + ("" if fired == ["undo"] else f", expected ['undo']; keys seen in order: {format_sequence(sequence)}."
                                           f"{sequence_hint(sequence)}"))


def panel_listed(profile):
    import hid
    return any(d.get("usage_page") == profile.usage_page for d in hid.enumerate(profile.vid, profile.pid))


def step_unplug(ctx):
    profile = ctx.profile
    if ctx.bus == "Bluetooth":
        ctx.add("SKIP", "Unplug test: the panel is connected by Bluetooth")
        return
    print(f"      -> Unplug the panel's USB cable now ({STEP_SECONDS + 5} s{', Enter = skip' if msvcrt else ''})", flush=True)
    end = time.monotonic() + STEP_SECONDS + 5
    error_name, vanished_at, next_listing = None, None, 0.0
    while time.monotonic() < end:
        if enter_pressed():
            ctx.add("SKIP", "Unplug test: skipped")
            return
        try:
            ctx.dev.read(64, 100)
        except Exception as e:  # noqa: BLE001
            error_name = type(e).__name__
            break
        if time.monotonic() >= next_listing:
            next_listing = time.monotonic() + 1.0
            if not panel_listed(profile) and vanished_at is None:
                vanished_at = time.monotonic()
        if vanished_at is not None and time.monotonic() - vanished_at > 5:
            break
    if error_name in ("OSError", "ValueError"):
        ctx.add("PASS", f"Unplug: the read call failed with {error_name}, the program reconnects on this error")
    elif error_name:
        ctx.add("FAIL", f"Unplug: the read call failed with {error_name}, but the program only reconnects on OSError/ValueError")
    elif vanished_at is not None:
        ctx.add("FAIL", "Unplug: the panel left the device list but the read call raised no error (the program would not reconnect)")
    else:
        ctx.add("WARN", "Unplug: no disconnect noticed (cable not unplugged?)")
        return
    try:
        ctx.dev.close()
    except Exception:  # noqa: BLE001
        pass
    ctx.dev = None

    def reopen():
        try:
            return open_panel(profile) or None
        except OSError:
            return None
    status, dev = wait_until("Plug the cable in again", 30, lambda: (time.sleep(0.5), reopen())[1])
    if status == "ok":
        ctx.dev = dev
        ctx.add("PASS", "Replug: the panel could be opened again")
    elif status == "skipped":
        ctx.add("SKIP", "Replug: skipped")
    else:
        ctx.add("FAIL", "Replug: the panel could not be opened again within 30 s")


def step_foreground_pair(ctx):
    if not IS_WINDOWS:
        ctx.add("SKIP", "Foreground check with Resolve: Windows only")
        return
    if not ctx.resolve_running:
        ctx.add("SKIP", "Foreground check with Resolve: Resolve is not running")
        return
    status, _ = wait_until("Bring DaVinci Resolve to the front", STEP_SECONDS,
                           lambda: (time.sleep(0.3), True if resolve_is_foreground()[0] else None)[1])
    ctx.add({"ok": "PASS", "skipped": "SKIP", "timeout": "FAIL"}[status],
            {"ok": "Foreground detection recognizes Resolve", "skipped": "Foreground detection with Resolve: skipped",
             "timeout": "Foreground detection did not recognize Resolve within 15 s"}[status])
    if status != "ok":
        return
    status, _ = wait_until("Now click on this terminal window (any other program)", STEP_SECONDS,
                           lambda: (time.sleep(0.3), True if not resolve_is_foreground()[0] else None)[1])
    ctx.add({"ok": "PASS", "skipped": "SKIP", "timeout": "FAIL"}[status],
            {"ok": "Foreground detection recognizes that Resolve is not in front", "skipped": "Foreground detection without Resolve: skipped",
             "timeout": "Foreground detection still reports Resolve after 15 s"}[status])


ASSISTED_STEPS = [
    ("Press USER", step_press_user),
    ("Shift up + undo", make_combo_step("shift_up", "SHIFT UP (key with the triangle in the upper left)")),
    ("Shift down + undo", make_combo_step("shift_down", "SHIFT DOWN (key with the triangle in the lower right)")),
    ("Order rule", step_order_rule),
    ("Foreground with Resolve", step_foreground_pair),
    ("Unplug and replug", step_unplug),
]


def run_part_c(ctx):
    ctx.section("C: assisted steps at the real panel (nothing is executed, nothing is sent to the panel)")
    if ctx.profile is None or ctx.dev is None:
        ctx.add("SKIP", "Assisted steps need the panel to be found and opened (see part A)")
        return
    if ctx.owns_lock is False:
        ctx.add("SKIP", "Assisted steps skipped because another instance of the program is running")
        return
    if ctx.resolve_running is False:
        ctx.add("INFO", "Resolve is not running. In a measurement the panel then sent no button reports at all, so the "
                        "steps below probably see nothing. Start Resolve (test project) and run again.")
    extras = ([("All inputs", step_full_inputs)] if ctx.full else []) + \
             ([("Rotary elements", step_rotary_inputs)] if ctx.rotary else [])
    extras_done = False
    for title, func in ASSISTED_STEPS:
        if title == "Unplug and replug":
            for extra_title, extra_func in extras:             # before the unplug step, which closes the panel
                run_step(ctx, extra_title, extra_func)
            extras_done = True
        if ctx.dev is None and title != "Unplug and replug":
            ctx.add("SKIP", f"{title}: no open panel")
            continue
        run_step(ctx, title, func)
    if not extras_done:
        for extra_title, extra_func in extras:
            run_step(ctx, extra_title, extra_func)


# --------------------------------------------------------------------------
# --full (end of part C) and part D: judging functions (pure, tested in tests/test_diagnose.py) and the assisted steps
# --------------------------------------------------------------------------
MOUSE_TOLERANCE = 1          # pixels
FULL_PAUSE = 0.2             # seconds between two inputs of the --full run


# ---- judging functions (no system access) ----
def judge_moves(wanted, got, tolerance=MOUSE_TOLERANCE):
    """Rows (status, text): is the position read back after the move equal to the wanted one (within tolerance)?"""
    rows = []
    for label, (x, y) in wanted.items():
        read = got.get(label)
        if read is None:
            rows.append(("FAIL", f"Mouse move to click point {label}: the position could not be read back"))
            continue
        dx, dy = read[0] - x, read[1] - y
        if abs(dx) <= tolerance and abs(dy) <= tolerance:
            rows.append(("PASS", f"Mouse move to click point {label}: wanted ({x}, {y}), read back ({read[0]}, {read[1]})"))
        else:
            rows.append(("FAIL", f"Mouse move to click point {label}: wanted ({x}, {y}), read back ({read[0]}, {read[1]}), "
                                 f"off by ({dx:+d}, {dy:+d}) pixels"))
    return rows


def judge_return(start, end, tolerance=MOUSE_TOLERANCE):
    """Row (status, text): is the mouse back where it was before the test?"""
    if end is None:
        return "FAIL", "Mouse return: the final position could not be read"
    if abs(end[0] - start[0]) <= tolerance and abs(end[1] - start[1]) <= tolerance:
        return "PASS", "Mouse is back at its starting position"
    return "FAIL", (f"Mouse is not back at its start: was {start}, now {end} "
                    f"(did you touch the mouse during the test? then run it again)")


def judge_dpi(value):
    """Row (status, text) for the DPI awareness of this program (2 = per monitor)."""
    if value is None:
        return "WARN", "DPI awareness could not be read, so a wrong scaling cannot be excluded"
    name = DPI_NAMES.get(value, f"unknown value {value}")
    if value == 2:
        return "PASS", f"DPI awareness of the program: {name} (2), as required for clicks on scaled monitors"
    return "FAIL", (f"DPI awareness of the program is '{name}' ({value}), expected per monitor (2): "
                    f"on a monitor with scaling (for example 125 %) clicks would land on the wrong pixel")


def evaluate_full_input(expected, status, sequence):
    """One input of the --full run -> (outcome, detail).
    outcome: ok | ok_no_release | wrong | none | skipped | aborted. `sequence` is the list of pressed-sets."""
    if status in ("skipped", "aborted"):
        return status, ""
    names = set().union(*sequence) if sequence else set()
    if not names:
        return "none", ""
    if names != {expected}:
        return "wrong", ", ".join(sorted(names))
    return ("ok" if status == "ok" else "ok_no_release"), ""


def summarize_full(outcomes, total):
    """Rows (status, text) for the whole --full run. `outcomes` is a list of (name, outcome, detail)."""
    rows = []
    counts = {key: 0 for key in ("ok", "ok_no_release", "wrong", "none", "skipped", "aborted")}
    for name, outcome, detail in outcomes:
        counts[outcome] += 1
        if outcome == "wrong":
            rows.append(("FAIL", f"Input '{name}': recognized as [{detail}], expected only '{name}'"))
        elif outcome == "none":
            rows.append(("WARN", f"Input '{name}': no report received (not pressed in time?)"))
        elif outcome == "ok_no_release":
            rows.append(("WARN", f"Input '{name}': recognized, but the release was not seen"))
    recognized = counts["ok"] + counts["ok_no_release"]
    not_reached = total - len(outcomes) + counts["aborted"]
    parts = [f"{recognized} of {total} recognized correctly"]
    for key, label in (("wrong", "wrong"), ("none", "without report"), ("ok_no_release", "without seen release"),
                       ("skipped", "skipped")):
        if counts[key]:
            parts.append(f"{counts[key]} {label}")
    if not_reached:
        parts.append(f"{not_reached} not reached (stopped with q)")
    if counts["wrong"]:
        status = "FAIL"
    elif counts["none"] or counts["ok_no_release"]:
        status = "WARN"
    elif recognized == total:
        status = "PASS"
    else:
        status = "SKIP"
    rows.append((status, "All inputs: " + ", ".join(parts)))
    return rows


def eligible_action_bindings(actions):
    """Names of the active bindings that the action test may run: click and toggle, never keys."""
    return sorted(name for name, (kind, _data, _only) in actions.items() if kind in ("click", "toggle"))


def action_summary(action):
    kind, data, _only = action
    if kind == "click":
        return f"click at {data}"
    names, positions = data
    return "toggle " + " / ".join(f"{n} {p}" for n, p in zip(names, positions))


def parse_yes_no(text):
    """True for j/ja/y/yes, False for n/nein/no, otherwise None."""
    word = text.strip().lower()
    if word in ("j", "ja", "y", "yes"):
        return True
    if word in ("n", "nein", "no"):
        return False
    return None


def parse_yes(text):
    """Only the word YES (any case) confirms a risky step."""
    return text.strip().upper() == "YES"


def parse_choice(text, count):
    """'2' -> index 1 for a list of `count` entries; otherwise None."""
    word = text.strip()
    if word.isdigit() and 1 <= int(word) <= count:
        return int(word) - 1
    return None


def judge_action_result(results):
    """Row (status, text) from the 'result' fields of the 'action' log events of one execute() call."""
    if results == ["executed"]:
        return "PASS", "the program executed the action"
    if not results:
        return "FAIL", "the program logged no result for the action"
    return "FAIL", f"the action was not executed (result: {', '.join(str(r) for r in results)})"


# ---- --full: all inputs one after the other ----
FULL_WARNING = [
    "      Resolve reacts to the buttons while you press them: delete, reset*, auto_color, add_node, grab_still",
    "      and the knob presses change things in the open project. Open a test project first (with Resolve closed the panel sends no reports).",
]


def step_full_inputs(ctx):
    names = list(ctx.profile.buttons)
    print("\n      All inputs: the diagnose names one input after the other, you press and release it.")
    for line in FULL_WARNING:
        print(line)
    if ctx.resolve_running is False:
        print("      Resolve is not running. In a measurement the panel then sent no button reports, so probably nothing is recognized.")
        answer = ask_text("      Press Enter to try anyway, or type q to cancel (better: start Resolve with a test project): ")
        confirmed = answer.strip().lower() != "q"
    else:
        answer = ask_text("      Resolve is running (or could not be checked). Type YES to start, anything else cancels: ")
        confirmed = parse_yes(answer)
    if not confirmed:
        ctx.add("SKIP", "All inputs: cancelled before the first input")
        return
    outcomes = []
    try:
        for i, name in enumerate(names, start=1):
            status, sequence = collect_sequence(ctx, f"[{i}/{len(names)}] Press and release {name}", allow_abort=True)
            outcome, detail = evaluate_full_input(name, status, sequence)
            outcomes.append((name, outcome, detail))
            if outcome == "aborted":
                break
            time.sleep(FULL_PAUSE)
    except (OSError, ValueError) as e:
        ctx.add("FAIL", f"All inputs: the connection to the panel was lost ({type(e).__name__}); the run ends here")
    for status, text in summarize_full(outcomes, len(names)):
        ctx.add(status, text)


# ---- --rotary: every knob, ring and trackball once (end of part C) ----
ROTARY_TEXT = {
    "knob_turn": {"right": "turn it slowly to the RIGHT (clockwise) for about a second, then stop",
                  "left": "turn it slowly to the LEFT (counterclockwise) for about a second, then stop"},
    "ring": {"right": "turn the ring slowly to the RIGHT (clockwise) for about a second, then stop",
             "left": "turn the ring slowly to the LEFT (counterclockwise) for about a second, then stop"},
    "trackball": {"right": "roll the ball slowly to the RIGHT for about a second, then stop",
                  "up": "roll the ball slowly AWAY from you (toward the top of the panel) for about a second, then stop",
                  "upright": "roll the ball DIAGONALLY, away from you and to the right at the same time, for about a second, then stop"},
}
ROTARY_DIRECTIONS = {"knob_turn": ("right", "left"), "ring": ("right", "left"), "trackball": ("right", "up", "upright")}
ROTARY_CROSSTALK = 0.4       # another channel may move at most this fraction of the expected one (idle axis jitter measured: up to 0.14)
ROTARY_WEAK_AXIS = 0.15      # in a diagonal movement the weaker axis must reach this fraction of the stronger one
ROTARY_QUIET = 1.5           # seconds without a motion report that end a step


def rotary_plan(profile):
    """[(control name, control type, [(direction, instruction text), ...])] in the order of the profile."""
    return [(name, ctype, [(d, ROTARY_TEXT[ctype][d]) for d in ROTARY_DIRECTIONS[ctype]])
            for name, (ctype, _channels) in profile.rotary_channels.items()]


def expected_signs(channels, direction):
    """{axis: +1 or -1}: which sign the sum of each axis must have for this movement ('upright' = right and up)."""
    wanted = ("right", "up") if direction == "upright" else (direction,)
    result = {}
    for word in wanted:
        for channel in channels:
            sign = channel.sign_for(word)
            if sign is not None:
                result[channel.axis] = sign
    return result


def rotary_sums(profile, reports):
    """{(control name, axis): sum of all values} over a list of raw reports (all channels of the matching reports)."""
    lookup = make_rotary_lookup(profile)
    sums = {}
    for report in reports:
        for name, axis, value in decode_rotary(report, lookup):
            sums[(name, axis)] = sums.get((name, axis), 0) + value
    return sums


def evaluate_rotary(profile, name, direction, reports):
    """One step of the rotary run -> (outcome, detail).
    outcome: ok | none | wrong_channel | wrong_sign | crosstalk | weak_axis."""
    sums = rotary_sums(profile, reports)
    if not any(sums.values()):
        return "none", ""
    wanted = expected_signs(profile.rotary_channels[name][1], direction)
    targets = {(name, axis): sign for axis, sign in wanted.items()}
    moved = [(key, sums.get(key, 0)) for key in targets if sums.get(key, 0)]
    if not moved:
        top = sorted(((v, k) for k, v in sums.items() if v), key=lambda t: -abs(t[0]))[:3]
        return "wrong_channel", ", ".join(f"{n}.{a} {v:+d}" for v, (n, a) in top)
    for key, value in moved:
        if value * targets[key] < 0:
            return "wrong_sign", f"{key[1]} moved {value:+d}, expected {'+' if targets[key] > 0 else '-'}"
    strongest = max(abs(v) for _k, v in moved)
    others = sorted(f"{n}.{a} {v:+d}" for (n, a), v in sums.items() if (n, a) not in targets and abs(v) > ROTARY_CROSSTALK * strongest)
    if others:
        return "crosstalk", ", ".join(others)
    if len(targets) > 1:
        weakest = min(abs(sums.get(key, 0)) for key in targets)
        if weakest < ROTARY_WEAK_AXIS * strongest:
            return "weak_axis", "one axis hardly moved, roll more diagonally"
    return "ok", ""


def summarize_rotary(outcomes, total):
    """Rows (status, text) for the whole rotary run. `outcomes` is a list of (label, outcome, detail)."""
    rows = []
    counts = {key: 0 for key in ("ok", "none", "wrong_channel", "wrong_sign", "crosstalk", "weak_axis", "skipped", "aborted")}
    for label, outcome, detail in outcomes:
        counts[outcome] += 1
        if outcome in ("wrong_channel", "wrong_sign", "crosstalk"):
            what = {"wrong_channel": "another channel moved", "wrong_sign": "wrong direction of the numbers",
                    "crosstalk": "other channels moved as well"}[outcome]
            rows.append(("FAIL", f"Rotary {label}: {what} ({detail})"))
        elif outcome == "weak_axis":
            rows.append(("WARN", f"Rotary {label}: {detail}"))
        elif outcome == "none":
            rows.append(("WARN", f"Rotary {label}: no motion report received (not moved in time?)"))
    parts = [f"{counts['ok']} of {total} steps as expected"]
    for key, label in (("wrong_channel", "wrong channel"), ("wrong_sign", "wrong direction"), ("crosstalk", "with other channels"),
                       ("weak_axis", "not diagonal enough"), ("none", "without report"), ("skipped", "skipped")):
        if counts[key]:
            parts.append(f"{counts[key]} {label}")
    not_reached = total - len(outcomes) + counts["aborted"]
    if not_reached:
        parts.append(f"{not_reached} not reached (stopped with q)")
    if counts["wrong_channel"] or counts["wrong_sign"] or counts["crosstalk"]:
        status = "FAIL"
    elif counts["weak_axis"] or counts["none"]:
        status = "WARN"
    elif counts["ok"] == total:
        status = "PASS"
    else:
        status = "SKIP"
    rows.append((status, "Rotary elements: " + ", ".join(parts)))
    return rows


def collect_rotary(ctx, prompt, seconds: float = STEP_SECONDS, allow_abort=True, quiet: float = ROTARY_QUIET):
    """Records the raw motion reports of one movement. The step ends `quiet` seconds after the last motion report
    (the panel only sends them while an element moves). Returns (status, list of reports)."""
    ids = {channel.report for _ctype, channels in ctx.profile.rotary_channels.values() for channel in channels}
    reports: list = []
    last: list[float | None] = [None]

    def poll():
        report = ctx.dev.read(64, 100)
        now = time.monotonic()
        if report and report[0] in ids:
            reports.append(list(report))
            last[0] = now
            return None
        return True if last[0] is not None and now - last[0] >= quiet else None

    status, _ = wait_until(prompt, seconds, poll, allow_abort)
    if status == "timeout" and reports:
        status = "ok"                     # still moving after the time limit: the movement so far is enough
    return status, reports


def step_rotary_inputs(ctx):
    plan = rotary_plan(ctx.profile)
    total = sum(len(gestures) for _name, _ctype, gestures in plan)
    if not plan:
        ctx.add("SKIP", "Rotary elements: the device profile has no decoded rotary elements")
        return
    print("\n      Rotary elements: the diagnose names one movement after the other, you do it slowly and then stop.")
    print("      Knobs and rings: right (clockwise) and left. Trackballs: right, away from you, and diagonally away and right.")
    print("      Resolve reacts to the movements (colors change in the open project): open a test project first.")
    if ctx.resolve_running is False:
        print("      Resolve is not running. In a measurement the panel then sent no reports, so probably nothing is recognized.")
        answer = ask_text("      Press Enter to try anyway, or type q to cancel (better: start Resolve with a test project): ")
        confirmed = answer.strip().lower() != "q"
    else:
        answer = ask_text("      Resolve is running (or could not be checked). Type YES to start, anything else cancels: ")
        confirmed = parse_yes(answer)
    if not confirmed:
        ctx.add("SKIP", "Rotary elements: cancelled before the first step")
        return
    outcomes, number, stopped = [], 0, False
    try:
        for name, _ctype, gestures in plan:
            for direction, text in gestures:
                number += 1
                label = f"{name} {direction}"
                status, reports = collect_rotary(ctx, f"[{number}/{total}] {name}: {text}")
                if status == "aborted":
                    outcomes.append((label, "aborted", ""))
                    stopped = True
                    break
                if status == "skipped":
                    outcome, detail = "skipped", ""
                else:
                    outcome, detail = evaluate_rotary(ctx.profile, name, direction, reports)
                outcomes.append((label, outcome, detail))
                print("      ok" if outcome == "ok" else f"      {outcome}{': ' + detail if detail else ''}", flush=True)
                time.sleep(FULL_PAUSE)
            if stopped:
                break
    except (OSError, ValueError) as e:
        ctx.add("FAIL", f"Rotary elements: the connection to the panel was lost ({type(e).__name__}); the run ends here")
    for status, text in summarize_rotary(outcomes, total):
        ctx.add(status, text)


# ---- part D1: mouse path and DPI awareness ----
def get_dpi_awareness():
    """DPI awareness of this process (0 unaware, 1 system, 2 per monitor), or None if it cannot be read. Windows only."""
    import ctypes
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.GetProcessDpiAwareness.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        shcore.GetProcessDpiAwareness.restype = ctypes.c_long
        value = ctypes.c_int()
        if shcore.GetProcessDpiAwareness(None, ctypes.byref(value)) == 0:
            return value.value
    except Exception:  # noqa: BLE001
        pass
    return None


def move_mouse_through(points, sleep=time.sleep):
    """Moves the mouse (no click) to every point and reads the position back; a deviating point is tried once more.
    The mouse is always put back to where it was. Returns (start, {label: position read back}, end)."""
    from pynput.mouse import Controller
    mouse = Controller()

    def where():
        x, y = mouse.position
        return int(x), int(y)

    start, got = where(), {}
    try:
        for label, (x, y) in points.items():
            for _attempt in (1, 2):
                mouse.position = (x, y)
                sleep(0.15)
                got[label] = where()
                if max(abs(got[label][0] - x), abs(got[label][1] - y)) <= MOUSE_TOLERANCE:
                    break
    finally:
        mouse.position = start
        sleep(0.15)
    return start, got, where()


def step_mouse_points(ctx):
    if not IS_WINDOWS:
        ctx.add("SKIP", "Mouse path and DPI awareness: Windows only")
        return
    status, text = judge_dpi(get_dpi_awareness())
    ctx.add(status, text)
    points = collect_click_points()
    if not points:
        ctx.add("SKIP", "Mouse path: no click points defined (tabs.json is empty or missing)")
        return
    if any(row[0] == "FAIL" for row in judge_click_points(get_monitors(), points)):
        ctx.add("SKIP", "Mouse path: not all click points lie inside a monitor (see part A), calibrate first")
        return
    state, _ = wait_until("The mouse moves to every click point for a moment (no click). Do not touch mouse or keyboard",
                          5, lambda: (time.sleep(0.05), None)[1])
    if state == "skipped":
        ctx.add("SKIP", "Mouse path: skipped")
        return
    start, got, end = move_mouse_through(points)
    for row in judge_moves(points, got):
        ctx.add(*row)
    ctx.add(*judge_return(start, end))
    ctx.add("INFO", "The mouse path shows that the points are reachable; it does not show that a point lies on the right tab "
                    "in Resolve (that is what --action-test is for)")


# ---- part D2: one real action ----
def press_in_resolve(ctx, name, action):
    """Waits until Resolve is in front, then runs the real execute(). Returns the list of 'result' values or None."""
    status, _ = wait_until("Bring DaVinci Resolve to the front, the action runs as soon as it is there", STEP_SECONDS,
                           lambda: (time.sleep(0.3), True if resolve_is_foreground()[0] else None)[1])
    if status != "ok":
        return None
    ctx.capture.clear()
    execute(name, action)
    return [fields.get("result") for fields in ctx.capture.fields("action")]


def ask_yes_no(prompt):
    return parse_yes_no(ask_text(prompt))


def action_sequence(ctx, name, action, label):
    kind, data, _only = action
    results = press_in_resolve(ctx, name, action)
    if results is None:
        ctx.add("SKIP", f"Real action {label}: Resolve did not come to the front, nothing was executed")
        return
    status, text = judge_action_result(results)
    ctx.add(status, f"Real action {label}: {text}")
    if status != "PASS":
        return
    seen = ask_yes_no("      Click on this terminal. Did Resolve show the expected change? (y/n): ")
    if seen is None:
        ctx.add("WARN", f"Real action {label}: the answer was not understood, effect not confirmed")
        return
    if not seen:
        ctx.add("FAIL", f"Real action {label}: you saw no change in Resolve (check window position and scaling, "
                        f"calibrate again with tools\\calibration.py)")
        if kind == "toggle":
            ctx.add("INFO", "The return press was not run. Check by hand which palette Resolve shows.")
        return
    ctx.add("PASS", f"Real action {label}: you confirmed the change in Resolve")
    if kind != "toggle":
        return
    tab_names = data[0]
    count = len(tab_names)
    if count > 2:
        answer = ask_text(f"      The toggle has {count} tabs. Type YES to press it {count - 1} more times, "
                          f"so that Resolve is back on '{tab_names[-1]}': ")
        if not parse_yes(answer):
            ctx.add("WARN", f"Real action {label}: not run back to the start, Resolve may show another palette now")
            return
    for _ in range(count - 1):
        results = press_in_resolve(ctx, name, action)
        if results is None:
            ctx.add("WARN", f"Real action {label}: Resolve did not come to the front for the return press; "
                            f"check by hand which palette Resolve shows")
            return
        status, text = judge_action_result(results)
        if status != "PASS":
            ctx.add(status, f"Real action {label}, return press: {text}")
            return
    back = ask_yes_no(f"      Click on this terminal. Does Resolve show '{tab_names[-1]}' again, as at the start? (y/n): ")
    if back is None:
        ctx.add("WARN", f"Real action {label}: the answer was not understood, return not confirmed")
    else:
        ctx.add("PASS" if back else "FAIL",
                f"Real action {label}: " + ("Resolve is back at the starting palette" if back
                                            else "Resolve is not back at the starting palette (check by hand)"))


def run_action_flow(ctx, actions):
    """The conversation and the execution of the action test. `actions` is the compiled bindings dictionary."""
    names = eligible_action_bindings(actions)
    if not names:
        ctx.add("SKIP", "Real action: no click or toggle binding is active in bindings.json")
        return
    if len(names) == 1:
        choice = names[0]
    else:
        print("\n      Click and toggle bindings in your bindings.json:")
        for i, candidate in enumerate(names, start=1):
            print(f"        {i}) {candidate}: {action_summary(actions[candidate])}")
        index = parse_choice(ask_text(f"      Number of the binding to run (1-{len(names)}), Enter = skip: "), len(names))
        if index is None:
            ctx.add("SKIP", "Real action: no binding chosen")
            return
        choice = names[index]
    action = actions[choice]
    kind, data, _only = action
    label = f"'{choice}' ({action_summary(action)})"
    print(f"\n      This runs the real action {label} once in DaVinci Resolve (a mouse click).")
    if kind == "toggle":
        print(f"      The toggle starts at '{data[0][0]}'. The program cannot know what Resolve shows now, so first show "
              f"'{data[0][-1]}' in Resolve.")
        print("      Afterwards the toggle is pressed until Resolve is back at that palette.")
    if not parse_yes(ask_text("      Type YES to run it, anything else skips this step: ")):
        ctx.add("SKIP", f"Real action {label}: not confirmed")
        return
    saved = dict(toggle_state)
    toggle_state.clear()
    try:
        action_sequence(ctx, choice, action, label)
    finally:
        toggle_state.clear()
        toggle_state.update(saved)


def step_action_test(ctx):
    if not IS_WINDOWS:
        ctx.add("SKIP", "Real action: Windows only")
        return
    if ctx.profile is None:
        ctx.add("SKIP", "Real action: no valid device profile")
        return
    if not ctx.resolve_running:
        ctx.add("SKIP", "Real action: Resolve is not running" if ctx.resolve_running is False
                else "Real action: could not check whether Resolve is running")
        return
    points = collect_click_points()
    if any(row[0] == "FAIL" for row in judge_click_points(get_monitors(), points)):
        ctx.add("SKIP", "Real action: not all click points lie inside a monitor (see part A), calibrate first")
        return
    manager = ConfigManager(set(ctx.profile.buttons), ctx.profile.free_bindings)
    ctx.capture.clear()
    manager.load(initial=True)               # only reads the real files
    if any(r.levelno >= logging.ERROR for r in ctx.capture.records):
        ctx.add("SKIP", "Real action: bindings.json / tabs.json could not be loaded")
        return
    run_action_flow(ctx, manager.actions)


def run_part_d(ctx):
    ctx.section("D: mouse path, DPI awareness and real action (the mouse moves; a click only in the action test)")
    run_step(ctx, "Mouse path and DPI awareness", step_mouse_points)
    if ctx.action_test:
        run_step(ctx, "Real action", step_action_test)
    else:
        ctx.add("INFO", "Real action not run (start with --action-test to include it)")


# --------------------------------------------------------------------------
# Run + report
# --------------------------------------------------------------------------
def run(auto=False, full=False, action_test=False, rotary=False):
    """Runs the diagnose. Returns 0 if there was no FAIL, otherwise 1."""
    if auto:
        full = action_test = rotary = False        # all three need you at the panel (app.parse_args refuses the combination as well)
    ctx = Context(auto, full, action_test, rotary)
    handlers_before, propagate_before = log.handlers[:], log.propagate
    log.handlers[:] = [ctx.capture]
    log.propagate = False
    started = datetime.now()
    mode = "automatic checks only" if auto else "assisted" + (", full" if full else "") + (", rotary" if rotary else "") + \
        (", action test" if action_test else "")
    print(f"Micro Color Panel diagnose (program v{__version__}, {mode})")
    print("Nothing is sent to the panel. Close the normal program first.")
    if action_test:
        print("Action test: in part D one real click is executed in Resolve, but only after you type YES.")
    else:
        print("Nothing is executed in Resolve.")
    try:
        ctx.section("A: environment, configuration, panel, Resolve")
        for title, func in A_STEPS:
            run_step(ctx, title, func)
        if auto:
            ctx.section("C: assisted steps at the real panel")
            ctx.add("INFO", "Assisted steps skipped (--auto)")
            ctx.section("D: mouse path, DPI awareness and real action")
            ctx.add("INFO", "Mouse and action tests skipped (--auto)")
        else:
            run_part_c(ctx)
            run_part_d(ctx)
    except KeyboardInterrupt:
        ctx.add("WARN", "Diagnose interrupted by the user; the remaining steps were not run")
    finally:
        if ctx.dev is not None:
            try:
                ctx.dev.close()
            except Exception:  # noqa: BLE001
                pass
        log.handlers[:] = handlers_before
        log.propagate = propagate_before

    counts = {s: sum(1 for status, _ in ctx.rows if status == s) for s in ("FAIL", "WARN", "SKIP")}
    summary = f"Result: {counts['FAIL']} FAIL, {counts['WARN']} WARN, {counts['SKIP']} SKIP"
    lines = ["Micro Color Panel diagnose report",
             f"Program version: {__version__}    Created: {started.strftime('%Y-%m-%d %H:%M:%S')} (local time)    Mode: {mode}"]
    for status, text in ctx.rows:
        lines += ["", f"== {text} =="] if status == "SECTION" else [f"[{status}] {text}"]
    lines += ["", summary]
    report = BASE / "reports" / f"diagnose_{started.strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        report.parent.mkdir(exist_ok=True)
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        where = f"Report written: reports\\{report.name}"
    except OSError as e:
        where = f"Report could not be written ({type(e).__name__})"
    print(f"\n{summary}\n{where}")
    return 1 if counts["FAIL"] else 0
