from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Literal


SCHEDULE_MONTHS = (3, 6, 9, 12, 15, 18, 21, 24, 30, 36, 42, 48, 54, 60, 66, 72)


@dataclass(frozen=True)
class ChildAge:
    completed_months: int
    remainder_days: int
    rounded_months: int


def add_calendar_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_child_age(birth_date: date, on_date: date) -> ChildAge:
    """Calculate age using completed calendar months and the PDF's >16-day rule."""
    if birth_date > on_date:
        raise ValueError("Tanggal lahir tidak boleh setelah tanggal pemeriksaan.")

    completed_months = (on_date.year - birth_date.year) * 12 + on_date.month - birth_date.month
    anniversary = add_calendar_months(birth_date, completed_months)
    if anniversary > on_date:
        completed_months -= 1
        anniversary = add_calendar_months(birth_date, completed_months)

    remainder_days = (on_date - anniversary).days
    rounded_months = completed_months + (1 if remainder_days > 16 else 0)
    return ChildAge(completed_months, remainder_days, rounded_months)


def recommended_screening_age(
    rounded_age_months: int,
    mode: Literal["routine", "concern"],
) -> int | None:
    """Return the form age to use now, or the next routine appointment age."""
    if rounded_age_months < 0 or rounded_age_months > 72:
        return None
    if rounded_age_months in SCHEDULE_MONTHS:
        return rounded_age_months
    if mode == "routine":
        return next((age for age in SCHEDULE_MONTHS if age > rounded_age_months), None)
    return next((age for age in reversed(SCHEDULE_MONTHS) if age < rounded_age_months), None)


def is_routine_screening_due(rounded_age_months: int) -> bool:
    """The PDF says to invite a child back at the next scheduled age for routine screening."""
    return rounded_age_months in SCHEDULE_MONTHS
