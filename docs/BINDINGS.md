# How to edit bindings.json

`bindings.json` contains only your bindings. All help lives in this file.
Start from `bindings.example.json`: copy it to `bindings.json` (same folder) and edit the copy. Its `user` entry sends a default Resolve shortcut (check it in Resolve under Keyboard Customization), so it needs no `tabs.json`. Without `tabs.json` the log shows one harmless notice at each load (`Optional file missing: tabs.json`).

## 1. Changes take effect automatically (hot reload)

While the program runs, it checks `bindings.json` and `tabs.json` about once per second. After you save a change:

- the files are loaded again within about 2 seconds, the log shows `Config reloaded: N bindings active, M empty entries skipped`;
- if the file contains an error (for example a missing comma), the program **keeps the last working configuration** and logs
  `Reload failed, keeping previous configuration: ...` with line and column. Fix the file and save again; it is loaded automatically;
- if the error is in the file when the program **starts**, it starts without bindings, logs `Configuration not loaded: ...` and loads the file as soon as it is valid;
- both files are loaded together. If one of them is broken, nothing is replaced;
- an invalid **single entry** (wrong name, unknown key) is skipped with a warning, the other entries stay active;
- the toggle state is kept across reloads;
- **not** reloaded: `devices/micro_color_panel.json` (hardware facts). Restart the program after changing it.

## 2. Notes and comments

JSON has no comment syntax. Therefore every entry whose name starts with an underscore (`_`) is treated as a note and ignored by the script.
Use this to leave own notes, or to switch an entry off without deleting it (rename `"user"` to `"_user"`).

## 3. Binding names

- Normal button: `user` triggers immediately when pressed.
- With shift: `shift_up+user` or `shift_down+user`. Hold the shift key first, then press the button.
- Allowed: one button, or one shift key plus one button.
- Not allowed as a name: shift alone, two normal buttons in one name (`delete+next_node`), button before shift (`user+shift_up`).
- The program accepts any button without shift (for example `undo`), but Resolve already uses it natively. See section 7: the program warns you.

## 3a. When does a binding fire

- A binding fires when you **press** the button (not on release, and not again while you hold it).
- For `shift_up+user` and `shift_down+user` style names, **hold the shift key first**, then press the button. A shift key and a button that go down at the same moment fire nothing, not even the plain button. Pressing the button first and the shift key afterwards fires only the plain button entry.
- With a shift key held, only the `shift_...+button` entry is looked up, never the plain entry of that button.
- Holding both shift keys fires nothing. `user` is a normal button, not a shift key.
- **One button at a time:** a binding fires only if exactly one normal button is held after your press. If you roll from one button to the next without letting go, the second press fires nothing. Release first, then press the next button. With `--trace` such presses are logged as `press ignored`.

## 4. Button names

- Row 1 (left): auto_color, offset, copy, paste, undo, redo, delete, reset, bypass, disable, user, loop
- Modifiers (not bindable alone): shift_up, shift_down
- Top: play_still, wipe_still, grab_still, h_lite, viewer, cursor, select
- Reset row: reset_lift, reset_gamma, reset_gain
- Top right: add_node, add_window, add_keyframe
- Right: prev_still, next_still, prev_keyframe, next_keyframe, prev_node, next_node, prev_frame, next_frame, prev_clip, next_clip
- Transport: backward, forward, stop
- Knob presses (detent resets): ylift_knob_press, ygamma_knob_press, ygain_knob_press, contrast_knob_press, pivot_knob_press, mid_detail_knob_press,
  color_boost_knob_press, shadows_knob_press, highlights_knob_press, saturation_knob_press, hue_knob_press, lum_mix_knob_press

The turning of the knobs, the trackballs and the rings cannot be bound yet. The report positions of most of them are known (see docs/BUTTONS.md), but actions for rotation are planned for a later phase.

## 5. Actions

Every entry needs a field `type`: `keys`, `click` or `toggle`.

| Type | Example | Meaning |
|---|---|---|
| keys | `{ "type": "keys", "keys": "ctrl+alt+shift+f9" }` | sends a key combination; an empty `keys` string means the entry is skipped |
| click (tab) | `{ "type": "click", "tab": "hdr" }` | clicks a point named in `tabs.json` (create it with `tools/calibration.py`) |
| click (position) | `{ "type": "click", "pos": [1200, 800] }` | clicks screen pixel x, y; the mouse returns afterwards |
| toggle | `{ "type": "toggle", "tabs": ["primaries", "hdr"] }` | every press clicks the next tab in the list |
| any program | `{ "type": "keys", "keys": "media_play_pause", "only_resolve": false }` | action runs in any program |

`tabs.json` is a list of names and screen positions, for example `{ "primaries": [1200, 800], "hdr": [1260, 800] }`. The positions are valid for one computer, one monitor layout and one window position only. That is why there is no example file: create it with `tools/calibration.py`.

- `only_resolve` is `true` by default: the action only runs while Resolve is in the foreground.
- Mouse clicks: the safety abort of the mouse library (moving the cursor into a screen corner) is switched off on purpose. Every click is one instant move and the cursor returns afterwards, and a calibrated point may lie in a corner.
- The toggle only remembers its own clicks. If you switch by hand, it gets out of sync. If you change the list of tabs of a toggle, it starts again at the first entry.
- Resolve still runs its own function for each button. Only use buttons that Resolve does not assign (section 7).

## 6. Key names

- Join keys with `+`: `ctrl+alt+shift+f9`. Recommended: `ctrl+alt+shift` plus an F key, these are rarely assigned.
- Modifiers: ctrl, alt, shift, alt_gr. Avoid the Windows key (win) if possible.
- Letters, digits, symbols: a single character, e.g. `k`, `5`, `#`.
- Special keys: enter, tab, esc, space, backspace, delete, home, end, page_up, page_down, insert, up, down, left, right, caps_lock, num_lock, scroll_lock, pause, print_screen, menu, f1 to f20.
- Not every name exists on every system. `python panel_main.py --diagnose --auto` lists the names your system does not know ("Documented key names missing ..."). An entry that uses such a name stays active and logs an error each time the button is pressed.
- Special characters as words: plus, minus, comma, period, slash, backslash, semicolon, equals, quote, backtick, bracket_left, bracket_right.
- Numpad: num0 to num9, num_plus, num_minus, num_multiply, num_divide, num_decimal.
- Media: media_play_pause, media_next, media_previous, media_volume_up, media_volume_down, media_mute.
- On keyboard layouts with AltGr (e.g. German), combinations like `ctrl+alt+<character>` may misbehave. F keys are safer.

## 7. Free combinations (no native function)

The device profile lists 55 combinations that have no native function: 31 according to the Blackmagic manual (September 2024, Control Table) and 24 more (a shift key plus a knob press) found in a live test.
If you activate an entry that is **not** on this list, the log shows
`Entry '<name>' is not in the free list: Resolve also runs its native function for it`. The entry stays active, you decide.
All entries were live-tested on Resolve 21.0.4.5 Studio only. Other versions are untested. Native mappings may change with Resolve or panel firmware updates.

- `user` (plain), `shift_up+user`, `shift_down+user`
- `shift_down+offset`, `shift_down+copy`, `shift_down+paste`
- `shift_up+undo`, `shift_down+undo`, `shift_up+redo`, `shift_down+redo`
- `shift_up+bypass`, `shift_down+bypass`, `shift_up+disable`, `shift_down+disable`
- `shift_down+wipe_still`, `shift_up+grab_still`, `shift_down+grab_still`, `shift_down+h_lite`
- `shift_up+cursor`, `shift_down+cursor`, `shift_up+select`, `shift_down+select`
- `shift_down+add_keyframe`, `shift_down+next_still`
- `shift_up+prev_node`, `shift_up+next_node`, `shift_up+prev_frame`, `shift_up+next_frame`
- `shift_up+backward`, `shift_up+forward`, `shift_up+stop`
- `shift_up` or `shift_down` plus any of the 12 knob presses (24 combinations, see section 4 for the names), for example `shift_up+hue_knob_press`

Live test (Resolve 21.0.4.5 Studio, one computer): none of these 55 combinations did anything in Resolve. Turning a knob with a shift key held does the same as without shift, so those combinations are **not** free (and they cannot be bound yet).

Note: the manual calls the `user` button "reserved for future use". A future firmware or Resolve version may give it a native function.

## 8. Safety notes

- The script only reads from the panel. It never writes to it.
- The factory reset (hold AUTO COLOR + STOP on the panel) is done by the panel itself. This script cannot trigger it.
