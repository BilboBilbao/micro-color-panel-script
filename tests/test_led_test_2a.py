"""tools/led_test_stage2a.py (D23): the 48 bits of output report 4, one at a time, Enter before each bit.
The script is loaded from its file, because tools/ is not a package; it imports report4, send and open_usb_panel
from tools/led_test_stage1.py, so tools/ is put on the import path for the test. hid, input and sleep are faked.
Expected bytes are written by hand: report id 4, six data bytes, bit n in byte 1 + n // 8 with mask 1 << (n % 8)."""
import builtins
import importlib.util
import re
import sys

import pytest

from micropanel import BASE

SCRIPT = BASE / "tools" / "led_test_stage2a.py"
ALL_OFF = bytes([4, 0, 0, 0, 0, 0, 0])


def one_bit_on(bit):
    report = bytearray(ALL_OFF)
    report[1 + bit // 8] |= 1 << (bit % 8)
    return bytes(report)


class FakePanel:
    """Stands in for the opened hid device: records every write. Like Windows it reports 9 bytes for a 7-byte report."""

    def __init__(self):
        self.writes, self.closed = [], False

    def open_path(self, path):
        pass

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data) + 2

    def error(self):
        return "no error"

    def close(self):
        self.closed = True


class FakeHid:
    def __init__(self, panel):
        self.panel = panel

    def enumerate(self, vid=0, pid=0):
        return [{"usage_page": 0xFF00, "bus_type": 1, "path": b"usb"}]

    def device(self):
        return self.panel


@pytest.fixture
def stage(monkeypatch):
    monkeypatch.syspath_prepend(str(BASE / "tools"))
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    spec = importlib.util.spec_from_file_location("led_test_stage2a", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)                      # must have no side effects: no hid import, no start at load
    return module


@pytest.fixture
def panel(monkeypatch):
    fake = FakePanel()
    monkeypatch.setitem(sys.modules, "hid", FakeHid(fake))
    return fake


def test_steps_are_the_bits_0_to_47_once_in_order(stage):
    assert list(stage.STEPS) == list(range(48))


def test_script_has_no_write_and_no_feature_calls():                # the only write of all tools is send() of stage 1
    source = SCRIPT.read_text(encoding="utf-8")
    assert re.findall(r"\.write\(", source) == []
    assert re.findall(r"send_feature_report|send_output_report|get_feature_report|get_input_report", source) == []


def test_full_run_sends_each_bit_then_all_off_and_waits_for_enter_each_time(stage, panel, monkeypatch):
    prompts = []
    monkeypatch.setattr(builtins, "input", lambda prompt="": prompts.append(prompt) or "")
    stage.main()
    expected = []
    for bit in range(48):
        expected += [one_bit_on(bit), ALL_OFF]
    expected.append(ALL_OFF)                                    # the final all-off
    assert panel.writes == expected                             # 97 writes
    assert len(prompts) == 48
    assert panel.closed


def test_ctrl_c_at_the_second_enter_switches_everything_off_and_closes(stage, panel, monkeypatch):
    calls = []

    def interrupting(prompt=""):
        calls.append(prompt)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return ""

    monkeypatch.setattr(builtins, "input", interrupting)
    stage.main()
    assert panel.writes == [one_bit_on(0), ALL_OFF, ALL_OFF]
    assert panel.closed
