"""Pure verification and pay rules for work sessions. No database, no Flask.

Zoom classes all run on one shared host account, so the teacher row in a
participant report is the participant whose email is ZOOM_HOST_EMAIL. When
that row is missing (a second concurrent class, where the teacher claims host
after joining under their own name), the participant whose name contains
"teacher" is used instead. Everyone else is a student.

Paid time for a Zoom class is the shorter of the app clock and the teacher's
time in the meeting. Statuses:
  verified         gap <= 10 min, paid at the shorter time
  gap              gap > 10 min, still paid at the shorter time, needs review
  no_teacher       report exists but the teacher is not in it, paid 0
  awaiting_report  no report yet, paid 0 until one arrives
Office sessions are verified (paid at app time) or outside_geofence (paid 0).
"""
from datetime import datetime

GAP_TOLERANCE_MIN = 10

VERIFIED = 'verified'
GAP = 'gap'
NO_TEACHER = 'no_teacher'
AWAITING = 'awaiting_report'
OUTSIDE = 'outside_geofence'
OPEN = 'open'

FLAGGED_STATUSES = {GAP, NO_TEACHER, OUTSIDE}

LABELS = {
    VERIFIED: 'Verified',
    GAP: 'Gap',
    NO_TEACHER: 'Teacher not in meeting',
    AWAITING: 'Awaiting Zoom report',
    OUTSIDE: 'Outside geofence',
    OPEN: 'Clocked in',
}

# Calendar-dot colour for each status ('ok' / 'warn' / 'bad' / 'wait').
TONE = {VERIFIED: 'ok', GAP: 'warn', NO_TEACHER: 'bad', OUTSIDE: 'bad',
        AWAITING: 'wait', OPEN: 'wait'}


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace('Z', '+00:00'))


def _norm(value):
    return (value or '').strip().lower()


def teacher_rows(participants, host_email):
    """The participant segments that belong to the teacher."""
    host = _norm(host_email)
    rows = [p for p in participants or [] if host and _norm(p.get('email')) == host]
    if not rows:
        rows = [p for p in participants or [] if 'teacher' in _norm(p.get('name'))]
    return rows


def segment_minutes(p):
    if p.get('minutes') is not None:
        return float(p['minutes'])
    j, l = _parse_dt(p.get('join_at')), _parse_dt(p.get('leave_at'))
    if j and l:
        return max(0.0, (l - j).total_seconds() / 60)
    return 0.0


def student_count(participants, teacher):
    ids = {id(p) for p in teacher}
    seen = set()
    for p in participants or []:
        if id(p) in ids:
            continue
        seen.add(_norm(p.get('email')) or _norm(p.get('name')))
    return len(seen)


def evaluate_zoom(app_minutes, participants, host_email, has_report=True):
    """app_minutes: clock-in to clock-out. participants: the report rows for
    this meeting on this date, or None when there is no report yet."""
    out = {'mode': 'zoom', 'app_minutes': round(app_minutes, 2), 'zoom_minutes': None,
           'zoom_first_join': None, 'zoom_last_leave': None, 'students': None,
           'gap_minutes': None}
    if not has_report or participants is None:
        out.update(status=AWAITING, paid_minutes=0.0)
        return out
    teacher = teacher_rows(participants, host_email)
    out['students'] = student_count(participants, teacher)
    if not teacher:
        out.update(status=NO_TEACHER, paid_minutes=0.0)
        return out
    zoom_minutes = sum(segment_minutes(p) for p in teacher)
    joins = [_parse_dt(p.get('join_at')) for p in teacher if p.get('join_at')]
    leaves = [_parse_dt(p.get('leave_at')) for p in teacher if p.get('leave_at')]
    gap = abs(app_minutes - zoom_minutes)
    out.update(
        zoom_minutes=round(zoom_minutes, 2),
        zoom_first_join=min(joins) if joins else None,
        zoom_last_leave=max(leaves) if leaves else None,
        gap_minutes=round(gap, 1),
        paid_minutes=round(min(app_minutes, zoom_minutes), 2),
        status=GAP if gap > GAP_TOLERANCE_MIN else VERIFIED,
    )
    return out


def evaluate_office(app_minutes, distance_m, radius_m):
    inside = distance_m is not None and float(distance_m) <= float(radius_m)
    return {'mode': 'office', 'app_minutes': round(app_minutes, 2),
            'distance_m': distance_m, 'status': VERIFIED if inside else OUTSIDE,
            'paid_minutes': round(app_minutes, 2) if inside else 0.0}


def evaluate_session(session, participants, host_email, radius_m, has_report=True):
    """session: dict with mode, clock_in_at, clock_out_at, distance_m,
    auto_closed, review_status ('approved' / 'overridden' / None) and
    override_paid_minutes. Adds 'flagged', 'paid_hours' and 'label'."""
    cin, cout = _parse_dt(session.get('clock_in_at')), _parse_dt(session.get('clock_out_at'))
    if cout is None:
        res = {'mode': session.get('mode'), 'status': OPEN, 'app_minutes': None,
               'paid_minutes': 0.0, 'zoom_minutes': None}
    else:
        app_minutes = max(0.0, (cout - cin).total_seconds() / 60)
        if session.get('mode') == 'zoom':
            res = evaluate_zoom(app_minutes, participants, host_email, has_report)
        else:
            res = evaluate_office(app_minutes, session.get('distance_m'), radius_m)

    review = session.get('review_status')
    flagged = res['status'] in FLAGGED_STATUSES or bool(session.get('auto_closed'))
    if review == 'overridden' and session.get('override_paid_minutes') is not None:
        res['paid_minutes'] = round(float(session['override_paid_minutes']), 2)
        flagged = False
    elif review == 'approved':
        flagged = False
    res['flagged'] = flagged and res['status'] != OPEN
    res['review_status'] = review
    res['paid_hours'] = round(res['paid_minutes'] / 60, 4)
    label = LABELS[res['status']]
    if res['status'] == GAP:
        label = f"Gap {round(res['gap_minutes'])} min"
    elif res['status'] in (VERIFIED, OUTSIDE) and res.get('mode') == 'office' and res.get('distance_m') is not None:
        label = f"{label} · {round(float(res['distance_m']))} m"
    if session.get('auto_closed') and review is None:
        label += ' · auto-closed'
    if review == 'overridden':
        label += ' · overridden'
    elif review == 'approved' and res['status'] in FLAGGED_STATUSES:
        label += ' · approved'
    res['label'] = label
    res['tone'] = 'ok' if review in ('approved', 'overridden') and res['status'] != AWAITING else TONE[res['status']]
    if session.get('auto_closed') and review is None and res['tone'] == 'ok':
        res['tone'] = 'warn'
    return res
