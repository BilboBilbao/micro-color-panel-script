# Diagnostics: log, trace and diagnose

## Quick reference (TLDR)

Start everything from the project folder. If `python` is not one of Python 3.11 to 3.14 on your computer, write for example `py -3.11` instead of `python`.

| Command | What it does |
|---|---|
| `python panel_main.py` | normal operation: reads the panel, runs your bindings, writes `panel.log` |
| `python panel_main.py --trace` | normal operation, and every recognized button press is logged (also the ignored ones) |
| `python panel_main.py --diagnose` | diagnose: automatic checks (A) plus assisted steps at the panel (C) and the mouse/DPI check (D) |
| `python panel_main.py --diagnose --auto` | diagnose with the automatic checks only (A), no questions, mouse stays untouched |
| `python panel_main.py --diagnose --full` | like `--diagnose`, plus: you press all 52 inputs one after the other (Resolve reacts, use a test project) |
| `python panel_main.py --diagnose --rotary` | like `--diagnose`, plus: you turn every knob and ring and roll every trackball once (39 slow movements); the numbers of the panel are compared with the device profile (Resolve reacts, use a test project) |
| `python panel_main.py --diagnose --action-test` | like `--diagnose`, plus: one real click/toggle binding is run in Resolve, only after you type `YES` |
| `python panel_main.py --diagnose --full --rotary --action-test` | all additions in one run (any two can be combined as well) |
| `python tools\calibration.py` | records click points (tabs) into `tabs.json`; needed once per computer |
| `python tools\window_name.py` | shows the process name of the program in the foreground |
| `python tools\record_buttons.py` | records the button positions of the panel into `recordings\buttons_new.json` (read only) |
| `python tools\record_rotary.py` | records the raw reports of the knobs, trackballs and rings (42 slow movements) into `recordings\rotary_raw.json` (read only, Resolve must run, use a test project); `--redo ring` or `--redo <element names>` records some again (the old file is saved first) |
| `python tools\analyze_rotary.py` | evaluates that recording and writes `reports\rotary_analysis.txt` (changes nothing else) |
| `python tools\build_profile.py` | rebuilds `devices\micro_color_panel.json` from a recording and checks every position |
| `python tools\build_buttons_doc.py` | regenerates `docs\BUTTONS.md` from the device profile (run it after every change of the profile; a test fails if the file is out of date) |

- **Close the normal program before every diagnose.** `--auto`, `--full`, `--rotary` and `--action-test` only work together with `--diagnose`; `--full`, `--rotary` and `--action-test` cannot be combined with `--auto`, and `--trace` cannot be combined with `--diagnose` (the program refuses).
- **Files:** `panel.log` in the project folder; diagnose reports in `reports\diagnose_<date>_<time>.txt`. Neither contains user name, computer name, file paths, serial number or names of other programs.
- **Exit code of the diagnose:** 0 = no FAIL, 1 = at least one FAIL. Result words: `PASS`, `FAIL`, `WARN` (look at it), `INFO`, `SKIP`.
- **Keys during an assisted step:** Enter skips the step; in the `--full` and `--rotary` runs `q` stops the whole run. Questions are answered with `y` or `n` (`j`, `ja`, `nein` also work); risky steps need the word `YES`.
- **Resolve must be running for the assisted steps.** With Resolve closed the panel sent no button reports at all in a measurement (v0.3.3, desktop), so part C and `--full` see nothing.
- **Diagnose and Resolve:** without `--action-test` nothing is executed in Resolve; with it, exactly one real action runs, only after `YES`. The mouse only moves (no click) in the mouse check. The diagnose installs no keyboard or mouse listener.
- **For a bug report:** send the report file, or the `FAIL` and `WARN` lines of it. Without a report: the line `Start vX.Y.Z` and the last lines of `panel.log`.

Everything below is the long version.

## 1. The log file `panel.log`

One log file, one format. The terminal shows the plain text. The file shows the same text and, in square brackets behind it, fields a program can read:

```
terminal: -> user (toggle)
file:     -> user (toggle) [event=action binding=user type=toggle result=executed]
```

The file rotates automatically (500 KB, two backups). Fields are `key=value`, values with spaces are put in double quotes.

### Events

| event | level | fields | meaning |
|---|---|---|---|
| `start` | INFO | version, python, os | program started |
| `python_version_note` | INFO | | the Python version is outside the tested range (3.11 to 3.14); only a hint, the program runs |
| `trace_on` | INFO | | `--trace` is active |
| `instance_blocked` | ERROR | | a second instance was started and exits |
| `profile_loaded` | INFO | name, buttons, rotary_decoded | device profile loaded (buttons, rotary elements) |
| `profile_error` | ERROR | | device profile invalid, the program exits |
| `config_loaded` | INFO | active, skipped, reload | bindings and tabs loaded (`reload=true` after a change while running) |
| `config_failed` | ERROR | initial | a file is missing or invalid; the previous configuration stays active |
| `start_without_bindings` | ERROR | | the first load failed, the program runs without bindings until the file is fixed |
| `config_warning` | WARNING | entry, reason | single entry skipped or notable; reasons: `invalid_name`, `invalid_entry`, `bad_only_resolve`, `not_free`, `optional_file_missing` |
| `running` | INFO | | the main loop is running |
| `panel_connected` | INFO | connection | panel opened; `connection` is `USB`, `Bluetooth` or `unknown`; logged again after every reconnect |
| `panel_waiting` | WARNING | reason | panel not found or cannot be opened (`not_found`, `open_error`) |
| `panel_lost` | WARNING | | connection lost, reconnecting |
| `action` | INFO / WARNING / ERROR | binding, type, result | result is `executed`, `blocked_foreground`, `blocked_unknown` or `error` |
| `press` | INFO | key, has_binding / ignored | only with `--trace` |
| `foreground_check_failed` | ERROR | | the foreground check raised an error |
| `setup_warning`, `instance_check_warning` | WARNING | awareness (setup_warning) | non-critical start-up problems; `setup_warning` means the DPI awareness is not per monitor, clicks can miss on monitors with different scaling |
| `unexpected_error` | ERROR | function, line, error | an unexpected exception ended the program (exit code 1); function and line are where it was raised |
| `stop` | INFO | | program stopped with Ctrl+C |

## 2. What is not logged

- The names of other programs. A blocked action says `foreground is other_program, not resolve.exe`.
- Full file paths. The project folder appears as `<project>`, the home folder as `<home>`; file names are shown without folders.
- User name and computer name.
- The serial number and the USB path of the panel are never read into the log or the diagnose report.

## 3. Start problems before the log exists

If a required Python package is missing, the program does not show a traceback. It prints a short text on the console and exits with code 1:

```
The Python package 'hidapi' is not installed.
Install the required packages with this command, started in the project folder:
    python -m pip install -r requirements.txt
```

If the Python version is outside 3.11 to 3.14, the text adds the version hint (tested range, try Python 3.11 to 3.14). With `pythonw` (no console) nothing is shown; start the program once with `python panel_main.py` to see the message.

The Python version alone is never a reason to stop: the program only logs the hint `python_version_note` (and the diagnose shows it as INFO).

## 3a. `--trace`

`python panel_main.py --trace` runs the program normally and additionally logs every recognized button press:

```
press shift_up+undo (binding: no)
press ignored: user (shift state changed in this report, both shift keys held, or another button was already held)
```

The first line shows the name the program computed for the press and whether a binding exists for it. The second line appears when a press is deliberately ignored: a button and a shift key that appear in the same report, both shift keys held, or another non-shift button that was already held (the chord rule: a binding fires only if exactly one non-shift button is held). Without `--trace` these lines are not written.

## 4. Diagnose

```
python panel_main.py --diagnose                 automatic checks, assisted steps at the panel, mouse and DPI check
python panel_main.py --diagnose --auto          automatic checks only, no questions
python panel_main.py --diagnose --full          plus: all 52 inputs one after the other
python panel_main.py --diagnose --rotary        plus: every knob, ring and trackball once
python panel_main.py --diagnose --action-test   plus: one real click/toggle binding in Resolve
```

Close the normal program first. The diagnose never sends anything to the panel. `bindings.json` and `tabs.json` are only read. Without `--action-test` it never executes an action in Resolve. It installs no keyboard or mouse listener (a listener would see every key and mouse event of the whole system, which is not acceptable for a program that strangers install). Exit code 0 means no FAIL, 1 means at least one FAIL. `--full`, `--rotary` and `--action-test` cannot be combined with `--auto`, and `--trace` cannot be combined with `--diagnose`.

Result lines are `PASS`, `FAIL`, `WARN` (look at it), `INFO` (information) or `SKIP` (not run, for example not on this system or skipped by you).

If a check crashes by itself, the FAIL line names the error, a shortened message and the place, for example `(KeyError: 'x'; in step_resolve, diagnose.py line 412)`. Please include such a line in a bug report.

### Part A: environment, configuration, panel, Resolve (automatic)

Program, Python and system version (with a hint if Python is outside 3.11 to 3.14); versions of the packages; the device profile; `bindings.json` and `tabs.json` (counts and warnings); monitors with position, size and scale, and whether every click point lies inside a monitor (if not, a hint says that `tabs.json` probably comes from another computer and must be calibrated again with `python tools\calibration.py`); the panel (found by usage page 0xFF00, so over USB and over Bluetooth; product name, connection type if the hid library provides it, opened read-only); whether another instance runs, and (Windows) that a second instance is blocked (the check starts the program with the internal option `--no-log-file` and verifies that the real `panel.log` was not changed); whether Resolve runs (the `tasklist` output is read as raw bytes, so a localized text with umlauts cannot crash the step), file information of `Resolve.exe` and installed programs with "DaVinci" in the name; whether the foreground detection works; which of the key names of the program (the list in `micropanel/keys.py`, documented in `BINDINGS.md`) the key table of this system does not know (`INFO` with the list, never a FAIL; useful on another operating system).

Edition (free or Studio): the diagnose does not determine it and never touches the scripting interface of Resolve. The file information of Resolve.exe above may show the product name; please name your edition in a bug report. It never changes a setting in Resolve.

### Part B: now `python -m pytest -q`

Part B used to run the program code with a simulated panel inside the diagnose. Those checks are now ordinary tests in `tests/` (development only: `python -m pip install -r requirements-dev.txt`, then `python -m pytest -q`). No panel, no Resolve and no real keyboard or mouse is needed: a test that touches `hid` or `pynput` replaces the package by a fake for that one test.

They cover: hot reload (check twice, then load), broken JSON (previous configuration stays, reported once), start with a broken file, deleted file, byte order mark, entry validation and the warning for non-free bindings, `tabs.json` reload with the toggle state kept, blocking outside Resolve (no program name in the log), the trigger rules including the chord rule, lost connection and reconnect (also reload while the panel is missing), device profile validation, replay of recorded button and rotary reports, log format and anonymization, key specs and the key release of `press_keys`, the messages for a missing package and another Python version, and the diagnose's own judging functions and safety gates (nothing is clicked without `YES`, a `keys` binding is never offered, the toggle state is restored afterwards, the gates of `--full` and `--rotary`; also the `tasklist` output with non-ASCII bytesand the FAIL line of a crashing check).

Limit of the key tests: they check the splitting and the order, not that every name in the key table points to the right key, and not that Windows delivers the keys to Resolve. That stays a hand test (for example `alt+z` and `ctrl+alt+shift+f9` arrived in Resolve in v0.1.x).

These tests use simulated reports. They protect against accidental changes and wiring mistakes. They cannot prove that the rules match the real hardware; part C does that.

### Part C: assisted steps at the real panel

Each step shows what to do and waits up to 15 seconds; Enter skips a step. Resolve should be running (see the quick reference). If a key combination step fails, the FAIL line shows the expected result and the keys that were actually seen in order, for example `keys seen in order: shift_up+undo > shift_up > (released)`; if several keys arrived in the very first report, it adds the hint to press the first key, hold it, and press the second a moment later.

1. Press USER once: recognized as `user`, release seen.
2. Hold SHIFT UP and press UNDO: the program computes `shift_up+undo`.
3. Hold SHIFT DOWN and press UNDO: the program computes `shift_down+undo`.
4. Hold UNDO, then press SHIFT UP: the program computes only `undo` (order rule).
5. Bring Resolve to the front, then click another program: the foreground detection reports both correctly.
6. Unplug the USB cable and plug it in again (skipped when the panel is connected by Bluetooth): the read call must fail with an error type the program reconnects on, and the panel must open again.

The assisted steps are skipped if another instance of the program runs, so no real action can be triggered while you test.

#### `--full`: all 52 inputs

The diagnose names one input after the other in the order of the device profile (40 buttons, then 12 knob presses). You press and release it; the test checks that exactly this name is recognized. 15 seconds per input, Enter skips an input, `q` stops the run. The summary lists what was recognized, wrong (another name or several at once), without report, without seen release, skipped and not reached.

Why: the 52 positions are otherwise only backed by the recording and the comparison in `build_profile.py`. This tests the profile at the real device.

**Warning:** Resolve reacts to the buttons (for example `delete`, `reset*`, `auto_color`, `add_node`, `grab_still` and the knob presses). Open a test project first. With Resolve closed the panel sent no reports in a measurement, so the run would probably recognize nothing; if Resolve is not running, the diagnose says so and Enter starts anyway (`q` cancels). If Resolve runs (or this could not be checked), you must type `YES`.

#### `--rotary`: knobs, rings and trackballs (v0.3.5)

The diagnose names one movement after the other in the order of the device profile: every knob and every ring right (clockwise) and left, every trackball right, away from you and diagonally away from you and to the right (39 steps). You move the element slowly for about a second and stop; the step ends 1.5 s after the last report (the panel only sends motion reports while an element moves). 15 seconds per step, Enter skips, `q` stops. Type `YES` first (Resolve reacts to the movements).

What is checked per step: the channel of this element moved (and no other channel by more than 40 % of it), and the sum of its numbers has the sign the profile promises (knob and ring: right = positive; trackball x: right = negative; trackball y: away from you = negative). In the diagonal step both axes must have the promised sign (a WARN if one axis hardly moves). Results: `FAIL` for a wrong channel, a wrong sign or other channels moving along; `WARN` for no report or a weak diagonal; the summary line counts the steps.

Why: the report positions of the 18 rotary elements come from one recording (`tools/record_rotary.py`). This checks the profile at the real device. The numbers of the panel are deltas (the change since the previous report) in the signed little-endian format described in `devices/micro_color_panel.json`. The program does not use them yet (rotation actions come later).

### Part D: mouse path, DPI awareness and real action

Part D is part of every assisted run (not of `--auto`), Windows only.

1. **DPI awareness:** asks Windows whether the program is "per monitor DPI aware" (value 2). That is the precondition for correct clicks on monitors with different scaling. Other values are a FAIL with a clear text; "cannot be read" is a WARN. Since v0.3.4 the program requests this awareness *before* the third-party packages are imported (measured with the old `pyautogui`: importing it set the weaker value 1, and Windows then refused the change; since v0.3.37 the program uses `pynput`, and the value stays 2 on a desktop with several monitors and on a laptop); if it still is not 2, `panel.log` shows a `setup_warning` at every start. `tools\calibration.py` does the same, so both see the same coordinates.
2. **Mouse path:** after a 5-second notice (Enter skips) the mouse moves, without clicking, to every click point of `tabs.json` and `click` bindings; the position is read back with a tolerance of 1 pixel, a deviating point is tried once more. Then the mouse must be back at its starting position (it is always put back, also after an error). The test is skipped if a click point lies outside all monitors (see part A). Do not touch the mouse during the test.
3. **Real action (only with `--action-test`):** runs one `click` or `toggle` binding from your `bindings.json` once through the real `execute` function, including the foreground check. Never a `keys` binding (`ctrl+alt+shift+f9` could change something in Resolve). Conditions, all required: not `--auto`, Resolve runs, all click points lie inside a monitor, you type `YES`. With several candidates you choose one by number. For a toggle the first press clicks the first tab, so show the **last** tab of the toggle in Resolve first. After the action you answer `y/n`: did Resolve show the change? A toggle with two tabs is pressed a second time to return to the starting palette; with more tabs the test asks for `YES` before it presses the remaining times. After an `n` answer no return press is run. The toggle state of the program is restored at the end.

What part D does not show: that the mouse path is a clean test of the scaling. Reading the position back uses the same Windows interface family as moving, so it finds clamping and shifts but not a scaling error; the DPI check covers that. Whether a point lies on the right tab in Resolve is shown only by the real action and your `y/n` answer.

### Report

`reports\diagnose_<date>_<time>.txt` holds all result lines. It contains no user name, computer name, file paths, serial number, USB path or names of other programs.

### Not covered

The visible effect in Resolve (except in the `--action-test` answer you give yourself), whether Windows delivers keys to Resolve (no keyboard listener, on purpose), whether a key name points to the right key, other computers and monitor arrangements, whether a click lands on the right tab at a scaling other than 100 % (only the DPI check and the action test hint at it), Bluetooth latency, standby and range (over Bluetooth the unplug step is skipped; `--diagnose`, `--full` and `--rotary` were run there with 0 FAIL and 0 WARN), macOS, and starting with `pythonw`.
