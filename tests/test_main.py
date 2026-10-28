"""main(): start-up behavior and logging. The engine and the log setup are replaced, nothing here runs a loop."""
import logging
import sys
from pathlib import Path

import pytest

import micropanel.app as app
from micropanel import BASE
from micropanel.log import AnonymizeFilter, FileFormatter, LOG_FORMAT


@pytest.fixture
def quiet_start(monkeypatch):
    monkeypatch.setattr(app, "setup_logging", lambda *args, **kwargs: None)      # no console handler on a captured stream
    monkeypatch.setattr(app, "acquire_single_instance", lambda: True)
    monkeypatch.setattr(app, "configure_mouse", lambda: None)                    # the real one imports pyautogui


def test_unexpected_error_is_logged_with_function_and_line(monkeypatch, caplog, quiet_start, as_windows):   # B2
    caplog.set_level(logging.INFO)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(app, "run_engine", boom)
    with pytest.raises(SystemExit) as stop:
        app.main(["--no-log-file"], dpi_state=(2, 0))
    assert stop.value.code == 1
    found = [r.fields for r in caplog.records if getattr(r, "fields", {}).get("event") == "unexpected_error"]
    assert len(found) == 1
    assert found[0]["function"] == "boom" and isinstance(found[0]["line"], int)


def test_non_windows_start_gives_a_clear_message(monkeypatch, capsys, quiet_start):                         # B8
    monkeypatch.setattr(sys, "platform", "linux")

    def must_not_start(*args, **kwargs):
        raise AssertionError("the engine must not start on this system")

    monkeypatch.setattr(app, "run_engine", must_not_start)
    with pytest.raises(SystemExit) as stop:
        app.main(["--no-log-file"], dpi_state=(2, 0))
    assert stop.value.code == 1
    assert "Windows" in capsys.readouterr().out


def test_log_output_hides_home_and_project_folder():                                                       # B12
    home = Path.home()
    if len(str(home)) < 4:
        pytest.skip("home folder too short to check")
    record = logging.LogRecord("panel", logging.INFO, __file__, 1, "file %s and %s", (home / "x.json", BASE / "panel.log"), None)
    record.fields = {"event": "test", "path": str(home / "secret" / "y.json")}
    assert AnonymizeFilter().filter(record)
    text = FileFormatter(LOG_FORMAT).format(record)
    for hidden in (str(home), home.as_posix(), str(BASE), BASE.as_posix()):
        assert hidden.lower() not in text.lower()


@pytest.mark.parametrize("state,warnings", [((1, -2147024891), 1), ((2, 0), 0)],
                         ids=["system_aware_refused", "per_monitor"])
def test_setup_warns_about_dpi_only_when_not_per_monitor(monkeypatch, caplog, state, warnings):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(app, "setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "configure_mouse", lambda: None)
    app.setup(state, to_file=False, to_console=False)
    found = [r.fields for r in caplog.records if getattr(r, "fields", {}).get("event") == "setup_warning"]
    assert len(found) == warnings
    if warnings:
        assert found[0]["awareness"] == 1


def test_base_is_the_project_folder():
    assert (BASE / "panel_main.py").is_file()


@pytest.mark.parametrize("module,version,present,absent", [
    ("hid", (3, 11, 9), ["'hidapi'", "python -m pip install -r requirements.txt"], ["py -3.11"]),
    ("pynput.keyboard", (3, 15, 0), ["'pynput'", "3.15"], ["Traceback", "Newer Python versions"]),
    (None, (3, 11, 9), ["unknown"], ["Traceback"]),
], ids=["hid_tested_python", "dotted_name_other_python", "no_module_name"])
def test_missing_package_message(module, version, present, absent):
    text = app.missing_package_message(module, version)
    for part in present:
        assert part in text
    for part in absent:
        assert part not in text


# --------------------------------------------------------------------------
# Command line: --diagnose replaces --selftest (S5-3)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("argv,diagnose", [
    ([], False),
    (["--trace"], False),
    (["--diagnose"], True),
    (["--diagnose", "--auto"], True),
    (["--diagnose", "--full", "--rotary", "--action-test"], True),
], ids=["plain", "trace", "diagnose", "diagnose_auto", "diagnose_all_assisted"])
def test_parse_args_accepts(argv, diagnose):
    assert app.parse_args(argv).diagnose is diagnose


@pytest.mark.parametrize("argv", [
    ["--selftest"], ["--auto"], ["--full"], ["--rotary"], ["--action-test"],
    ["--diagnose", "--auto", "--full"], ["--diagnose", "--trace"],
], ids=["selftest_is_gone", "auto_alone", "full_alone", "rotary_alone", "action_test_alone",
        "auto_with_full", "trace_with_diagnose"])
def test_parse_args_rejects(argv):
    with pytest.raises(SystemExit) as stop:
        app.parse_args(argv)
    assert stop.value.code == 2


@pytest.mark.parametrize("system", ["win32", "linux"])
def test_diagnose_start_calls_run_with_the_flags_and_exits_with_its_result(monkeypatch, quiet_start, system):
    from micropanel import diagnose
    calls = []

    def fake_run(**flags):
        calls.append(flags)
        return 1

    def must_not_start(*args, **kwargs):
        raise AssertionError("the engine must not start in diagnose mode")

    monkeypatch.setattr(sys, "platform", system)                 # diagnose runs on every system
    monkeypatch.setattr(diagnose, "run", fake_run)
    monkeypatch.setattr(app, "run_engine", must_not_start)
    with pytest.raises(SystemExit) as stop:
        app.main(["--diagnose", "--auto"], dpi_state=(2, 0))
    assert stop.value.code == 1
    assert calls == [{"auto": True, "full": False, "action_test": False, "rotary": False}]


@pytest.mark.parametrize("filename,forbidden", [
    ("panel_main.py", ["selftest", "sys.modules[__name__]"]),
    ("micropanel/app.py", ["selftest_host"]),
], ids=["start_file", "app"])
def test_no_bridge_to_the_old_self_test_is_left(filename, forbidden):
    text = (BASE / filename).read_text(encoding="utf-8")
    for part in forbidden:
        assert part not in text


def test_selftest_py_is_gone():
    assert not (BASE / "selftest.py").exists()


# --------------------------------------------------------------------------
# RV-1: a failing setup (for example panel.log cannot be created) ends with a short message, not a traceback
# --------------------------------------------------------------------------
def test_setup_failure_prints_short_message_and_exits_1(monkeypatch, capsys, as_windows):
    def broken_setup(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(BASE / "panel.log"))

    def must_not_run(*args, **kwargs):
        raise AssertionError("run_program must not start after a failed setup")

    monkeypatch.setattr(app, "setup", broken_setup)
    monkeypatch.setattr(app, "run_program", must_not_run)
    with pytest.raises(SystemExit) as stop:
        app.main([], dpi_state=(2, 0))
    assert stop.value.code == 1
    out = capsys.readouterr().out
    assert "could not start" in out and "Permission denied" in out
    assert "Traceback" not in out and str(BASE) not in out


def test_setup_failure_without_console_is_silent_and_exits_1(monkeypatch, as_windows):
    def broken_setup(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(BASE / "panel.log"))

    monkeypatch.setattr(app, "setup", broken_setup)
    monkeypatch.setattr(sys, "stdout", None)                    # pythonw has no console
    with pytest.raises(SystemExit) as stop:
        app.main([], dpi_state=(2, 0))
    assert stop.value.code == 1


def test_log_file_cannot_be_created_gives_clean_exit(monkeypatch, capsys, as_windows):
    import micropanel.log as log_module

    def cannot_create(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(BASE / "panel.log"))

    monkeypatch.setattr(log_module.log, "handlers", [])         # setup_logging returns early when handlers exist
    monkeypatch.setattr(log_module, "RotatingFileHandler", cannot_create)
    with pytest.raises(SystemExit) as stop:                     # the real setup() runs, only the file creation fails
        app.main([], dpi_state=(2, 0))
    assert stop.value.code == 1
    assert "could not start" in capsys.readouterr().out


@pytest.mark.parametrize("version", [(3, 11, 9), (3, 12, 10), (3, 13, 15), (3, 14, 7)])
def test_python_version_note_inside_tested_range(version):
    assert app.python_version_note(version) is None


@pytest.mark.parametrize("version,shown", [((3, 9, 0), "3.9"), ((3, 10, 14), "3.10"),
                                           ((3, 15, 0), "3.15"), ((4, 0, 0), "4.0")])
def test_python_version_note_outside_tested_range(version, shown):
    assert app.python_version_note(version) == (
        f"Python {shown} is in use. This program was tested with Python 3.11 to 3.14. "
        "If something does not work, try Python 3.11 to 3.14.")


def test_missing_package_message_inside_range_has_no_version_hint():
    text = app.missing_package_message("hid", (3, 12, 10))
    assert "pip install -r requirements.txt" in text
    assert "is in use" not in text and "tested with" not in text


def test_missing_package_message_outside_range_has_only_the_hint():
    text = app.missing_package_message("hid", (3, 15, 0))
    assert ("Python 3.15 is in use. This program was tested with Python 3.11 to 3.14. "
            "If something does not work, try Python 3.11 to 3.14.") in text
    assert "Newer Python versions" not in text and "panel_main.py" not in text