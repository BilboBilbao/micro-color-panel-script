"""Key specs ('ctrl+alt+f9') become neutral key names. The core knows no pynput and no Windows codes.
Expected values are written by hand from docs/BINDINGS.md section 6."""
import ast

import pytest

from micropanel import BASE
from micropanel.keys import parse_keys

# The key names documented in docs/BINDINGS.md section 6, written by hand (the program's own list is NAMED_KEYS in micropanel/keys.py).
DOCUMENTED = (
    ["ctrl", "alt", "shift", "alt_gr", "enter", "tab", "esc", "space", "backspace", "delete", "home", "end",
     "page_up", "page_down", "insert", "up", "down", "left", "right", "caps_lock", "win"]
    + [f"f{i}" for i in range(1, 21)]
    + ["plus", "minus", "comma", "period", "slash", "backslash", "semicolon", "equals", "quote", "backtick",
       "bracket_left", "bracket_right"]
    + [f"num{i}" for i in range(10)]
    + ["num_plus", "num_minus", "num_multiply", "num_divide", "num_decimal"]
    + ["media_play_pause", "media_next", "media_previous", "media_volume_up", "media_volume_down", "media_mute"]
)


@pytest.mark.parametrize("spec,expected", [
    ("f9", ["f9"]),
    ("ctrl+alt+shift+f9", ["ctrl", "alt", "shift", "f9"]),
    ("Ctrl + Alt + F9", ["ctrl", "alt", "f9"]),            # case and spaces do not matter
    ("ctrl+s", ["ctrl", "s"]),
    ("win+r", ["cmd", "r"]),                               # aliases are resolved in the core
    ("return", ["enter"]),
    ("pageup", ["page_up"]),
    ("del", ["delete"]),
    ("media_mute", ["media_volume_mute"]),
    ("ctrl+plus", ["ctrl", "+"]),                          # symbol names become the character itself
    ("comma", [","]),
    ("bracket_left", ["["]),
    ("num5", ["num5"]),
    ("num_plus", ["num_plus"]),
])
def test_key_spec_gives_neutral_names(spec, expected):
    assert parse_keys(spec) == expected


@pytest.mark.parametrize("spec", ["", "   "])
def test_empty_spec_gives_empty_list(spec):
    assert parse_keys(spec) == []


@pytest.mark.parametrize("spec", [None, 123, ["ctrl"], "ctrl++f", "+", "ctrl+", "+f9"])
def test_invalid_spec_raises(spec):
    with pytest.raises(ValueError):
        parse_keys(spec)


def test_unknown_name_is_named_in_the_error():
    with pytest.raises(ValueError, match="nokey"):
        parse_keys("ctrl+nokey")


@pytest.mark.parametrize("name", DOCUMENTED)
def test_every_documented_name_is_accepted(name):
    assert len(parse_keys(name)) == 1


CORE_MODULES = ["log.py", "keys.py", "profile.py", "decoder.py", "config.py", "engine.py"]        # grows with every core module (core modules import no third-party package)
THIRD_PARTY = {"hid", "pynput", "pyautogui"}


@pytest.mark.parametrize("filename", CORE_MODULES)
def test_core_module_imports_no_third_party_package(filename):
    tree = ast.parse((BASE / "micropanel" / filename).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):                            # also finds imports inside functions
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & THIRD_PARTY
    

IO_MODULES = ["actions.py", "device.py", "app.py", "diagnose.py"]       # I/O modules: they need third-party packages, but only inside functions


@pytest.mark.parametrize("filename", IO_MODULES)
def test_io_module_imports_third_party_packages_only_inside_functions(filename):
    tree = ast.parse((BASE / "micropanel" / filename).read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:                             # module level only: an import inside a function is allowed
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & THIRD_PARTY