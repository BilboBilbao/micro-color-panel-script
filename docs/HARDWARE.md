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

### LEDs and the report descriptor (Phase 2b, read only, nothing was sent to the panel)

**Observation (user; Resolve 21.0.4 Studio, panel on USB, this program not running):**
- Resolve closed, also after unplugging and plugging in again: no LED is lit. Resolve running: **all button LEDs are white**. The LEDs are therefore set by the computer, not by the panel itself.
- Pressing a button turns it green (Shift Up/Down while held, Offset, H/Lite, Cursor, and Play Still only while a playable still is selected) or red (Bypass, Disable); the next press turns it white again. All other buttons, **User included**, stay white when pressed. Switching Resolve from the Color page to the Edit page changes no LED.
- Resolve decides the state (Play Still depends on the selected still, which the panel cannot know).

**Report descriptor** (251 bytes, read with `hid.device.get_report_descriptor()` over USB; on Windows hidapi rebuilds it from system data, so details may differ from the descriptor stored in the panel). All usage pages are vendor defined (0xFF01 to 0xFF09):

| Report id | Direction | Data | Meaning |
|---|---|---|---|
| 2 | Input | 64 x 1 bit | buttons (52 bits used, see above) |
| 2 | Output | 64 x 1 bit | unknown, same layout as the button report |
| 3 | Feature | 2 x 8 bit | set by Resolve; hypothesis: LED brightness (see capture) |
| 4 | Output | 48 x 1 bit | coloured LEDs (green, red), one bit per LED (inferred, see capture) |
| 5 | Input | 3 x 96 bit | trackballs and rings (three groups of 12 bytes) |
| 6 | Input | 16 x 32 bit | knobs (12 decoded, channels 13 to 16 not used) |
| 7 | Feature | 1 x 8 bit + 4 x 8 bit | unknown |
| 8 | Input | 2 x 8 bit | never seen, unknown (status?) |
| 8 | Feature | 2 x 8 bit | read by Resolve; hypothesis: battery (see capture) |
| 10 | Feature | 1 x 8 bit | set to 1 by Resolve, purpose unknown |

A collection with usage 9 has no reports. The program has never sent an output or feature report or requested a feature report.

**Readings (hypotheses, not measured):**
- Both output reports consist of single bits only (no byte or multi-bit fields), so there are no colour or brightness values. One bit per LED (on/off) is more likely than an RGB value; whether green and red are separate bits is open.
- Resolve probably writes whole 64-bit or 48-bit masks. The LED state cannot be read back (no input report for it was seen), so a second writer would not know the current state and could switch off LEDs set by Resolve, and Resolve may overwrite its change.
- Open questions about the output path were partly answered by the capture below.

**Checked against the recordings (`recordings/rotary_raw.json`, slow gestures only, 18 elements, no truncated step):**
- Report 6 is 16 x 4 = 64 data bytes plus the report id byte, i.e. 65 bytes; the program and the recorder read 64. All 5491 recorded reports had length 64 and no read error. Bytes 49 to 63 were 0 in all of them, so nothing used is lost (the last used channel ends at byte 48). If channels 13 to 16 are ever needed, read 65 bytes. Measured only on the recording path, not separately for USB and Bluetooth.
- Report 5 has nine 4-byte channels from byte 1 in the descriptor. Byte 1 + 4k was 0 in all 2339 recorded reports, so the 24 bit reading from byte 2 + 4k loses nothing. Read as 32 bit from byte 1 + 4k the values would be 256 times larger (trackballs multiples of 4096, rings +-4096); sign and direction are the same. Not checked: fast movements (the low byte could become non-zero if the ring value grows with speed, see above).
- Bytes 45 and 46 (`38 04`) are the only non-zero bytes after byte 36 in report 5, although the wire report has 37 bytes. Their origin is unknown; the profile does not use them.

**Capture of what Resolve sends (Phase 2b step C; USBPcap and Wireshark on Windows 11, panel on USB, Resolve 21.0.4 Studio; two short captures, one while Resolve starts and one while the user pressed buttons; the captures stay local, they are not in the repo):**
- All traffic is HID class traffic on interface 2: interrupt OUT on endpoint 0x01, interrupt IN on endpoint 0x81, and the class requests SET_REPORT and GET_REPORT for feature reports. No vendor requests and no string descriptor requests were seen, so the vendor interface 0 plays no part here (at least in these captures).
- On the wire the button report (id 2) is 9 bytes (id + 8) and the trackball/ring report (id 5) is 37 bytes (id + 36), as in the descriptor. The 64 in the program is the read size.
- **Resolve starting** (in this order, within about 0.1 s): SET feature 3 = `03 00 00`; output report 4 = all zero; output report 2 = all zero; GET feature 1 (8 bytes, content not recorded here); SET feature 10 = `0a 01`; GET feature 8 = `08 00 64`. About 4 s later: GET feature 8 again (same value) and SET feature 3 = `03 32 32`.
- **Resolve running:** every 30 s it sends SET feature 10 = `0a 01` and SET feature 3 = `03 32 32` (a refresh).
- Hypotheses: feature 3 holds the LED brightness (0 = dark, 0x32 = 50 for both values), which would explain why the LEDs are dark without Resolve and white with it, while output report 2 stayed all zero. Feature 8 `00 64` may be the battery (100 %), also unconfirmed.
- **Every colour change is one output report 4** (`04` + 6 bytes, bit n = byte 1 + n // 8, bit n % 8). It sets one bit when the LED turns green or red and an all-zero report when it goes back to white. Output report 2 was never sent again, and pressing **User** sent nothing.
- Bits seen (assigned by the order in which the user pressed the buttons, Offset, Bypass, Disable, Shift Up, Shift Down, H/Lite, Cursor; not labelled by the capture, so an inference): Bypass 0, Offset 2, Disable 3, Shift Up 4, Shift Down 5, H/Lite 8, Cursor 10. Bits 1 and 9 were not seen (Play Still was not pressed, so one of them may be Play Still). No bit for User is known.
- The report always has all 48 bits, so each report probably sets the whole state of the coloured LEDs. A second program that sends it would switch off whatever Resolve has set, and Resolve rewrites it on its next change.

**Not done on purpose:** any write, any SET_REPORT and any GET_REPORT by this program. Whether the User LED can be controlled at all is unknown: its only candidate is the never-used output report 2 (64 bits) or an unused bit of report 4, and neither effect is known.

- The throwaway scripts of stages 1 and 2a (tools/led_test_stage1.py, tools/led_test_stage2a.py) and their tests were removed after the measurement; they are in the Git history.

### LED write test, stage 1 (D22, measured, user hardware, USB, Resolve 21.0.4 running on the Color page)

Throwaway script tools/led_test_stage1.py, only output report 4 (7 bytes: id 4 plus 6 data bytes), nothing else was sent. Each bit was on for 3 seconds, then all bits off.

Bit table: see stage 2a.

- Writing works while Resolve has the device open. No error, `write` returned 9 for every 7-byte report (hypothesis: hidapi pads to the 9 bytes of output report 2; the wire was not captured).
- Resolve never lights User or Viewer, but the panel does. Only green was seen; red is known from Bypass and Disable in Resolve.
- Panel works normally afterwards.
- Resolve restores its colors on the next change (Offset or Bypass pressed).
- Not measured: the other 39 bits, other colors, brightness, how long a lit LED stays on without further reports, what Resolve's own full report does to an externally lit bit. Report 4 always carries all 48 bits, so a second writer and Resolve overwrite each other.
- Further stages need a new decision by the user.

### LED write test, stage 2a (D23, measured, user hardware, USB, Resolve 21.0.4 running on the Color page)

Throwaway script tools/led_test_stage2a.py, only output report 4, all 48 bits one at a time (Enter before each, 2 seconds on, then all bits off). The call returned 9 for every 7-byte report, no error.

| Bit | Button | Color |
|---|---|---|
| 0 | Bypass | red |
| 1 | User | green |
| 2 | Offset | green |
| 3 | Disable | red |
| 4 | Shift Up | green |
| 5 | Shift Down | green |
| 6 | Play Still | green |
| 7 | Wipe Still | green |
| 8 | H/Lite | green |
| 9 | Viewer | light green (very bright in stage 1) |
| 10 | Cursor | green |
| 11 to 47 | none | nothing visible |

- Only 11 buttons have a colored LED in report 4, one bit each. No other colors were seen, and there are no two bits for one button, so there is nothing to combine inside report 4.
- Red or green seems to belong to the button, not to a value (Bypass and Disable are red). Why Viewer is lighter is unknown.
- The white light of all buttons is not controlled by report 4. Hypothesis, not measured: output report 2 (64 single bits, sent all zero by Resolve at start).
- Panel works normally afterwards. Resolve restores its colors afterwards.
- This table replaces the bit table of stage 1.

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
  Whether other colors are possible is unknown (see the LED section above).
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
