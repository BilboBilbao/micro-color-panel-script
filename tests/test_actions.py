"""press_keys: every key that was pressed is released again. to_pynput and execute: neutral names become real keys."""
import json
import logging
import sys
import types

import pytest

import micropanel.actions as actions
from micropanel.config import ConfigManager
from helpers import Controller


class _KeyNames(type):
    def __getattr__(cls, name):                 # FakeKey.ctrl, FakeKey.f9 ... exist for every name
        if name.startswith("__"):
            raise AttributeError(name)
        return f"Key.{name}"


class FakeKey(metaclass=_KeyNames):
    pass


class FakeKeyCode:
    @staticmethod
    def from_vk(vk):
        return f"vk{vk}"


@pytest.fixture
def fake_pynput(monkeypatch):
    """Stands in for pynput.keyboard (the real package is never imported): Key.<name> gives "Key.<name>",
    KeyCode.from_vk(n) gives "vk<n>"."""
    keyboard = types.ModuleType("pynput.keyboard")
    setattr(keyboard, "Key", FakeKey)                 # setattr: the type checker does not know these names
    setattr(keyboard, "KeyCode", FakeKeyCode)
    package = types.ModuleType("pynput")
    setattr(package, "keyboard", keyboard)
    monkeypatch.setitem(sys.modules, "pynput", package)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", keyboard)


class FailingController(Controller):
    def __init__(self, fail_press=None, fail_release=None):
        super().__init__()
        self.fail_press, self.fail_release = fail_press, fail_release

    def press(self, key):
        if key == self.fail_press:
            raise RuntimeError("press failed")
        super().press(key)

    def release(self, key):
        super().release(key)
        if key == self.fail_release:
            raise RuntimeError("release failed")


def released(controller):
    return [key for event, key in controller.events if event == "release"]


def test_keys_are_released_in_reverse_order(monkeypatch):
    kb = FailingController()
    monkeypatch.setattr(actions, "_keyboard", kb)
    actions.press_keys(["a", "b", "c"])
    assert released(kb) == ["c", "b", "a"]


def test_pressed_keys_are_released_when_a_press_fails(monkeypatch):
    kb = FailingController(fail_press="c")
    monkeypatch.setattr(actions, "_keyboard", kb)
    try:
        actions.press_keys(["a", "b", "c"])
    except RuntimeError:
        pass
    assert released(kb) == ["b", "a"]


def test_press_keys_releases_all_keys_when_one_release_fails(monkeypatch):   # B13
    kb = FailingController(fail_release="b")
    monkeypatch.setattr(actions, "_keyboard", kb)
    try:
        actions.press_keys(["a", "b", "c"])
    except RuntimeError:
        pass
    assert set(released(kb)) == {"a", "b", "c"}


@pytest.mark.parametrize("name,expected", [
    ("f9", "Key.f9"), ("cmd", "Key.cmd"), ("a", "a"), ("+", "+"),
    ("num0", "vk96"), ("num5", "vk101"), ("num9", "vk105"),             # 0x60, 0x65, 0x69
    ("num_multiply", "vk106"), ("num_plus", "vk107"), ("num_minus", "vk109"),       # 0x6A, 0x6B, 0x6D
    ("num_decimal", "vk110"), ("num_divide", "vk111"),                  # 0x6E, 0x6F
])
def test_to_pynput(fake_pynput, name, expected):
    assert actions.to_pynput(name) == expected


def test_execute_translates_keys_before_pressing(monkeypatch, fake_pynput):
    kb = Controller()
    monkeypatch.setattr(actions, "_keyboard", kb)
    actions.execute("user", ("keys", ["ctrl", "f9"], False))                 # False: no foreground check
    assert kb.events == [("press", "Key.ctrl"), ("press", "Key.f9"),
                         ("release", "Key.f9"), ("release", "Key.ctrl")]


def action_results(caplog):
    """The 'result' field of every logged action, in order."""
    return [r.fields["result"] for r in caplog.records if getattr(r, "fields", {}).get("event") == "action"]


@pytest.mark.parametrize("keyboard,error", [
    (FailingController(fail_press="b"), "press failed"),
    (FailingController(fail_release="b"), "release failed"),
], ids=["press_error", "release_error"])
def test_key_errors_are_passed_on(monkeypatch, keyboard, error):
    monkeypatch.setattr(actions, "_keyboard", keyboard)
    with pytest.raises(RuntimeError, match=error):
        actions.press_keys(["a", "b", "c"])


def test_empty_key_list_presses_nothing(monkeypatch):
    kb = Controller()
    monkeypatch.setattr(actions, "_keyboard", kb)
    actions.press_keys([])
    assert kb.events == []


def screen(left, top, right, bottom):
    return {"left": left, "top": top, "right": right, "bottom": bottom, "primary": False, "scale": 100}


# Four monitors without overlap: main (0,0 to 1920,1080), left, above and right of it. Written by hand.
MONITORS = [screen(0, 0, 1920, 1080), screen(-1920, -600, 0, 480), screen(0, -1200, 1920, 0), screen(1920, 0, 5760, 2160)]


def shifted(*offsets):
    """Landing function for FakeMouse: the n-th move lands (dx, dy) pixels away from where it was sent, as listed in
    `offsets`; every later move lands exactly."""
    pending = list(offsets)

    def landing(pos):
        dx, dy = pending.pop(0) if pending else (0, 0)
        return pos[0] + dx, pos[1] + dy
    return landing


class FakeMouse:
    """Stands in for pynput.mouse.Controller: every move, click and sleep goes into one shared list, in order.
    The position read back is where the cursor landed: the last position set, moved by `landing` (default: exactly there).
    Never touches the real mouse."""

    def __init__(self, calls, start=(500, 500), click_error=None, landing=None):
        self.calls, self.click_error = calls, click_error
        self.landing = landing or (lambda pos: pos)
        self.pos = start

    @property
    def position(self):
        return self.pos

    @position.setter
    def position(self, pos):
        self.calls.append(("move", tuple(pos)))
        self.pos = self.landing(tuple(pos))

    def click(self, button, count=1):
        self.calls.append(("click", button, count))
        if self.click_error is not None:
            raise self.click_error


@pytest.fixture
def fake_mouse(monkeypatch):
    """install(start, click_error, landing, monitors) -> the list of calls. Replaces pynput.mouse (Button.left is "left"),
    the pause and the monitor list (get_monitors). pyautogui is set to None: importing it raises ImportError,
    so no test can ever click for real."""
    def install(start=(500, 500), click_error=None, landing=None, monitors=MONITORS):
        calls = []
        mouse = types.ModuleType("pynput.mouse")
        setattr(mouse, "Controller", lambda: FakeMouse(calls, start, click_error, landing))
        setattr(mouse, "Button", types.SimpleNamespace(left="left"))
        package = types.ModuleType("pynput")
        setattr(package, "mouse", mouse)
        monkeypatch.setitem(sys.modules, "pynput", package)
        monkeypatch.setitem(sys.modules, "pynput.mouse", mouse)
        monkeypatch.setitem(sys.modules, "pyautogui", None)
        monkeypatch.setattr(actions, "sleep", lambda seconds: calls.append(("sleep", seconds)))
        monkeypatch.setattr(actions, "get_monitors", lambda: monitors)
        return calls
    return install


def test_click_at_returns_the_mouse_to_its_start(fake_mouse):
    calls = fake_mouse(start=(500, 400))
    actions.click_at((10, 20))
    assert calls == [("move", (10, 20)), ("click", "left", 1), ("sleep", 0.05), ("move", (500, 400))]


@pytest.mark.parametrize("point", [(-1500, -300), (200, -1100), (5000, 1700)],
                         ids=["left_of_primary", "above_primary", "right_monitor"])
def test_click_at_accepts_points_on_any_monitor(fake_mouse, point):
    calls = fake_mouse(start=(500, 400))
    actions.click_at(point)
    assert calls == [("move", point), ("click", "left", 1), ("sleep", 0.05), ("move", (500, 400))]


def test_click_at_returns_the_mouse_even_when_the_click_fails(fake_mouse):          # RV-3 (CONS-003)
    calls = fake_mouse(start=(500, 400), click_error=RuntimeError("click failed"))
    with pytest.raises(RuntimeError, match="click failed"):
        actions.click_at((10, 20))
    assert calls == [("move", (10, 20)), ("click", "left", 1), ("move", (500, 400))]      # no pause after a failed click


def test_click_error_still_returns_the_mouse_through_execute(fake_mouse, caplog):   # RV-3
    caplog.set_level(logging.INFO)
    calls = fake_mouse(start=(500, 400), click_error=RuntimeError("click failed"))
    actions.execute("user", ("click", (30, 40), False))                      # must not raise
    assert action_results(caplog) == ["error"]
    assert calls == [("move", (30, 40)), ("click", "left", 1), ("move", (500, 400))]


# ---- click guard (B22): the point must lie on a monitor and the cursor must land there ----
@pytest.mark.parametrize("point", [(99999, 99999), (1920, -1), (-1921, 0)],
                         ids=["far_away", "gap_between_monitors", "left_of_all"])
def test_click_outside_all_monitors_is_blocked(fake_mouse, point):
    calls = fake_mouse()
    with pytest.raises(actions.ClickBlocked) as blocked:
        actions.click_at(point)
    assert blocked.value.result == "blocked_position"
    assert calls == []                                                # the mouse was not even moved


def test_empty_monitor_list_blocks_the_click(fake_mouse):
    calls = fake_mouse(monitors=[])
    with pytest.raises(actions.ClickBlocked) as blocked:
        actions.click_at((10, 20))
    assert blocked.value.result == "blocked_position"
    assert calls == []


def test_monitor_list_is_read_fresh_for_every_click(fake_mouse, monkeypatch):
    calls = fake_mouse(start=(500, 400))
    layouts = [MONITORS, MONITORS[:1]]                                # the right monitor is unplugged after the first click
    asked = []

    def get_monitors():
        asked.append(1)
        return layouts[len(asked) - 1]

    monkeypatch.setattr(actions, "get_monitors", get_monitors)
    actions.click_at((2500, 500))
    with pytest.raises(actions.ClickBlocked):
        actions.click_at((2500, 500))
    assert len(asked) == 2
    assert calls == [("move", (2500, 500)), ("click", "left", 1), ("sleep", 0.05), ("move", (500, 400))]   # nothing for click 2


def test_monitor_list_error_is_an_action_error(fake_mouse, monkeypatch, clean_toggle, caplog):
    caplog.set_level(logging.INFO)
    calls = fake_mouse()

    def failing():
        raise OSError("monitor list failed")

    monkeypatch.setattr(actions, "get_monitors", failing)
    actions.execute("user", ("toggle", (("a", "b"), [(10, 20), (30, 40)]), False))     # must not raise
    assert action_results(caplog) == ["error"]
    assert actions.toggle_state == {} and calls == []


@pytest.mark.parametrize("offset", [(1, 0), (0, -1)], ids=["one_pixel_right", "one_pixel_up"])
def test_cursor_within_one_pixel_still_clicks(fake_mouse, offset):               # characterization: green at once
    calls = fake_mouse(start=(500, 400), landing=shifted(offset))
    actions.click_at((10, 20))
    assert calls == [("move", (10, 20)), ("click", "left", 1), ("sleep", 0.05), ("move", (500, 400))]


@pytest.mark.parametrize("offset", [(2, 0), (0, 2)], ids=["two_pixels_right", "two_pixels_down"])
def test_cursor_off_by_two_pixels_blocks_the_click(fake_mouse, offset):
    calls = fake_mouse(start=(500, 400), landing=shifted(offset, offset))
    with pytest.raises(actions.ClickBlocked) as blocked:
        actions.click_at((10, 20))
    assert blocked.value.result == "blocked_cursor"
    assert calls == [("move", (10, 20)), ("move", (10, 20)), ("move", (500, 400))]   # two tries, no click, back at the start


def test_single_cursor_disturbance_is_fixed_by_one_retry(fake_mouse):
    calls = fake_mouse(start=(500, 400), landing=shifted((5, 0)))
    actions.click_at((10, 20))
    assert calls == [("move", (10, 20)), ("move", (10, 20)), ("click", "left", 1), ("sleep", 0.05), ("move", (500, 400))]


@pytest.mark.parametrize("positions,landing,result", [
    ([(99999, 99999), (10, 20)], None, "blocked_position"),
    ([(10, 20), (30, 40)], shifted((2, 0), (2, 0)), "blocked_cursor"),
], ids=["outside_all_monitors", "cursor_does_not_land"])
def test_blocked_clicks_are_logged_and_the_toggle_stays(fake_mouse, clean_toggle, caplog, positions, landing, result):
    caplog.set_level(logging.INFO)
    calls = fake_mouse(start=(500, 400), landing=landing)
    actions.execute("user", ("toggle", (("a", "b"), positions), False))              # must not raise
    assert action_results(caplog) == [result]
    levels = [r.levelno for r in caplog.records if getattr(r, "fields", {}).get("event") == "action"]
    assert levels == [logging.WARNING]
    assert actions.toggle_state == {}
    assert ("click", "left", 1) not in calls


TOGGLE = ("toggle", (("a", "b"), [(1, 1), (2, 2)]), False)           # False: no foreground check


@pytest.fixture
def clean_toggle():
    actions.toggle_state.clear()
    yield
    actions.toggle_state.clear()


@pytest.fixture
def clicks(monkeypatch, clean_toggle):
    """Replaces the real click by a list that records the positions."""
    recorded = []
    monkeypatch.setattr(actions, "click_at", recorded.append)
    return recorded


def test_toggle_alternates_between_the_tab_positions(clicks):
    for _ in range(3):
        actions.execute("user", TOGGLE)
    assert clicks == [(1, 1), (2, 2), (1, 1)]


def test_bindings_with_the_same_tab_group_share_one_toggle_state(clicks):
    actions.execute("user", TOGGLE)
    actions.execute("shift_up+user", TOGGLE)
    assert clicks == [(1, 1), (2, 2)]


def test_click_action_clicks_once_at_the_position(clicks):
    actions.execute("user", ("click", (30, 40), False))
    assert clicks == [(30, 40)]


@pytest.mark.parametrize("foreground,result", [
    ((False, "SecretProgram.exe"), "blocked_foreground"),
    ((False, None), "blocked_unknown"),
], ids=["other_program", "unknown"])
def test_action_outside_resolve_is_blocked(monkeypatch, caplog, clicks, foreground, result):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(actions, "resolve_is_foreground", lambda: foreground)
    actions.execute("user", ("toggle", TOGGLE[1], True))                  # True: only in Resolve
    assert clicks == [] and actions.toggle_state == {}                    # no click, no state change
    assert action_results(caplog) == [result]
    assert "SecretProgram" not in caplog.text                        # the other program's name is never logged
    assert all("SecretProgram" not in str(r.fields) for r in caplog.records if hasattr(r, "fields"))


def test_action_in_resolve_runs(monkeypatch, clicks):
    monkeypatch.setattr(actions, "resolve_is_foreground", lambda: (True, "Resolve.exe"))
    actions.execute("user", ("click", (30, 40), True))
    assert clicks == [(30, 40)]


def test_action_error_is_logged_and_does_not_advance_the_toggle(monkeypatch, caplog, clean_toggle):
    caplog.set_level(logging.INFO)

    def failing(_pos):
        raise RuntimeError("click failed")

    monkeypatch.setattr(actions, "click_at", failing)
    actions.execute("user", TOGGLE)                                       # must not raise
    assert actions.toggle_state == {}
    assert action_results(caplog) == ["error"]
    

def test_toggle_state_survives_a_tabs_reload_and_uses_the_new_point(tmp_path, profile, clicks):
    bindings, tabs = tmp_path / "bindings.json", tmp_path / "tabs.json"
    bindings.write_text(json.dumps({"user": {"type": "toggle", "tabs": ["a", "b"], "only_resolve": False}}),
                        encoding="utf-8")
    tabs.write_text(json.dumps({"a": [10, 20], "b": [30, 40]}), encoding="utf-8")
    config = ConfigManager(set(profile.buttons), profile.free_bindings, bindings, tabs, interval=0)
    config.load(initial=True)
    actions.execute("user", config.actions["user"])                  # clicks tab a
    tabs.write_text(json.dumps({"a": [110, 120], "b": [130, 140]}), encoding="utf-8")   # longer text: the size changes
    config.poll()                                                     # sees the change
    config.poll()                                                     # sees it a second time and loads
    actions.execute("user", config.actions["user"])                  # state kept: clicks tab b, at the new point
    assert clicks == [(10, 20), (130, 140)]