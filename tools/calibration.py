"""Calibrate click points -> writes/updates ../tabs.json

Steps for each point:
  1. Enter a name (e.g. primaries, hdr, log)
  2. Move the mouse over the tab in Resolve, then press Enter in the terminal
  3. Do not move the mouse during the countdown

Existing points in tabs.json are kept; points with the same name are overwritten.
The Resolve window must be positioned the way you will use it later.
The points are valid for this computer only (screens, scaling and window position). Calibrate on every computer.

Start (from the project folder): python tools\\calibration.py
"""
import ctypes
import json
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TABS_FILE = BASE / "tabs.json"

# Same DPI setting as the program (set_dpi_awareness in micropanel/platform/windows.py, called first in panel_main.py).
# This must happen BEFORE pyautogui is imported: pyautogui sets the weaker
# "system" awareness (1) when it is imported, and Windows then refuses the change to 2.
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

import pyautogui  # noqa: E402  (deliberately after the DPI call)

pyautogui.FAILSAFE = False

tabs = {}
if TABS_FILE.exists():
    try:
        tabs = json.loads(TABS_FILE.read_text(encoding="utf-8"))
        print("Existing points:", tabs)
    except json.JSONDecodeError:
        print("WARNING: the existing tabs.json is not valid JSON and will be overwritten.")

print("\nExample names: primaries, hdr")
while True:
    name = input("\nName of the point (empty = finish): ").strip()
    if not name:
        break
    if name in tabs:
        print(f"  '{name}' already exists ({tabs[name]}) and will be overwritten.")
    input(f"  Move the mouse over '{name}', then press Enter here ...")
    for i in (3, 2, 1):
        print(" ", i, end="", flush=True)
        time.sleep(1)
    p = pyautogui.position()
    tabs[name] = [int(p.x), int(p.y)]
    TABS_FILE.write_text(json.dumps(tabs, indent=2), encoding="utf-8")   # saved after every point
    print(f"\n  -> {name}: {tabs[name]} saved")

print("\nDone. tabs.json:", tabs)
