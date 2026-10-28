"""Judging functions, safety gates and the run of the assisted diagnose steps (micropanel/diagnose.py).
Pure logic: no hardware, no mouse, no Resolve. Expected values are written by hand from the old part B scenarios
and from docs/DIAGNOSTICS.md."""
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import micropanel.actions as actions
from helpers import motion_report
from micropanel import diagnose as st
from micropanel.keys import NAMED_KEYS
from micropanel.log import log


def scripted(answers):
    """ask_text replacement: hands out the prepared answers and fails if it is asked more than prepared."""
    pending = list(answers)

    def ask(prompt):
        if not pending:
            raise AssertionError(f"asked more questions than expected: {prompt!r}")
        return pending.pop(0)
    return ask


def texts_and_statuses(rows):
    return [status for status, _text in rows], " | ".join(text for _status, text in rows)


# --------------------------------------------------------------------------
# Click points, mouse, DPI
# --------------------------------------------------------------------------
ONE = [{"left": 0, "top": 0, "right": 1920, "bottom": 1080, "primary": True, "scale": 125}]
TWO = ONE + [{"left": 1920, "top": 0, "right": 3840, "bottom": 1080, "primary": False, "scale": 100}]


@pytest.mark.parametrize("monitors,points,statuses,part", [
    (ONE, {"tab 'a'": (100, 100), "tab 'b'": (1919, 1079)}, ["PASS", "PASS"], None),
    (ONE, {"tab 'a'": (100, 100), "tab 'b'": (2069, 675), "tab 'c'": (1920, 10)},
     ["PASS", "FAIL", "FAIL", "INFO"], "another computer"),                # the right edge (x=1920) is outside
    (TWO, {"tab 'a'": (2069, 675)}, ["PASS"], "monitor 2"),
], ids=["inside", "outside_gives_hint", "second_monitor"])
def test_judge_click_points(monitors, points, statuses, part):
    rows = st.judge_click_points(monitors, points)
    assert [status for status, _text in rows] == statuses
    if part:
        assert part in rows[-1][1]


WANTED = {"tab 'a'": (100, 100), "tab 'b'": (200, 200)}


@pytest.mark.parametrize("got,statuses,part", [
    ({"tab 'a'": (100, 100), "tab 'b'": (201, 199)}, ["PASS", "PASS"], None),     # 1 pixel is within the tolerance
    ({"tab 'a'": (100, 100), "tab 'b'": (202, 200)}, ["PASS", "FAIL"], "+2"),     # 2 pixels fail and name the deviation
    ({"tab 'a'": None}, ["FAIL", "FAIL"], None),                                  # unreadable or missing position
], ids=["one_pixel_off", "two_pixels_off", "unreadable"])
def test_judge_moves(got, statuses, part):
    rows = st.judge_moves(WANTED, got)
    assert [status for status, _text in rows] == statuses
    if part:
        assert part in rows[1][1]


@pytest.mark.parametrize("end,status", [((5, 5), "PASS"), ((6, 4), "PASS"), ((9, 5), "FAIL"), (None, "FAIL")],
                         ids=["same", "one_pixel_off", "far_away", "unreadable"])
def test_judge_return(end, status):
    assert st.judge_return((5, 5), end)[0] == status


@pytest.mark.parametrize("value,status,part", [(2, "PASS", None), (1, "FAIL", "system"), (0, "FAIL", None),
                                               (None, "WARN", None)],
                         ids=["per_monitor", "system_aware", "unaware", "unknown"])
def test_judge_dpi(value, status, part):
    got, text = st.judge_dpi(value)
    assert got == status
    if part:
        assert part in text


class FakeMouse:
    """Simulated pyautogui: records moves, can clamp x at a screen edge, be off once or fail a read; never clicks."""

    def __init__(self, start=(500, 500), clamp_x=None, off_once=None, fail_on_read=None):
        self.pos, self.moves, self.reads = list(start), [], 0
        self.clamp_x, self.off_once, self.fail_on_read = clamp_x, dict(off_once or {}), fail_on_read

    def position(self):
        self.reads += 1
        if self.fail_on_read and self.reads == self.fail_on_read:
            raise RuntimeError("simulated read error")
        return SimpleNamespace(x=self.pos[0], y=self.pos[1])

    def moveTo(self, x, y):
        self.moves.append((x, y))
        if self.clamp_x is not None:
            x = min(x, self.clamp_x)
        if (x, y) in self.off_once:
            x, y = x + self.off_once.pop((x, y)), y
        self.pos = [x, y]

    def click(self, *_args):
        raise AssertionError("the mouse test must never click")


POINTS = {"tab 'a'": (100, 120), "tab 'b'": (300, 340)}


def mouse_path(monkeypatch, gui):
    monkeypatch.setitem(sys.modules, "pyautogui", gui)         # the package is imported inside move_mouse_through
    return st.move_mouse_through(POINTS, sleep=lambda _seconds: None)


def test_mouse_path_reads_every_point_back_and_returns_to_the_start(monkeypatch):
    start, got, end = mouse_path(monkeypatch, FakeMouse())
    assert start == (500, 500) and end == (500, 500)
    assert got == POINTS
    assert [status for status, _text in st.judge_moves(POINTS, got)] == ["PASS", "PASS"]


def test_mouse_path_point_clamped_at_the_screen_edge_fails_after_two_tries(monkeypatch):
    gui = FakeMouse(start=(200, 200), clamp_x=250)
    _start, got, end = mouse_path(monkeypatch, gui)
    assert [status for status, _text in st.judge_moves(POINTS, got)] == ["PASS", "FAIL"]
    assert gui.moves.count((300, 340)) == 2
    assert end == (200, 200)                       # back at the start even after a failure


def test_mouse_path_single_disturbance_is_fixed_by_one_retry(monkeypatch):
    gui = FakeMouse(off_once={(100, 120): 5})
    _start, got, _end = mouse_path(monkeypatch, gui)
    assert got["tab 'a'"] == (100, 120)
    assert gui.moves.count((100, 120)) == 2


def test_mouse_path_error_is_passed_on_and_the_mouse_is_put_back(monkeypatch):
    gui = FakeMouse(fail_on_read=3)
    with pytest.raises(RuntimeError):
        mouse_path(monkeypatch, gui)
    assert gui.moves[-1] == (500, 500)


# --------------------------------------------------------------------------
# --full: evaluation of one input and of the whole run
# --------------------------------------------------------------------------
@pytest.mark.parametrize("status,sequence,result", [
    ("ok", [{"user"}, set()], ("ok", "")),
    ("timeout", [{"user"}, set()], ("ok_no_release", "")),
    ("ok", [{"undo"}, set()], ("wrong", "undo")),
    ("ok", [{"user"}, {"user", "undo"}, set()], ("wrong", "undo, user")),
    ("timeout", [], ("none", "")),
    ("skipped", [], ("skipped", "")),
    ("aborted", [], ("aborted", "")),
], ids=["clean_press", "no_release_seen", "other_input", "two_inputs", "no_report", "skipped", "aborted"])
def test_evaluate_full_input(status, sequence, result):
    assert st.evaluate_full_input("user", status, sequence) == result


@pytest.mark.parametrize("outcomes,total,statuses,part", [
    ([(f"b{i}", "ok", "") for i in range(52)], 52, ["PASS"], "All inputs: 52 of 52 recognized correctly"),
    ([("a", "ok", ""), ("b", "wrong", "undo"), ("c", "none", ""), ("d", "skipped", "")], 4,
     ["FAIL", "WARN", "FAIL"], "'c'"),
    ([("a", "ok", ""), ("b", "none", "")], 2, ["WARN", "WARN"], "1 without report"),
    ([("a", "ok", ""), ("b", "skipped", "")], 2, ["SKIP"], "1 skipped"),
    ([("a", "ok", ""), ("b", "aborted", "")], 5, ["SKIP"], "4 not reached"),
    ([("a", "ok_no_release", "")], 1, ["WARN", "WARN"], "1 without seen release"),
], ids=["all_52_ok", "mixed", "no_report", "only_skipped", "aborted", "no_release_seen"])
def test_summarize_full(outcomes, total, statuses, part):
    got, text = texts_and_statuses(st.summarize_full(outcomes, total))
    assert got == statuses
    assert part in text


# --------------------------------------------------------------------------
# --rotary: judging one movement and the whole run
# --------------------------------------------------------------------------
K, K2, T, T2, R = "ylift_knob_turn", "ygamma_knob_turn", "lift_trackball", "gamma_trackball", "gain_ring"


def reports(profile, name, axis, number, count):
    """`count` motion reports that carry `number` on one channel of one element (the position comes from the profile)."""
    channel = next(c for c in profile.rotary_channels[name][1] if c.axis == axis)
    return [motion_report(channel.report, {channel.byte: (channel.width, number)})] * count


# id, element, direction, reports, expected outcome. Signs as in the recordings: knob and ring right = positive,
# trackball right = negative x, away from you (up) = negative y.
ROTARY_CASES = [
    ("knob_right_positive", K, "right", lambda p: reports(p, K, "turn", 1080, 5), "ok"),
    ("knob_left_negative", K, "left", lambda p: reports(p, K, "turn", -1080, 5), "ok"),
    ("knob_right_negative_numbers", K, "right", lambda p: reports(p, K, "turn", -1080, 5), "wrong_sign"),
    ("other_knob_moved", K, "right", lambda p: reports(p, K2, "turn", 1080, 5), "wrong_channel"),
    ("half_on_another_knob", K, "right",
     lambda p: reports(p, K, "turn", 1080, 10) + reports(p, K2, "turn", 1080, 5), "crosstalk"),
    ("thirty_percent_on_another_knob", K, "right",
     lambda p: reports(p, K, "turn", 1080, 10) + reports(p, K2, "turn", 1080, 3), "ok"),
    ("ball_right_with_y_jitter", T, "right",
     lambda p: reports(p, T, "x", -16, 50) + reports(p, T, "y", 16, 5), "ok"),
    ("ball_right_positive_x", T, "right", lambda p: reports(p, T, "x", 16, 50), "wrong_sign"),
    ("ball_up_negative_y", T, "up", lambda p: reports(p, T, "y", -16, 50), "ok"),
    ("ball_up_only_x_moves", T, "up", lambda p: reports(p, T, "x", -16, 50), "wrong_channel"),
    ("diagonal_both_axes", T, "upright",
     lambda p: reports(p, T, "x", -16, 50) + reports(p, T, "y", -16, 50), "ok"),
    ("diagonal_one_axis_only", T, "upright", lambda p: reports(p, T, "x", -16, 50), "weak_axis"),
    ("diagonal_ten_percent_on_one_axis", T, "upright",
     lambda p: reports(p, T, "x", -16, 50) + reports(p, T, "y", -16, 5), "weak_axis"),
    ("diagonal_wrong_y_sign", T, "upright",
     lambda p: reports(p, T, "x", -16, 50) + reports(p, T, "y", 16, 50), "wrong_sign"),
    ("diagonal_y_on_another_ball", T, "upright",
     lambda p: reports(p, T, "x", -16, 50) + reports(p, T2, "y", -16, 50), "crosstalk"),
    ("ring_right_plus_16", R, "right", lambda p: reports(p, R, "turn", 16, 30), "ok"),
    ("ring_left_minus_16", R, "left", lambda p: reports(p, R, "turn", -16, 30), "ok"),
    ("ring_left_plus_16", R, "left", lambda p: reports(p, R, "turn", 16, 30), "wrong_sign"),
]
DETAIL_PARTS = {"other_knob_moved": "ygamma_knob_turn.turn", "diagonal_y_on_another_ball": "gamma_trackball.y"}


@pytest.mark.parametrize("case_id,name,direction,build,outcome", ROTARY_CASES, ids=[c[0] for c in ROTARY_CASES])
def test_evaluate_rotary(profile, case_id, name, direction, build, outcome):
    got, detail = st.evaluate_rotary(profile, name, direction, build(profile))
    assert got == outcome
    if case_id in DETAIL_PARTS:
        assert DETAIL_PARTS[case_id] in detail           # the detail names the element that moved


@pytest.mark.parametrize("given", [[], [motion_report(5, {})], [motion_report(2, {})]],
                         ids=["no_reports", "all_zero_motion_report", "button_report"])
def test_rotary_without_motion(profile, given):
    assert st.evaluate_rotary(profile, K, "right", given) == ("none", "")


@pytest.mark.parametrize("name,direction,expected", [
    (T, "upright", {"x": -1, "y": -1}), (K, "right", {"turn": 1}), (K, "left", {"turn": -1}),
], ids=["trackball_diagonal", "knob_right", "knob_left"])
def test_expected_signs(profile, name, direction, expected):
    assert st.expected_signs(profile.rotary_channels[name][1], direction) == expected


def test_rotary_plan(profile):
    plan = st.rotary_plan(profile)
    assert len(plan) == 18
    assert sum(len(gestures) for _name, _ctype, gestures in plan) == 39      # 12 knobs and 3 rings x 2, 3 balls x 3
    assert plan[0][0] == "ylift_knob_turn"


OK5 = [("a", "ok", "")] * 5


@pytest.mark.parametrize("outcomes,total,statuses,part", [
    (OK5, 5, ["PASS"], "Rotary elements: 5 of 5 steps as expected"),
    (OK5 + [("b", "wrong_sign", "turn moved -5, expected +")], 6, ["FAIL", "FAIL"], "Rotary b"),
    (OK5 + [("b", "none", "")], 6, ["WARN", "WARN"], "no motion report"),
    (OK5 + [("b", "weak_axis", "x")], 6, ["WARN", "WARN"], "Rotary b: x"),
    (OK5 + [("b", "crosstalk", "x")], 6, ["FAIL", "FAIL"], "other channels moved as well"),
    ([("a", "skipped", "")], 1, ["SKIP"], "1 skipped"),
    (OK5 + [("b", "aborted", "")], 9, ["SKIP"], "4 not reached"),
], ids=["all_ok", "wrong_sign", "no_report", "weak_axis", "crosstalk", "only_skipped", "aborted"])
def test_summarize_rotary(outcomes, total, statuses, part):
    got, text = texts_and_statuses(st.summarize_rotary(outcomes, total))
    assert got == statuses
    assert part in text


# --------------------------------------------------------------------------
# Answers and actions of the action test
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("j", True), ("Ja", True), (" y ", True), ("YES", True), ("n", False), ("Nein", False), ("no", False),
    ("", None), ("vielleicht", None),
])
def test_parse_yes_no(text, expected):
    assert st.parse_yes_no(text) is expected


@pytest.mark.parametrize("text,expected", [("YES", True), (" yes ", True), ("y", False), ("", False), ("j", False)])
def test_parse_yes_confirms_only_the_word_yes(text, expected):
    assert st.parse_yes(text) is expected


@pytest.mark.parametrize("text,expected", [("1", 0), (" 3 ", 2), ("0", None), ("4", None), ("x", None), ("", None)])
def test_parse_choice(text, expected):
    assert st.parse_choice(text, 3) == expected


ACTIONS = {"a": ("keys", [1], True), "b": ("click", (1, 2), True),
           "c": ("toggle", (("x", "y"), [(1, 2), (3, 4)]), True)}


@pytest.mark.parametrize("bindings,expected", [(ACTIONS, ["b", "c"]), ({}, [])], ids=["never_keys", "no_bindings"])
def test_eligible_action_bindings(bindings, expected):
    assert st.eligible_action_bindings(bindings) == expected


@pytest.mark.parametrize("name,expected", [("b", "click at (1, 2)"), ("c", "toggle x (1, 2) / y (3, 4)")])
def test_action_summary(name, expected):
    assert st.action_summary(ACTIONS[name]) == expected


@pytest.mark.parametrize("results,status", [
    (["executed"], "PASS"), ([], "FAIL"), (["blocked_foreground"], "FAIL"), (["blocked_unknown"], "FAIL"),
    (["error"], "FAIL"), (["executed", "executed"], "FAIL"),
])
def test_judge_action_result(results, status):
    assert st.judge_action_result(results)[0] == status


# --------------------------------------------------------------------------
# Key sequences of the assisted steps
# --------------------------------------------------------------------------
SHIFT_SEQUENCE = [{"shift_up"}, {"shift_up", "undo"}, {"shift_up", "undo"}, {"shift_up"}, set()]


@pytest.mark.parametrize("sequence,expected", [
    (SHIFT_SEQUENCE, "shift_up > shift_up+undo > shift_up > (released)"),     # repeated reports are collapsed
    ([], "(no report)"),
], ids=["collapses_repeats", "empty"])
def test_format_sequence(sequence, expected):
    assert st.format_sequence(sequence) == expected


@pytest.mark.parametrize("sequence,has_hint", [([{"shift_up", "undo"}, set()], True), (SHIFT_SEQUENCE, False), ([], False)],
                         ids=["two_keys_in_first_report", "keys_one_after_the_other", "empty"])
def test_sequence_hint_only_for_several_keys_in_the_first_report(sequence, has_hint):
    assert bool(st.sequence_hint(sequence)) is has_hint


def run_step_with(monkeypatch, sequence, step):
    """Runs one assisted step with a prepared key sequence; returns its last result row (status, text)."""
    ctx = st.Context(False)
    monkeypatch.setattr(st, "collect_sequence", lambda *args, **kwargs: ("ok", sequence))
    step(ctx)
    return ctx.rows[-1]


@pytest.mark.parametrize("sequence,status,present,absent", [
    ([{"shift_up", "undo"}, {"shift_up"}, set()], "FAIL",
     ["expected ['shift_up+undo']", "shift_up+undo > shift_up > (released)", "same report"], []),
    ([{"shift_up"}, {"shift_up", "undo"}, {"shift_up"}, set()], "PASS", [], ["seen"]),
], ids=["both_keys_in_one_report", "shift_first"])
def test_combo_step(monkeypatch, sequence, status, present, absent):
    got, text = run_step_with(monkeypatch, sequence, st.make_combo_step("shift_up", "SHIFT UP"))
    assert got == status
    assert all(part in text for part in present) and not any(part in text for part in absent)


@pytest.mark.parametrize("sequence,status,present", [
    ([{"undo"}, {"undo", "shift_up"}, {"shift_up"}, set()], "PASS", []),
    ([{"shift_up", "undo"}, set()], "FAIL", ["keys seen in order"]),
], ids=["button_first", "same_report"])
def test_order_rule_step(monkeypatch, sequence, status, present):
    got, text = run_step_with(monkeypatch, sequence, st.step_order_rule)
    assert got == status
    assert all(part in text for part in present)


# --------------------------------------------------------------------------
# Helpers of the diagnose code itself
# --------------------------------------------------------------------------
UMLAUT = b"INFO: Es sind keine Aufgaben vorhanden, die den angegebenen Kriterien entsprechen (K\x81rzel).\r\n"


def test_tasklist_output_with_oem_umlaut_and_no_resolve_gives_false():       # crashed as text in v0.3.1
    assert st.listing_has_resolve(UMLAUT) is False


def test_tasklist_listing_with_resolve_gives_true():
    assert st.listing_has_resolve(b'"Resolve.exe","12345","Console","1","900.000 K"\r\n') is True


def test_resolve_process_running_reads_bytes_and_does_not_crash(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stdout=UMLAUT)

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    assert st.resolve_process_running() is False
    assert calls and not calls[0].get("text") and not calls[0].get("universal_newlines")


def test_crash_in_a_step_gives_one_short_line():
    def broken(_ctx):
        raise KeyError("probe\nwith a very long text " + "x" * 300)

    ctx = st.Context(True)
    st.run_step(ctx, "Dummy step", broken)
    rows = [text for status, text in ctx.rows if status == "FAIL"]
    assert len(rows) == 1
    assert re.search(r"in \w+, \w+\.py line \d+", rows[0])        # function, file and line, never a folder
    assert "\n" not in rows[0] and len(rows[0]) < 330
    assert str(Path(__file__).parent) not in rows[0]


# --------------------------------------------------------------------------
# Safety gates of the assisted runs (Resolve reacts to what the diagnose does)
# --------------------------------------------------------------------------
TOGGLE2 = ("toggle", (("primaries", "hdr"), [(10, 20), (30, 40)]), True)


def play_action_flow(monkeypatch, bindings, answers, foreground=True):
    """The conversation of the action test with scripted answers, a simulated Resolve and a recorded click.
    Returns (result rows, clicks, whether the toggle state of the program was restored)."""
    ctx = st.Context(False, action_test=True)
    clicks = []
    monkeypatch.setattr(actions, "click_at", clicks.append)
    monkeypatch.setattr(actions, "resolve_is_foreground",
                        lambda: (foreground, "Resolve.exe" if foreground else "Other.exe"))
    monkeypatch.setattr(st, "ask_text", scripted(answers))
    monkeypatch.setattr(st, "wait_until", lambda *args, **kwargs: ("ok", True))
    actions.toggle_state.clear()
    actions.toggle_state[("sentinel",)] = 7                     # must survive the run
    log.addHandler(ctx.capture)
    try:
        st.run_action_flow(ctx, bindings)
        kept = actions.toggle_state == {("sentinel",): 7}
    finally:
        log.removeHandler(ctx.capture)
        actions.toggle_state.clear()
    return ctx.rows, clicks, kept


def test_action_flow_clicks_nothing_without_yes(monkeypatch):
    rows, clicks, kept = play_action_flow(monkeypatch, {"user": TOGGLE2}, ["no"])
    assert clicks == [] and rows[-1][0] == "SKIP" and kept


def test_action_flow_blocked_action_does_not_click(monkeypatch):
    rows, clicks, kept = play_action_flow(monkeypatch, {"user": TOGGLE2}, ["YES"], foreground=False)
    assert clicks == [] and kept
    assert any(status == "FAIL" and "blocked" in text for status, text in rows)


def test_action_flow_never_offers_a_keys_binding(monkeypatch):
    rows, clicks, _kept = play_action_flow(monkeypatch, {"k": ("keys", [1], True)}, [])    # no question may be asked
    assert clicks == [] and rows[-1][0] == "SKIP"


def test_action_flow_restores_the_toggle_state_after_success(monkeypatch):
    rows, clicks, kept = play_action_flow(monkeypatch, {"user": TOGGLE2}, ["YES", "y", "y"])
    assert clicks == [(10, 20), (30, 40)] and kept
    assert not any(status == "FAIL" for status, _text in rows)


def test_action_flow_restores_the_toggle_state_after_the_answer_n(monkeypatch):
    rows, clicks, kept = play_action_flow(monkeypatch, {"user": TOGGLE2}, ["YES", "n"])
    assert clicks == [(10, 20)] and kept                    # no return press after an n
    assert any(status == "FAIL" for status, _text in rows)


GATE_IDS = ["resolve_running_no", "state_unknown_enter", "resolve_closed_q", "resolve_closed_enter"]


def gate_cases(total):
    """(Resolve running?, answer, steps that must run, last result). Running or unknown needs the word YES."""
    return [(True, "no", 0, "SKIP"), (None, "", 0, "SKIP"), (False, "q", 0, "SKIP"), (False, "", total, "PASS")]


@pytest.mark.parametrize("running,answer,steps,status", gate_cases(52), ids=GATE_IDS)
def test_full_gate(monkeypatch, profile, running, answer, steps, status):
    names = list(profile.buttons)
    calls = []

    def fake_collect(_ctx, prompt, seconds=st.STEP_SECONDS, allow_abort=False):
        name = names[len(calls)]
        calls.append(name)
        return "ok", [{name}, set()]

    ctx = st.Context(False, full=True)
    ctx.profile, ctx.dev, ctx.resolve_running = profile, object(), running
    monkeypatch.setattr(st, "collect_sequence", fake_collect)
    monkeypatch.setattr(st, "ask_text", scripted([answer]))
    monkeypatch.setattr(st, "FULL_PAUSE", 0)
    st.step_full_inputs(ctx)
    assert len(calls) == steps
    assert ctx.rows[-1][0] == status
    if steps:
        assert f"{steps} of {steps}" in ctx.rows[-1][1]


def ideal_reports(profile, name, direction):
    """Reports as the real panel would send them for a correct movement."""
    found = []
    for axis, sign in st.expected_signs(profile.rotary_channels[name][1], direction).items():
        found += reports(profile, name, axis, sign * 48, 20)
    return found


@pytest.mark.parametrize("running,answer,steps,status", gate_cases(39), ids=GATE_IDS)
def test_rotary_gate(monkeypatch, profile, running, answer, steps, status):
    plan = [(name, direction) for name, _ctype, gestures in st.rotary_plan(profile) for direction, _text in gestures]
    calls = []

    def fake_collect(_ctx, prompt, seconds=st.STEP_SECONDS, allow_abort=True, quiet=st.ROTARY_QUIET):
        step = plan[len(calls)]
        calls.append(step)
        return "ok", ideal_reports(profile, *step)

    ctx = st.Context(False, rotary=True)
    ctx.profile, ctx.dev, ctx.resolve_running = profile, object(), running
    monkeypatch.setattr(st, "collect_rotary", fake_collect)
    monkeypatch.setattr(st, "ask_text", scripted([answer]))
    monkeypatch.setattr(st, "FULL_PAUSE", 0)
    st.step_rotary_inputs(ctx)
    assert len(calls) == steps
    assert ctx.rows[-1][0] == status
    if steps:
        assert f"{steps} of {steps}" in ctx.rows[-1][1]


# --------------------------------------------------------------------------
# Key names of the key table check
# --------------------------------------------------------------------------
@pytest.mark.parametrize("unknown,status,parts", [
    (None, "PASS", [f"all {len(NAMED_KEYS)}"]),
    ("pause", "INFO", ["pause", f"(1 of {len(NAMED_KEYS)})"]),
], ids=["all_known", "pause_missing"])
def test_documented_keys_step_checks_every_named_key(monkeypatch, unknown, status, parts):
    asked = []

    def fake_to_pynput(name):
        asked.append(name)
        if name == unknown:
            raise AttributeError(name)
        return name

    monkeypatch.setattr(st, "to_pynput", fake_to_pynput)
    ctx = st.Context(True)
    st.step_documented_keys(ctx)
    assert sorted(asked) == sorted(NAMED_KEYS)                 # every name of the key table, each exactly once
    got, text = ctx.rows[-1]
    assert got == status
    assert all(part in text for part in parts)


# --------------------------------------------------------------------------
# run(): result, report, log handlers, --auto
# --------------------------------------------------------------------------
def pass_step(ctx):
    ctx.add("PASS", "fine")


def fail_step(ctx):
    ctx.add("FAIL", "broken")


def interrupted_step(_ctx):
    raise KeyboardInterrupt


@pytest.fixture
def isolated_run(monkeypatch, tmp_path):
    """run() with the report folder in tmp_path and the given part A steps; returns the call function."""
    monkeypatch.setattr(st, "BASE", tmp_path)

    def call(steps, **flags):
        monkeypatch.setattr(st, "A_STEPS", [("Step", step) for step in steps])
        return st.run(**flags)
    return call


@pytest.mark.parametrize("step,code", [(pass_step, 0), (fail_step, 1)], ids=["no_fail", "one_fail"])
def test_run_returns_1_only_when_a_step_failed(isolated_run, step, code):
    assert isolated_run([step], auto=True) == code


def test_run_writes_the_report(isolated_run, tmp_path, capsys):
    isolated_run([pass_step], auto=True)
    files = list((tmp_path / "reports").glob("diagnose_*.txt"))
    assert len(files) == 1 and re.fullmatch(r"diagnose_\d{8}_\d{6}\.txt", files[0].name)
    text = files[0].read_text(encoding="utf-8")
    assert text.splitlines()[0] == "Micro Color Panel diagnose report"
    assert "Result: 0 FAIL, 0 WARN, 0 SKIP" in text
    assert "Report written" in capsys.readouterr().out


def test_run_restores_the_log_handlers_after_an_interrupt(isolated_run):
    handlers, propagate = log.handlers[:], log.propagate
    assert isolated_run([interrupted_step], auto=True) == 0        # an interrupt is a WARN, not a FAIL
    assert log.handlers == handlers and log.propagate == propagate


def test_auto_never_starts_part_c_and_d(monkeypatch, isolated_run, capsys):
    def must_not_run(_ctx):
        raise AssertionError("an assisted part was started with --auto")

    monkeypatch.setattr(st, "run_part_c", must_not_run)
    monkeypatch.setattr(st, "run_part_d", must_not_run)
    assert isolated_run([pass_step], auto=True, full=True, rotary=True, action_test=True) == 0
    assert "Assisted steps skipped (--auto)" in capsys.readouterr().out

    
def _click_point_files(monkeypatch, tmp_path, tabs, bindings):
    """Points the diagnose at two files in tmp_path (the real tabs.json and bindings.json are never read)."""
    tabs_file, bindings_file = tmp_path / "tabs.json", tmp_path / "bindings.json"
    tabs_file.write_text(tabs, encoding="utf-8")
    bindings_file.write_text(bindings, encoding="utf-8")
    monkeypatch.setattr(st, "TABS_PATH", tabs_file)
    monkeypatch.setattr(st, "BINDINGS_PATH", bindings_file)


def test_collect_click_points_ignores_bool_coordinates(monkeypatch, tmp_path):         # RV-4 (CONS-004)
    _click_point_files(
        monkeypatch, tmp_path,
        '{"a": [true, 5], "b": [10, 20]}',
        '{"x": {"type": "click", "pos": [5, false]}, "y": {"type": "click", "pos": [30, 40]}}')
    assert st.collect_click_points() == {"tab 'b'": (10, 20), "binding 'y'": (30, 40)}


def test_collect_click_points_collects_valid_points_only(monkeypatch, tmp_path):       # RV-4 (pins old behavior)
    _click_point_files(
        monkeypatch, tmp_path,
        '{"a": [1, 2]}',
        '{"_note": {"type": "click", "pos": [9, 9]}, "k": {"type": "keys", "keys": "f9"}, '
        '"c": {"type": "click", "pos": [3, 4]}, "d": {"type": "click"}}')
    assert st.collect_click_points() == {"tab 'a'": (1, 2), "binding 'c'": (3, 4)}