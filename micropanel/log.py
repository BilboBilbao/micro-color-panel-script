"""Logging: one logger 'panel', anonymized, with machine-readable fields. Standard library only.

Console: plain text.  panel.log: the same text plus machine-readable fields in [brackets].
Paths are shortened and the names of other programs are never logged.
Nothing here runs at import time except creating the logger; setup_logging() adds the handlers.
"""
import json
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from micropanel import BASE

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

log = logging.getLogger("panel")
log.setLevel(logging.INFO)


def _sanitize_pairs():
    """(text, replacement) pairs that hide the project folder and the home folder."""
    pairs = []
    try:
        home = Path.home()
    except RuntimeError:
        home = None
    for path, label in ((BASE, "<project>"), (home, "<home>")):   # project first: it usually lies inside home
        if path is None:
            continue
        doubled = str(path).replace("\\", "\\\\")     # how Python writes a Windows file name inside an OSError text
        for text in dict.fromkeys((str(path), path.as_posix(), doubled)):
            if text and text not in (".", "/", "\\", "\\\\"):
                pairs.append((text, label))
    return pairs


_SANITIZE = _sanitize_pairs()


def anonymize(text):
    """Replaces the project folder and the home folder in a text by <project> and <home>."""
    for needle, label in _SANITIZE:
        text = re.sub(re.escape(needle), lambda _m, label=label: label, text, flags=re.IGNORECASE)
    return text


class AnonymizeFilter(logging.Filter):
    def filter(self, record):
        record.msg = anonymize(record.getMessage())
        record.args = ()
        fields = getattr(record, "fields", None)
        if fields:
            record.fields = {k: anonymize(v) if isinstance(v, str) else v for k, v in fields.items()}
        return True


def _field_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text == "" or any(c in text for c in ' []"='):
        return json.dumps(text, ensure_ascii=False)
    return text


class FileFormatter(logging.Formatter):
    """Normal log line plus ' [key=value key=value]' for machine reading."""

    def format(self, record):
        text = super().format(record)
        fields = getattr(record, "fields", None)
        if fields:
            text += " [" + " ".join(f"{k}={_field_text(v)}" for k, v in fields.items()) + "]"
        return text


def setup_logging(to_file=True, to_console=True):
    if log.handlers:
        return
    anonymizer = AnonymizeFilter()
    if to_file:
        fh = RotatingFileHandler(BASE / "panel.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(FileFormatter(LOG_FORMAT, LOG_DATE_FORMAT))
        fh.addFilter(anonymizer)
        log.addHandler(fh)
    if to_console and sys.stdout is not None:     # pythonw has no console
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        ch.addFilter(anonymizer)
        log.addHandler(ch)
    if not log.handlers:
        log.addHandler(logging.NullHandler())     # no handler at all would print warnings to stderr


def emit(level, event, message, *args, **fields):
    """One call writes the readable text and the machine-readable fields (event=..., plus the given fields)."""
    log.log(level, message, *args, extra={"fields": {"event": event, **fields}})