"""Reading reports: which controls are pressed, which bindings fire, how far a knob moved.
Pure functions, standard library only."""
from micropanel.profile import MODS


def make_lookup(profile):
    """Returns ({(byte, bit): control name}, shortest valid report length)."""
    lookup = {position: name for name, position in profile.buttons.items()}
    return lookup, max(byte for byte, _ in lookup) + 1


def decode_held(report, lookup, report_id, min_length):
    """Set of pressed control names in a report, or None if it is not a (complete) button report."""
    if not report or len(report) < min_length or report[0] != report_id:
        return None
    return {name for (byte, bit), name in lookup.items() if report[byte] & (1 << bit)}


def triggers_for_report(prev, held):
    """Binding names that fire for this report ('button' or 'shift_x+button').

    prev and held are sets of control names (previous and current report).
    Rules: the shift key must already be held in the previous report; if the shift state changes in this
    report nothing fires; with both shift keys held nothing fires."""
    mods = prev & MODS
    if (held & MODS) != mods:
        return []
    if len(held - MODS) != 1:      # rule 7: exactly one non-shift button held after this report
        return []
    keys = []
    for n in sorted(held - prev):
        if n in MODS:
            continue
        if len(mods) == 1:
            keys.append(f"{next(iter(mods))}+{n}")
        elif not mods:
            keys.append(n)
    return keys


def make_rotary_lookup(profile):
    """{report id: [(control name, Channel), ...]} for all decoded rotary controls."""
    lookup = {}
    for name, (_ctype, channels) in profile.rotary_channels.items():
        for channel in channels:
            lookup.setdefault(channel.report, []).append((name, channel))
    return lookup


def decode_rotary(report, lookup):
    """[(control name, axis, value), ...] for every channel in this motion report (zero values included),
    or [] if it is not a motion report. The value is the signed change since the previous report; the program
    does not use it yet (rotation actions come later), the diagnose does."""
    if not report or report[0] not in lookup:
        return []
    found = []
    for name, channel in lookup[report[0]]:
        end = channel.byte + channel.width // 8
        if len(report) >= end:
            found.append((name, channel.axis, int.from_bytes(bytes(report[channel.byte:end]), "little", signed=True)))
    return found