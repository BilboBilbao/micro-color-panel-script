"""Rules for the device profile file (developer-owned data). They are checked here, not at run time (B9).
profile_problems() works on the raw JSON data; the expected values are written by hand from docs/HARDWARE.md."""
import copy

import pytest

from profile_rules import profile_problems
from test_profile import raw_profile

# Byte 1 to 6 use all 8 bits, byte 7 uses bit 0 to 3: 48 + 4 = 52 positions (written by hand, not read from the profile)
EXPECTED_BIT_POSITIONS = {(byte, bit) for byte in range(1, 7) for bit in range(8)} | {(7, bit) for bit in range(4)}


def control(data, name):
    return next(c for c in data["controls"] if c["name"] == name)


def duplicate_position(d):
    first, second = d["controls"][0], d["controls"][1]
    second["byte"], second["bit"] = first["byte"], first["bit"]


def unknown_type(d):
    d["controls"][0]["type"] = "banana"


def drop_shift_up(d):
    d["controls"] = [c for c in d["controls"] if c["name"] != "shift_up"]


def bad_free_binding(d):
    d["free_bindings"].append("nonsense+name")


def bad_vid(d):
    d["device"]["vid"] = "zzz"


def bad_usage_page(d):
    d["device"]["hid_usage_page"] = "zzz"


def bad_width(d):
    control(d, "ylift_knob_turn")["channels"][0]["width"] = 20


def bad_positive(d):
    control(d, "ylift_knob_turn")["channels"][0]["positive"] = "up"


def missing_axis(d):
    control(d, "lift_trackball")["channels"] = control(d, "lift_trackball")["channels"][:1]


def axis_listed_twice(d):
    control(d, "lift_trackball")["channels"][1]["axis"] = "x"


def axis_not_allowed(d):
    control(d, "lift_ring")["channels"][0]["axis"] = "x"


def overlapping_channels(d):
    control(d, "ygamma_knob_turn")["channels"][0]["byte"] = 3


def channel_in_button_report(d):
    control(d, "ylift_knob_turn")["channels"][0]["report"] = 2


def channel_too_long(d):
    control(d, "lum_mix_knob_turn")["channels"][0]["byte"] = 62


def empty_channels(d):
    control(d, "gain_ring")["channels"] = []


def control_listed_twice(d):
    d["controls"].append(copy.deepcopy(control(d, "gain_ring")))


def wrong_profile_version(d):
    d["profile_version"] = 3


def type_is_a_list(d):
    d["controls"][0]["type"] = ["button"]            # CONS-007: a data error, not a TypeError


def rotary_without_channels(d):
    del control(d, "ylift_knob_turn")["channels"]


DEFECTS = [
    (duplicate_position, "use the same position"), (unknown_type, "unknown type"),
    (drop_shift_up, "required control 'shift_up'"), (bad_free_binding, "not a valid binding name"),
    (bad_vid, "device.vid"), (bad_usage_page, "device.hid_usage_page"), (bad_width, "width must be one of"), (bad_positive, "positive must be one of"),
    (missing_axis, "channel for axis y is missing"), (axis_listed_twice, "listed twice"),
    (axis_not_allowed, "not allowed for ring"), (overlapping_channels, "overlap"),
    (channel_in_button_report, "is the button report"), (channel_too_long, "do not fit"),
    (empty_channels, "non-empty list"), (control_listed_twice, "'gain_ring' is listed twice"),
    (wrong_profile_version, "profile_version"), (type_is_a_list, "unknown type"),
    (rotary_without_channels, "no 'channels'"),
]


def test_shipped_profile_has_no_problems():
    assert profile_problems(raw_profile()) == []


def test_shipped_profile_covers_exactly_the_52_report_bits():          # CONS-020
    positions = {(c["byte"], c["bit"]) for c in raw_profile()["controls"] if c["type"] in ("button", "knob_press")}
    assert positions == EXPECTED_BIT_POSITIONS


def test_profile_that_is_not_an_object_is_a_problem():
    assert "JSON object" in " | ".join(profile_problems([]))


@pytest.mark.parametrize("change,expected", DEFECTS, ids=[change.__name__ for change, _ in DEFECTS])
def test_profile_problems_detects(change, expected):
    data = raw_profile()
    change(data)
    assert expected in " | ".join(profile_problems(data))