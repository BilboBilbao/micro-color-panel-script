"""Start-up: command line, log setup, the checks before the loop, and the wiring of the parts (profile, config,
panel, actions, engine). No import side effects: the DPI call is made by the start file (panel_main.py), which
passes its result in as `dpi_state`. Third-party packages are only imported inside functions of other modules."""
import argparse
import logging
import platform
import sys

from micropanel import __version__
from micropanel.actions import configure_mouse, execute
from micropanel.config import ConfigManager, load_profile
from micropanel.device import open_panel
from micropanel.engine import run_engine
from micropanel.log import anonymize, emit, setup_logging
from micropanel.platform.windows import acquire_single_instance, dpi_warning_text

TESTED_PYTHON = (3, 11)      # the Python version this program was tested with
REQUIRED_PACKAGES = {"hid": "hidapi", "pynput": "pynput", "pyautogui": "pyautogui"}   # module name -> package name
NOT_WINDOWS_MESSAGE = ("This program only works on Windows at the moment (macOS support is planned).\n"
                       "Detected system: {system}")
SETUP_FAILED_MESSAGE = ("The program could not start: {error}\n"
                        "Check that the project folder is writable (the log file panel.log is created there).")


def python_version_note(version_info):
    """Hint text if the Python version differs from the tested one, otherwise None. Only a hint, never an error."""
    if tuple(version_info[:2]) == TESTED_PYTHON:
        return None
    return (f"Python {version_info[0]}.{version_info[1]} is in use. This program was tested with Python "
            f"{TESTED_PYTHON[0]}.{TESTED_PYTHON[1]}. If something does not work, try Python "
            f"{TESTED_PYTHON[0]}.{TESTED_PYTHON[1]}.")


def missing_package_message(module_name, version_info):
    """Friendly text for a Python package that cannot be loaded (shown before the log exists)."""
    module_name = module_name.split(".")[0] if module_name else ""
    package = REQUIRED_PACKAGES.get(module_name)
    if package:
        lines = [f"The Python package '{package}' is not installed.",
                 "Install the required packages with this command, started in the project folder:",
                 "    python -m pip install -r requirements.txt"]
    else:
        lines = [f"A required Python package could not be loaded ({module_name or 'unknown'}).",
                 "Try to install the required packages again, started in the project folder:",
                 "    python -m pip install -r requirements.txt"]
    note = python_version_note(version_info)
    if note:
        lines += ["", note,
                  "Newer Python versions often have no ready-made packages yet. If the installation fails,",
                  "install Python 3.11 and start the program with:  py -3.11 panel_main.py"]
    return "\n".join(lines)


def setup(dpi_state, to_file=True, to_console=True):
    """Everything that must happen once at start (not at import time). dpi_state is the result of
    set_dpi_awareness(), made by the start file before pyautogui was imported."""
    setup_logging(to_file, to_console)
    warning = dpi_warning_text(*dpi_state)
    if warning:
        emit(logging.WARNING, "setup_warning", "%s", warning, awareness=dpi_state[0])
    configure_mouse()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="panel_main.py", description="Extra bindings for the DaVinci Resolve Micro Color Panel.")
    parser.add_argument("--trace", action="store_true", help="log every recognized button press")
    parser.add_argument("--diagnose", action="store_true", help="run the assisted diagnose instead of the program")
    parser.add_argument("--auto", action="store_true", help="with --diagnose: automatic checks only, no questions")
    parser.add_argument("--full", action="store_true",
                        help="with --diagnose: also press all 52 inputs one after the other (Resolve reacts to the buttons)")
    parser.add_argument("--rotary", action="store_true",
                        help="with --diagnose: also turn every knob, ring and trackball once and check the profile (Resolve reacts)")
    parser.add_argument("--action-test", action="store_true", dest="action_test",
                        help="with --diagnose: also run one real click/toggle binding in Resolve, only after you type YES")
    parser.add_argument("--no-log-file", action="store_true", help=argparse.SUPPRESS)   # used by the diagnose, keeps panel.log untouched
    args = parser.parse_args(argv)
    if args.auto and not args.diagnose:
        parser.error("--auto only works together with --diagnose")
    if (args.full or args.action_test or args.rotary) and not args.diagnose:
        parser.error("--full, --rotary and --action-test only work together with --diagnose")
    if (args.full or args.action_test or args.rotary) and args.auto:
        parser.error("--full, --rotary and --action-test need you at the panel and cannot be combined with --auto")
    if args.trace and args.diagnose:
        parser.error("--trace cannot be combined with --diagnose")
    return args


def log_unexpected_error(error):
    """Writes an unexpected exception to the log: function and line where it was raised, and the error text."""
    tb = error.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    function = tb.tb_frame.f_code.co_name if tb is not None else "unknown"
    line = tb.tb_lineno if tb is not None else 0
    emit(logging.ERROR, "unexpected_error", "Unexpected error in %s, line %d: %r", function, line, error,
         function=function, line=line, error=repr(error))


def main(argv=None, dpi_state=(None, None)):
    args = parse_args(argv)
    if args.diagnose:
        setup(dpi_state, to_file=False, to_console=False)      # the diagnose prints its own output and writes its own report
        from micropanel import diagnose                        # only loaded here, never by a normal start
        sys.exit(diagnose.run(auto=args.auto, full=args.full, action_test=args.action_test, rotary=args.rotary))

    if sys.platform != "win32":                  # read at run time, never at import
        if sys.stdout is not None:               # pythonw has no console
            print(NOT_WINDOWS_MESSAGE.format(system=sys.platform))
        sys.exit(1)

    try:
        setup(dpi_state, to_file=not args.no_log_file)
    except Exception as e:  # noqa: BLE001
        if sys.stdout is not None:               # pythonw has no console
            print(SETUP_FAILED_MESSAGE.format(error=anonymize(repr(e))))
        sys.exit(1)
    try:
        run_program(args)
    except Exception as e:  # noqa: BLE001
        log_unexpected_error(e)
        sys.exit(1)


def run_program(args):
    emit(logging.INFO, "start", "Start v%s", __version__,
         version=__version__, python=platform.python_version(), os=platform.platform())
    note = python_version_note(sys.version_info)
    if note:
        emit(logging.INFO, "python_version_note", "%s", note)
    if args.trace:
        emit(logging.INFO, "trace_on", "Trace mode on: every button press is logged")
    if not acquire_single_instance():
        emit(logging.ERROR, "instance_blocked",
             "The script is already running (other terminal or pythonw). Exiting this instance.")
        sys.exit(1)

    profile, errors = load_profile()
    if profile is None or errors:
        for message in errors:
            emit(logging.ERROR, "profile_error", "Device profile: %s", message)
        sys.exit(1)
    emit(logging.INFO, "profile_loaded",
         "Profile loaded: %s, %d buttons decoded, %d rotary elements decoded",
         profile.name, len(profile.buttons), len(profile.rotary_channels),
         name=profile.name, buttons=len(profile.buttons), rotary_decoded=len(profile.rotary_channels))

    config = ConfigManager(set(profile.buttons), profile.free_bindings)
    config.load(initial=True)
    emit(logging.INFO, "running", "Running. Press Ctrl+C to quit.")
    run_engine(profile, config, lambda: open_panel(profile), execute, trace=args.trace)