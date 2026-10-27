"""Small helpers shared by the tests (dev only)."""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
BUTTON_REPORT_ID = 2      # written by hand from docs/HARDWARE.md, not read from the profile


def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def recorded_report(name):
    """64-byte button report rebuilt from the recording tests/data/buttons.json ([[byte, value], ...] per control)."""
    report = bytearray(64)
    report[0] = BUTTON_REPORT_ID
    for byte, value in load_json("buttons.json")[name]:
        report[byte] |= value
    return bytes(report)


def idle_report():
    return bytes([BUTTON_REPORT_ID]) + bytes(63)


def report_of(*names):
    """Button report with several controls held at once: the recorded single-control reports combined bit by bit."""
    report = bytearray(idle_report())
    for name in names:
        for position, value in enumerate(recorded_report(name)):
            report[position] |= value
    return bytes(report)


def real_config(tmp_path, profile, bindings, tabs=None):
    """A loaded ConfigManager on two files in tmp_path (interval 0: every poll checks). Returns (manager, bindings file)."""
    from micropanel.config import ConfigManager
    bindings_file, tabs_file = tmp_path / "bindings.json", tmp_path / "tabs.json"
    bindings_file.write_text(json.dumps(bindings), encoding="utf-8")
    tabs_file.write_text(json.dumps(tabs or {}), encoding="utf-8")
    manager = ConfigManager(set(profile.buttons), profile.free_bindings, bindings_file, tabs_file, interval=0)
    manager.load(initial=True)
    return manager, bindings_file


def motion_report(report_id, values):
    """Raw motion report, written by hand. values: {first byte: (bits, number)}, signed little endian."""
    report = bytearray(64)
    report[0] = report_id
    for byte, (bits, number) in values.items():
        report[byte:byte + bits // 8] = number.to_bytes(bits // 8, "little", signed=True)
    return bytes(report)


class Controller:
    def __init__(self):
        self.events = []

    def press(self, key):
        self.events.append(("press", key))

    def release(self, key):
        self.events.append(("release", key))


class FakeDevice:
    """Plays a script of reads. An exception in the script is raised. When the script is over, read() raises
    KeyboardInterrupt, which ends run_engine. Any write to the panel is a test failure."""

    def __init__(self, script=()):
        self.script = list(script)
        self.closed = False

    def read(self, size, timeout_ms=0):
        if not self.script:
            raise KeyboardInterrupt
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return list(item)

    def close(self):
        self.closed = True

    def write(self, *args, **kwargs):
        raise AssertionError("write call to the panel")

    def send_feature_report(self, *args, **kwargs):
        raise AssertionError("send_feature_report call to the panel")


class ConfigStub:
    def __init__(self, actions=None):
        self.actions = actions or {}

    def poll(self):
        pass


def events(caplog):
    """Names of the log events (event=... field) in the order they were logged."""
    return [r.fields["event"] for r in caplog.records if hasattr(r, "fields")]


def fields(caplog, event):
    """The fields of every log record of this event, in order."""
    return [r.fields for r in caplog.records if getattr(r, "fields", {}).get("event") == event]


def messages(caplog, event):
    """The readable text of every log record of this event, in order."""
    return [r.getMessage() for r in caplog.records if getattr(r, "fields", {}).get("event") == event]
