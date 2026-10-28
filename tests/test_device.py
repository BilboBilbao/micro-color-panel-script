"""open_panel: finds the panel by VID, PID and usage page 0xFF00. The interface number is not used: over Bluetooth it is -1.
The entries are made up by hand (which usage page the other USB interfaces report is not measured); the DFU
interface must never be opened, so a test fails if anything but the panel entry is opened."""
import sys

import pytest

from micropanel.device import open_panel


class FakeHid:
    """Stands in for the hid module: lists the given entries and records which path was opened."""

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


def entry(path, interface, usage_page=0xFF00):
    return {"interface_number": interface, "usage_page": usage_page, "path": path}


def test_open_panel_opens_only_the_usb_hid_entry(monkeypatch, profile):
    fake = FakeHid([entry(b"dfu", 1, 0x0001),                         # interface 1 (firmware update) is never touched
                    entry(b"hid", 2),
                    entry(b"driver", 0, 0x0001)])
    monkeypatch.setitem(sys.modules, "hid", fake)
    assert open_panel(profile) is not None
    assert fake.opened == [b"hid"]
    assert fake.asked == (0x1EDB, 0xDA0F)


def test_open_panel_opens_the_bluetooth_entry(monkeypatch, profile):   # measured in Phase 2c: interface number -1
    fake = FakeHid([entry(b"bt", -1)])
    monkeypatch.setitem(sys.modules, "hid", fake)
    assert open_panel(profile) is not None
    assert fake.opened == [b"bt"]


def test_open_panel_gives_none_without_the_panel_usage_page(monkeypatch, profile):
    fake = FakeHid([entry(b"dfu", 1, 0x0001)])
    monkeypatch.setitem(sys.modules, "hid", fake)
    assert open_panel(profile) is None
    assert fake.opened == []


def test_usage_page_decides_not_the_interface_number(monkeypatch, profile):
    fake = FakeHid([entry(b"other", 2, 0x0001)])
    monkeypatch.setitem(sys.modules, "hid", fake)
    assert open_panel(profile) is None
    assert fake.opened == []


def test_open_error_reaches_the_caller(monkeypatch, profile):          # CONS-010: wait_for_panel decides what to do
    fake = FakeHid([entry(b"hid", 2)])

    def failing(self, path):
        raise OSError("open failed")

    fake.device.open_path = failing
    monkeypatch.setitem(sys.modules, "hid", fake)
    with pytest.raises(OSError):
        open_panel(profile)