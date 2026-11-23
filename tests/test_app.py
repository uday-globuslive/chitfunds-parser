import pytest

from app.ocr import normalize_date


def test_normalize_date_iso():
    assert str(normalize_date("2026-11-21")) == "2026-11-21"


def test_normalize_date_indian_format():
    assert str(normalize_date("21 Nov 2026")) == "2026-11-21"


def test_normalize_date_rejects_unknown():
    assert normalize_date("not a date") is None
