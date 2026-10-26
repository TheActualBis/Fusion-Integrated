"""Pure leave-policy rules used by the ELM services."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

LEAVE_CATEGORIES = ("CL", "RH", "SCL", "EL", "COL", "VL")
CONTINUOUS_CATEGORIES = frozenset({"EL", "COL", "VL"})
HALF_DAY = Decimal("0.5")


def requested_days(
    start: date,
    end: date,
    holidays: set[date] | None = None,
    *,
    category: str = "CL",
    half_day: str = "",
) -> Decimal:
    """Return chargeable days under the selected category's counting rule.

    EL, COL, and VL count every date in the interval. The other categories
    count only working dates not listed as closed holidays. A CL half-day is
    valid only for a one-day request and consumes half a day.
    """
    category = category.upper()
    if category not in LEAVE_CATEGORIES:
        raise ValueError("Choose one of CL, RH, SCL, EL, COL, or VL.")
    if end < start:
        raise ValueError("End date must be on or after start date.")
    if half_day and (category != "CL" or start != end or half_day not in {"first", "second"}):
        raise ValueError("Only a one-day CL request can use a first-half or second-half option.")
    if half_day:
        return HALF_DAY

    # Walk one date at a time so weekends, published holidays, and leave type
    # rules are all handled in one easy-to-follow place.
    closed = holidays or set()
    count = 0
    day = start
    while day <= end:
        if category in CONTINUOUS_CATEGORIES or (day.weekday() < 5 and day not in closed):
            count += 1
        day += timedelta(days=1)
    if count == 0:
        raise ValueError("The selected dates contain no chargeable leave days.")
    return Decimal(count)


def overlaps(
    start: date,
    end: date,
    other_start: date,
    other_end: date,
    *,
    half_day: str = "",
    other_half_day: str = "",
) -> bool:
    """Check interval overlap, allowing opposite CL halves on the same day."""
    if end < other_start or other_end < start:
        return False
    if start == end == other_start == other_end and half_day and other_half_day:
        return half_day == other_half_day
    return True


def year_end_entitlement(
    *,
    category: str,
    unused: Decimal,
    carry_forward_limit: Decimal | None = None,
) -> tuple[Decimal, Decimal]:
    """Return (lapsed, carried) days for an account at year end."""
    unused = max(unused, Decimal("0"))
    # These categories do not carry unused days into the next year.
    if category in {"CL", "RH", "SCL", "VL"}:
        return unused, Decimal("0")
    # EL and COL can carry days forward, but the policy may set a cap.
    if category in {"EL", "COL"}:
        carried = unused if carry_forward_limit is None else min(unused, carry_forward_limit)
        return unused - carried, carried
    raise ValueError("Unsupported leave category.")


def vacation_conversion(unused_vl: Decimal) -> Decimal:
    """Convert unused Vacation Leave to Earned Leave at two to one."""
    if unused_vl < 0:
        raise ValueError("Unused Vacation Leave cannot be negative.")
    return unused_vl / Decimal("2")


def validate_extension(*, category: str, original_end: date, new_end: date) -> None:
    if category not in CONTINUOUS_CATEGORIES:
        raise ValueError("Only ongoing EL, COL, or VL can be extended.")
    if new_end <= original_end:
        raise ValueError("An extension must end after the current approved leave.")


def resumption_outcome(approved_end: date, actual_return: date) -> str:
    """Classify return-to-duty date relative to the approved last leave day."""
    if actual_return == approved_end + timedelta(days=1):
        return "normal"
    return "early" if actual_return <= approved_end else "late"
