"""Trigger rules. Each case is a sequence of reports (sets of pressed controls)
and the bindings that must fire. su = shift_up, sd = shift_down."""
import pytest

from micropanel.decoder import triggers_for_report


def fired(sequence):
    prev, out = set(), []
    for held in sequence:
        out += triggers_for_report(prev, held)
        prev = held
    return out


def S(*names):
    return set(names)


CASES = [
    ("plain_user_fires_once", [S(), S("user"), S("user"), S()], ["user"]),
    ("shift_then_button", [S(), S("shift_up"), S("shift_up", "user"), S("shift_up"), S()], ["shift_up+user"]),
    ("shift_down_then_button", [S(), S("shift_down"), S("shift_down", "undo"), S()], ["shift_down+undo"]),
    ("button_then_shift", [S(), S("user"), S("user", "shift_up"), S("shift_up"), S()], ["user"]),
    ("button_and_shift_same_report", [S(), S("user", "shift_up"), S("shift_up"), S()], []),
    ("both_shifts_held", [S(), S("shift_up"), S("shift_up", "shift_down"), S("shift_up", "shift_down", "user"), S()], []),
    ("shift_alone", [S(), S("shift_up"), S()], []),
    ("shift_released_while_button_held", [S(), S("shift_up"), S("shift_up", "user"), S("user"), S()], ["shift_up+user"]),
    ("held_button_does_not_refire",
     [S(), S("shift_up"), S("shift_up", "user"), S("shift_up", "user"), S("shift_up"), S()], ["shift_up+user"]),
    # rule 7 / B1 (decision D1): a trigger needs exactly one non-shift button held after the report
    ("user_is_not_a_modifier", [S(), S("user"), S("user", "undo"), S("undo"), S()], ["user"]),
    ("second_button_while_first_held", [S(), S("undo"), S("undo", "redo"), S()], ["undo"]),
    ("rolling_to_the_next_button", [S(), S("undo"), S("undo", "redo"), S("redo"), S()], ["undo"]),
    ("two_buttons_same_report", [S(), S("undo", "redo"), S()], []),
    ("shift_held_second_button",
     [S(), S("shift_up"), S("shift_up", "undo"), S("shift_up", "undo", "redo"), S()], ["shift_up+undo"]),
]


@pytest.mark.parametrize("sequence,expected", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_trigger_rules(sequence, expected):
    assert fired(sequence) == expected
