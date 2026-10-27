"""Generate docs/BUTTONS.md from devices/micro_color_panel.json (development tool, not part of the program).

Lists every control of the panel with its report position, whether it can be bound, and which of its
combinations (plain, shift_up, shift_down) have no native Resolve function. tests/test_buttons_doc.py fails if the
committed docs/BUTTONS.md differs from what this tool writes, so run it after every change of the profile.

Start (from the project folder): python tools\\build_buttons_doc.py
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TARGET = BASE / "docs" / "BUTTONS.md"

BUTTON_TYPES = ("button", "knob_press")                  # a position (byte, bit) in the button report
MODIFIERS = ("shift_up", "shift_down")
TYPE_WORDS = {"button": "button", "knob_press": "knob press", "knob_turn": "knob turn",
              "trackball": "trackball", "ring": "ring"}


def free_combinations(name, free):
    """Which of 'plain', 'shift_up', 'shift_down' have no native Resolve function for this button."""
    combos = (("plain", name), ("shift_up", f"shift_up+{name}"), ("shift_down", f"shift_down+{name}"))
    return ", ".join(label for label, binding in combos if binding in free) or "-"


def render_buttons_md(data):
    """The text of docs/BUTTONS.md. data: the content of the device profile file (already checked by parse_profile)."""
    free = set(data["free_bindings"])
    controls = data["controls"]
    pressed = [c for c in controls if c["type"] in BUTTON_TYPES]
    rotary = [c for c in controls if c["type"] not in BUTTON_TYPES]
    report = data["reports"]["buttons"]
    report = int(report, 0) if isinstance(report, str) else report

    lines = ["# Controls of the Micro Color Panel", "",
             "Generated from devices/micro_color_panel.json by tools/build_buttons_doc.py. Do not edit by hand.", "",
             f"{len(pressed)} buttons and knob presses (decoded, bindable except the two shift keys), "
             f"{len(rotary)} rotary elements (decoded, not bindable yet), {len(free)} free bindings.", "",
             f"## Buttons and knob presses (report {report:#04x})", "",
             "| Name | Type | Byte | Bit | Bindable | Free combinations |", "|---|---|---|---|---|---|"]
    for c in pressed:
        bindable = "modifier only" if c["name"] in MODIFIERS else "yes"
        lines.append(f"| {c['name']} | {TYPE_WORDS[c['type']]} | {c['byte']} | {c['bit']} | {bindable} | "
                     f"{free_combinations(c['name'], free)} |")
    lines += ["", "## Knobs, trackballs and rings", "",
              "| Name | Type | Axis | Report | Byte | Width | Positive | Bindable |", "|---|---|---|---|---|---|---|---|"]
    for c in rotary:
        for ch in c["channels"]:
            lines.append(f"| {c['name']} | {TYPE_WORDS[c['type']]} | {ch['axis']} | {ch['report']:#04x} | {ch['byte']} | "
                         f"{ch['width']} bit | {ch['positive']} | not yet |")
    return "\n".join(lines) + "\n"


def main():
    sys.path.insert(0, str(BASE))                         # so that `python tools\\build_buttons_doc.py` finds micropanel
    from micropanel.config import PROFILE_PATH, load_profile, read_json
    profile, errors = load_profile()
    if profile is None or errors:
        raise SystemExit("The device profile is invalid, nothing written: " + "; ".join(errors))
    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(render_buttons_md(read_json(PROFILE_PATH)), encoding="utf-8", newline="\n")
    print(f"Written: docs\\{TARGET.name}")


if __name__ == "__main__":
    main()
