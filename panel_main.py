"""Micro Color Panel -> extra key bindings for DaVinci Resolve (v0.3.39)

Start:
  python panel_main.py                      normal operation
  python panel_main.py --trace              normal operation, additionally logs every button press
  python panel_main.py --diagnose           assisted diagnose (see docs/DIAGNOSTICS.md)
  python panel_main.py --diagnose --auto    diagnose with the automatic checks only, no questions
  python panel_main.py --diagnose --full    diagnose, plus: press all 52 inputs one after the other
  python panel_main.py --diagnose --rotary  diagnose, plus: turn every knob, ring and trackball once (checks the profile)
  python panel_main.py --diagnose --action-test
                                            diagnose, plus: run one real click/toggle binding in Resolve

Files in the same folder as this script:
  devices/micro_color_panel.json  hardware facts (USB ids, controls, report positions, free bindings)
  bindings.json                   your key bindings (reloaded automatically when the file changes)
  tabs.json                       calibrated click points (optional, reloaded automatically)
  micropanel/                     the program itself (micropanel/diagnose.py is only loaded with --diagnose)
Log file: panel.log in the same folder
"""
import sys

from micropanel.platform.windows import set_dpi_awareness

# This must run BEFORE the third-party packages are imported: a package can set the weaker 'system' awareness (1)
# when it is imported (measured with pyautogui, which is no longer used), and Windows then refuses the change to 2.
# The result is logged by app.setup().
DPI_STATE = set_dpi_awareness()

from micropanel.app import main, missing_package_message  # noqa: E402  (after the DPI call above)

try:
    import hid                 # noqa: F401  package check only (micropanel imports it lazily)
    import pynput.mouse        # noqa: F401  package check only (micropanel imports it lazily)
    import pynput.keyboard     # noqa: F401  package check only (micropanel imports it lazily)
except ImportError as _import_error:
    _text = missing_package_message(getattr(_import_error, "name", None), sys.version_info)
    if sys.stdout is not None:                  # pythonw has no console
        print(_text)
    sys.exit(1)

if __name__ == "__main__":
    main(dpi_state=DPI_STATE)
