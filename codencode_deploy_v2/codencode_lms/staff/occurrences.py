"""Expand recurring schedules into concrete dated sessions.

A rule is one weekday + time slot of a cohort (Zoom class) or a staff shift
(office). `every_n_weeks` is counted from the first matching weekday on or
after the rule's start date. All dates and times here are Malaysia time.
"""
import json
from datetime import timedelta

from staff.timeutil import myt_to_utc, parse_date, minutes_of

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
_DAY_INDEX = {n.lower(): i for i, n in enumerate(DAY_NAMES)}
_DAY_INDEX.update({n.lower(): i for i, n in enumerate(DAY_SHORT)})


def day_index(value):
    if isinstance(value, int):
        return value
    return _DAY_INDEX.get(str(value).strip().lower())


def occurs_on(rule, d):
    """rule: weekday, start_date (or None), end_date (or None), every_n_weeks, skip_dates (set of dates)."""
    if d.weekday() != rule['weekday']:
        return False
    sd, ed = rule.get('start_date'), rule.get('end_date')
    if sd and d < sd:
        return False
    if ed and d > ed:
        return False
    if d in rule.get('skip_dates', ()):
        return False
    n = max(1, int(rule.get('every_n_weeks') or 1))
    if n == 1:
        return True
    anchor = sd or parse_date('1970-01-05')  # a Monday; only used when there is no start date
    first = anchor + timedelta(days=(rule['weekday'] - anchor.weekday()) % 7)
    if d < first:
        return False
    return ((d - first).days // 7) % n == 0


def expand_rule(rule, date_from, date_to):
    out = []
    d = date_from
    while d <= date_to:
        if occurs_on(rule, d):
            out.append(make_occurrence(rule, d))
        d += timedelta(days=1)
    return out


def make_occurrence(rule, d):
    start_at = myt_to_utc(d, rule['start'])
    end_at = myt_to_utc(d, rule['end'])
    if end_at <= start_at:          # a slot that runs past midnight
        end_at += timedelta(days=1)
    occ = {k: rule.get(k) for k in ('kind', 'source', 'ref_id', 'cohort_id', 'shift_id', 'user_id',
                                     'title', 'code', 'zoom_meeting_id', 'zoom_link', 'every_n_weeks')}
    occ.update(date=d, start=rule['start'], end=rule['end'], start_at=start_at, end_at=end_at,
               key=f"{rule['source']}:{rule['ref_id']}:{d.isoformat()}:{rule['start']}")
    return occ


def cohort_slots(cohort):
    try:
        raw = json.loads(cohort.schedule) if cohort.schedule else []
    except Exception:
        raw = []
    slots = []
    for s in raw or []:
        wd = day_index(s.get('day'))
        if wd is None or not s.get('start') or not s.get('end'):
            continue
        slots.append({'weekday': wd, 'start': s['start'][:5], 'end': s['end'][:5]})
    return slots


def cohort_rules(cohort, skip_dates=()):
    course = cohort.course
    title = f"{course.title} · {cohort.name}" if course else cohort.name
    rules = []
    for s in cohort_slots(cohort):
        rules.append({
            'kind': 'zoom', 'source': 'cohort', 'ref_id': cohort.id, 'cohort_id': cohort.id,
            'shift_id': None, 'user_id': cohort.teacher_id, 'title': title,
            'code': cohort.name, 'zoom_meeting_id': cohort.zoom_meeting_id,
            'zoom_link': cohort.zoom_link or (f'https://zoom.us/j/{cohort.zoom_meeting_id}' if cohort.zoom_meeting_id else None),
            'weekday': s['weekday'], 'start': s['start'], 'end': s['end'],
            'start_date': cohort.start_date, 'end_date': cohort.end_date,
            'every_n_weeks': getattr(cohort, 'every_n_weeks', None) or 1,
            'skip_dates': set(skip_dates),
        })
    return rules


def shift_rules(shift):
    skips = {parse_date(s) for s in (shift.skip_dates or [])}
    return [{
        'kind': 'office', 'source': 'shift', 'ref_id': shift.id, 'cohort_id': None,
        'shift_id': shift.id, 'user_id': shift.user_id, 'title': shift.title, 'code': 'Office',
        'zoom_meeting_id': None, 'zoom_link': None,
        'weekday': int(wd), 'start': shift.start_time, 'end': shift.end_time,
        'start_date': shift.start_date, 'end_date': shift.end_date,
        'every_n_weeks': shift.every_n_weeks or 1, 'skip_dates': skips,
    } for wd in (shift.days or [])]


def rules_for_user(user_id):
    from models import Cohort
    from staff.models import StaffShift, CohortSkipDate
    rules = []
    cohorts = Cohort.query.filter(Cohort.teacher_id == user_id).all()
    skips = {}
    if cohorts:
        for row in CohortSkipDate.query.filter(CohortSkipDate.cohort_id.in_([c.id for c in cohorts])):
            skips.setdefault(row.cohort_id, set()).add(row.date)
    for c in cohorts:
        rules += cohort_rules(c, skips.get(c.id, ()))
    for s in StaffShift.query.filter_by(user_id=user_id, status='active').all():
        rules += shift_rules(s)
    return rules


def occurrences(user, date_from, date_to):
    """Every scheduled class and shift for `user` between two MYT dates
    (inclusive), sorted by start. `user` is a User or a user id."""
    user_id = getattr(user, 'id', user)
    out = []
    for rule in rules_for_user(user_id):
        out += expand_rule(rule, date_from, date_to)
    out.sort(key=lambda o: o['start_at'])
    return out


def rules_overlap(a, b):
    """Same weekday, overlapping times and overlapping date ranges.
    Every-2-weeks parity is ignored on purpose (a conservative clash check)."""
    if a['weekday'] != b['weekday']:
        return False
    if not (minutes_of(a['start']) < minutes_of(b['end']) and minutes_of(b['start']) < minutes_of(a['end'])):
        return False
    a0, a1 = a.get('start_date'), a.get('end_date')
    b0, b1 = b.get('start_date'), b.get('end_date')
    if a0 and b1 and a0 > b1:
        return False
    if b0 and a1 and b0 > a1:
        return False
    return True
