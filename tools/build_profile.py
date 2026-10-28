"""Build devices/micro_color_panel.json from the old button file and the two name lists.

Usage (from the project folder):
  python tools\\build_profile.py                           (reads recordings\\buttons.json)
  python tools\\build_profile.py path\\to\\recording.json

Reads:   a button recording (name -> [[byte, mask]]), tools/button_list.txt, tools/knobs_list.txt
         The report positions of knobs, trackballs and rings are not in buttons_clean.json: they are built in main()
         from the measured layout described above KNOB_REPORT (tools/record_rotary.py, docs/HARDWARE.md).
Writes:  devices/micro_color_panel.json (an existing file is saved as micro_color_panel.bak.json first)

After writing, the new profile is read back and every button position is compared with the source.
Nothing is written if the inputs are inconsistent.
"""
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TOOLS = BASE / "tools"
TARGET = BASE / "devices" / "micro_color_panel.json"

# The 31 combinations without a native function (Blackmagic manual, Sept. 2024, Control Table).
# Live-tested on Resolve 21.0.4.5 Studio: no reaction. main() adds shift_up/shift_down + every knob press (24, live test only).
FREE_BINDINGS = [
    "user", "shift_up+user", "shift_down+user",
    "shift_down+offset", "shift_down+copy", "shift_down+paste",
    "shift_up+undo", "shift_down+undo", "shift_up+redo", "shift_down+redo",
    "shift_up+bypass", "shift_down+bypass", "shift_up+disable", "shift_down+disable",
    "shift_down+wipe_still", "shift_up+grab_still", "shift_down+grab_still", "shift_down+h_lite",
    "shift_up+cursor", "shift_down+cursor", "shift_up+select", "shift_down+select",
    "shift_down+add_keyframe", "shift_down+next_still",
    "shift_up+prev_node", "shift_up+next_node", "shift_up+prev_frame", "shift_up+next_frame",
    "shift_up+backward", "shift_up+forward", "shift_up+stop",
]

DEVICE = {"name": "DaVinci Resolve Micro Color Panel", "vid": "0x1EDB", "pid": "0xDA0F", "hid_usage_page": "0xFF00"}
REPORTS = {"buttons": "0x02", "trackballs_rings": "0x05", "knobs": "0x06"}
INFO = ("Hardware facts of the DaVinci Resolve Micro Color Panel. Buttons and knob presses: a bit in report 0x02. "
        "Knobs, trackballs and rings: 'channels', each a signed little-endian number in report 0x05 or 0x06 that holds the "
        "change since the previous report (a delta), positive in the direction named by 'positive'. "
        "Restart the program after editing this file.")

# Measured layout of the motion reports (tools/record_rotary.py, docs/HARDWARE.md).
# knobs: report 0x06, 12 channels of 32 bit at byte 1 + 4 x k (k = order of the *_knob names in knobs_list.txt), right = positive.
# trackballs and rings: report 0x05, 24 bit, three groups of 12 bytes (k = order of the *_trackball / *_ring names):
#   x at byte 2 + 12 k (right = negative), y at byte 6 + 12 k (up, away from you = negative), ring at byte 10 + 12 k (right = positive).
KNOB_REPORT, MOTION_REPORT = 6, 5


def read_names(path):
    if not path.exists():
        raise SystemExit(f"List not found: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def find_source():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    candidate = BASE / "recordings" / "buttons.json"
    if candidate.exists():
        return candidate
    raise SystemExit("recordings\\buttons.json not found; give the path of a button recording as argument")


def main():
    source = find_source()
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    button_names = read_names(TOOLS / "button_list.txt")
    knob_names = read_names(TOOLS / "knobs_list.txt")
    problems, controls = [], []

    if len(button_names) != len(set(button_names)):
        problems.append("button_list.txt contains a name twice")
    if set(button_names) != set(raw):
        problems.append(f"names differ: only in button_list.txt {sorted(set(button_names) - set(raw))}, "
                        f"only in the recording {sorted(set(raw) - set(button_names))}")
    for needed in ("shift_up", "shift_down"):
        if needed not in button_names:
            problems.append(f"'{needed}' is missing")

    for name in button_names:
        entry = raw.get(name)
        if not (isinstance(entry, list) and len(entry) == 1 and len(entry[0]) == 2):
            problems.append(f"{name}: expected exactly one [byte, mask] pair, got {entry}")
            continue
        byte, mask = entry[0]
        if mask <= 0 or mask & (mask - 1):
            problems.append(f"{name}: mask {mask} is not a single bit")
            continue
        kind = "knob_press" if name.endswith("_knob_press") else "button"
        controls.append({"name": name, "type": kind, "byte": byte, "bit": mask.bit_length() - 1})

    counts = {"knob": 0, "trackball": 0, "ring": 0}
    for name in knob_names:
        if name.endswith("_knob"):
            k = counts["knob"]
            counts["knob"] += 1
            channels = [{"axis": "turn", "report": KNOB_REPORT, "byte": 1 + 4 * k, "width": 32, "positive": "right"}]
            controls.append({"name": name + "_turn", "type": "knob_turn", "channels": channels})
        elif name.endswith("_trackball"):
            k = counts["trackball"]
            counts["trackball"] += 1
            channels = [{"axis": "x", "report": MOTION_REPORT, "byte": 2 + 12 * k, "width": 24, "positive": "left"},
                        {"axis": "y", "report": MOTION_REPORT, "byte": 6 + 12 * k, "width": 24, "positive": "down"}]
            controls.append({"name": name, "type": "trackball", "channels": channels})
        elif name.endswith("_ring"):
            k = counts["ring"]
            counts["ring"] += 1
            channels = [{"axis": "turn", "report": MOTION_REPORT, "byte": 10 + 12 * k, "width": 24, "positive": "right"}]
            controls.append({"name": name, "type": "ring", "channels": channels})
        else:
            problems.append(f"knobs_list.txt: cannot classify '{name}' (expected *_knob, *_trackball or *_ring)")
    if counts != {"knob": 12, "trackball": 3, "ring": 3}:
        problems.append(f"knobs_list.txt must name 12 knobs, 3 trackballs and 3 rings, found {counts}")

    if problems:
        print("NOT WRITTEN, please check:")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)

    free_bindings = FREE_BINDINGS + [f"{shift}+{name}" for shift in ("shift_up", "shift_down")
                                     for name in button_names if name.endswith("_knob_press")]
    lines = ["{", f'  "_info": {json.dumps(INFO)},', '  "profile_version": 2,',
             f'  "device": {json.dumps(DEVICE)},', f'  "reports": {json.dumps(REPORTS)},', '  "controls": [']
    for i, control in enumerate(controls):
        lines.append("    " + json.dumps(control) + ("," if i < len(controls) - 1 else ""))
    lines += ["  ],", '  "free_bindings": [']
    for i, name in enumerate(free_bindings):
        lines.append("    " + json.dumps(name) + ("," if i < len(free_bindings) - 1 else ""))
    lines += ["  ]", "}"]

    TARGET.parent.mkdir(exist_ok=True)
    if TARGET.exists():
        shutil.copy2(TARGET, TARGET.with_suffix(".bak.json"))
        print("Existing profile saved as micro_color_panel.bak.json")
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # read back and compare every position with the source
    written = json.loads(TARGET.read_text(encoding="utf-8"))
    mismatches = 0
    for c in written["controls"]:
        if c["type"] in ("button", "knob_press"):
            if [[c["byte"], 1 << c["bit"]]] != raw[c["name"]]:
                print("MISMATCH:", c["name"])
                mismatches += 1
    decoded = sum(1 for c in written["controls"] if c["type"] in ("button", "knob_press"))
    rotary = len(written["controls"]) - decoded
    rotary_open = sum(1 for c in written["controls"] if c["type"] not in ("button", "knob_press") and "channels" not in c)
    print(f"{decoded} buttons decoded, {rotary - rotary_open} rotary elements decoded, {rotary_open} not decoded yet, "
          f"{len(written['free_bindings'])} free bindings, {mismatches} mismatch(es)")
    print("OK: all button positions identical to the source." if mismatches == 0 else "ERROR: see MISMATCH lines")
    print("Written:", TARGET)


if __name__ == "__main__":
    main()
