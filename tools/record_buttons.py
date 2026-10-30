"""Record panel buttons -> writes ../recordings/buttons_new.json

Reads the button names from button_list.txt (one name per line, same folder as this script)
and asks for one button at a time. Only bytes 1 to 8 of report 02 are evaluated.
Nothing is sent to the panel.

Notes:
  - Resolve reacts to the buttons while you record. Use a test project.
  - Press only one button at a time. Do not touch rings or trackballs.
  - Buttons already present in buttons_new.json are skipped.
    To record again, delete the file or remove the entry.
  - An existing recordings/buttons.json is never overwritten.
Next step (only if the device profile should be rebuilt from this recording):
  python tools\\build_profile.py recordings\\buttons_new.json
It checks the recording against the name lists and saves the old profile as micro_color_panel.bak.json.

Start (from the project folder): python tools\\record_buttons.py
"""
import json
import time
from pathlib import Path

import hid

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
LIST_FILE = HERE / "button_list.txt"
OUT_FILE = BASE / "recordings" / "buttons_new.json"

VID, PID, USAGE_PAGE = 0x1EDB, 0xDA0F, 0xFF00   # as in devices/micro_color_panel.json; found by usage page (Bluetooth has no interface 2)
KEY_BYTES = range(1, 9)

if not LIST_FILE.exists():
    raise SystemExit(f"{LIST_FILE} is missing (one button name per line).")
names = [line.strip() for line in LIST_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]

OUT_FILE.parent.mkdir(exist_ok=True)
result = {}
if OUT_FILE.exists():
    result = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    print(f"{len(result)} buttons already recorded, skipping them.")

path = next((d["path"] for d in hid.enumerate(VID, PID) if d["usage_page"] == USAGE_PAGE), None)
if path is None:
    raise SystemExit("Panel not found. Is it connected (USB or Bluetooth) and is Resolve/the driver active?")
dev = hid.device()
dev.open_path(path)


def key_bits(report):
    return {i: report[i] for i in KEY_BYTES if len(report) > i and report[i]}


def read_report_02():
    report = dev.read(64, 100)
    if report and len(report) >= 9 and report[0] == 0x02:
        return report
    return None


def wait_for_press(timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        report = read_report_02()
        if report and key_bits(report):
            return key_bits(report)
    return None


def collect_until_release(first, timeout=8):
    acc = dict(first)
    end = time.time() + timeout
    while time.time() < end:
        report = read_report_02()
        if report is None:
            continue
        bits = key_bits(report)
        if not bits:
            return acc
        for i, b in bits.items():
            acc[i] = acc.get(i, 0) | b
    print("   (release not detected, using the data collected so far)")
    return acc


def used_by_other(byte, mask, own_name):
    for other_name, entry in result.items():
        if other_name != own_name and entry and entry[0] == [byte, mask]:
            return other_name
    return None


try:
    for name in names:
        if name in result:
            continue
        while True:
            print(f"\n>>> {name}: press and release the button now (20 s)")
            first = wait_for_press()
            if first is None:
                answer = input("   No input. Enter = retry, s = skip: ").strip().lower()
                if answer == "s":
                    break
                continue
            bits = collect_until_release(first)
            shown = {i: f"{b:02x}" for i, b in bits.items()}
            if len(bits) != 1 or bin(next(iter(bits.values()))).count("1") != 1:
                print("   WARNING: more than one bit detected:", shown, "- press only this button.")
                continue
            byte, mask = next(iter(bits.items()))
            other = used_by_other(byte, mask, name)
            if other:
                print(f"   WARNING: byte {byte} / mask {mask:02x} already belongs to '{other}'. Try again.")
                continue
            print("   detected:", shown)
            result[name] = [[byte, mask]]
            OUT_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")   # saved after every button
            time.sleep(0.4)
            break
except KeyboardInterrupt:
    print("\nAborted. Results so far are saved.")
finally:
    dev.close()

print(f"\nDone. {len(result)} buttons in {OUT_FILE}")
