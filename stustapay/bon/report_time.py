from datetime import date, datetime, time, timezone
from enum import Enum

import pytz
from sftkit.error import InvalidArgument

REPORT_TIMEZONE = pytz.timezone("Europe/Berlin")


class ReportDayMode(str, Enum):
    CALENDAR_DAY = "calendar_day"
    EVENT_DAY = "event_day"


def selected_date_ranges(
    selected_dates: list[str] | None,
    *,
    day_mode: ReportDayMode,
    daily_end_time: time | None,
) -> list[tuple[datetime, datetime]]:
    if day_mode == ReportDayMode.EVENT_DAY and daily_end_time is None:
        raise InvalidArgument("daily end time must be configured when using event days")
    if not selected_dates:
        return []

    normalized_dates: set[date] = set()
    for selected_date_value in selected_dates:
        for part in selected_date_value.split(","):
            value = part.strip()
            if not value:
                continue
            try:
                normalized_dates.add(date.fromisoformat(value))
            except ValueError as exc:
                raise InvalidArgument(f"Invalid selected date: {value}") from exc

    boundary = daily_end_time if day_mode == ReportDayMode.EVENT_DAY else time()
    assert boundary is not None
    ranges: list[tuple[datetime, datetime]] = []
    for selected_date in sorted(normalized_dates):
        next_date = date.fromordinal(selected_date.toordinal() + 1)
        local_start = REPORT_TIMEZONE.localize(datetime.combine(selected_date, boundary))
        local_end = REPORT_TIMEZONE.localize(datetime.combine(next_date, boundary))
        ranges.append((local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)))
    return ranges


def is_in_ranges(value: datetime, ranges: list[tuple[datetime, datetime]]) -> bool:
    if not ranges:
        return True
    normalized = normalize_datetime(value)
    return any(start <= normalized < end for start, end in ranges)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def report_day(value: datetime, *, day_mode: ReportDayMode, daily_end_time: time | None) -> date:
    if day_mode == ReportDayMode.EVENT_DAY and daily_end_time is None:
        raise InvalidArgument("daily end time must be configured when using event days")
    local = normalize_datetime(value).astimezone(REPORT_TIMEZONE)
    if day_mode == ReportDayMode.EVENT_DAY:
        assert daily_end_time is not None
        if local.timetz().replace(tzinfo=None) >= daily_end_time:
            return local.date()
        return date.fromordinal(local.date().toordinal() - 1)
    return local.date()
