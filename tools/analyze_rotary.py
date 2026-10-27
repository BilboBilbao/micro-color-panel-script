"""Analyze the rotary recording -> prints a report and writes ../reports/rotary_analysis.txt

Reads recordings/rotary_raw.json (made by tools/record_rotary.py). Nothing is sent to the panel, nothing is changed
in the device profile: the result is for you and Claude to read; the profile entries are a separate step.

For every element and report id the tool looks for the bytes that change (a report id without resting reports
counts as resting at all zero, bytes that never change anywhere in the file are ignored), groups neighbouring
bytes into one channel, widens a channel over the sign-extension bytes (a negative 32 bit number ends in ff ff),
reads each channel as a signed little-endian number and shows per movement: how many different values, the
smallest and largest value, the sum of all values (a delta channel adds up to the distance moved), the change
between the resting value and the last value, and a hint "delta" or "absolute". The hint is a HYPOTHESIS.
The channel with the largest sum in a movement is marked (main). At the end of every element a suggestion for the
device profile is printed (channel, width, which direction is positive).

Start (from the project folder): python tools\\analyze_rotary.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_rotary import changed_bytes, runs_of, GESTURES  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
RAW_FILE = BASE / "recordings" / "rotary_raw.json"
OUT_FILE = BASE / "reports" / "rotary_analysis.txt"

# Known layout (docs/HARDWARE.md), used only for the final comparison: report id -> (start bytes, width in bit)
KNOWN_LAYOUT = {0x05: ([2 + 4 * i for i in range(9)], 24), 0x06: ([1 + 4 * i for i in range(12)], 32)}
PAIRS = (("right", "left"), ("up", "down"))
PLUS_WORD = {"right": "right", "left": "left", "up": "up", "down": "down"}


def decode(data, a, b):
    """Signed little-endian number from the bytes a..b of a report, or None if the report is too short."""
    if len(data) <= b:
        return None
    return int.from_bytes(data[a:b + 1], "little", signed=True)


def global_constants(raw):
    """{report id: set of byte positions that have the same value in every report of the whole file}."""
    seen = {}
    for element in raw.get("elements", {}).values():
        for step in element["steps"].values():
            for text in list(step["baseline"]) + [e[1] for e in step["reports"]]:
                data = bytes.fromhex(text)
                if data:
                    per_id = seen.setdefault(data[0], {})
                    for i, v in enumerate(data):
                        per_id.setdefault(i, set()).add(v)
    return {rid: {i for i, vals in per_id.items() if len(vals) == 1} for rid, per_id in seen.items()}


def widen(datas, a, b):
    """Extends the run a..b to the right over sign-extension bytes (up to 4 bytes in total).
    The next byte belongs to the number if it is only ever 00 or ff, ff occurs, and ff never occurs unless the top
    bit of the byte before is set (the sign). Nothing else is guessed."""
    while b - a + 1 < 4:
        p = b + 1
        values = {d[p] for d in datas if len(d) > p}
        if not values or not values <= {0x00, 0xFF} or 0xFF not in values:
            break
        if any(d[p] == 0xFF and not d[b] & 0x80 for d in datas if len(d) > p):
            break
        b = p
    return a, b


def step_stats(step, rid, a, b):
    """Numbers of one channel in one step, or None if the step has no report of this id."""
    entries = []
    for _ms, text, count in step["reports"]:
        data = bytes.fromhex(text)
        if data and data[0] == rid:
            value = decode(data, a, b)
            if value is not None:
                entries.append((value, count))
    if not entries:
        return None
    base = None
    for text in step["baseline"]:
        data = bytes.fromhex(text)
        if data and data[0] == rid:
            base = decode(data, a, b)
    values = [v for v, _c in entries]
    start = base if base is not None else 0
    rising = all(x <= y for x, y in zip(values, values[1:]))
    falling = all(x >= y for x, y in zip(values, values[1:]))
    moved = changed_bytes(step["baseline"], step["reports"], zero_rest=True).get(rid, [])
    net = sum(v * c for v, c in entries)
    hint = "absolute" if (rising or falling) and values[-1] != start and len(set(values)) > 1 else "delta"
    return {"entries": len(entries), "reports": sum(c for _v, c in entries), "distinct": len(set(values)),
            "min": min(values), "max": max(values), "net": net, "change": values[-1] - start,
            "base_known": base is not None, "hint": hint,
            "size": abs(net if hint == "delta" else values[-1] - start),
            "active": any(a <= i <= b for i in moved)}


def sign(number):
    return "+" if number > 0 else "-" if number < 0 else "0"


def element_channels(element, constants):
    """[(report id, a, b)] of one element: changed bytes of all evaluated steps, constants removed, widened."""
    used = [s for s in element["steps"].values() if s["status"] in ("ok", "done", "max_time")]
    union, datas = {}, {}
    for step in used:
        for rid, indices in changed_bytes(step["baseline"], step["reports"], zero_rest=True).items():
            union.setdefault(rid, set()).update(i for i in indices if i not in constants.get(rid, ()))
        for text in list(step["baseline"]) + [e[1] for e in step["reports"]]:
            data = bytes.fromhex(text)
            if data:
                datas.setdefault(data[0], []).append(data)
    channels = []
    for rid in sorted(union):
        for a, b in runs_of(sorted(union[rid])):
            a, b = widen(datas.get(rid, []), a, b)
            channels.append((rid, a, b))
    return channels


def analyze(raw):
    """Returns the report as a list of lines."""
    lines, found = [], {}
    elements = raw.get("elements", {})
    constants = global_constants(raw)
    lines.append(f"Rotary analysis: {len(elements)} element(s) in the recording")
    lines.append("The hints 'delta' / 'absolute' are hypotheses, not facts. Numbers are signed little-endian.")
    for rid, positions in sorted(constants.items()):
        fixed = [i for i in sorted(positions) if i]
        if fixed:
            lines.append(f"Bytes that never change in report {rid:02x} (ignored): {', '.join(str(i) for i in fixed)}")
    for name, element in elements.items():
        steps = element["steps"]
        lines += ["", f"{name} ({element['kind']})"]
        used = {g: s for g, s in steps.items() if s["status"] in ("ok", "done", "max_time")}
        for gesture in steps:
            if gesture not in used:
                lines.append(f"  step {gesture}: status {steps[gesture]['status']}, not evaluated")
        channels = element_channels(element, constants)
        if not channels:
            lines.append("  no byte changed in any evaluated step (movement not seen, or the panel sent nothing)")
            continue
        stats = {ch: {g: step_stats(s, *ch) for g, s in used.items()} for ch in channels}
        main = {}                                   # gesture -> channel with the largest movement
        for g in used:
            sized = []
            for ch in channels:
                stat = stats[ch][g]
                if stat is not None:
                    sized.append((stat["size"], ch))
            if sized:
                main[g] = max(sized)[1]
        for ch in channels:
            rid, a, b = ch
            lines.append(f"  report {rid:02x}, bytes {a}-{b} ({(b - a + 1) * 8} bit)")
            active_in = []
            for g in used:
                st = stats[ch][g]
                if st is None:
                    continue
                if st["active"]:
                    active_in.append(g)
                rest = "" if st["base_known"] else ", rest assumed 0"
                lines.append(f"    {g:<5}{' (main)' if main.get(g) == ch else '       '} {st['reports']} reports in {st['entries']} entries, "
                             f"{st['distinct']} different values, {st['min']:+d}..{st['max']:+d}, sum {st['net']:+d}, "
                             f"hint {st['hint']}{rest}")
            found.setdefault(ch, []).append((name, active_in))
        for first, second in PAIRS:
            if first in main and second in main and main[first] == main[second]:
                ch = main[first]
                s1, s2 = stats[ch][first], stats[ch][second]
                assert s1 is not None and s2 is not None   # main[...] only names channels that have numbers in this step
                key = "net" if s1["hint"] == "delta" else "change"
                v1, v2 = s1[key], s2[key]
                verdict = "opposite signs, as expected" if v1 * v2 < 0 else "NOT opposite signs, check by hand"
                lines.append(f"  direction (report {ch[0]:02x} bytes {ch[1]}-{ch[2]}): {first} {sign(v1)}, {second} {sign(v2)} ({verdict})")
                if v1 * v2 < 0:
                    plus = first if v1 > 0 else second
                    lines.append(f"  => suggestion: report {ch[0]:02x}, byte {ch[1]}, {(ch[2] - ch[1] + 1) * 8} bit, positive = {PLUS_WORD[plus]}")
        if not any(main.get(a) == main.get(b) and a in main for a, b in PAIRS):
            lines.append("  (no suggestion: right/left or up/down did not move the same channel)")

    lines += ["", "Channels found (report id, bytes, width): elements and steps in which they were active"]
    if not found:
        lines.append("  none")
    for (rid, a, b), users in sorted(found.items()):
        text = "; ".join(f"{n} [{', '.join(s) or 'quiet'}]" for n, s in users)
        lines.append(f"  report {rid:02x} bytes {a}-{b} ({(b - a + 1) * 8} bit): {text}")

    problems = []
    for (rid, a, b), users in sorted(found.items()):
        movers = sorted({n for n, steps in users if steps})
        if len(movers) > 1:
            problems.append(f"report {rid:02x} bytes {a}-{b} moves with several elements: {', '.join(movers)}")
    ordered = sorted(found)
    for i, (rid1, a1, b1) in enumerate(ordered):
        for rid2, a2, b2 in ordered[i + 1:]:
            if rid1 == rid2 and a2 <= b1:
                problems.append(f"report {rid1:02x}: bytes {a1}-{b1} and {a2}-{b2} overlap "
                                f"(the same channel seen with different widths, or two channels too close together)")
    lines += ["", "Things to check: " + ("none" if not problems else "")]
    lines += [f"  CHECK: {p}" for p in problems]

    lines += ["", "Check against the known layout (docs/HARDWARE.md)"]
    for rid, (starts, width) in sorted(KNOWN_LAYOUT.items()):
        seen = sorted({(a, (b - a + 1) * 8) for (r, a, b) in found if r == rid})
        found_starts = [a for a, _w in seen]
        widths = sorted({w for _a, w in seen})
        missing = [s for s in starts if s not in found_starts]
        extra = [s for s in found_starts if s not in starts]
        lines.append(f"  report {rid:02x}: expected {len(starts)} channels at {starts}, {width} bit; found start bytes {found_starts}, "
                     f"widths {widths} bit; missing {missing or 'none'}, unexpected {extra or 'none'}")

    others = {k: v for k, v in raw.get("other_report_ids", {}).items() if int(k, 16) not in (0x02, 0x05, 0x06)}
    lines += ["", "Report ids other than 02, 05 and 06: " + ("none seen" if not others else "")]
    lines += [f"  {k}: {v['count']} reports, first: {v['first']}" for k, v in sorted(others.items())]
    expected_steps = sum(len(GESTURES[e["kind"]]) for e in elements.values())
    got = sum(len(e["steps"]) for e in elements.values())
    lines += ["", f"Steps in the file: {got} (expected {expected_steps} for the recorded elements)"]
    return lines


def main():
    if not RAW_FILE.exists():
        raise SystemExit("recordings\\rotary_raw.json not found Record first: python tools\\record_rotary.py")
    try:
        OUT_FILE.parent.mkdir(exist_ok=True)
        raw = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"rotary_raw.json cannot be read: {e}")
    lines = analyze(raw)
    print("\n".join(lines))
    try:
        OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nWritten: reports\\{OUT_FILE.name}   ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    except OSError as e:
        print(f"\nReport file could not be written ({type(e).__name__})")


if __name__ == "__main__":
    main()
