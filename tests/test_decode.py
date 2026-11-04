"""Button reports, decoded with the shipped profile and compared with the recording tests/data/buttons.json."""
import pytest

from micropanel.decoder import decode_held, make_lookup
from helpers import BUTTON_REPORT_ID, load_json, recorded_report

RECORDED = sorted(load_json("buttons.json"))


def test_every_recorded_button_decodes_to_its_own_name(profile):
    assert len(RECORDED) == 52
    lookup, min_length = make_lookup(profile)
    wrong = {}
    for name in RECORDED:
        held = decode_held(recorded_report(name), lookup, BUTTON_REPORT_ID, min_length)
        if held != {name}:
            wrong[name] = held
    assert wrong == {}                    # one failure lists every control that decodes wrongly


@pytest.mark.parametrize("report", [None, [], [5] + [0] * 63, [2, 0, 0]], ids=["none", "empty", "other_id", "too_short"])
def test_short_or_foreign_report_is_ignored(profile, report):
    lookup, min_length = make_lookup(profile)
    assert decode_held(report, lookup, BUTTON_REPORT_ID, min_length) is None