"""tools/led_test_stage1.py (D22): the pure part report4() and a text scan of the throwaway script.
The script is loaded from its file, because tools/ is not a package. Expected bytes are written by hand from
docs/HARDWARE.md: bit n is in byte 1 + n // 8, mask 1 << (n % 8); report id 4, six data bytes."""
import importlib.util
import re

import pytest

from micropanel import BASE

SCRIPT = BASE / "tools" / "led_test_stage1.py"


@pytest.fixture(scope="module")
def report4():
    spec = importlib.util.spec_from_file_location("led_test_stage1", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)                      # must have no side effects: no hid import, no start at load
    return module.report4


@pytest.mark.parametrize("bits, expected", [
    ([], [4, 0, 0, 0, 0, 0, 0]),
    ([2], [4, 4, 0, 0, 0, 0, 0]),
    ([1], [4, 2, 0, 0, 0, 0, 0]),
    ([9], [4, 0, 2, 0, 0, 0, 0]),
    ([0, 10], [4, 1, 4, 0, 0, 0, 0]),
    ([47], [4, 0, 0, 0, 0, 0, 128]),
], ids=["all_off", "bit2_offset", "bit1", "bit9", "two_bits", "last_bit"])
def test_report4_bytes(report4, bits, expected):
    assert list(report4(bits)) == expected


@pytest.mark.parametrize("bits", [[48], [-1]], ids=["too_high", "negative"])
def test_report4_rejects_bits_outside_0_to_47(report4, bits):
    with pytest.raises(ValueError):
        report4(bits)


def test_script_has_exactly_one_write_and_no_feature_calls():      # D22: only output report 4, nothing else
    source = SCRIPT.read_text(encoding="utf-8")
    assert len(re.findall(r"\.write\(", source)) == 1
    assert re.findall(r"send_feature_report|send_output_report|get_feature_report|get_input_report", source) == []