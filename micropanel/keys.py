"""Key specs such as 'ctrl+alt+f9' -> neutral key names. Standard library only.

A name with exactly one character is that character ('a', '+'). Every other name is a named key ('ctrl', 'f9').
Aliases ('win', 'return') and symbol names ('plus', 'comma') are resolved here, so the result is always
canonical. Turning a name into a real key of an input library happens in the I/O part (to_pynput, later actions.py).
"""

NAMED_KEYS = frozenset(
    ["ctrl", "alt", "alt_gr", "shift", "cmd", "enter", "tab", "esc", "space", "backspace", "delete",
     "up", "down", "left", "right", "home", "end", "page_up", "page_down", "caps_lock", "insert", "menu",
     "num_lock", "scroll_lock", "pause", "print_screen", "media_play_pause", "media_next", "media_previous",
     "media_volume_up", "media_volume_down", "media_volume_mute"]
    + [f"f{i}" for i in range(1, 21)]
    + [f"num{i}" for i in range(10)]
    + ["num_multiply", "num_plus", "num_minus", "num_decimal", "num_divide"]
)

ALIASES = {
    "altgr": "alt_gr", "win": "cmd", "return": "enter", "del": "delete",
    "ins": "insert", "pageup": "page_up", "pagedown": "page_down",
    "capslock": "caps_lock", "numlock": "num_lock", "scrolllock": "scroll_lock",
    "printscreen": "print_screen", "media_mute": "media_volume_mute",
}

SYMBOLS = {
    "plus": "+", "minus": "-", "comma": ",", "period": ".", "dot": ".",
    "slash": "/", "backslash": "\\", "semicolon": ";", "equals": "=",
    "quote": "'", "backtick": "`", "bracket_left": "[", "bracket_right": "]",
}


def parse_keys(spec):
    """'ctrl+alt+f5' -> ['ctrl', 'alt', 'f5']. Empty text -> []. Invalid -> ValueError."""
    if not isinstance(spec, str):
        raise ValueError("'keys' must be a string")
    spec = spec.lower().replace(" ", "")
    if not spec:
        return []
    out = []
    for part in spec.split("+"):
        part = ALIASES.get(part, part)
        if part in SYMBOLS:
            out.append(SYMBOLS[part])
        elif part in NAMED_KEYS or len(part) == 1:
            out.append(part)
        else:
            raise ValueError(f"unknown key '{part}'")
    return out