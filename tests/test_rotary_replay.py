"""Rotary reports. Expected values are written by hand from what was done during the recording
(tests/data/rotary_vectors.json, taken from recordings/rotary_raw.json), never computed from the profile."""
import pytest

from micropanel.decoder import decode_rotary, make_rotary_lookup
from helpers import load_json, motion_report

VECTORS = load_json("rotary_vectors.json")["elements"]

# element -> (control name, axis) and the sign of the value for each recorded direction, read by hand from the recordings:
# knobs and rings: right is positive; trackballs: right is negative x, left positive x, up negative y, down positive y.
EXPECTED = {}
for _el in VECTORS:
    if _el.endswith("_knob"):
        EXPECTED[_el] = (_el + "_turn", {"right": ("turn", +1), "left": ("turn", -1)})
    elif _el.endswith("_ring"):
        EXPECTED[_el] = (_el, {"right": ("turn", +1), "left": ("turn", -1)})
    else:
        EXPECTED[_el] = (_el, {"right": ("x", -1), "left": ("x", +1), "up": ("y", -1), "down": ("y", +1)})


def padded(hex_text):
    return bytes.fromhex(hex_text).ljust(64, b"\x00")


def decode(report, profile):
    return decode_rotary(report, make_rotary_lookup(profile))


def test_knob_right_is_positive(profile):
    report = bytes.fromhex("06" "48120000").ljust(64, b"\x00")          # ylift_knob, right: 0x00001248
    assert [v for n, a, v in decode(report, profile) if n == "ylift_knob_turn"] == [4680]


def test_knob_left_is_negative(profile):
    report = bytes.fromhex("06" "48e5ffff").ljust(64, b"\x00")          # ylift_knob, left: 0xFFFFE548
    assert [v for n, a, v in decode(report, profile) if n == "ylift_knob_turn"] == [-6840]


def test_trackball_right_is_negative_x(profile):
    report = bytes.fromhex("05" "00" "d0ffff").ljust(64, b"\x00")       # lift_trackball, right: x = 0xFFFFD0
    assert [v for n, a, v in decode(report, profile) if (n, a) == ("lift_trackball", "x")] == [-48]


def test_foreign_report_id_gives_nothing(profile):
    assert decode(padded("07" + "ff" * 63), profile) == []


@pytest.mark.parametrize("element,step", [(e, s) for e, steps in sorted(VECTORS.items()) for s in sorted(steps)])
def test_recorded_step_moves_the_right_channel_in_the_right_direction(profile, element, step):
    control, directions = EXPECTED[element]
    axis, sign = directions[step]
    totals = {}
    for hex_text, count in VECTORS[element][step]:
        for name, ax, value in decode(padded(hex_text), profile):
            totals[(name, ax)] = totals.get((name, ax), 0) + count * value
    strongest = max(totals, key=lambda key: abs(totals[key]))
    assert strongest == (control, axis)
    assert totals[strongest] * sign > 0


@pytest.mark.parametrize("element,step", [(e, s) for e, steps in sorted(VECTORS.items()) for s in sorted(steps)])
def test_profile_direction_word_matches_the_recording(profile, element, step):
    """The profile says in which direction a channel is positive ('positive'). The recording says what the
    sign was when the element was turned that way (hand table EXPECTED)."""
    control, directions = EXPECTED[element]
    axis, sign = directions[step]
    channels = {c.axis: c for c in profile.rotary_channels[control][1]}
    assert channels[axis].sign_for(step) == sign


def test_knob_report_gives_12_channels_with_only_the_moved_one_nonzero(profile):
    got = decode(motion_report(6, {9: (32, -3600)}), profile)
    assert len(got) == 12
    assert ("ygain_knob_turn", "turn", -3600) in got
    assert sum(1 for _name, _axis, value in got if value) == 1


def test_trackball_report_gives_9_channels(profile):
    got = decode(motion_report(5, {2: (24, -16), 6: (24, 112), 10: (24, 16), 34: (24, -16)}), profile)
    found = {(name, axis): value for name, axis, value in got}
    assert len(got) == 9
    assert found[("lift_trackball", "x")] == -16 and found[("lift_trackball", "y")] == 112
    assert found[("lift_ring", "turn")] == 16 and found[("gain_ring", "turn")] == -16
    assert found[("gamma_ring", "turn")] == 0


def test_24_bit_channel_ignores_the_next_byte(profile):
    report = bytearray(motion_report(5, {2: (24, 5)}))
    report[5] = 0xFF                                                   # the 4th byte does not belong to a 24 bit channel
    found = {(name, axis): value for name, axis, value in decode(bytes(report), profile)}
    assert found[("lift_trackball", "x")] == 5


def test_large_positive_32_bit_value(profile):
    assert ("ylift_knob_turn", "turn", 2_000_000) in decode(motion_report(6, {1: (32, 2_000_000)}), profile)


def test_short_report_gives_only_channels_that_fit(profile):
    got = decode(motion_report(6, {1: (32, 7)})[:20], profile)
    assert len(got) == 4
    assert ("ylift_knob_turn", "turn", 7) in got


@pytest.mark.parametrize("report", [motion_report(2, {}), b"", None], ids=["button_report", "empty", "none"])
def test_non_motion_input_gives_empty_list(profile, report):
    assert decode(report, profile) == []