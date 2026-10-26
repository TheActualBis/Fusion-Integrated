from datetime import date
from decimal import Decimal

import pytest

from modules.leave.domain import (
    overlaps,
    requested_days,
    resumption_outcome,
    vacation_conversion,
    year_end_entitlement,
)


def test_cl_counts_weekdays_and_allows_half_day():
    assert requested_days(date(2026, 3, 2), date(2026, 3, 8), category="CL") == 5
    assert requested_days(
        date(2026, 3, 2), date(2026, 3, 2), category="CL", half_day="first",
    ) == Decimal("0.5")


def test_continuous_categories_include_weekends_and_holidays():
    assert requested_days(
        date(2026, 3, 6), date(2026, 3, 9), {date(2026, 3, 9)}, category="EL",
    ) == 4


def test_different_cl_halves_do_not_overlap_but_same_half_does():
    day = date(2026, 3, 2)
    assert not overlaps(day, day, day, day, half_day="first", other_half_day="second")
    assert overlaps(day, day, day, day, half_day="first", other_half_day="first")


def test_year_end_carry_and_vacation_conversion():
    assert year_end_entitlement(category="EL", unused=Decimal("7"), carry_forward_limit=None) == (Decimal("0"), Decimal("7"))
    assert year_end_entitlement(category="COL", unused=Decimal("7"), carry_forward_limit=Decimal("5")) == (Decimal("2"), Decimal("5"))
    assert year_end_entitlement(category="CL", unused=Decimal("7")) == (Decimal("7"), Decimal("0"))
    assert vacation_conversion(Decimal("3.5")) == Decimal("1.75")


@pytest.mark.parametrize("actual, expected", [
    (date(2026, 6, 2), "normal"),
    (date(2026, 6, 1), "early"),
    (date(2026, 6, 3), "late"),
])
def test_resumption_outcome(actual, expected):
    assert resumption_outcome(date(2026, 6, 1), actual) == expected
