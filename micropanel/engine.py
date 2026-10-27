"""The main loop: waits for the panel, reads reports, runs the bindings. Standard library only (plus the other
core modules). The panel and the action executor are passed in, so tests can run this very loop
with a simulated panel and without real key presses. Nothing here runs at import time."""
import logging
import time

from micropanel.decoder import decode_held, make_lookup, triggers_for_report
from micropanel.log import emit
from micropanel.profile import MODS

READ_TIMEOUT_MS = 100
RETRY_SECONDS = 2


def wait_for_panel(open_device, on_idle, sleep=time.sleep):
    """Waits until open_device() returns a device. on_idle() is called while waiting (used for config reload)."""
    warned = False
    while True:
        try:
            dev = open_device()
            if dev is not None:
                emit(logging.INFO, "panel_connected", "Panel connected")
                return dev
            if not warned:
                emit(logging.WARNING, "panel_waiting", "Panel not found, waiting ...", reason="not_found")
                warned = True
        except OSError as e:
            if not warned:
                emit(logging.WARNING, "panel_waiting", "Cannot open panel (%r), waiting ...", e, reason="open_error")
                warned = True
        on_idle()
        sleep(RETRY_SECONDS)


def run_engine(profile, config, open_device, execute_fn, trace=False, sleep=time.sleep):
    """Reads the panel and runs the bindings until Ctrl+C.

    open_device() and execute_fn(name, action) are passed in, so tests can run this
    very loop with a simulated panel and without real key presses."""
    lookup, min_length = make_lookup(profile)
    dev = None
    prev = set()    # survives a reconnect: a button still held after it must not fire a second time
    try:
        while True:
            dev = wait_for_panel(open_device, config.poll, sleep)
            try:
                while True:
                    try:
                        d = dev.read(64, READ_TIMEOUT_MS)
                    except (OSError, ValueError) as e:     # only a failed read means a lost panel
                        emit(logging.WARNING, "panel_lost", "Connection to the panel lost (%r), reconnecting", e)
                        break
                    config.poll()   # checks the files at most once per interval
                    held = decode_held(d, lookup, profile.report_id, min_length)
                    if held is None:
                        continue
                    keys = triggers_for_report(prev, held)
                    if trace:
                        for key in keys:
                            has = key in config.actions
                            emit(logging.INFO, "press", "press %s (binding: %s)", key, "yes" if has else "no",
                                 key=key, has_binding=has)
                        new = sorted((held - prev) - MODS)
                        if new and not keys:
                            emit(logging.INFO, "press",
                                 "press ignored: %s (shift state changed in this report, both shift keys held, "
                                 "or another button was already held)",
                                 ", ".join(new), ignored=",".join(new))
                    for key in keys:
                        if key in config.actions:
                            execute_fn(key, config.actions[key])
                    prev = held
            finally:
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
                dev = None
            sleep(RETRY_SECONDS)    # only reached after a failed read; Ctrl+C skips it
    except KeyboardInterrupt:
        emit(logging.INFO, "stop", "Stopped.")