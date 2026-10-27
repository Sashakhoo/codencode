"""Time helpers for the staff module.

Every datetime is stored as timezone-aware UTC. Day boundaries, display and
schedules are in Malaysia time (Asia/Kuala_Lumpur, UTC+8, no DST).
SQLite (local dev, tests) hands back naive datetimes, so everything read from
the database goes through as_utc() first.
"""
from datetime import datetime, date, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    MYT = ZoneInfo('Asia/Kuala_Lumpur')
except Exception:  # pragma: no cover - tzdata missing; Malaysia has no DST
    MYT = timezone(timedelta(hours=8), 'MYT')

UTC = timezone.utc


def utcnow():
    return datetime.now(UTC)


def as_utc(dt):
    """Naive values are treated as UTC (that is what we store)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_myt(dt):
    dt = as_utc(dt)
    return dt.astimezone(MYT) if dt else None


def myt_date(dt):
    return to_myt(dt).date() if dt else None


def today_myt():
    return utcnow().astimezone(MYT).date()


def parse_hhmm(value):
    h, m = str(value).strip().split(':')[:2]
    return time(int(h), int(m))


def minutes_of(value):
    t = parse_hhmm(value) if not isinstance(value, time) else value
    return t.hour * 60 + t.minute


def myt_to_utc(d, t):
    """A Malaysia-local date + 'HH:MM' (or time) -> aware UTC datetime."""
    if not isinstance(t, time):
        t = parse_hhmm(t)
    return datetime.combine(d, t, tzinfo=MYT).astimezone(UTC)


def day_bounds_utc(d):
    start = datetime.combine(d, time(0, 0), tzinfo=MYT).astimezone(UTC)
    return start, start + timedelta(days=1)


def month_bounds(year, month):
    """First and last MYT date of the month."""
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def month_bounds_utc(year, month):
    first, last = month_bounds(year, month)
    return day_bounds_utc(first)[0], day_bounds_utc(last)[1]


def parse_month(value, default=None):
    """'2026-10' -> (2026, 10). Falls back to the current MYT month."""
    try:
        y, m = str(value).split('-')[:2]
        y, m = int(y), int(m)
        if 1 <= m <= 12 and 2000 <= y <= 2100:
            return y, m
    except Exception:
        pass
    if default:
        return default
    t = today_myt()
    return t.year, t.month


def parse_date(value):
    if isinstance(value, date):
        return value
    if not value:
        return None
    return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()


def fmt_time(dt):
    """'7:30 pm' in MYT."""
    local = to_myt(dt)
    if not local:
        return ''
    h = local.hour % 12 or 12
    return f"{h}:{local.minute:02d} {'pm' if local.hour >= 12 else 'am'}"


def fmt_hhmm(value):
    t = parse_hhmm(value)
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'pm' if t.hour >= 12 else 'am'}"
