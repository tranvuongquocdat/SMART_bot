"""Tests for src.utils.validation — pure enum validation helpers."""
import pytest

from src.utils.validation import (
    TASK_PRIORITY_VALUES,
    TASK_STATUS_VALUES,
    validate_priority,
    validate_status,
)


def test_task_status_values_canonical():
    assert TASK_STATUS_VALUES == ("Mới", "Đang làm", "Hoàn thành", "Huỷ")


def test_task_priority_values_canonical():
    assert TASK_PRIORITY_VALUES == ("Cao", "Trung bình", "Thấp")


def test_validate_status_case_insensitive():
    assert validate_status("mới") == "Mới"
    assert validate_status("ĐANG LÀM") == "Đang làm"


def test_validate_status_returns_canonical_form():
    assert validate_status("Hoàn thành") == "Hoàn thành"


def test_validate_status_invalid_raises():
    with pytest.raises(ValueError, match="Status 'foo' không hợp lệ"):
        validate_status("foo")


def test_validate_priority_case_insensitive():
    assert validate_priority("cao") == "Cao"
    assert validate_priority("TRUNG BÌNH") == "Trung bình"


def test_validate_priority_invalid_raises():
    with pytest.raises(ValueError, match="Priority 'urgent' không hợp lệ"):
        validate_priority("urgent")
