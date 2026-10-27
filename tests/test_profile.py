"""The shipped device profile (devices/micro_color_panel.json) as the program loads it. Expected values are written by hand
from docs/HARDWARE.md. The rules for the file itself are in test_profile_rules.py (B9)."""
import json

import pytest

import micropanel.config as cfg
from micropanel.profile import parse_profile


def raw_profile():
    return json.loads(cfg.PROFILE_PATH.read_text(encoding="utf-8-sig"))


def test_shipped_profile_is_valid(profile):
    assert (profile.vid, profile.pid, profile.interface, profile.report_id) == (0x1EDB, 0xDA0F, 2, 2)
    assert len(profile.buttons) == 52
    assert len(set(profile.buttons.values())) == 52                  # no position used twice
    assert {"shift_up", "shift_down"} <= set(profile.buttons)
    assert len(profile.rotary_channels) == 18
    assert len(profile.free_bindings) == 55 and len(set(profile.free_bindings)) == 55


def test_profile_has_no_list_of_undecoded_rotary_controls(profile):       # B9: every rotary control has channels
    assert not hasattr(profile, "rotary")


def test_rotary_channels_sit_in_the_right_reports(profile):
    for name, (ctype, channels) in profile.rotary_channels.items():
        expected_report = 6 if ctype == "knob_turn" else 5
        assert {c.report for c in channels} == {expected_report}, name


@pytest.mark.parametrize("path,value", [(("device", "vid"), True), (("reports", "buttons"), True)],
                         ids=["bool_vid", "bool_report_id"])
def test_bool_is_rejected_as_number(path, value):
    data = raw_profile()
    data[path[0]][path[1]] = value
    loaded, errors = parse_profile(data)
    assert loaded is None and errors


def test_unknown_profile_version_rejected():                          # B3
    data = raw_profile()
    data["profile_version"] = 3
    loaded, errors = parse_profile(data)
    assert loaded is None
    assert any("profile_version" in e for e in errors)


def test_missing_profile_file_gives_an_error_text(tmp_path):
    loaded, errors = cfg.load_profile(tmp_path / "nope.json")
    assert loaded is None
    assert len(errors) == 1 and "nope.json" in errors[0]


KNOB_PRESSES = ["ylift_knob_press", "ygamma_knob_press", "ygain_knob_press", "contrast_knob_press",
                "pivot_knob_press", "mid_detail_knob_press", "color_boost_knob_press", "shadows_knob_press",
                "highlights_knob_press", "saturation_knob_press", "hue_knob_press", "lum_mix_knob_press"]


def test_shift_plus_knob_press_is_free(profile):         # live test, Resolve 21.0.4.5 Studio: no reaction
    expected = {f"{shift}+{press}" for shift in ("shift_up", "shift_down") for press in KNOB_PRESSES}
    assert len(expected) == 24
    assert expected <= set(profile.free_bindings)    