"""Tests for src.utils.text — pure string helpers."""
from src.utils.text import full_name


def test_full_name_first_and_last():
    assert full_name({"first_name": "Đạt", "last_name": "Trần"}) == "Đạt Trần"


def test_full_name_first_only():
    assert full_name({"first_name": "Đạt"}) == "Đạt"


def test_full_name_last_only():
    assert full_name({"last_name": "Trần"}) == "Trần"


def test_full_name_empty():
    assert full_name({}) == ""


def test_full_name_strips_whitespace():
    assert full_name({"first_name": "  Đạt  ", "last_name": ""}) == "Đạt"
