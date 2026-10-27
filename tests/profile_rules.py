"""Rules for the device profile file (developer-owned data), checked by tests, not at run time (B9).
profile_problems() works on the raw JSON data and returns a list of problem texts (empty = the file is fine).
Development only: strangers do not receive this file."""
from micropanel.profile import MODS, PROFILE_VERSION, valid_binding_name

BUTTON_TYPES = {"button", "knob_press"}                # have a position (byte, bit) in the button report
ROTARY_AXES = {"knob_turn": ("turn",), "ring": ("turn",), "trackball": ("x", "y")}
ROTARY_POSITIVE = {"turn": ("right", "left"), "x": ("right", "left"), "y": ("up", "down")}
ROTARY_WIDTHS = (8, 16, 24, 32)                        # bits of one channel


def _number(value, label, problems, low, high):
    """Whole number from an int or a text such as '0x1EDB'. Appends a problem and returns None if invalid."""
    try:
        number = int(value, 0) if isinstance(value, str) else value
        if isinstance(number, bool) or not isinstance(number, int) or not low <= number <= high:
            raise ValueError
        return number
    except ValueError:
        problems.append(f"{label} must be a whole number from {low} to {high} (text like \"0x1EDB\" is allowed)")
        return None


def _channel_problems(name, ctype, channels, button_report, problems):
    """Checks the 'channels' list of one rotary control. Returns the valid byte spans
    [(report, first byte, last byte, label)] for the overlap check."""
    axes_needed = ROTARY_AXES[ctype]
    if not isinstance(channels, list) or not channels or not all(isinstance(c, dict) for c in channels):
        problems.append(f"{name}: 'channels' must be a non-empty list of objects")
        return []
    spans, seen = [], []
    for i, c in enumerate(channels):
        label = f"{name}.channels[{i}]"
        axis = c.get("axis")
        if axis not in axes_needed:
            problems.append(f"{label}: axis {axis!r} is not allowed for {ctype} (allowed: {', '.join(axes_needed)})")
            continue
        if axis in seen:
            problems.append(f"{label}: axis '{axis}' is listed twice")
            continue
        seen.append(axis)
        report = _number(c.get("report"), f"{label}.report", problems, 0, 255)
        byte = _number(c.get("byte"), f"{label}.byte", problems, 0, 63)
        width = _number(c.get("width"), f"{label}.width", problems, 1, 64)
        positive = c.get("positive")
        if positive not in ROTARY_POSITIVE[axis]:
            problems.append(f"{label}: positive must be one of {', '.join(ROTARY_POSITIVE[axis])}, not {positive!r}")
            continue
        if report is None or byte is None or width is None:
            continue
        if width not in ROTARY_WIDTHS:
            problems.append(f"{label}: width must be one of {', '.join(str(w) for w in ROTARY_WIDTHS)} bit, not {width}")
            continue
        if byte + width // 8 > 64:
            problems.append(f"{label}: bytes {byte} to {byte + width // 8 - 1} do not fit into a 64 byte report")
            continue
        if report == button_report:
            problems.append(f"{label}: report {report:#04x} is the button report")
            continue
        spans.append((report, byte, byte + width // 8 - 1, f"{name}.{axis}"))
    missing = [a for a in axes_needed if a not in seen]
    if missing:
        problems.append(f"{name}: the channel for axis {', '.join(missing)} is missing")
    return spans


def profile_problems(data):
    """All problems found in the profile data, as texts. An empty list means the file is fine."""
    if not isinstance(data, dict):
        return ["the file must contain a JSON object"]
    problems = []
    if data.get("profile_version") != PROFILE_VERSION:
        problems.append(f"profile_version must be {PROFILE_VERSION}, found {data.get('profile_version')!r}")
    device, reports = data.get("device"), data.get("reports")
    if not isinstance(device, dict):
        device = {}
    if not isinstance(reports, dict):
        reports = {}
    _number(device.get("vid"), "device.vid", problems, 0, 0xFFFF)
    _number(device.get("pid"), "device.pid", problems, 0, 0xFFFF)
    _number(device.get("hid_interface"), "device.hid_interface", problems, 0, 255)
    button_report = _number(reports.get("buttons"), "reports.buttons", problems, 0, 255)

    names, buttons, used, spans = set(), set(), {}, []
    controls = data.get("controls")
    if not isinstance(controls, list) or not controls:
        problems.append("'controls' must be a non-empty list")
        controls = []
    for i, c in enumerate(controls):
        if not isinstance(c, dict):
            problems.append(f"controls[{i}] is not an object")
            continue
        name, ctype = c.get("name"), c.get("type")
        if not isinstance(name, str) or not name or name.startswith("_") or "+" in name:
            problems.append(f"controls[{i}]: invalid name {name!r}")
            continue
        if name in names:
            problems.append(f"control '{name}' is listed twice")
            continue
        names.add(name)
        if not isinstance(ctype, str) or (ctype not in BUTTON_TYPES and ctype not in ROTARY_AXES):
            problems.append(f"control '{name}': unknown type {ctype!r}")
        elif ctype in BUTTON_TYPES:
            byte = _number(c.get("byte"), f"{name}.byte", problems, 0, 63)
            bit = _number(c.get("bit"), f"{name}.bit", problems, 0, 7)
            if byte is None or bit is None:
                continue
            if (byte, bit) in used:
                problems.append(f"'{name}' and '{used[(byte, bit)]}' use the same position byte {byte} bit {bit}")
                continue
            used[(byte, bit)] = name
            buttons.add(name)
        elif "channels" not in c:
            problems.append(f"{name}: no 'channels' (every rotary control needs its report positions)")
        else:
            spans += _channel_problems(name, ctype, c["channels"], button_report, problems)

    for needed in sorted(MODS):
        if needed not in buttons:
            problems.append(f"required control '{needed}' is missing")

    spans.sort()
    for (r1, a1, b1, n1), (r2, a2, _b2, n2) in zip(spans, spans[1:]):
        if r1 == r2 and a2 <= b1:
            problems.append(f"'{n1}' and '{n2}' overlap in report {r1:#04x} (bytes {a1}-{b1} and {a2}-...)")

    free = data.get("free_bindings")
    if not isinstance(free, list) or not all(isinstance(n, str) for n in free):
        problems.append("'free_bindings' must be a list of names")
    else:
        problems += [f"free_bindings: '{n}' is not a valid binding name" for n in free
                     if not valid_binding_name(n, buttons)]
    return problems