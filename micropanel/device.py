"""Opening the panel: found by VID, PID and HID usage page, not by interface number (over Bluetooth it is -1). Read only.
Needs the third-party package hidapi, imported inside the function."""

CONNECTION_NAMES = {1: "USB", 2: "Bluetooth"}      # hidapi bus_type values; the panel is connected in one of these ways


def bus_name(bus_type):
    """'USB', 'Bluetooth' or 'unknown' for a hidapi bus_type; None if the library gives no bus_type."""
    if bus_type is None:
        return None
    return CONNECTION_NAMES.get(bus_type, "unknown")


class OpenedPanel:
    """The opened hid device, reduced to what the program may do with it: read and close. There is no write call on
    it, so writing to the panel is impossible by construction. connection is 'USB', 'Bluetooth' or 'unknown'."""

    def __init__(self, dev, connection):
        self._dev, self.connection = dev, connection

    def read(self, size, timeout_ms=0):
        return self._dev.read(size, timeout_ms)

    def close(self):
        self._dev.close()


def open_panel(profile):
    """Returns an OpenedPanel, or None if the panel is not available."""
    import hid
    for d in hid.enumerate(profile.vid, profile.pid):
        if d["usage_page"] == profile.usage_page:
            dev = hid.device()
            dev.open_path(d["path"])
            return OpenedPanel(dev, bus_name(d.get("bus_type")) or "unknown")
    return None