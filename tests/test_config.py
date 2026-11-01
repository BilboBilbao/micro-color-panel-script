"""Bindings and tabs: validation of single entries and hot reload."""
import json
import logging
import os

import pytest

import micropanel.config as cfg
from micropanel import BASE
from micropanel.keys import parse_keys
from helpers import events, fields, messages, real_config


@pytest.mark.parametrize("entry,tabs", [
    ({"type": "click", "pos": [True, 5]}, {}),
    ({"type": "click", "pos": [5, False]}, {}),
    ({"type": "click", "tab": "x"}, {"x": [True, 5]}),
    ({"type": "toggle", "tabs": ["x"]}, {"x": [5, True]}),
], ids=["pos_bool_x", "pos_bool_y", "tab_bool_x", "toggle_tab_bool_y"])
def test_bool_coordinate_rejected(entry, tabs):                       # B5
    with pytest.raises(ValueError):
        cfg.compile_action(entry, tabs)


def test_whole_number_coordinate_accepted():
    assert cfg.compile_action({"type": "click", "pos": [10, 5]}, {}) == ("click", (10, 5))


def write(path, data):
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def make_config(tmp_path, profile):
    write(tmp_path / "bindings.json", {"user": {"type": "keys", "keys": "f9"}})
    write(tmp_path / "tabs.json", {})
    config = cfg.ConfigManager(set(profile.buttons), profile.free_bindings,
                              tmp_path / "bindings.json", tmp_path / "tabs.json", interval=0)
    config.load(initial=True)
    return config


def test_reload_keeps_old_actions_on_broken_json(tmp_path, profile, caplog):
    caplog.set_level(logging.INFO)
    config = make_config(tmp_path, profile)
    assert list(config.actions) == ["user"]
    write(tmp_path / "bindings.json", '{"user": {"type": "keys", "keys": "f10"} BROKEN')
    for _ in range(4):                                                # first poll sees the change, second loads, rest idle
        config.poll()
    assert list(config.actions) == ["user"]
    assert config.actions["user"][1] == parse_keys("f9")
    assert events(caplog).count("config_failed") == 1                 # reported once, not on every poll


def test_changed_file_is_loaded_after_two_polls(tmp_path, profile):
    config = make_config(tmp_path, profile)
    write(tmp_path / "bindings.json", {"user": {"type": "keys", "keys": "f10"}})
    config.poll()
    assert config.actions["user"][1] == parse_keys("f9")           # debounce: not yet
    config.poll()
    assert config.actions["user"][1] == parse_keys("f10")


def test_invalid_entry_is_skipped_not_fatal(tmp_path, profile):
    write(tmp_path / "bindings.json", {
        "user": {"type": "keys", "keys": "f9"},
        "not_a_button": {"type": "keys", "keys": "f9"},
        "shift_up+user": {"type": "nonsense"},
        "_note": "ignored",
    })
    write(tmp_path / "tabs.json", {})
    config = cfg.ConfigManager(set(profile.buttons), profile.free_bindings,
                              tmp_path / "bindings.json", tmp_path / "tabs.json", interval=0)
    config.load(initial=True)
    assert list(config.actions) == ["user"]


def test_example_bindings_load_cleanly(profile, caplog):
    caplog.set_level(logging.INFO)
    bindings = cfg.read_json(BASE / "bindings.example.json")
    actions, skipped = cfg.build_actions(bindings, set(profile.buttons), {}, set(profile.free_bindings))
    assert list(actions) == ["user"]
    assert skipped == 0
    assert events(caplog) == []


def test_read_json_accepts_file_with_byte_order_mark(tmp_path):         # Notepad saves with BOM
    path = tmp_path / "x.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"a": 1}')
    assert cfg.read_json(path) == {"a": 1}


@pytest.mark.parametrize("content,expected", [
    (b'{"a": ', "x.json is not valid JSON"),
    (None, "file missing: x.json"),
], ids=["invalid_json", "missing_required_file"])
def test_read_json_error_names_the_file(tmp_path, content, expected):
    path = tmp_path / "x.json"
    if content is not None:
        path.write_bytes(content)
    with pytest.raises(cfg.ConfigError, match=expected):
        cfg.read_json(path)


def test_optional_missing_file_gives_empty_dict_and_a_warning(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    assert cfg.read_json(tmp_path / "nope.json", required=False) == {}
    assert events(caplog) == ["config_warning"]


def test_broken_file_at_start_runs_without_bindings_and_loads_after_repair(tmp_path, profile, caplog):
    caplog.set_level(logging.INFO)
    write(tmp_path / "bindings.json", '{"user": BROKEN')
    write(tmp_path / "tabs.json", {})
    config = cfg.ConfigManager(set(profile.buttons), profile.free_bindings,
                              tmp_path / "bindings.json", tmp_path / "tabs.json", interval=0)
    config.load(initial=True)
    assert config.actions == {}
    assert "start_without_bindings" in events(caplog)
    write(tmp_path / "bindings.json", {"user": {"type": "keys", "keys": "f9"}})
    config.poll()                                                     # sees the change
    config.poll()                                                     # sees it a second time and loads
    assert list(config.actions) == ["user"]
    

def test_broken_json_message_names_line_and_column(tmp_path, profile, caplog):
    caplog.set_level(logging.INFO)
    config = make_config(tmp_path, profile)
    write(tmp_path / "bindings.json", '{"user": {"type": "keys", "keys": "f10"} BROKEN')
    for _ in range(4):
        config.poll()
    found = messages(caplog, "config_failed")
    assert len(found) == 1
    assert "line" in found[0] and "column" in found[0]


def test_deleted_file_keeps_old_actions_and_message_has_no_full_path(tmp_path, profile, caplog):
    caplog.set_level(logging.INFO)
    config = make_config(tmp_path, profile)
    (tmp_path / "bindings.json").unlink()
    for _ in range(2):                                                # first poll sees the change, second loads
        config.poll()
    found = messages(caplog, "config_failed")
    assert list(config.actions) == ["user"]
    assert len(found) == 1
    assert "file missing" in found[0] and "bindings.json" in found[0]
    assert str(tmp_path) not in found[0]


def test_entry_warning_reasons(profile, caplog):
    caplog.set_level(logging.INFO)
    bindings = {
        "_info": "note",
        "bogus": {"type": "keys", "keys": "f9"},                                  # not a button
        "user": {"type": "keys", "keys": "nokey"},                                # unknown key name
        "stop": {"type": "keys", "keys": "f9", "only_resolve": "yes"},            # not true/false
        "undo": {"type": "keys", "keys": "f9"},                                   # native function in Resolve
        "shift_up+copy": {"type": "keys", "keys": "f9"},                          # not in the free list
    }
    actions, _skipped = cfg.build_actions(bindings, set(profile.buttons), {}, set(profile.free_bindings))
    reasons = sorted(f["reason"] for f in fields(caplog, "config_warning"))
    assert reasons == ["bad_only_resolve", "invalid_entry", "invalid_name", "not_free", "not_free"]
    assert set(actions) == {"undo", "shift_up+copy"}


def test_config_loaded_reports_counts_and_reload_flag(tmp_path, profile, caplog):
    caplog.set_level(logging.INFO)
    bindings = {"user": {"type": "keys", "keys": "f9"}, "shift_up+undo": {"type": "keys", "keys": ""}}   # one empty entry
    write(tmp_path / "bindings.json", bindings)
    write(tmp_path / "tabs.json", {})
    config = cfg.ConfigManager(set(profile.buttons), profile.free_bindings,
                              tmp_path / "bindings.json", tmp_path / "tabs.json", interval=0)
    config.load(initial=True)
    first = fields(caplog, "config_loaded")[-1]
    assert (first["active"], first["skipped"], first["reload"]) == (1, 1, False)
    bindings["shift_down+undo"] = {"type": "keys", "keys": "f9"}
    write(tmp_path / "bindings.json", bindings)
    config.poll()
    config.poll()
    second = fields(caplog, "config_loaded")[-1]
    assert (second["active"], second["skipped"], second["reload"]) == (2, 1, True)


def test_same_size_rewrite_with_restored_mtime_is_loaded(tmp_path, profile):          # RV-2 (CONS-001)
    config = make_config(tmp_path, profile)
    path = tmp_path / "bindings.json"
    before = path.stat()
    write(path, {"user": {"type": "keys", "keys": "f8"}})                 # same length as "f9"
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))           # modification time back to the old value
    assert path.stat().st_size == before.st_size
    config.poll()
    config.poll()
    assert config.actions["user"][1] == parse_keys("f8")


def test_touch_without_content_change_does_not_reload(tmp_path, profile, caplog):     # RV-2
    caplog.set_level(logging.INFO)
    config = make_config(tmp_path, profile)
    path = tmp_path / "bindings.json"
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))   # 5 s later, same content
    for _ in range(4):
        config.poll()
    assert events(caplog).count("config_loaded") == 1                     # only the start


def test_missing_tabs_file_is_a_change_and_recreating_it_is_loaded(tmp_path, profile):   # RV-2 (pins old behavior)
    manager, _bindings_file = real_config(tmp_path, profile, {"user": {"type": "click", "tab": "x"}}, {"x": [10, 20]})
    assert manager.actions["user"][:2] == ("click", (10, 20))
    (tmp_path / "tabs.json").unlink()
    manager.poll()
    manager.poll()
    assert manager.actions == {}                                          # entry is invalid without its tab
    write(tmp_path / "tabs.json", {"x": [10, 20]})
    manager.poll()
    manager.poll()
    assert manager.actions["user"][:2] == ("click", (10, 20))


def test_unreadable_file_does_not_crash_poll_and_keeps_actions(tmp_path, profile, caplog):   # RV-2 (guard)
    caplog.set_level(logging.INFO)
    config = make_config(tmp_path, profile)
    (tmp_path / "tabs.json").unlink()
    (tmp_path / "tabs.json").mkdir()                                      # a folder with that name cannot be read
    for _ in range(4):
        config.poll()
    assert list(config.actions) == ["user"]
    assert events(caplog).count("config_failed") == 1


@pytest.mark.parametrize("value,expected", [
    ([10, 20], (10, 20)),
    ([0, 0], (0, 0)),
    ([-5, 7], (-5, 7)),                                                   # monitors left of the main monitor
    ([True, 1], None),                                                    # bool counts as 1 in Python: rejected
    ([1, False], None),
    ([1.5, 2], None),
    ([1, "2"], None),
    ([1], None),
    ([1, 2, 3], None),
    ((1, 2), None),                                                       # JSON only ever gives lists
    ({"x": 1, "y": 2}, None),
    (None, None),
], ids=["whole_numbers", "zeros", "negative", "bool_x", "bool_y", "float", "string", "one_item", "three_items",
        "tuple", "dict", "none"])
def test_as_point(value, expected):                                       # rule in CLAUDE.md section 6 (_as_point renamed)
    assert cfg.as_point(value) == expected


# --------------------------------------------------------------------------
# B23: monitor layout saved in tabs.json under "_monitors"
# --------------------------------------------------------------------------
def mon(left, top, right, bottom, primary=False, scale=100):
    """One monitor in the format of get_monitors()."""
    return {"left": left, "top": top, "right": right, "bottom": bottom, "primary": primary, "scale": scale}


ONE = [mon(0, 0, 2560, 1440, primary=True)]
TWO = [mon(0, 0, 2560, 1440, primary=True), mon(2560, 0, 4480, 1080)]
SAVED_ONE = [[0, 0, 2560, 1440]]
SAVED_TWO = [[0, 0, 2560, 1440], [2560, 0, 4480, 1080]]


def layout_config(tmp_path, profile, saved, monitors):
    """Loaded ConfigManager; tabs.json holds the tab 'x' and, unless saved is None, the key _monitors."""
    tabs = {"x": [10, 20]}
    if saved is not None:
        tabs["_monitors"] = saved
    write(tmp_path / "bindings.json", {"user": {"type": "click", "tab": "x"}})
    write(tmp_path / "tabs.json", tabs)
    config = cfg.ConfigManager(set(profile.buttons), profile.free_bindings,
                              tmp_path / "bindings.json", tmp_path / "tabs.json", interval=0, monitors=monitors)
    config.load(initial=True)
    return config


@pytest.mark.parametrize("value,expected", [
    ([[2560, 0, 4480, 1080], [0, 0, 2560, 1440]], [(0, 0, 2560, 1440), (2560, 0, 4480, 1080)]),
    ([[-1920, 0, 0, 1080]], [(-1920, 0, 0, 1080)]),
    ([], None),
    ({"a": 1}, None),
    ([[0, 0, 100]], None),
    ([[True, 0, 100, 100]], None),
    ([[0, 0, 100.5, 100]], None),
    ([[10, 0, 10, 100]], None),
], ids=["valid_sorted", "negative", "empty_list", "not_a_list", "three_numbers", "bool", "float", "empty_rectangle"])
def test_parse_layout(value, expected):                                   # B23
    assert cfg.parse_layout(value) == expected


def test_current_layout_keeps_only_the_rectangles_sorted():              # B23
    monitors = [mon(2560, 0, 4480, 1080, scale=150), mon(0, 0, 2560, 1440, primary=True)]
    assert cfg.current_layout(monitors) == [(0, 0, 2560, 1440), (2560, 0, 4480, 1080)]


def test_tabs_without_layout_load_silently(tmp_path, profile, caplog):   # B23: old files still load
    caplog.set_level(logging.INFO)
    config = layout_config(tmp_path, profile, None, lambda: TWO)
    assert list(config.actions) == ["user"]
    assert "monitor_layout_changed" not in events(caplog)
    assert "bad_monitors" not in [f["reason"] for f in fields(caplog, "config_warning")]


def test_same_layout_gives_no_warning(tmp_path, profile, caplog):        # B23
    caplog.set_level(logging.INFO)
    config = layout_config(tmp_path, profile, SAVED_TWO, lambda: TWO)
    assert list(config.actions) == ["user"]
    assert "monitor_layout_changed" not in events(caplog)


def test_same_layout_in_other_order_gives_no_warning(tmp_path, profile, caplog):   # B23
    caplog.set_level(logging.INFO)
    layout_config(tmp_path, profile, SAVED_TWO, lambda: list(reversed(TWO)))
    assert "monitor_layout_changed" not in events(caplog)


@pytest.mark.parametrize("saved,current", [
    (SAVED_TWO, ONE),
    (SAVED_ONE, TWO),
    (SAVED_TWO, [mon(0, 0, 2560, 1440, primary=True), mon(2560, 100, 4480, 1180)]),
    (SAVED_TWO, [mon(0, 0, 1920, 1080, primary=True), mon(1920, 0, 3840, 1080)]),
], ids=["monitor_missing", "monitor_added", "monitor_moved", "resolution_changed"])
def test_different_layout_warns_once_and_keeps_bindings(tmp_path, profile, caplog, saved, current):   # B23
    caplog.set_level(logging.INFO)
    config = layout_config(tmp_path, profile, saved, lambda: current)
    assert events(caplog).count("monitor_layout_changed") == 1
    assert list(config.actions) == ["user"]


@pytest.mark.parametrize("saved", ["abc", [[0, 0, 100]]], ids=["not_a_list", "broken_rectangle"])
def test_invalid_layout_is_ignored_with_one_warning(tmp_path, profile, caplog, saved):   # B23
    caplog.set_level(logging.INFO)
    config = layout_config(tmp_path, profile, saved, lambda: TWO)
    assert [f["reason"] for f in fields(caplog, "config_warning")].count("bad_monitors") == 1
    assert "monitor_layout_changed" not in events(caplog)
    assert list(config.actions) == ["user"]


def test_reload_with_different_layout_warns_once(tmp_path, profile, caplog):   # B23
    caplog.set_level(logging.INFO)
    config = layout_config(tmp_path, profile, None, lambda: TWO)
    assert "monitor_layout_changed" not in events(caplog)
    write(tmp_path / "tabs.json", {"x": [10, 20], "_monitors": [[0, 0, 100, 100]]})
    config.poll()
    config.poll()
    assert events(caplog).count("monitor_layout_changed") == 1


def test_failing_monitor_list_still_loads_bindings(tmp_path, profile, caplog):   # B23
    caplog.set_level(logging.INFO)

    def broken():
        raise OSError("no monitors")

    config = layout_config(tmp_path, profile, SAVED_TWO, broken)
    assert list(config.actions) == ["user"]
    assert [f["reason"] for f in fields(caplog, "config_warning")].count("monitor_list_failed") == 1


def test_layout_warning_text_and_fields(tmp_path, profile, caplog):      # B23
    caplog.set_level(logging.INFO)
    layout_config(tmp_path, profile, SAVED_ONE, lambda: TWO)
    text = messages(caplog, "monitor_layout_changed")[0]
    assert "tabs.json" in text and "calibration.py" in text
    assert str(tmp_path) not in text
    found = fields(caplog, "monitor_layout_changed")[0]
    assert (found["saved"], found["current"]) == (1, 2)