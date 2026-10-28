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


def test_title_and_generated_notice_come_first(render):
    lines = rows(render)
    assert lines[0] == "# Controls of the Micro Color Panel"
    assert lines[2] == "Generated from devices/micro_color_panel.json by tools/build_buttons_doc.py. Do not edit by hand."


def test_summary_line_counts_the_controls(render):
    assert ("6 buttons and knob presses (decoded, bindable except the two shift keys), "
            "3 rotary elements (decoded, not bindable yet), 3 free bindings.") in rows(render)


@pytest.mark.parametrize("row", [
    "| user | button | 3 | 6 | yes | plain, shift_up |",
    "| undo | button | 3 | 0 | yes | shift_down |",
    "| delete | button | 3 | 2 | yes | - |",
    "| shift_up | button | 4 | 0 | modifier only | - |",
    "| shift_down | button | 4 | 1 | modifier only | - |",
    "| ylift_knob_press | knob press | 1 | 0 | yes | - |",
], ids=["free_plain_and_shift_up", "free_shift_down", "nothing_free", "shift_up_key", "shift_down_key", "knob_press"])
def test_button_rows(render, row):
    assert row in rows(render)


def test_buttons_table_header_names_the_button_report(render):
    lines = rows(render)
    at = lines.index("## Buttons and knob presses (report 0x02)")
    assert lines[at + 2] == "| Name | Type | Byte | Bit | Bindable | Free combinations |"


def test_trackball_gives_one_row_per_axis(render):
    lines = rows(render)
    assert "| lift_trackball | trackball | x | 0x05 | 2 | 24 bit | left | not yet |" in lines
    assert "| lift_trackball | trackball | y | 0x05 | 6 | 24 bit | down | not yet |" in lines


@pytest.mark.parametrize("row", [
    "| lift_ring | ring | turn | 0x05 | 10 | 24 bit | right | not yet |",
    "| ylift_knob_turn | knob turn | turn | 0x06 | 1 | 32 bit | right | not yet |",
], ids=["ring", "knob_turn"])
def test_rotary_rows(render, row):
    assert row in rows(render)


def test_text_has_one_final_newline_no_trailing_spaces_and_only_ascii(render):
    text = render(small_profile_data())
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert all(line == line.rstrip() for line in text.split("\n"))
    assert text.isascii()


def test_same_profile_gives_the_same_text(render):
    assert render(small_profile_data()) == render(small_profile_data())


def test_real_profile_summary(render):
    assert ("52 buttons and knob presses (decoded, bindable except the two shift keys), "
            "18 rotary elements (decoded, not bindable yet), 55 free bindings.") in render(read_json(PROFILE_PATH)).splitlines()


def test_committed_doc_is_up_to_date(render):
    committed = (BASE / "docs" / "BUTTONS.md").read_text(encoding="utf-8")
    assert committed == render(read_json(PROFILE_PATH)), "docs/BUTTONS.md is out of date: run python tools\\build_buttons_doc.py"
