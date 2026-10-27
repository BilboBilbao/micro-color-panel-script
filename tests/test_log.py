"""Log lines: machine-readable fields and anonymization. Expected values are written by hand."""
import logging
from pathlib import Path

import pytest

from micropanel import BASE
from micropanel.log import FileFormatter, LOG_DATE_FORMAT, LOG_FORMAT, anonymize


def test_file_formatter_appends_fields():
    record = logging.LogRecord("panel", logging.INFO, "", 0, "hello %s", ("world",), None)
    record.fields = {"event": "x", "name": "a b", "ok": True}
    text = FileFormatter(LOG_FORMAT, LOG_DATE_FORMAT).format(record)
    assert text.endswith('hello world [event=x name="a b" ok=true]')


def test_anonymize_replaces_project_and_home_folder():
    home = Path.home()
    if len(str(home)) < 4:
        pytest.skip("home folder too short to check")
    assert anonymize(f"{BASE}/bindings.json") == "<project>/bindings.json"
    assert anonymize(f"{home}/x") == "<home>/x"
    

@pytest.mark.parametrize("label, folder", [("<project>", BASE), ("<home>", Path.home())], ids=["project", "home"])
def test_anonymize_hides_folder_in_oserror_text(label, folder):        # RV-7
    if len(folder.name) < 4:
        pytest.skip("folder name too short to check")
    text = str(FileNotFoundError(2, "No such file or directory", str(folder / "bindings.json")))
    result = anonymize(text)       # on Windows Python writes the file name of an OSError with doubled backslashes
    assert label in result
    assert folder.name not in result