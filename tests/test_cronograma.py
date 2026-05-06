from datetime import date

import pytest

from src.commands.cronograma import (
    WEEKDAY_OPTIONS,
    _PYTHON_WEEKDAY,
    _compute_study_window,
    _parse_test_date,
)
from src.prompts.cronograma import (
    CRONOGAMA_SYSTEM_PROMPT,
    build_cronograma_messages,
    format_date_pt,
)


def test_parse_test_date_valid() -> None:
    result = _parse_test_date("2026-06-15")
    assert result == date(2026, 6, 15)


def test_parse_test_date_valid_leap_year() -> None:
    result = _parse_test_date("2028-02-29")
    assert result == date(2028, 2, 29)


def test_parse_test_date_invalid_garbage() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _parse_test_date("not-a-date")


def test_parse_test_date_invalid_wrong_format() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _parse_test_date("15/06/2026")


def test_parse_test_date_invalid_empty() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _parse_test_date("")


def test_format_date_pt() -> None:
    assert format_date_pt(date(2026, 5, 18)) == "Seg 18/Mai/2026"
    assert format_date_pt(date(2026, 6, 15)) == "Seg 15/Jun/2026"
    assert format_date_pt(date(2026, 1, 1)) == "Qui 01/Jan/2026"


def test_calendar_window_computation() -> None:
    test_date = date(2026, 6, 15)
    today = date(2026, 5, 10)
    selected_weekdays = [0, 1, 2, 3, 4]
    days_before_test = 3

    dates, error = _compute_study_window(
        test_date=test_date,
        today=today,
        days_before_test=days_before_test,
        selected_weekdays=selected_weekdays,
    )

    assert error is None
    assert len(dates) > 0
    for d in dates:
        assert d.weekday() in selected_weekdays
        assert today < d < test_date


def test_calendar_window_weekends_only() -> None:
    test_date = date(2026, 6, 15)
    today = date(2026, 5, 10)
    selected_weekdays = [5, 6]
    days_before_test = 3

    dates, error = _compute_study_window(
        test_date=test_date,
        today=today,
        days_before_test=days_before_test,
        selected_weekdays=selected_weekdays,
    )

    assert error is None
    assert len(dates) > 0
    for d in dates:
        assert d.weekday() in (5, 6)


def test_calendar_window_empty_when_no_weekdays_match() -> None:
    test_date = date(2026, 5, 19)
    today = date(2026, 5, 12)
    selected_weekdays = [0]
    days_before_test = 3

    dates, error = _compute_study_window(
        test_date=test_date,
        today=today,
        days_before_test=days_before_test,
        selected_weekdays=selected_weekdays,
    )

    assert error is not None
    assert "Nenhum dia" in error
    assert len(dates) == 0


def test_calendar_window_too_short() -> None:
    test_date = date(2026, 5, 13)
    today = date(2026, 5, 10)
    selected_weekdays = [0, 1, 2, 3, 4]
    days_before_test = 3

    dates, error = _compute_study_window(
        test_date=test_date,
        today=today,
        days_before_test=days_before_test,
        selected_weekdays=selected_weekdays,
    )

    assert error is not None
    assert "muito próxima" in error
    assert len(dates) == 0


def test_build_messages_structure() -> None:
    test_date = date(2026, 6, 15)
    calendar_dates = [date(2026, 5, 18), date(2026, 5, 19)]
    messages = build_cronograma_messages(
        test_date=test_date,
        subjects="Civil, Penal",
        hours_per_day=4,
        instructions=None,
        calendar_dates=calendar_dates,
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_build_messages_includes_hours_per_day() -> None:
    test_date = date(2026, 6, 15)
    calendar_dates = [date(2026, 5, 18)]
    messages = build_cronograma_messages(
        test_date=test_date,
        subjects="Civil",
        hours_per_day=6,
        instructions=None,
        calendar_dates=calendar_dates,
    )

    assert "6h" in messages[0]["content"]
    assert "6h" in messages[1]["content"]


def test_build_messages_includes_selected_dates() -> None:
    test_date = date(2026, 6, 15)
    calendar_dates = [date(2026, 5, 18), date(2026, 5, 19), date(2026, 5, 20)]
    messages = build_cronograma_messages(
        test_date=test_date,
        subjects="Civil",
        hours_per_day=4,
        instructions=None,
        calendar_dates=calendar_dates,
    )

    user_content = messages[1]["content"]
    for d in calendar_dates:
        assert format_date_pt(d) in user_content


def test_build_messages_instructions_none() -> None:
    test_date = date(2026, 6, 15)
    calendar_dates = [date(2026, 5, 18)]
    messages = build_cronograma_messages(
        test_date=test_date,
        subjects="Civil",
        hours_per_day=4,
        instructions=None,
        calendar_dates=calendar_dates,
    )

    assert "Nenhuma" in messages[1]["content"]


def test_build_messages_instructions_custom() -> None:
    test_date = date(2026, 6, 15)
    calendar_dates = [date(2026, 5, 18)]
    messages = build_cronograma_messages(
        test_date=test_date,
        subjects="Civil",
        hours_per_day=4,
        instructions="foco mais em Civil",
        calendar_dates=calendar_dates,
    )

    assert "foco mais em Civil" in messages[1]["content"]


def test_weekday_select_options_count() -> None:
    assert len(WEEKDAY_OPTIONS) == 7


def test_weekday_mapping_complete() -> None:
    assert len(_PYTHON_WEEKDAY) == 7
    assert _PYTHON_WEEKDAY["segunda"] == 0
    assert _PYTHON_WEEKDAY["domingo"] == 6


def test_system_prompt_includes_hours_constraint() -> None:
    assert "{hours_per_day}" in CRONOGAMA_SYSTEM_PROMPT
