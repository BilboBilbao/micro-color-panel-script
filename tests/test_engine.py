"""run_engine with a fake panel and a fake action executor."""
import json
import logging
import re

import pytest

import micropanel.engine as engine
from micropanel import BASE
from helpers import ConfigStub, FakeDevice, events, fields, idle_report, real_config, recorded_report, report_of

USER_ACTION = ("keys", ["Key.f9"], True)


def run(profile, devices, config=None, execute=lambda name, action: None):
    opened = []

    def open_device():
        opened.append(1)
        return devices[len(opened) - 1]

    engine.run_engine(profile, config or ConfigStub({"user": USER_ACTION}), open_device, execute, sleep=lambda seconds: None)
    return len(opened)


def test_normal_run_executes_the_binding_once(profile):
    executed = []
    dev = FakeDevice([recorded_report("user"), recorded_report("user"), idle_report()])
    run(profile, [dev], execute=lambda name, action: executed.append((name, action)))
    assert executed == [("user", USER_ACTION)]


def test_read_error_reconnects(profile, caplog):
    caplog.set_level(logging.INFO)
    first, second = FakeDevice([OSError("unplugged")]), FakeDevice()
    assert run(profile, [first, second]) == 2
    assert "panel_lost" in events(caplog) and first.closed


def test_action_error_does_not_reconnect(profile, caplog):             # B4
    caplog.set_level(logging.INFO)

    def failing(name, action):
        raise ValueError("bug in an action")

    first, second = FakeDevice([recorded_report("user")]), FakeDevice()
    opened = 0
    try:
        opened = run(profile, [first, second], execute=failing)
    except ValueError:
        opened = 1                                                    # the error may also reach the caller
    assert "panel_lost" not in events(caplog)
    assert opened == 1


def test_normal_run_never_writes_to_the_panel(profile):               # B6, behavior (FakeDevice fails on any write)
    run(profile, [FakeDevice([recorded_report("user"), idle_report(), recorded_report("undo"), idle_report()])])


def test_runtime_code_has_no_write_call():                            # B6, text scan of the start file and the package
    files = [BASE / "panel_main.py", *sorted((BASE / "micropanel").rglob("*.py"))]
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert re.findall(r"\.(write|send_feature_report|send_output_report)\(", source) == []


class EditingDevice(FakeDevice):
    """Calls hook(n) before the n-th read (used to edit a file while the panel is connected)."""

    def __init__(self, script, hook):
        super().__init__(script)
        self.hook, self.reads = hook, 0

    def read(self, size, timeout_ms=0):
        self.reads += 1
        self.hook(self.reads)
        return super().read(size, timeout_ms)


def test_reload_while_connected_applies_new_binding(tmp_path, profile, caplog):
    caplog.set_level(logging.INFO)
    start = {"user": {"type": "keys", "keys": "f9"}}
    after = {**start, "shift_up+user": {"type": "keys", "keys": "f9"}}
    config, bindings_file = real_config(tmp_path, profile, start)

    def hook(n):
        if n == 2:
            bindings_file.write_text(json.dumps(after), encoding="utf-8")      # edited while the panel is connected

    idle = idle_report()
    script = [idle] * 5 + [report_of("shift_up"), report_of("shift_up", "user"), report_of("shift_up"), idle]
    fired = []
    run(profile, [EditingDevice(script, hook)], config=config, execute=lambda name, action: fired.append(name))
    assert fired == ["shift_up+user"]
    assert len([f for f in fields(caplog, "config_loaded") if f["reload"]]) == 1


def test_panel_missing_then_found_reloads_config_and_reports_once(tmp_path, profile, caplog):
    caplog.set_level(logging.INFO)
    start = {"user": {"type": "keys", "keys": "f9"}, "shift_up+undo": {"type": "keys", "keys": "f9"}}
    after = {**start, "shift_down+undo": {"type": "keys", "keys": "f9"}, "shift_up+user": {"type": "keys", "keys": "f9"}}
    config, bindings_file = real_config(tmp_path, profile, start)
    idle, user = idle_report(), report_of("user")
    devices = [FakeDevice([idle, user, idle, OSError("unplugged")]), FakeDevice([user, idle])]
    calls = []

    def open_device():
        calls.append(1)
        if len(calls) == 1:
            bindings_file.write_text(json.dumps(after), encoding="utf-8")      # edited while the panel is missing
        return None if len(calls) <= 3 else devices.pop(0)

    fired = []
    engine.run_engine(profile, config, open_device, lambda name, action: fired.append(name), sleep=lambda seconds: None)
    assert fired == ["user", "user"]
    names = events(caplog)
    assert (names.count("panel_waiting"), names.count("panel_connected"),
            names.count("panel_lost"), names.count("stop")) == (1, 2, 1, 1)
    assert len(config.actions) == 4
    assert len([f for f in fields(caplog, "config_loaded") if f["reload"]]) == 1


def run_counting_sleeps(profile, devices, execute=lambda name, action: None):
    """Like run(), but returns the list of sleep() calls instead of the number of opened devices."""
    sleeps, opened = [], []

    def open_device():
        opened.append(1)
        return devices[len(opened) - 1]

    config = ConfigStub({"user": USER_ACTION, "undo": USER_ACTION})
    engine.run_engine(profile, config, open_device, execute, sleep=sleeps.append)
    return sleeps


def test_button_held_across_reconnect_fires_once(profile):             # RV-5 (a)
    fired = []
    first = FakeDevice([recorded_report("user"), OSError("unplugged")])
    second = FakeDevice([recorded_report("user"), idle_report()])     # still held after the reconnect
    run_counting_sleeps(profile, [first, second], execute=lambda name, action: fired.append(name))
    assert fired == ["user"]


def test_other_button_after_reconnect_fires(profile):                  # RV-5 (a), guards against a baseline variant
    fired = []
    first = FakeDevice([recorded_report("user"), OSError("unplugged")])
    second = FakeDevice([recorded_report("undo"), idle_report()])
    run_counting_sleeps(profile, [first, second], execute=lambda name, action: fired.append(name))
    assert fired == ["user", "undo"]


def test_ctrl_c_does_not_sleep(profile):                               # RV-5 (b)
    assert run_counting_sleeps(profile, [FakeDevice([idle_report()])]) == []


def test_read_error_sleeps_once_before_reconnect(profile):             # RV-5 (b)
    sleeps = run_counting_sleeps(profile, [FakeDevice([OSError("unplugged")]), FakeDevice()])
    assert sleeps == [engine.RETRY_SECONDS]


def test_open_error_waits_then_connects(caplog):                       # CONS-010
    caplog.set_level(logging.INFO)
    answers = [OSError("open failed"), OSError("open failed"), "device"]
    sleeps, idles = [], []

    def open_device():
        answer = answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    assert engine.wait_for_panel(open_device, lambda: idles.append(1), sleeps.append) == "device"
    assert sleeps == [engine.RETRY_SECONDS] * 2
    assert len(idles) == 2
    names = events(caplog)
    assert (names.count("panel_waiting"), names.count("panel_connected")) == (1, 1)
    assert fields(caplog, "panel_waiting")[0]["reason"] == "open_error"


def test_other_open_error_is_not_swallowed():                          # CONS-010, B2: bugs must not look like "panel missing"
    def open_device():
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        engine.wait_for_panel(open_device, lambda: None, lambda seconds: None)