"""Configuration: file locations, reading JSON files, the device profile, bindings and tabs, hot reload.
Standard library only (plus the other core modules). Nothing here runs at import time."""
import json
import logging
import time
from pathlib import Path

from micropanel import BASE
from micropanel.keys import parse_keys
from micropanel.log import emit
from micropanel.profile import parse_profile, valid_binding_name

PROFILE_PATH = BASE / "devices" / "micro_color_panel.json"
BINDINGS_PATH = BASE / "bindings.json"
TABS_PATH = BASE / "tabs.json"
RELOAD_INTERVAL = 1.0         # seconds between checks for changed config files


def rel_path(path):
    """Path relative to the project folder; for files outside only the file name."""
    path = Path(path)
    try:
        return str(path.relative_to(BASE))
    except ValueError:
        return path.name


# --------------------------------------------------------------------------
# Reading JSON files (never exits the program; the caller decides what to do)
# --------------------------------------------------------------------------
class ConfigError(Exception):
    """A configuration file is missing or invalid. The message is meant for the log."""


def read_json(path, required=True):
    if not path.exists():
        if required:
            raise ConfigError(f"file missing: {rel_path(path)}")
        emit(logging.WARNING, "config_warning", "Optional file missing: %s", rel_path(path),
             reason="optional_file_missing")
        return {}
    try:
        # utf-8-sig also accepts files saved with a byte order mark (Windows Notepad does this)
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path.name} is not valid JSON: {e}") from None
    except UnicodeDecodeError:
        raise ConfigError(f"{path.name} is not valid UTF-8 text") from None
    except OSError as e:
        raise ConfigError(f"{path.name} cannot be read: {e}") from None


# --------------------------------------------------------------------------
# Device profile (hardware facts). Loaded once at start; errors are fatal for the program.
# --------------------------------------------------------------------------
def load_profile(path=PROFILE_PATH):
    """Reads and checks the device profile. Returns (profile, []) or (None, list of error texts)."""
    try:
        data = read_json(path)
    except ConfigError as e:
        return None, [str(e)]
    return parse_profile(data)


# --------------------------------------------------------------------------
# Bindings: validate and compile
# --------------------------------------------------------------------------
def as_point(value):
    """(x, y) for a list of two whole numbers, otherwise None. bool is rejected (in Python, True counts as 1)."""
    if (isinstance(value, list) and len(value) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in value)):
        return (value[0], value[1])
    return None


def _tab_pos(tabs, name):
    point = as_point(tabs.get(name))
    if point is None:
        raise ValueError(f"tab '{name}' missing or invalid in tabs.json")
    return point


def compile_action(entry, tabs):
    """Returns (action_type, data), or None for an empty entry. Raises ValueError on errors."""
    if not isinstance(entry, dict) or "type" not in entry:
        raise ValueError("entry needs a 'type' field")
    action_type = entry["type"]
    if action_type == "keys":
        keys = parse_keys(entry.get("keys", ""))
        return ("keys", keys) if keys else None
    if action_type == "click":
        if "tab" in entry:
            return ("click", _tab_pos(tabs, entry["tab"]))
        point = as_point(entry.get("pos"))
        if point is not None:
            return ("click", point)
        raise ValueError("click needs 'tab' or 'pos': [x, y]")
    if action_type == "toggle":
        names = entry.get("tabs")
        if not isinstance(names, list) or not names:
            raise ValueError("toggle needs a non-empty list 'tabs'")
        return ("toggle", (tuple(names), [_tab_pos(tabs, n) for n in names]))
    raise ValueError(f"unknown type '{action_type}' (allowed: keys, click, toggle)")


def build_actions(bindings, button_names, tabs, free_bindings):
    """Returns (actions, number of empty entries). Invalid single entries are logged and skipped."""
    actions, skipped_empty = {}, 0
    for name, entry in bindings.items():
        if name.startswith("_"):      # notes are ignored
            continue
        if not valid_binding_name(name, button_names):
            emit(logging.WARNING, "config_warning", "Invalid name in bindings.json, ignored: %s", name,
                 entry=name, reason="invalid_name")
            continue
        only_resolve = entry.get("only_resolve", True) if isinstance(entry, dict) else True
        if not isinstance(only_resolve, bool):
            emit(logging.WARNING, "config_warning", "Entry '%s' ignored: 'only_resolve' must be true or false", name,
                 entry=name, reason="bad_only_resolve")
            continue
        try:
            compiled = compile_action(entry, tabs)
        except ValueError as e:
            emit(logging.WARNING, "config_warning", "Entry '%s' ignored: %s", name, e,
                 entry=name, reason="invalid_entry")
            continue
        if compiled is None:
            skipped_empty += 1
            continue
        if name not in free_bindings:
            emit(logging.WARNING, "config_warning",
                 "Entry '%s' is not in the free list: Resolve also runs its native function for it", name,
                 entry=name, reason="not_free")
        actions[name] = (compiled[0], compiled[1], only_resolve)
    return actions, skipped_empty


# --------------------------------------------------------------------------
# Config manager: loads bindings.json + tabs.json and reloads them when they change
# --------------------------------------------------------------------------
class ConfigManager:
    def __init__(self, button_names, free_bindings, bindings_path=BINDINGS_PATH, tabs_path=TABS_PATH,
                 interval=RELOAD_INTERVAL):
        self.button_names = button_names
        self.free_bindings = set(free_bindings)
        self.bindings_path = Path(bindings_path)
        self.tabs_path = Path(tabs_path)
        self.interval = interval
        self.actions = {}          # the active bindings, replaced as a whole on every successful load
        self._applied = None       # file signature at the last load attempt
        self._pending = None       # changed signature that must be seen twice before it is loaded
        self._last_check = 0.0

    def _signature(self):
        """Content (bytes) of both files; None for a missing or unreadable file."""
        sig = []
        for path in (self.bindings_path, self.tabs_path):
            try:
                sig.append(path.read_bytes())
            except OSError:
                sig.append(None)
        return tuple(sig)

    def _build(self):
        bindings = read_json(self.bindings_path)
        tabs = read_json(self.tabs_path, required=False)
        if not isinstance(bindings, dict):
            raise ConfigError("bindings.json must contain a JSON object { ... }")
        if not isinstance(tabs, dict):
            raise ConfigError("tabs.json must contain a JSON object { ... }")
        return build_actions(bindings, self.button_names, tabs, self.free_bindings)

    def load(self, initial=False):
        """Load both files. On any error the previous actions stay active (empty at the first start)."""
        signature = self._signature()
        try:
            actions, skipped = self._build()
        except ConfigError as e:
            self._report_failure(initial, str(e))
        except Exception as e:  # noqa: BLE001
            self._report_failure(initial, repr(e))
        else:
            self.actions = actions
            emit(logging.INFO, "config_loaded", "%s%d bindings active, %d empty entries skipped",
                 "" if initial else "Config reloaded: ", len(actions), skipped,
                 active=len(actions), skipped=skipped, reload=not initial)
        self._applied = signature
        self._pending = None

    @staticmethod
    def _report_failure(initial, message):
        if initial:
            emit(logging.ERROR, "config_failed", "Configuration not loaded: %s", message, initial=True)
            emit(logging.ERROR, "start_without_bindings",
                 "Starting without bindings. Fix the file, it is loaded automatically.")
        else:
            emit(logging.ERROR, "config_failed", "Reload failed, keeping previous configuration: %s", message,
                 initial=False)

    def poll(self):
        """Call often. At most once per interval it checks the files and reloads after a change."""
        now = time.monotonic()
        if now - self._last_check < self.interval:
            return
        self._last_check = now
        signature = self._signature()
        if signature == self._applied:
            self._pending = None
            return
        if signature != self._pending:
            # The file just changed. Wait for one more check, so a half-written file is never read.
            self._pending = signature
            return
        self.load()