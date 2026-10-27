"""open_panel: finds the panel by VID, PID and interface number and never opens another interface.
Expected values are written by hand from docs/HARDWARE.md."""
import sys

import pytest

from micropanel.device import open_panel


class FakeHid:
    """Stands in for the hid module: lists the given interfaces and records which path was opened."""

    def __init__(self, entries):
        self.entries, self.asked, self.opened = entries, None, []
        outer = self

        class device:
            def open_path(self, path):
                outer.opened.append(path)

        self.device = device

    def enumerate(self, vid=0, pid=0):
        self.asked = (vid, pid)
        return self.entries


def test_open_panel_opens_only_the_hid_interface(monkeypatch, profile):
    fake = FakeHid([{"interface_number": 1, "path": b"dfu"},          # interface 1 (firmware update) is never touched
                    {"interface_number": 2, "path": b"hid"},
                    {"interface_number": 0, "path": b"driver"}])
    monkeypatch.setitem(sys.modules, "hid", fake)
    assert open_panel(profile) is not None
    assert fake.opened == [b"hid"]
    assert fake.asked == (0x1EDB, 0xDA0F)


def test_open_panel_gives_none_without_the_hid_interface(monkeypatch, profile):
    fake = FakeHid([{"interface_number": 1, "path": b"dfu"}])
    monkeypatch.setitem(sys.modules, "hid", fake)
    assert open_panel(profile) is None
    assert fake.opened == []


def test_open_error_reaches_the_caller(monkeypatch, profile):          # CONS-010: wait_for_panel decides what to do
    fake = FakeHid([{"interface_number": 2, "path": b"hid"}])

    def failing(self, path):
        raise OSError("open failed")

    fake.device.open_path = failing
    monkeypatch.setitem(sys.modules, "hid", fake)
    with pytest.raises(OSError):
        open_panel(profile)