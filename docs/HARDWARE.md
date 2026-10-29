# Hardware findings (Micro Color Panel)

> Read this file only when working on report decoding, the device profile or the recorder tools.


### USB (measured)

USB device `VID 0x1EDB` (Blackmagic), `PID 0xDA0F`, full-speed composite device:

| Interface | Class | Notes |
|---|---|---|
| 0 | vendor-specific, no endpoints | used by Blackmagic driver `DaVinciPanels_x64.sys` (control transfers) |
| 1 | DFU (runtime) | firmware update, **never touch** |
| 2 | HID, usage page `0xFF00` | EP `0x81` IN and `0x01` OUT, 64 bytes, 10 ms. **This is what the script reads.** |

- Interface 2 can be opened **read-only in parallel to Resolve**. Verified: Resolve keeps working normally.
- The script **never writes** to the panel (no OUT reports).
- **With Resolve not running the panel sent no button reports at all** (measured once on the desktop in v0.3.3: "Press USER", the shift steps and the order rule saw nothing, `--full` was stopped after the first input; opening the panel read-only still worked and unplug/replug still behaved). **Measured in v0.3.4 (hardware, user):** a program started *before* Resolve does receive reports and runs the `user` binding once Resolve is running, so plug and play with any start order works. Hypothesis (still not tested): Resolve or the Blackmagic driver activates the panel. Whether the panel ever sends without Resolve stays open and is unimportant for operation.
- HID report descriptor (297 bytes) could not be read with USBTreeView; the format was reverse engineered from live reports.

### Bluetooth (measured in Phase 2c, v0.3.34, user hardware, Windows 11)

- `hid.enumerate()` lists the panel over USB as `0x1edb 0xda0f`, usage page `0xff00`, interface 2, and over Bluetooth with the **same IDs and usage page but interface number -1**. One entry each. With cable and Bluetooth together a second entry never appeared (the panel uses one way at a time). This is why the program finds the panel by usage page and not by interface number (B10, D20).
- The old search for interface 2 did not find the panel over Bluetooth (`panel_waiting`, reason `not_found`) although Resolve used it normally; after the cable was plugged in the program found it.
- Read measurement (a probe that only opened the entry and read; not kept in the repo): the entry can be opened while Resolve runs. All 406 reports had length 64 and the first byte `0x02` (buttons), `0x06` (knobs) or `0x05` (trackballs and rings). The report id is at the start as over USB, no extra header; the delta layout matches the sections below.
- Pairing needed no PIN; Windows lists the panel as an input device.
- `--diagnose` (and `--auto`), `--full` and `--rotary` over Bluetooth: 0 FAIL, 0 WARN; the unplug step is skipped (1 SKIP, on purpose).
- Switching between USB and Bluetooth while the program runs (measured in v0.3.35 with the log): `dev.read` fails with `OSError('read error')` both when the cable is plugged in and when it is pulled out. The program reconnects at its first retry, 2 s later (log resolution 1 s), over the new way and logs `Panel connected (USB)` or `Panel connected (Bluetooth)`.
- Resolve shows battery level and connection type under "Panels" (bottom right), Windows shows the battery under "Bluetooth & devices". **Hypothesis, not measured:** the battery level comes from the standard Bluetooth LE battery service and not from the HID reports (only report ids 02, 05 and 06 were seen).
- **Not measured:** latency over Bluetooth, behavior in standby, range, the exception type of a pure Bluetooth drop (out of range, panel off), protection of interface 1 (DFU) over Bluetooth (indirect evidence over USB only: `hid.enumerate()` listed one entry of this VID/PID, never the DFU interface).

### Report 0x02 (buttons) (measured)

- Byte 0 = `0x02`. Bytes 1 to 7 hold **one bit per control**. 52 bits are mapped in the device profile: **40 normal buttons**
  (bytes 2-7) and **12 knob presses** (byte 1, byte 2 bits 0-3). Byte 7 bits 4-7 unused.
- The 40 normal buttons match the manual: 14 left (incl. shift up/down), 13 top, 13 right.
- The 12 knob presses are the **"detent resets"** named in the manual (confirmed by user).
- **Knobs, trackballs and rings turn freely, they have no detents** (confirmed by the user). The word "detent reset" in the manual means pressing the knob. Consequence for C3: no fixed number of clicks can be asked for, the recorder uses slow gestures (about one turn) and the scale per turn is an estimate.
- **Trackballs and rings have no push button** (confirmed by user).
- A press sets the bit, release returns the bytes to zero. Multiple simultaneous buttons set multiple bits (verified).
- Bytes 9 and up of early recordings contained extra values. **Corrected by the C3 run:** these are most likely not part of report 02 (the old recorder probably did not filter by report id), but knob and ring deltas from reports 06 and 05 that arrived while a knob was pressed (the old value at byte 34 = `0x10` equals the gain ring delta +16 of report 05, the 32-bit values at bytes 9, 17, ... match the knob slots of report 06). Not verified against the old recorder code. Report 02 itself carries the 52 button bits only.

### Report 0x06 (knobs) (measured in the C3 run, user hardware, desktop)

- 64 bytes, byte 0 = `0x06`. **12 channels, each a signed little-endian 32-bit delta, at byte 1 + 4 x k**, in the order of the profile: ylift 1, ygamma 5, ygain 9, contrast 13, pivot 17, mid_detail 21, color_boost 25, shadows 29, highlights 33, saturation 37, hue 41, lum_mix 45 (k = 0 to 11).
- **Turning right = positive, left = negative**, identical for all 12 knobs. Seen: only one slot non-zero per report (4788 reports, none with two), no crosstalk with other elements.
- The values are **deltas** (they keep their sign during a turn and add up to the distance moved), not positions. Every value is a multiple of 360. A turn of "about one full turn" gave sums of roughly 1.2 to 1.9 million per direction (rough estimate only, the turn was not exact), i.e. on the order of 4000 steps of 360 per turn.
- Reports come about every 30 to 60 ms **only while the knob moves**. There are no resting reports and no zero report at the end (a step ends with a normal non-zero value, then the stream stops).
- Hint on the width: the bytes of the sign extension (for example `ff ff` in bytes 3 and 4 of a negative value) never change inside one turn direction, so a naive "which bytes change" analysis shows only 16 bit. The reports show 32 bit: `06 f0 f1 ff ff ...` is -3600.

### Report 0x05 (trackballs and rings) (measured in the C3 run)

- 64 bytes, byte 0 = `0x05`. **9 channels, each a signed little-endian 24-bit delta (byte 4 of a group never non-zero, no sign extension seen), at bytes 2, 6, 10, 14, 18, 22, 26, 30, 34.** The nine channels are three groups of 12 bytes: per group x axis, y axis, ring.
  - lift: trackball x = byte 2, y = byte 6, **lift ring = byte 10**; gamma: x = 14, y = 18, **gamma ring = 22**; gain: x = 26, y = 30, **gain ring = 34**.
- **Signs (same for all three groups):** x axis: rolling the ball to the **right is negative**, left positive. y axis: rolling **away from the user (up) is negative**, toward the user (down) positive. Ring: turning **right (clockwise) is positive**, left negative. Assumption to confirm: the user's "right" and "up" were meant as written in the recorder text.
- Trackball values are multiples of 16, ring values were +16 (right) and -16 (left) in nearly every report of the recordings (85 to 110 identical reports per slow quarter-turn step, about 3 s at roughly 33 ms per report). **Hint that the ring value grows with speed (one step only, not confirmed):** in a first re-recording `gain_ring left` ran for 18.7 s with the values -16 (34x), -32 (42x), -48 (7x), +16 (7x) and 0 (7x); the second re-recording had only slow turns (all +-16, one stray -16 at the end of `lift_ring right`). Whether and how the value scales with speed is open (matters for the thresholds of the rotation actions in Phase 4).
- Bytes 45 and 46 are `38 04` (= 1080) in every **trackball** report 05 and 0 in the **ring** reports (corrected from "every report 05", measured in the ring re-recording). They do not depend on direction or speed. Not a control, not in the profile. Meaning unknown (the analyzer's CHECK line about them is a false alarm).
- The trackball is a **free ball** (information from the user): it can be moved in any direction, not only along the axes. Its x and y are two independent channels, so a diagonal movement simply moves both at once (no extra decoding needed; the `--rotary` self-test has a diagonal step to confirm this at the device).
- Reports come about every 33 ms only while a ball or ring moves, no resting reports. Report 05 and report 06 never mixed in the recording (no 06 during ball/ring steps, no 05 during knob steps).
- Hypothesis from the first version of this section (nine 24-bit delta channels, 3 balls x 2 axes + 3 rings, starting at byte 2 with a distance of 4 bytes) is **confirmed**; the knobs are **not** in report 05 (they are in report 06).
- Only report ids 02, 05 and 06 were seen. No battery or connection status.

### Findings from the manual (September 2024, hints only)

- Connection: USB-C (data + charging) or Bluetooth. Bluetooth name is "Micro Color Panel" (shown as "Micro Color Panel 4" on
  Windows/iPadOS in screenshots). Panel is always on (no power switch). Built-in rechargeable battery. Battery level is shown in Resolve
  System Preferences (so the panel reports it somewhere; location unknown, see the Bluetooth section). A hardware Bluetooth button is on the rear.
- The manual says **Resolve 19 or higher is required for the panel itself**. This is Blackmagic's statement about the panel, not
  about this project.
- **Factory reset:** hold AUTO COLOR + STOP until the LEDs cycle. It removes Bluetooth pairing. It is a **physical action handled
  by panel firmware**. The script cannot trigger it (read-only, and key output goes to the PC, not to the panel). Only a README
  note is needed; no software protection.
- **LEDs:** green for Shift Up/Down (while held), Offset, Play Still, H/Lite, Cursor (active modes); red for Bypass and Disable.
  Whether other colors are possible is unknown (Phase 2b).
- **User button** is "Reserved for future use" (manual p. 16). A future firmware or Resolve version may give it a native function.
- **Trackball/ring meaning depends on Resolve state** (Primary / Log / Offset mode, shifted Window and Sizing modes). The HID report only
  carries "element + delta"; the meaning lives in Resolve. Consequence for the device profile: store physical element identity only.
- Shift Up modifier toggled with Offset gives Log mode (native); Shift Up + trackballs controls Windows palette, Shift Down + trackballs
  controls Sizing palette (native).
- **Free combinations (55 in the device profile, `free_bindings`):** 31 of them (30 shift combinations + plain `user`) were checked against the manual's
  Control Table (p. 18-22). Every one is listed as "-" (no native function), and the manual has exactly 30 such shift cells plus the plain
  user key. The other 24 (`shift_up` or `shift_down` + one of the 12 knob presses) are not in the manual's table; they were found in the live test below.

- **Live test of the free combinations** (Resolve 21.0.4.5 Studio, one computer, panel on USB, this program not running, throw-away project):
  - All 31 button combinations from the manual: no reaction in Resolve (manual confirmed).
  - `shift_up` / `shift_down` + each of the 12 knob presses: no reaction. A knob press **without** shift resets the control (native, so not free).
  - `shift_up` / `shift_down` + each of the 12 knob turns: the same reaction as without shift (not free).
  - `shift_up` / `shift_down` + lift trackball, and `shift_down` + lift ring: nothing happens at all, not even the normal lift change.
  - **Not tested:** `shift_up` + lift ring, and all gamma and gain trackballs and rings with a shift key.
  - Shift + a turning element cannot be used as a binding yet: `valid_binding_name` accepts buttons only (Phase 4).
- Not decoded yet: battery/connection status and the rear Bluetooth button (only report ids 02, 05 and 06 were seen). Turning of knobs, trackballs and rings **is decoded since the C3 run and entered in the device profile since v0.3.5** (`channels`, see the report sections above).

### Naming scheme (decided, applied in v0.3.0)

- Knob press: `<name>_knob_press`, knob turn: `<name>_knob_turn`.
- Knob names: ylift, ygamma, ygain, contrast, pivot, mid_detail, color_boost, shadows, highlights, saturation, hue, lum_mix.
- Trackballs: `lift_trackball`, `gamma_trackball`, `gain_trackball`. Rings: `lift_ring`, `gamma_ring`, `gain_ring`.
- The user renamed the knob presses by hand in v0.2.1; the device profile carries the same names.
