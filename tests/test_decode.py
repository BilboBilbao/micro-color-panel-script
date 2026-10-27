"""Button reports, decoded with the shipped profile and compared with the recording tests/data/buttons.json."""
import pytest

from micropanel.decoder import decode_held, make_lookup
from helpers import BUTTON_REPORT_ID, load_json, recorded_report

RECORDED = sorted(load_json("buttons.json"))


def test_recording_has_52_controls():
    assert len(RECORDED) == 52


@pytest.mark.parametrize("name", RECORDED)
def test_recorded_button_decodes_to_its_own_name(profile, name):
    lookup, min_length = make_lookup(profile)
    assert decode_held(recorded_report(name), lookup, BUTTON_REPORT_ID, min_length) == {name}


@pytest.mark.parametrize("report", [None, [], [5] + [0] * 63, [2, 0, 0]], ids=["none", "empty", "other_id", "too_short"])
def test_short_or_foreign_report_is_ignored(profile, report):
    lookup, min_length = make_lookup(profile)
    assert decode_held(report, lookup, BUTTON_REPORT_ID, min_length) is None


def test_bytes_after_the_button_area_are_ignored(profile):
    lookup, min_length = make_lookup(profile)
    report = [2, 0b100] + [0] * 6 + [0xFF] * 56          # ygain_knob_press (byte 1, bit 2), junk from byte 8 on
    assert decode_held(report, lookup, BUTTON_REPORT_ID, min_length) == {"ygain_knob_press"}
