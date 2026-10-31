"""Test setup: makes the project folder and the tests folder importable and provides the shared fixtures.
No test touches the real panel, keyboard or mouse: every test that needs hid or pynput
replaces the package by a fake for that one test."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for folder in (ROOT, HERE):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))


@pytest.fixture
def profile():
    from micropanel.config import load_profile
    loaded, errors = load_profile()
    assert errors == [] and loaded is not None, errors
    return loaded


@pytest.fixture
def as_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")