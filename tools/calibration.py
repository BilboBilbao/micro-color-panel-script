"""Calibrate click points -> writes/updates ../tabs.json

Steps for each point:
  1. Enter a name (e.g. primaries, hdr, log)
  2. Move the mouse over the tab in Resolve, then press Enter in the terminal
  3. Do not move the mouse during the countdown

Existing points in tabs.json are kept; points with the same name are overwritten.
Every save also stores the current monitor layout under "_monitors". panel_main.py warns when the layout differs later.
Names starting with an underscore are reserved for notes and cannot be used as point names.
The Resolve window must be positioned the way you will use it later.
The points are valid for this computer only (screens, scaling and window position). Calibrate on every computer.
Points on a monitor left of or above the main monitor have negative numbers; that is correct.

Start (from the project folder): python tools\\calibration.py
"""
import ctypes
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TABS_FILE = BASE / "tabs.json"

# Same DPI setting as the program (set_dpi_awareness in micropanel/platform/windows.py, called first in panel_main.py).
# This must happen BEFORE the mouse package is imported (see panel_main.py), the same order as in the program.
_awareness = None
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    _value = ctypes.c_int()
    if ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(_value)) == 0:
        _awareness = _value.value
except Exception as e:  # noqa: BLE001
    print("Note: DPI awareness not set:", repr(e))
if _awareness is not None and _awareness != 2:
    print(f"WARNING: DPI awareness is {_awareness} instead of 2 (per monitor). The points may not match panel_main.py.")

from pynput.mouse import Controller  # noqa: E402  (deliberately after the DPI call)

sys.path.insert(0, str(BASE))     # this script lives in tools/, the micropanel package is one folder up
from micropanel.config import current_layout, parse_layout  # noqa: E402  (standard library only)
from micropanel.platform.windows import get_monitors  # noqa: E402

mouse = Controller()

try:
    layout = current_layout(get_monitors())     # sorted rectangles; json.dumps writes them as lists
except Exception as e:  # noqa: BLE001
    layout = None
    print("Note: the monitor layout could not be read and will not be saved:", repr(e))

tabs = {}
if TABS_FILE.exists():
    try:
        tabs = json.loads(TABS_FILE.read_text(encoding="utf-8"))
        print("Existing points:", {k: v for k, v in tabs.items() if not k.startswith("_")})
    except json.JSONDecodeError:
        print("WARNING: the existing tabs.json is not valid JSON and will be overwritten.")

saved_layout = parse_layout(tabs.get("_monitors"))
if layout is not None and saved_layout is not None and saved_layout != layout:
    print("WARNING: the existing points were made for another monitor layout.\n"
          "  Saving now marks ALL points as valid for the current layout, so recalibrate the old ones.")

print("\nExample names: primaries, hdr")
while True:
    name = input("\nName of the point (empty = finish): ").strip()
    if not name:
        break
    if name.startswith("_"):
        print("  Names starting with '_' are reserved for notes. Choose another name.")
        continue
    if name in tabs:
        print(f"  '{name}' already exists ({tabs[name]}) and will be overwritten.")
    input(f"  Move the mouse over '{name}', then press Enter here ...")
    for i in (3, 2, 1):
        print(" ", i, end="", flush=True)
        time.sleep(1)
    x, y = mouse.position
    tabs[name] = [int(x), int(y)]
    if layout is not None:
        tabs["_monitors"] = layout
    TABS_FILE.write_text(json.dumps(tabs, indent=2), encoding="utf-8")   # saved after every point
    print(f"\n  -> {name}: {tabs[name]} saved")

print("\nDone. tabs.json:", tabs)
