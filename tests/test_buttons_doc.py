"""docs/BUTTONS.md is generated from the device profile by tools/build_buttons_doc.py (dev only).
The generator gets the content of devices/micro_color_panel.json (a profile that parse_profile accepted).
Expected texts are written by hand. The generator is loaded from its file, because tools/ is not a package."""
import importlib.util

import pytest

from micropanel import BASE
from micropanel.config import PROFILE_PATH, read_json
from micropanel.profile import parse_profile


@pytest.fixture(scope="module")
def render():
    path = BASE / "tools" / "build_buttons_doc.py"
    spec = importlib.util.spec_from_file_location("build_buttons_doc", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render_buttons_md


def small_profile_data():
    """A tiny profile: 6 buttons and knob presses, 3 rotary elements, 3 free bindings."""
    def button(name, byte, bit, kind="button"):
        return {"name": name, "type": kind, "byte": byte, "bit": bit}

    data = {
        "profile_version": 2,
        "device": {"name": "Test panel", "vid": "0x1EDB", "pid": "0xDA0F", "hid_usage_page": "0xFF00"},
        "reports": {"buttons": "0x02"},
        "controls": [
            button("undo", 3, 0), button("delete", 3, 2), button("user", 3, 6),
            button("shift_up", 4, 0), button("shift_down", 4, 1),
            button("ylift_knob_press", 1, 0, "knob_press"),
            {"name": "ylift_knob_turn", "type": "knob_turn",
             "channels": [{"axis": "turn", "report": 6, "byte": 1, "width": 32, "positive": "right"}]},
            {"name": "lift_trackball", "type": "trackball",
             "channels": [{"axis": "x", "report": 5, "byte": 2, "width": 24, "positive": "left"},
                          {"axis": "y", "report": 5, "byte": 6, "width": 24, "positive": "down"}]},
            {"name": "lift_ring", "type": "ring",
             "channels": [{"axis": "turn", "report": 5, "byte": 10, "width": 24, "positive": "right"}]},
        ],
        "free_bindings": ["user", "shift_up+user", "shift_down+undo"],
    }
    profile, errors = parse_profile(data)
    assert errors == [] and profile is not None, errors      # the test data is itself a valid profile
    return data


def rows(render):
    return render(small_profile_data()).splitlines()


def test_summary_line_counts_the_controls(render):
    assert ("6 buttons and knob presses (decoded, bindable except the two shift keys), "
            "3 rotary elements (4 channels, decoded, not bindable yet), 3 free bindings.") in rows(render)


@pytest.mark.parametrize("row", [
    "| user | button | 3 | 6 | yes | plain, shift_up |",
    "| undo | button | 3 | 0 | yes | shift_down |",
    "| delete | button | 3 | 2 | yes | - |",
    "| shift_up | button | 4 | 0 | modifier only | - |",
    "| ylift_knob_press | knob press | 1 | 0 | yes | - |",
], ids=["free_plain_and_shift_up", "free_shift_down", "nothing_free", "shift_up_key", "knob_press"])
def test_button_rows(render, row):
    assert row in rows(render)


def test_trackball_gives_one_row_per_axis(render):
    lines = rows(render)
    assert "| lift_trackball | trackball | x | 0x05 | 2 | 24 bit | left | not yet |" in lines
    assert "| lift_trackball | trackball | y | 0x05 | 6 | 24 bit | down | not yet |" in lines


def test_knob_turn_row_uses_the_word_knob_turn(render):               # the one type word that differs from the profile type
    assert "| ylift_knob_turn | knob turn | turn | 0x06 | 1 | 32 bit | right | not yet |" in rows(render)


def test_committed_doc_is_up_to_date(render):
    committed = (BASE / "docs" / "BUTTONS.md").read_text(encoding="utf-8")
    assert committed == render(read_json(PROFILE_PATH)), "docs/BUTTONS.md is out of date: run python tools\\build_buttons_doc.py"
