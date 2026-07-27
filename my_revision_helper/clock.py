"""
Dates and times as the household experiences them.

Two different frames are in play and conflating them causes off-by-a-day bugs:

- **Calendar dates.** A due date is a day, not an instant: work set for Friday is
  due "on Friday" wherever the server happens to be running. These are stored as
  naive midnight and must be compared against the household's local date.
- **Timestamps.** `submitted_at` and friends are recorded with `utcnow()`, so
  they are naive UTC and must be compared against UTC instants.

Railway runs containers in UTC, so `datetime.now()` there is UTC rather than
local. During British Summer Time that is an hour behind, which is enough to put
late-evening work on the wrong day and to shift the week boundary. Everything
user-facing therefore goes through here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Where the family actually lives. A single timezone is correct for this app; if
# it ever needs to vary it belongs on the child's profile.
HOUSEHOLD_TZ = ZoneInfo("Europe/London")


def local_now() -> datetime:
    """The household's wall-clock time, naive so it can meet stored dates."""
    return datetime.now(HOUSEHOLD_TZ).replace(tzinfo=None)


def local_today() -> date:
    """Today's date where the family lives, not where the server runs."""
    return datetime.now(HOUSEHOLD_TZ).date()


def to_local_date(moment: datetime | None) -> date | None:
    """
    The household's calendar date for a stored UTC timestamp.

    Needed for anything counted in days, such as a streak: work finished at half
    past midnight is recorded as the previous day in UTC, which is not the day the
    child did it.
    """
    if moment is None:
        return None
    return moment.replace(tzinfo=ZoneInfo("UTC")).astimezone(HOUSEHOLD_TZ).date()


def week_dates(reference: date | None = None) -> tuple[date, date]:
    """
    The Monday of this week and the following Monday, as calendar dates.

    Use for anything compared against a due date.
    """
    today = reference or local_today()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=7)


def week_bounds(reference: datetime | None = None) -> tuple[datetime, datetime]:
    """
    This week's Monday-to-Monday span as naive midnights.

    Use for anything compared against a due date, which is stored as naive
    midnight on the day itself.
    """
    now = reference or local_now()
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, start + timedelta(days=7)


def week_bounds_utc(reference: datetime | None = None) -> tuple[datetime, datetime]:
    """
    The same week, expressed as the naive UTC instants it begins and ends at.

    Use for anything compared against a recorded timestamp. In summer the
    household week starts at 23:00 UTC the previous day, so comparing stored
    timestamps against a local midnight would misfile an hour of work each week.
    """
    local_start, local_end = week_bounds(reference)

    def to_utc(moment: datetime) -> datetime:
        return moment.replace(tzinfo=HOUSEHOLD_TZ).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    return to_utc(local_start), to_utc(local_end)
