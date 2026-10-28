"""Device profile (hardware facts): turning the profile data into a Profile, and the binding names. Standard library only.
No file access here: reading the file is done by the caller (load_profile). The rules for the file itself
(types, ranges, overlaps, duplicates, free bindings) are checked by tests (tests/profile_rules.py), not at run time (B9)."""
from dataclasses import dataclass, field

MODS = {"shift_up", "shift_down"}
PROFILE_VERSION = 2           # the only device profile format this program understands
BUTTON_TYPES = {"button", "knob_press"}               # have a position (byte, bit) in the button report; all other types have 'channels'
OPPOSITE_DIRECTION = {"right": "left", "left": "right", "up": "down", "down": "up"}


@dataclass(frozen=True)
class Channel:
    """One number in a motion report: a signed little-endian delta (the change since the previous report)."""
    axis: str        # 'turn' (knob, ring), 'x' or 'y' (trackball)
    report: int      # report id
    byte: int        # position of the first byte in the report
    width: int       # bits: 8, 16, 24 or 32
    positive: str    # direction in which the value is positive: right/left (turn, x) or up/down (y)

    def sign_for(self, direction):
        """+1 if this direction gives positive values, -1 if the opposite direction does, None if not on this axis."""
        if direction == self.positive:
            return 1
        if direction == OPPOSITE_DIRECTION.get(self.positive):
            return -1
        return None


@dataclass
class Profile:
    name: str
    vid: int
    pid: int
    usage_page: int
    report_id: int
    buttons: dict          # control name -> (byte, bit) in the button report
    free_bindings: list    # bindings without a native Resolve function
    rotary_channels: dict = field(default_factory=dict)   # control name -> (control type, tuple of Channel)


def valid_binding_name(key, button_names):
    parts = key.split("+")
    if len(parts) == 1:
        return parts[0] in button_names and parts[0] not in MODS
    if len(parts) == 2:
        return (parts[0] in MODS and parts[1] in button_names
                and parts[1] not in MODS)
    return False


def _int_field(value, label, errors, low, high):
    """Whole number from an int or a text such as '0x1EDB'. Appends to errors and returns None if invalid."""
    try:
        number = int(value, 0) if isinstance(value, str) else value
        if isinstance(number, bool) or not isinstance(number, int) or not low <= number <= high:
            raise ValueError
        return number
    except ValueError:
        errors.append(f"{label} must be a whole number from {low} to {high} (text like \"0x1EDB\" is allowed)")
        return None


def parse_profile(data):
    """Profile data -> (profile, []) or (None, list of error texts). Only the file shape, the version and the
    device numbers are checked here; the rest of the file is checked by tests (B9)."""
    if not isinstance(data, dict):
        return None, ["the file must contain a JSON object"]
    if data.get("profile_version") != PROFILE_VERSION:
        return None, [f"profile_version must be {PROFILE_VERSION}, found {data.get('profile_version')!r}"]
    errors = []
    device, reports = data["device"], data["reports"]
    vid = _int_field(device.get("vid"), "device.vid", errors, 0, 0xFFFF)
    pid = _int_field(device.get("pid"), "device.pid", errors, 0, 0xFFFF)
    usage_page = _int_field(device.get("hid_usage_page"), "device.hid_usage_page", errors, 0, 0xFFFF)
    report_id = _int_field(reports.get("buttons"), "reports.buttons", errors, 0, 255)
    if vid is None or pid is None or usage_page is None or report_id is None:
        return None, errors

    buttons, rotary_channels = {}, {}
    for c in data["controls"]:
        if c["type"] in BUTTON_TYPES:
            buttons[c["name"]] = (c["byte"], c["bit"])
        else:
            rotary_channels[c["name"]] = (c["type"], tuple(
                Channel(ch["axis"], ch["report"], ch["byte"], ch["width"], ch["positive"]) for ch in c["channels"]))
    return Profile(str(device.get("name", "unknown device")), vid, pid, usage_page, report_id,
                   buttons, list(data["free_bindings"]), rotary_channels), []