"""Running actions: keys, mouse click, toggle. Needs the third-party packages pynput and pyautogui, imported inside
the functions. Whoever uses this module must call set_dpi_awareness() (micropanel/platform/windows.py) before
pyautogui is imported anywhere: otherwise Windows refuses per-monitor awareness and clicks can miss."""
import logging

from micropanel.log import emit
from micropanel.platform.windows import RESOLVE_EXE, resolve_is_foreground

# --------------------------------------------------------------------------
# Neutral key names (micropanel/keys.py) -> real keys (pynput)
# --------------------------------------------------------------------------
NUMPAD_VK = {**{f"num{i}": 0x60 + i for i in range(10)},
             "num_multiply": 0x6A, "num_plus": 0x6B, "num_minus": 0x6D, "num_decimal": 0x6E, "num_divide": 0x6F}

_keyboard = None


def _get_keyboard():
    """The keyboard controller. It is created at the first key press (not at import) and then reused."""
    global _keyboard
    if _keyboard is None:
        from pynput.keyboard import Controller
        _keyboard = Controller()
    return _keyboard


def to_pynput(name):
    """Neutral key name -> pynput key. A name that pynput does not know on this system
    raises AttributeError; execute() logs that as an action error."""
    from pynput.keyboard import Key, KeyCode
    if len(name) == 1:
        return name
    if name in NUMPAD_VK:
        return KeyCode.from_vk(NUMPAD_VK[name])
    return getattr(Key, name)


def press_keys(keys):
    kb = _get_keyboard()
    pressed = []
    try:
        for k in keys:
            kb.press(k)
            pressed.append(k)
    finally:                      # every pressed key gets its own release attempt
        release_error = None
        for k in reversed(pressed):
            try:
                kb.release(k)
            except Exception as e:  # noqa: BLE001
                if release_error is None:
                    release_error = e
        if release_error is not None:
            raise release_error


def configure_mouse():
    """Settings of pyautogui, once at start (called by app.setup)."""
    import pyautogui
    pyautogui.PAUSE = 0.05
    # FAILSAFE stays off on purpose: with it on, pyautogui raises an exception when the cursor is in a screen corner.
    # Every action is one instant move or click and the cursor goes back afterwards, and a calibrated click point
    # may legitimately lie in a corner, so the abort would only produce false errors.
    pyautogui.FAILSAFE = False


def click_at(pos):
    import pyautogui
    x0, y0 = pyautogui.position()
    try:
        pyautogui.click(*pos)
    finally:                      # the cursor goes back even when the click fails
        pyautogui.moveTo(x0, y0)


# --------------------------------------------------------------------------
# Execute actions
# --------------------------------------------------------------------------
toggle_state = {}   # one state per tab group, not per binding. Survives config reloads.


def execute(name, action):
    action_type, data, only_resolve = action
    if only_resolve:
        ok, foreground = resolve_is_foreground()
        if not ok:
            if foreground is None:
                emit(logging.WARNING, "action", "%s blocked: could not determine the foreground program", name,
                     binding=name, result="blocked_unknown")
            else:
                # the name of the other program is deliberately not logged
                emit(logging.INFO, "action", "%s blocked: foreground is other_program, not %s", name, RESOLVE_EXE,
                     binding=name, result="blocked_foreground")
            return
    try:
        if action_type == "keys":
            press_keys([to_pynput(k) for k in data])
        elif action_type == "click":
            click_at(data)
        elif action_type == "toggle":
            names, positions = data
            i = toggle_state.get(names, 0) % len(names)
            click_at(positions[i])
            toggle_state[names] = (i + 1) % len(names)
    except Exception as e:  # noqa: BLE001
        emit(logging.ERROR, "action", "Error in %s: %r", name, e,
             binding=name, type=action_type, result="error")
        return
    emit(logging.INFO, "action", "-> %s (%s)", name, action_type,
         binding=name, type=action_type, result="executed")