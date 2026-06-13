from datetime import datetime
from zoneinfo import ZoneInfo

from src.agents.agent_loop import _current_time_directive


def test_directive_contains_tz_and_current_year():
    d = _current_time_directive("Asia/Ho_Chi_Minh")
    year = str(datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).year)
    assert "Asia/Ho_Chi_Minh" in d
    assert year in d
    assert "KHÔNG nói" in d  # chỉ thị không được nói "không biết giờ"


def test_directive_falls_back_on_bad_tz():
    d = _current_time_directive("Not/AZone")
    assert "Asia/Ho_Chi_Minh" in d


def test_directive_handles_none_tz():
    d = _current_time_directive(None)
    assert "Asia/Ho_Chi_Minh" in d
