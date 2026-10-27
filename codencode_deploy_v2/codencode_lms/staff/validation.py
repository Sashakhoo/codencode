"""Server-side validation for schedule requests: field checks, teacher
clashes across cohorts and shifts, and the shared Zoom account's limit on
concurrent meetings."""
import re

from staff.occurrences import (DAY_SHORT, cohort_rules, shift_rules, rules_overlap)
from staff.timeutil import parse_date, minutes_of


class ScheduleError(ValueError):
    pass


def normalize(data, kind):
    """Check and clean the posted form. kind: 'zoom' or 'office'."""
    title = (data.get('title') or data.get('name') or '').strip()
    if not title:
        raise ScheduleError('Enter a title.')
    try:
        days = sorted({int(d) for d in (data.get('days') or [])})
    except (TypeError, ValueError):
        raise ScheduleError('Days must be weekday numbers (Mon=0).')
    if not days or any(d < 0 or d > 6 for d in days):
        raise ScheduleError('Pick at least one day it repeats on.')
    start, end = (data.get('start') or '').strip()[:5], (data.get('end') or '').strip()[:5]
    try:
        start_min, end_min = minutes_of(start), minutes_of(end)
    except (ValueError, TypeError):
        raise ScheduleError('Enter start and end times as HH:MM.')
    if end_min <= start_min:
        raise ScheduleError('End time must be after the start time.')
    try:
        sd, ed = parse_date(data.get('start_date')), parse_date(data.get('end_date'))
    except ValueError:
        raise ScheduleError('Enter dates as YYYY-MM-DD.')
    if not sd or not ed:
        raise ScheduleError('Enter the From and Until dates.')
    if ed < sd:
        raise ScheduleError('"Until" must be on or after "From".')
    try:
        every = int(data.get('every_n_weeks') or 1)
    except (TypeError, ValueError):
        every = 0
    if every not in (1, 2):
        raise ScheduleError('Repeat must be every 1 or 2 weeks.')
    mid = re.sub(r'\D', '', str(data.get('zoom_meeting_id') or ''))
    if kind == 'zoom' and mid and not re.fullmatch(r'\d{9,11}', mid):
        raise ScheduleError('The Zoom meeting ID must be 9–11 digits.')
    return {'title': title, 'days': days, 'start': start, 'end': end,
            'start_date': sd.isoformat(), 'end_date': ed.isoformat(),
            'every_n_weeks': every, 'zoom_meeting_id': mid or None}


def _candidate_rules(p, kind):
    sd, ed = parse_date(p['start_date']), parse_date(p['end_date'])
    return [{'kind': kind, 'weekday': d, 'start': p['start'], 'end': p['end'],
             'start_date': sd, 'end_date': ed, 'every_n_weeks': p['every_n_weeks']}
            for d in p['days']]


def _request_rules(req):
    p = req.payload or {}
    try:
        rules = _candidate_rules({**p, 'days': p.get('days') or []}, 'zoom')
    except Exception:
        return []
    for r in rules:
        r['title'] = p.get('name') or p.get('title') or f'request #{req.id}'
    return rules


def _label(rule):
    return f"{rule.get('title')} on {DAY_SHORT[rule['weekday']]} {rule['start']}–{rule['end']}"


def check_conflicts(p, kind, teacher_id, *, exclude_cohort_id=None, exclude_shift_id=None,
                    exclude_request_id=None, zoom_max=2):
    """Raise ScheduleError naming the conflicting class, or return None."""
    from models import Cohort, User
    from staff.models import StaffShift, CohortScheduleRequest, CohortSkipDate  # noqa: F401

    new_rules = _candidate_rules(p, kind)
    teacher = User.query.get(teacher_id)
    tname = teacher.name if teacher else 'This teacher'

    cohorts = [c for c in Cohort.query.filter(Cohort.schedule.isnot(None)).all() if c.id != exclude_cohort_id]
    pending = [r for r in CohortScheduleRequest.query.filter_by(status='pending').all()
               if r.id != exclude_request_id and (exclude_cohort_id is None or r.cohort_id != exclude_cohort_id)]

    # 1. Teacher clash, across cohorts, shifts and pending cohort requests.
    mine = []
    for c in cohorts:
        if c.teacher_id == teacher_id:
            mine += cohort_rules(c)
    for s in StaffShift.query.filter(StaffShift.user_id == teacher_id,
                                     StaffShift.status.in_(('pending', 'active'))).all():
        if s.id != exclude_shift_id:
            mine += shift_rules(s)
    for r in pending:
        if r.requested_by == teacher_id:
            mine += _request_rules(r)
    for n in new_rules:
        for m in mine:
            if rules_overlap(n, m):
                raise ScheduleError(f'{tname} already has {_label(m)}.')

    # 2. Shared Zoom account: at most `zoom_max` meetings at the same time.
    if kind == 'zoom':
        zoom_rules = []
        for c in cohorts:
            zoom_rules += cohort_rules(c)
        for r in pending:
            zoom_rules += _request_rules(r)
        for n in new_rules:
            clashes = [z for z in zoom_rules if rules_overlap(n, z)]
            if len(clashes) >= zoom_max:
                names = ' and '.join(sorted({z['title'] for z in clashes}))
                raise ScheduleError(
                    f'Zoom limit: {names} already run on {DAY_SHORT[n["weekday"]]} at that time. '
                    f'The shared account can run {zoom_max} classes at once.')
    return None
