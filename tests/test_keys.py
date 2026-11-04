"""Key specs ('ctrl+alt+f9') become neutral key names. The core knows no pynput and no Windows codes.
Expected values are written by hand from docs/BINDINGS.md section 6."""
import pytest

from micropanel.keys import parse_keys

# The key names documented in docs/BINDINGS.md section 6, written by hand (the program's own list is NAMED_KEYS in micropanel/keys.py).
DOCUMENTED = (
    ["ctrl", "alt", "shift", "alt_gr", "enter", "tab", "esc", "space", "backspace", "delete", "home", "end",
     "page_up", "page_down", "insert", "up", "down", "left", "right", "caps_lock", "win",
     "menu", "num_lock", "scroll_lock", "pause", "print_screen", "cmd"]
    + [f"f{i}" for i in range(1, 21)]
    + ["plus", "minus", "comma", "period", "slash", "backslash", "semicolon", "equals", "quote", "backtick",
       "bracket_left", "bracket_right"]
    + [f"num{i}" for i in range(10)]
    + ["num_plus", "num_minus", "num_multiply", "num_divide", "num_decimal"]
    + ["media_play_pause", "media_next", "media_previous", "media_volume_up", "media_volume_down", "media_mute"]
    + ["return", "del", "pageup", "pagedown", "ins", "altgr", "capslock", "numlock", "scrolllock", "printscreen", "dot"]
)

# Documented name -> the one key it must give. Every documented name that is not listed here must come out unchanged.
CHANGED = {
    "win": "cmd", "media_mute": "media_volume_mute",
    "plus": "+", "minus": "-", "comma": ",", "period": ".", "slash": "/", "backslash": "\\",
    "semicolon": ";", "equals": "=", "quote": "'", "backtick": "`", "bracket_left": "[", "bracket_right": "]",
    "return": "enter", "del": "delete", "pageup": "page_up", "pagedown": "page_down", "ins": "insert",
    "altgr": "alt_gr", "capslock": "caps_lock", "numlock": "num_lock", "scrolllock": "scroll_lock",
    "printscreen": "print_screen", "dot": ".",
}


@pytest.mark.parametrize("spec,expected", [
    ("f9", ["f9"]),
    ("ctrl+alt+shift+f9", ["ctrl", "alt", "shift", "f9"]),
    ("Ctrl + Alt + F9", ["ctrl", "alt", "f9"]),            # case and spaces do not matter
    ("ctrl+s", ["ctrl", "s"]),
    ("win+r", ["cmd", "r"]),                               # aliases are resolved in the core
    ("ctrl+plus", ["ctrl", "+"]),                          # symbol names become the character itself
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


def test_every_documented_name_gives_its_key():
    wrong = {}
    for name in DOCUMENTED:
        result = parse_keys(name)
        if result != [CHANGED.get(name, name)]:
            wrong[name] = result
    assert wrong == {}                    # one failure lists every wrong name