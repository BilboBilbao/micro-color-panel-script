"""Record the rotary elements (knobs, trackballs, rings) -> writes ../recordings/rotary_raw.json

The 12 knobs, 3 trackballs and 3 rings turn freely (no detents). For every element the tool asks for a few
slow movements and stores the RAW reports of the panel, so the analysis does not depend on any assumption:
  knob       2 steps: slowly to the right, slowly to the left (about one full turn each)
  trackball  4 steps: right, left, up (away from you), down (toward you)
  ring       2 steps: slowly to the right, slowly to the left (about a quarter turn each)
That makes 42 steps for the 18 elements in tools/knobs_list.txt.

Per step: "hands off" for 1.5 s (this records the resting reports), then GO. Move the element slowly and
steadily, then stop. The step ends 2 s after the last report that is not a resting report (the panel only
sends reports while an element moves, so this is 2 s after you stopped; identical reports in a row count too,
a ring turned at constant speed sends the same value over and over). Enter ends a step early (before any
movement it skips the step), q stops the whole recording.
The trackball is a free ball: a diagonal movement simply moves both axes at the same time.

Notes:
  - Nothing is sent to the panel. Only interface 2 is read, as in the other tools.
  - Resolve must be running (without Resolve the panel sent no reports in a measurement), and Resolve
    reacts to the movements. Use a test project. The tool changes nothing in Resolve itself.
  - Elements already present in rotary_raw.json are skipped. To record one again, delete its entry (or the file).
  - The file is saved after every element. An element that was interrupted is not saved.
  - All reports are stored, identical reports directly after each other are stored once with a count,
    so sums over the movement stay exact.
To record some elements again (the old entries are saved to a backup file first):
  python tools\\record_rotary.py --redo ring              (all rings)
  python tools\\record_rotary.py --redo lift_ring hue_knob  (single elements by name)
Next step: python tools\\analyze_rotary.py

Start (from the project folder): python tools\\record_rotary.py
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

try:
    import msvcrt          # Windows only: Enter / q during a step
except ImportError:
    msvcrt = None

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
LIST_FILE = HERE / "knobs_list.txt"
PROFILE_FILE = BASE / "devices" / "micro_color_panel.json"
OUT_FILE = BASE / "recordings" / "rotary_raw.json"

RECORDER_VERSION = 1
KNOWN_IDS = (0x02, 0x05, 0x06)      # report ids that are already known (buttons, trackballs and rings, knobs)
MAX_BASELINE = 50             # distinct resting reports kept
MAX_ENTRIES = 3000            # entries kept per step (identical neighbours count as one entry)

GESTURES = {
    "knob": [("right", "turn it slowly to the RIGHT (clockwise), about one full turn, then stop"),
             ("left", "turn it slowly to the LEFT (counterclockwise), about one full turn, then stop")],
    "trackball": [("right", "roll the ball slowly to the RIGHT for about 3 seconds, then stop"),
                  ("left", "roll the ball slowly to the LEFT for about 3 seconds, then stop"),
                  ("up", "roll the ball slowly AWAY from you (toward the top of the panel) for about 3 seconds, then stop"),
                  ("down", "roll the ball slowly TOWARD you for about 3 seconds, then stop")],
    "ring": [("right", "turn the ring slowly to the RIGHT (clockwise), about a quarter turn, then stop"),
             ("left", "turn the ring slowly to the LEFT (counterclockwise), about a quarter turn, then stop")],
}


def element_kind(name):
    for suffix, kind in (("_knob", "knob"), ("_trackball", "trackball"), ("_ring", "ring")):
        if name.endswith(suffix):
            return kind
    return None


def poll_key():
    """'skip' for Enter, 'abort' for q, otherwise None. Without msvcrt (not Windows) there are no keys."""
    if msvcrt is None:
        return None
    action = None
    while msvcrt.kbhit():
        char = msvcrt.getwch()
        if char in ("\r", "\n"):
            action = action or "skip"
        elif char.lower() == "q":
            action = "abort"
    return action


# --------------------------------------------------------------------------
# Pure helpers (also used by analyze_rotary.py)
# --------------------------------------------------------------------------
def changed_bytes(baseline, entries, zero_rest=False):
    """{report id: sorted byte positions that take more than one value}, looking at the resting reports
    (`baseline`: list of hex texts) and the reports of the step (`entries`: list of [ms, hex, count]) together.
    zero_rest: for a report id without a resting report, an all-zero report counts as the resting state
    (the panel sends no resting reports for the rotary elements, a delta of 0 is their rest). Without it a
    value that stays constant during the whole step (a ring turned at constant speed) would look unchanged."""
    values = {}
    for text in list(baseline) + [e[1] for e in entries]:
        data = bytes.fromhex(text)
        if not data:
            continue
        per_id = values.setdefault(data[0], {})
        for index, value in enumerate(data):
            per_id.setdefault(index, set()).add(value)
    if zero_rest:
        resting = {bytes.fromhex(t)[0] for t in baseline if t}
        for rid, per_id in values.items():
            if rid not in resting:
                for index in per_id:
                    per_id[index].add(rid if index == 0 else 0)
    return {rid: sorted(i for i, vals in per_id.items() if len(vals) > 1) for rid, per_id in values.items()
            if any(len(vals) > 1 for vals in per_id.values())}


def runs_of(indices):
    """[3, 4, 5, 9, 10] -> [(3, 5), (9, 10)] (runs of neighbouring byte positions)."""
    runs = []
    for i in indices:
        if runs and i == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], i)
        else:
            runs.append((i, i))
    return runs


def record_step(read, now, poll, say=print, baseline_s=1.5, quiet_s=2.0, no_motion_s=20.0, max_s=30.0,
                max_entries=MAX_ENTRIES, strict_baseline=True):
    """Records one movement. read() returns a report (list of numbers) or an empty value after a timeout and
    raises OSError if the panel is gone. now() is a clock in seconds, poll() returns 'skip', 'abort' or None.
    Returns {"status", "baseline", "reports", "truncated"}; status is one of
    ok (ended by the 2 s quiet time), done (Enter after the movement), no_motion, max_time,
    skipped, aborted, moving_baseline (only with strict_baseline)."""
    baseline, seen = [], set()
    start = now()
    while now() - start < baseline_s:
        key = poll()
        if key:
            return {"status": "skipped" if key == "skip" else "aborted", "baseline": baseline,
                    "reports": [], "truncated": False}
        report = read()
        if report:
            text = bytes(report).hex()
            if text not in seen and len(baseline) < MAX_BASELINE:
                seen.add(text)
                baseline.append(text)
    if strict_baseline and len(baseline) > 3:
        return {"status": "moving_baseline", "baseline": baseline, "reports": [], "truncated": False}

    say("      GO")
    go = now()
    entries, last_entry, truncated = [], {}, False
    moved, last_change = False, go
    while True:
        t = now()
        key = poll()
        if key == "abort":
            status = "aborted"
            break
        if key == "skip":
            status = "done" if moved else "skipped"
            break
        if moved and t - last_change >= quiet_s:
            status = "ok"
            break
        if not moved and t - go >= no_motion_s:
            status = "no_motion"
            break
        if t - go >= max_s:
            status = "max_time"
            break
        report = read()
        if not report:
            continue
        text, rid = bytes(report).hex(), report[0]
        if text not in seen:                       # not a resting report: the element is moving, also when the
            moved, last_change = True, t           # same value comes again and again (constant speed)
        previous = last_entry.get(rid)
        if previous is not None and previous[1] == text:
            previous[2] += 1                       # same as the last report of this id: count it
            continue
        entry = [int((t - go) * 1000), text, 1]
        last_entry[rid] = entry
        if len(entries) < max_entries:
            entries.append(entry)
        else:
            truncated = True
    return {"status": status, "baseline": baseline, "reports": entries, "truncated": truncated}


def describe_step(result):
    """One line for the screen: what was recorded and which bytes changed."""
    entries = result["reports"]
    total = sum(e[2] for e in entries)
    changed = changed_bytes(result["baseline"], entries)

    def show(indices):
        return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs_of(indices))
    if changed:
        where = "; ".join(f"report {rid:02x}: bytes {show(idx)}" for rid, idx in sorted(changed.items()))
    elif entries:
        data = bytes.fromhex(entries[0][1])
        nonzero = [i for i in range(1, len(data)) if data[i]]
        where = (f"every report is identical (constant speed?), report {data[0]:02x}: non-zero bytes {show(nonzero)}"
                 if nonzero else "every report is identical and all zero")
    else:
        where = "no report received"
    extra = " (cut off, too many entries)" if result["truncated"] else ""
    return f"{total} reports in {len(entries)} entries, status {result['status']}{extra}; {where}"


def note_other_ids(store, result):
    """Remembers report ids other than the known ones (count and first example), for the status question."""
    counts = {}
    for _ms, text, count in result["reports"]:
        counts[text] = counts.get(text, 0) + count
    for text in result["baseline"]:
        counts.setdefault(text, 1)
    for text, count in counts.items():
        data = bytes.fromhex(text)
        if data and data[0] not in KNOWN_IDS:
            entry = store.setdefault(f"0x{data[0]:02x}", {"count": 0, "first": text})
            entry["count"] += count


# --------------------------------------------------------------------------
# File and device
# --------------------------------------------------------------------------
def save(data):
    OUT_FILE.parent.mkdir(exist_ok=True)
    temp = OUT_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(temp, OUT_FILE)                      # a crash while writing never damages the old file


def load():
    if OUT_FILE.exists():
        data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        if data.get("recorder_version") != RECORDER_VERSION:
            raise SystemExit("rotary_raw.json was written by another recorder version. Move it away and record again.")
        return data
    return {"_info": "Raw reports of the rotary elements. Written by tools/record_rotary.py, read by tools/analyze_rotary.py. "
                     "reports: [milliseconds after GO, report as hex, how many identical reports in a row].",
            "recorder_version": RECORDER_VERSION, "elements": {}, "other_report_ids": {}}


def open_panel():
    try:
        import hid
    except ImportError:
        raise SystemExit("The Python package 'hidapi' is not installed. Start the tool with the same Python as the program\n"
                         "(on the laptop for example: py -3.11 tools\\record_rotary.py).")
    profile = json.loads(PROFILE_FILE.read_text(encoding="utf-8-sig"))
    vid, pid = int(profile["device"]["vid"], 0), int(profile["device"]["pid"], 0)
    interface = int(profile["device"]["hid_interface"])
    path = next((d["path"] for d in hid.enumerate(vid, pid) if d["interface_number"] == interface), None)
    if path is None:
        raise SystemExit("Panel (interface 2) not found. Is it connected and is Resolve running?")
    dev = hid.device()
    dev.open_path(path)
    return dev


def drain(dev, limit=20000):
    """Throws away reports that piled up while nobody was reading."""
    for _ in range(limit):
        if not dev.read(64, 20):
            return


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="record_rotary.py", description="Record the raw reports of knobs, trackballs and rings.")
    parser.add_argument("--redo", nargs="+", metavar="KIND_OR_NAME",
                        help="record these again: a kind (knob, trackball, ring) or element names; old entries are backed up first")
    return parser.parse_args(argv)


def select_redo(elements, data, wanted):
    """Which recorded elements are removed for --redo. Returns (names to remove, unknown words)."""
    kinds = {kind for _name, kind in elements}
    names = {name for name, _kind in elements}
    unknown = [w for w in wanted if w not in kinds and w not in names]
    remove = [name for name, kind in elements if (name in wanted or kind in wanted) and name in data["elements"]]
    return remove, unknown


def main(argv=None):
    args = parse_args(argv)
    if not LIST_FILE.exists():
        raise SystemExit(f"{LIST_FILE} is missing.")
    names = [line.strip() for line in LIST_FILE.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    elements = []
    for name in names:
        kind = element_kind(name)
        if kind is None:
            raise SystemExit(f"knobs_list.txt: cannot classify '{name}' (expected *_knob, *_trackball or *_ring)")
        elements.append((name, kind))
    total_steps = sum(len(GESTURES[kind]) for _name, kind in elements)

    data = load()
    if args.redo:
        remove, unknown = select_redo(elements, data, args.redo)
        if unknown:
            raise SystemExit(f"--redo: unknown name or kind: {', '.join(unknown)}. Kinds: knob, trackball, ring. "
                             f"Names: see tools\\knobs_list.txt")
        if remove:
            backup = OUT_FILE.with_name(f"rotary_raw.{time.strftime('%Y%m%d_%H%M%S')}.bak.json")
            shutil.copy2(OUT_FILE, backup)
            for name in remove:
                del data["elements"][name]
            save(data)
            print(f"--redo: {len(remove)} element(s) removed from the recording, old file saved as {backup.name}")
        else:
            print("--redo: nothing to remove (these elements are not in the recording yet), recording them now.")
    done = len([n for n, _k in elements if n in data["elements"]])
    print(f"{len(elements)} elements, {total_steps} steps. {done} elements already recorded, skipping them.")
    print("Resolve must be running (test project). Enter ends a step early or skips it, q stops everything.")
    dev = open_panel()
    step_number = 0
    try:
        for name, kind in elements:
            gestures = GESTURES[kind]
            if name in data["elements"]:
                step_number += len(gestures)
                continue
            steps = {}
            for gesture, text in gestures:
                step_number += 1
                attempts = 0
                while True:
                    attempts += 1
                    print(f"\n>>> [{step_number}/{total_steps}] {name}, {gesture}: {text}")
                    print("      Hands off for a moment ...")
                    drain(dev)
                    result = record_step(lambda: dev.read(64, 50), time.monotonic, poll_key,
                                         strict_baseline=attempts < 3)
                    status = result["status"]
                    if status == "aborted":
                        raise KeyboardInterrupt
                    if status == "moving_baseline":
                        print("      The element moved during the wait. Please keep your hands off until GO. Trying again.")
                        continue
                    if status == "no_motion":
                        print("      No movement seen.")
                        answer = input("      Enter = try again, s = skip this step: ").strip().lower()
                        if answer == "s":
                            result["status"] = "skipped"
                            break
                        continue
                    break
                print("      " + describe_step(result))
                if len(result["baseline"]) > 3:
                    print("      Note: the resting reports were not steady, the analysis may be less clear.")
                note_other_ids(data["other_report_ids"], result)
                steps[gesture] = result
                time.sleep(1.5)
            data["elements"][name] = {"kind": kind, "steps": steps}
            save(data)
            print(f"   {name} saved.")
    except KeyboardInterrupt:
        print("\nStopped. Finished elements are saved, the interrupted one is not.")
    except OSError as e:
        print(f"\nConnection to the panel lost ({type(e).__name__}). Finished elements are saved.")
    finally:
        try:
            dev.close()
        except Exception:  # noqa: BLE001
            pass
    others = data["other_report_ids"]
    if others:
        print("Report ids other than 02, 05 and 06 seen: " + ", ".join(f"{k} ({v['count']}x)" for k, v in sorted(others.items())))
    else:
        print("No report ids other than 02, 05 and 06 were seen.")
    print(f"{len([n for n, _k in elements if n in data['elements']])} of {len(elements)} elements in {OUT_FILE.name}. "
          f"Next: python tools\\analyze_rotary.py")


if __name__ == "__main__":
    main()
