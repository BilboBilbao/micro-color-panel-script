"""Windows helpers: DPI awareness and the foreground check. The Windows API calls themselves are not tested here
(--diagnose does that on real Windows); these tests use fakes. Expected values are written by hand."""
import ctypes
import importlib.util
import logging

import pytest

import micropanel.platform.windows as win
from helpers import events


class FakeShcore:
    """Stands in for ctypes.windll.shcore: reports `state` as the awareness and returns `code` from the set call."""

    def __init__(self, state, code=0, fail=False):
        self.state, self.code, self.fail = state, code, fail

    def SetProcessDpiAwareness(self, _value):
        if self.fail:
            raise OSError("simulated")
        return self.code

    def GetProcessDpiAwareness(self, _handle, reference):
        reference._obj.value = self.state
        return 0


@pytest.mark.parametrize("shcore,expected", [
    (FakeShcore(2, 0), (2, 0)),
    (FakeShcore(1, -2147024891), (1, -2147024891)),       # refused: awareness stays 1, no error is raised
    (FakeShcore(0, fail=True), (None, None)),
], ids=["set_succeeds", "set_refused", "call_raises"])
def test_set_dpi_awareness(shcore, expected):
    assert win.set_dpi_awareness(shcore) == expected


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


def test_importing_the_module_calls_no_windows_api(monkeypatch):
    """Importing must have no side effects (no import side effects): the DPI call happens in the start file, before pyautogui."""
    calls = []

    class Spy:
        def __getattr__(self, name):
            calls.append(name)
            raise AttributeError(name)

    def spy_win_dll(*args, **kwargs):
        calls.append("WinDLL")
        raise OSError("simulated")

    monkeypatch.setattr(ctypes, "windll", Spy(), raising=False)      # raising=False: does not exist on Linux and macOS
    monkeypatch.setattr(ctypes, "WinDLL", spy_win_dll, raising=False)
    spec = importlib.util.spec_from_file_location("windows_import_check", win.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)                                   # a separate copy, the real module stays untouched
    assert calls == []