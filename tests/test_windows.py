"""Windows helpers: DPI awareness and the foreground check. The Windows API calls themselves are not tested here
(--diagnose does that on real Windows); these tests use fakes. Expected values are written by hand."""
import logging

import pytest

import micropanel.platform.windows as win
from helpers import events


class FakeShcore:
    """Stands in for ctypes.windll.shcore: reports `state` as the awareness and returns `code` from the set call.
    read_code is what the read call returns (0 = success), read_fail makes the read call raise."""

    def __init__(self, state, code=0, fail=False, read_code=0, read_fail=False):
        self.state, self.code, self.fail = state, code, fail
        self.read_code, self.read_fail = read_code, read_fail

    def SetProcessDpiAwareness(self, _value):
        if self.fail:
            raise OSError("simulated")
        return self.code

    def GetProcessDpiAwareness(self, _handle, reference):
        if self.read_fail:
            raise OSError("simulated")
        reference._obj.value = self.state
        return self.read_code


@pytest.mark.parametrize("shcore,expected", [
    (FakeShcore(2, 0), (2, 0)),
    (FakeShcore(1, -2147024891), (1, -2147024891)),       # refused: awareness stays 1, no error is raised
    (FakeShcore(0, fail=True), (None, None)),
    (FakeShcore(2, 0, read_code=1), (None, None)),        # set call ok, but the awareness cannot be read back
], ids=["set_succeeds", "set_refused", "call_raises", "read_fails"])
def test_set_dpi_awareness(shcore, expected):
    assert win.set_dpi_awareness(shcore) == expected


@pytest.mark.parametrize("shcore,expected", [
    (FakeShcore(2), 2),
    (FakeShcore(0), 0),
    (FakeShcore(2, read_code=1), None),                   # the read call reports an error
    (FakeShcore(2, read_fail=True), None),                # the read call raises
], ids=["per_monitor", "unaware", "read_refused", "read_raises"])
def test_get_dpi_awareness(shcore, expected):
    assert win.get_dpi_awareness(shcore) == expected


@pytest.mark.parametrize("awareness,code,expected_parts", [
    (2, 0, None),                                         # per monitor: no warning
    (None, None, None),                                   # unknown: no warning
    (1, -2147024891, ["system DPI aware", "0x80070005", "instead of per monitor (2)"]),
    (7, 0, ["unknown value 7"]),
], ids=["per_monitor", "unknown", "system_aware_refused", "other_value"])
def test_dpi_warning_text(awareness, code, expected_parts):
    text = win.dpi_warning_text(awareness, code)
    if expected_parts is None:
        assert text is None
    else:
        assert text is not None
        for part in expected_parts:
            assert part in text


@pytest.mark.parametrize("foreground,expected", [
    ("Resolve.exe", True),
    ("resolve.exe", True),                                # the comparison ignores case
    ("Other.exe", False),
    (None, False),                                        # no foreground program found
], ids=["resolve", "resolve_lowercase", "other_program", "none"])
def test_resolve_is_foreground(monkeypatch, foreground, expected):
    monkeypatch.setattr(win, "foreground_process_name", lambda: foreground)
    assert win.resolve_is_foreground() == (expected, foreground)


def test_foreground_check_error_gives_false_and_is_logged(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def broken():
        raise OSError("simulated")

    monkeypatch.setattr(win, "foreground_process_name", broken)
    assert win.resolve_is_foreground() == (False, None)
    assert events(caplog) == ["foreground_check_failed"]


def monitor(left, top, right, bottom):
    return {"left": left, "top": top, "right": right, "bottom": bottom, "primary": False, "scale": 100}


ONE = [monitor(0, 0, 1920, 1080)]
LEFT = ONE + [monitor(-1920, 0, 0, 1080)]          # second monitor left of the main monitor


@pytest.mark.parametrize("monitors,point,expected", [
    (ONE, (0, 0), 1),                                 # top left corner belongs to the monitor
    (ONE, (1919, 1079), 1),                           # last pixel
    (ONE, (1920, 500), None),                         # the right edge is already outside
    (ONE, (500, 1080), None),                         # the bottom edge is already outside
    (ONE, (-1, 500), None),
    (LEFT, (-1500, 300), 2),                          # negative numbers are valid
    ([], (100, 100), None),                           # no monitor known: outside
], ids=["top_left_corner", "last_pixel", "right_edge", "bottom_edge", "left_of_all",
        "left_of_primary", "no_monitors"])
def test_monitor_index(monitors, point, expected):
    assert win.monitor_index(monitors, point) == expected