from datetime import datetime

import pytest

from app.models import AppConfig, calculate_advance, parse_time, target_datetime_today, trigger_datetime


def test_calculate_advance_without_cap() -> None:
    result = calculate_advance(20.0, 4.0, 80.0)
    assert result.theoretical_ms == 24.0
    assert result.final_ms == 24.0
    assert not result.capped


def test_calculate_advance_with_cap() -> None:
    result = calculate_advance(100.0, 10.0, 80.0)
    assert result.theoretical_ms == 110.0
    assert result.final_ms == 80.0
    assert result.capped


def test_target_and_trigger_time() -> None:
    now = datetime(2026, 8, 16, 7, 30)
    target = target_datetime_today("08:00:00.000", now)
    assert target == datetime(2026, 8, 16, 8, 0)
    assert trigger_datetime(target, 28.0) == datetime(2026, 8, 16, 7, 59, 59, 972000)


def test_time_requires_milliseconds() -> None:
    assert parse_time("08:00:00.123").microsecond == 123000
    with pytest.raises(ValueError):
        parse_time("8点")


def test_config_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        AppConfig(extra_compensation_ms=-1).validated()
