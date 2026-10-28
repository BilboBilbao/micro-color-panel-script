"""Opening the panel: found by VID, PID and HID usage page, not by interface number (over Bluetooth it is -1). Read only.
Needs the third-party package hidapi, imported inside the function."""


def open_panel(profile):
    """Returns an opened hid.device, or None if the panel is not available."""
    import hid
    for d in hid.enumerate(profile.vid, profile.pid):
        if d["usage_page"] == profile.usage_page:
            dev = hid.device()
            dev.open_path(d["path"])
            return dev
    return None