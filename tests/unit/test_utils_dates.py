"""Tests for src.utils.dates — pure date conversion helpers."""
import pytest

from src.utils.dates import date_to_ms, ms_to_date


def test_date_to_ms_returns_millisecond_timestamp():
    ms = date_to_ms("2026-01-01")
    assert isinstance(ms, int)
    assert ms > 0


def test_ms_to_date_round_trip():
    ms = date_to_ms("2026-04-28")
    assert ms_to_date(ms) == "2026-04-28"


def test_date_to_ms_invalid_raises():
    with pytest.raises(ValueError):
        date_to_ms("28/04/2026")
