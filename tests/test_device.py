"""open_panel: finds the panel by VID, PID and usage page 0xFF00. The interface number is not used: over Bluetooth it is -1.
The entries are made up by hand (which usage page the other USB interfaces report is not measured); the DFU
interface must never be opened, so a test fails if anything but the panel entry is opened.
The opened panel also says how it is connected (USB, Bluetooth or unknown), taken from the entry that is opened."""
import sys

import pytest

from micropanel import diagnose
from micropanel.device import open_panel


class FakeHid:
    """Stands in for the hid module: lists the given entries and records which path was opened."""

    def __init__(self, entries):
        self.entries, self.asked, self.opened, self.devices = entries, None, [], []
        outer = self

        class device:
            def __init__(self):
                self.closed = False
                outer.devices.append(self)

            def open_path(self, path):
                outer.opened.append(path)

            def read(self, size, timeout_ms=0):
                return [2, 0, 0]

            def close(self):
                self.closed = True

        self.device = device

    def enumerate(self, vid=0, pid=0):
        self.asked = (vid, pid)
        return self.entries


def opened_panel(profile):
    """open_panel for tests that use the result: fails clearly if the panel was not found."""
    opened = open_panel(profile)
    assert opened is not None
    return opened


def entry(path, interface, usage_page=0xFF00, bus_type=None):
    result = {"interface_number": interface, "usage_page": usage_page, "path": path}
    if bus_type is not None:                                           # hidapi: 1 = USB, 2 = Bluetooth
        result["bus_type"] = bus_type
    return result


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


# --- v0.3.35: how the panel is connected ---------------------------------------------------------------------

@pytest.mark.parametrize("bus_type, expected", [(1, "USB"), (2, "Bluetooth"), (0, "unknown"), (3, "unknown"),
                                                (7, "unknown"), (None, None)])
def test_bus_name(bus_type, expected):                                 # hidapi enum: 0 unknown, 1 USB, 2 Bluetooth
    from micropanel.device import bus_name
    assert bus_name(bus_type) == expected


@pytest.mark.parametrize("bus_type, expected", [(1, "USB"), (2, "Bluetooth"), (None, "unknown")])
def test_open_panel_reports_the_connection(monkeypatch, profile, bus_type, expected):
    monkeypatch.setitem(sys.modules, "hid", FakeHid([entry(b"hid", 2, bus_type=bus_type)]))
    assert opened_panel(profile).connection == expected


def test_connection_comes_from_the_opened_entry(monkeypatch, profile):
    fake = FakeHid([entry(b"dfu", 1, 0x0001, bus_type=1), entry(b"bt", -1, bus_type=2)])
    monkeypatch.setitem(sys.modules, "hid", fake)
    opened = opened_panel(profile)
    assert fake.opened == [b"bt"]
    assert opened.connection == "Bluetooth"


def test_opened_panel_passes_read_and_close_on(monkeypatch, profile):  # characterization, green at once
    fake = FakeHid([entry(b"hid", 2)])
    monkeypatch.setitem(sys.modules, "hid", fake)
    opened = opened_panel(profile)
    assert opened.read(64, 100) == [2, 0, 0]
    opened.close()
    assert fake.devices[0].closed


@pytest.mark.parametrize("name", ["write", "send_feature_report", "send_output_report"])
def test_opened_panel_has_no_write_call(monkeypatch, profile, name):  # principle 1; green now, guards the wrapper
    monkeypatch.setitem(sys.modules, "hid", FakeHid([entry(b"hid", 2)]))
    assert not hasattr(opened_panel(profile), name)


# --- the diagnose keeps showing the connection type (characterization, green at once) -----------------------

def diagnose_context(profile):
    ctx = diagnose.Context(auto=True)
    ctx.profile = profile
    return ctx


def test_diagnose_shows_a_bluetooth_connection(monkeypatch, profile):
    monkeypatch.setitem(sys.modules, "hid", FakeHid([entry(b"bt", -1, bus_type=2)]))
    ctx = diagnose_context(profile)
    diagnose.step_panel(ctx)
    assert ctx.bus == "Bluetooth"
    assert ("INFO", "Connection type reported by the hid library: Bluetooth") in ctx.rows


def test_diagnose_without_connection_type(monkeypatch, profile):
    monkeypatch.setitem(sys.modules, "hid", FakeHid([entry(b"hid", 2)]))
    ctx = diagnose_context(profile)
    diagnose.step_panel(ctx)
    assert ctx.bus is None
    assert ("INFO", "Connection type reported by the hid library: not provided by this version of the library") in ctx.rows


def test_diagnose_skips_the_unplug_step_over_bluetooth(profile):
    ctx = diagnose_context(profile)
    ctx.bus = "Bluetooth"
    diagnose.step_unplug(ctx)
    assert ctx.rows == [("SKIP", "Unplug test: the panel is connected by Bluetooth")]
