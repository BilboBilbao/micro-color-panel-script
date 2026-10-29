# Micro Color Panel Bindings for DaVinci Resolve

Extra actions for the **DaVinci Resolve Micro Color Panel**. The program listens to the panel next to Resolve and runs
an action (a key combination or a mouse click) when you press a button that Resolve does not use.

Example: the **User** button adds a serial node before the current one `(shift+s)` (Yes, this program allows you to use the user button, which is not natively supported by Blackmagic.)

I am not a programmer, this is an independent hobby project. It is not made, supported or endorsed by Blackmagic Design.
"DaVinci Resolve" and "Micro Color Panel" are trademarks of their owner.
All code in this project was written by an AI: Claude, made by Anthropic. For more information see: [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md).

## What it does and does not do

- It only **reads** from the panel. It never writes to it and never touches its firmware.
- The panel can be connected by USB cable or by Bluetooth. The program finds it either way.
- Resolve keeps working as usual. The program does **not** switch off the native function of a button. It only adds a second action.
  Use buttons that Resolve does not assign (see "Free buttons" below).
- Today only **buttons** (50 of them) can have an action. Turning knobs, rings and trackballs is decoded, but cannot be bound yet.

## Compatibility

| Item | Status |
|---|---|
| Windows 11, USB cable | tested |
| Windows 11, Bluetooth connection | tested |
| DaVinci Resolve 21 Studio (21.0.4.5 and 21.1.0.17) | tested |
| Python 3.11 to 3.14 | tested |
| Python older than 3.11 | no planned testing |
| Automatic tests without a panel (GitHub Actions: Windows, macOS; Python 3.11 to 3.14) | run on every change |
| Windows 10 | untested |
| Resolve 19 and 20, Resolve free edition | untested |
| macOS | not supported yet (the automatic tests pass there, the panel itself was not tried) |

## Installation (for now)

A ready-made program without Python is planned. Until then:

1. Install **Python 3.11 to 3.14** from python.org.
2. Download or clone this project into a folder.
3. Open a terminal in that folder and run:

       python -m pip install -r requirements.txt

4. Start the program:

       python panel_main.py

   To run it without a console window, use `pythonw panel_main.py` (stop it in Task Manager, tab Details).
   You can start it before or after Resolve. If the panel is not found, it waits and connects as soon as it appears.

## Your first binding

1. Copy `bindings.example.json` to `bindings.json` (same folder).
2. Open `bindings.json` in a text editor and change it. Save.
3. The program loads the change by itself within a few seconds. No restart needed.

The example file sends `shift+s` (add a serial node before the current one) when you press **User**. Check in Resolve under
Keyboard Customization that this shortcut is set on your system.

All binding names, key names, action types and rules are explained in [docs/BINDINGS.md](docs/BINDINGS.md).

### Mouse clicks

For some functions, there is no keyboard shortcut in Resolve—for example, for the HDR palette tab. In this case, the program can click on a specific location on the screen.
The positions depend on your computer, monitor layout and window position, so they are stored in `tabs.json`,
which you create with `tools/calibration.py`. Recalibrate after moving the Resolve window or changing monitors or scaling.

### Free buttons

55 button combinations have no native function: 31 according to the Blackmagic manual (plain `User` and 30 combinations with a shift key) and 24 more (a shift key plus a knob press) found in a live test on Resolve 21.0.4.5 Studio.
The program logs a notice if you bind something else, because Resolve will then run both its own function and yours.
The list of free combinations is in [docs/BINDINGS.md](docs/BINDINGS.md). All 55 were checked in a live test on one computer (Resolve 21.0.4.5 Studio); see [docs/HARDWARE.md](docs/HARDWARE.md) for the details.

### Only in Resolve

By default an action only runs while Resolve is the active window. For an action that should work in any program
(for example media keys) add `"only_resolve": false` to the entry.

## If something does not work

- Look at `panel.log` in the project folder. It contains no user name, computer name or other program names.
- Start with `python panel_main.py --trace` to see every button press the program recognizes.
- `python panel_main.py --diagnose --auto` runs automatic checks. More in [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md).

## Development

Tests: `python -m pip install -r requirements-dev.txt`, then `python -m pytest -q`. The same tests run on every push on GitHub (Windows, macOS).
Hardware details: [docs/HARDWARE.md](docs/HARDWARE.md), all controls: [docs/BUTTONS.md](docs/BUTTONS.md). How this project was made: [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md).

## License

MIT, see [LICENSE](LICENSE).