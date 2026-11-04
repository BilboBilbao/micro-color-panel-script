"""The shipped device profile (devices/micro_color_panel.json) as the program loads it. Expected values are written by hand
from docs/HARDWARE.md. The file is developer-owned data: these tests pin it, there is no run-time validation (B9)."""
import json

import micropanel.config as cfg
from micropanel.profile import parse_profile, valid_binding_name


def raw_profile():
    return json.loads(cfg.PROFILE_PATH.read_text(encoding="utf-8-sig"))


def test_shipped_profile_is_valid(profile):
    assert (profile.vid, profile.pid, profile.usage_page, profile.report_id) == (0x1EDB, 0xDA0F, 0xFF00, 2)
    assert len(profile.buttons) == 52
    assert {"shift_up", "shift_down"} <= set(profile.buttons)
    assert len(profile.rotary_channels) == 18
    assert len(profile.free_bindings) == 55 and len(set(profile.free_bindings)) == 55
    assert all(valid_binding_name(name, set(profile.buttons)) for name in profile.free_bindings)


def test_rotary_channels_follow_the_documented_report_layout(profile):
    layout = {}
    for _name, (_ctype, channels) in profile.rotary_channels.items():
        for c in channels:
            layout.setdefault(c.report, []).append((c.byte, c.width))
    assert {report: sorted(spans) for report, spans in layout.items()} == {
        6: [(1 + 4 * k, 32) for k in range(12)],     # 12 knobs, 32 bit
        5: [(2 + 4 * k, 24) for k in range(9)],      # 3 trackballs (x, y) and 3 rings, 24 bit
    }


def test_bool_is_rejected_as_number():
    data = raw_profile()
    data["reports"]["buttons"] = True
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