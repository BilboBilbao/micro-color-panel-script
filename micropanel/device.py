"""Opening the panel: HID interface 2, read only. Needs the third-party package hidapi, imported inside the function."""


def open_panel(profile):
    """Returns an opened hid.device, or None if the panel is not available."""
    import hid
    for d in hid.enumerate(profile.vid, profile.pid):
        if d["interface_number"] == profile.interface:
            dev = hid.device()
            dev.open_path(d["path"])
            return dev
    return None