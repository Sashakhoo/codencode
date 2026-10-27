"""Staff module business logic on top of the database: clock-in/out,
evaluation of stored sessions, month summaries, payroll, reminders."""
from datetime import timedelta
from decimal import Decimal

from flask import current_app
from sqlalchemy.exc import IntegrityError

from models import db, User, Cohort
from staff import evaluate as ev
from staff.geo import haversine_m
from staff.models import (StaffProfile, WorkSession, ZoomParticipantReport, AuditLog,
                          StaffShift, CohortScheduleRequest)
from staff.occurrences import occurrences, DAY_SHORT
from staff.timeutil import (utcnow, as_utc, to_myt, myt_date, month_bounds, month_bounds_utc,
                            fmt_time, today_myt, MYT)

START_EARLY_MIN = 15
TL_START_H, TL_END_H = 8, 23   # timeline axis, 8am–11pm


class ClockError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def cfg(key, default=None):
    return current_app.config.get(key, default)


def is_staff(user):
    return bool(user and getattr(user, 'is_authenticated', False) and user.role in ('teacher', 'admin'))


def audit(actor_id, action, entity, entity_id, before=None, after=None, reason=None, commit=True):
    db.session.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id,
                            before=before, after=after, reason=reason))
    if commit:
        db.session.commit()


def staff_users():
    """Users who can appear in the staff portal (teachers and admins)."""
    return (User.query.filter(User.role.in_(('teacher', 'admin')))
            .order_by(User.role.desc(), User.name).all())


def profile_for(user_id):
    return StaffProfile.query.filter_by(user_id=user_id).first()


# ── Evaluation of stored sessions ───────────────────────────

class ReportCache:
    def __init__(self):
        self._c = {}

    def get(self, meeting_id, d):
        key = (meeting_id, d)
        if key not in self._c:
            rep = ZoomParticipantReport.query.filter_by(zoom_meeting_id=str(meeting_id), local_date=d).first() \
                if meeting_id else None
            self._c[key] = rep.participants if rep else None
        return self._c[key]


def evaluate_ws(ws, cache=None):
    cache = cache or ReportCache()
    participants = None
    if ws.mode == 'zoom':
        participants = cache.get(ws.zoom_meeting_id, myt_date(ws.clock_in_at))
    return ev.evaluate_session(ws.as_eval_dict(), participants,
                               cfg('ZOOM_HOST_EMAIL'), cfg('OFFICE_RADIUS_M'),
                               has_report=participants is not None)


def session_title(ws):
    if ws.mode == 'zoom':
        c = ws.cohort
        if c is not None:
            return (c.name, f"{c.course.title} · {c.name}" if c.course else c.name)
        return ('Zoom', f'Zoom {ws.zoom_meeting_id or ""}'.strip())
    task = ws.task or (ws.shift.title if ws.shift else 'Office work')
    return (task, task)


def _pos(dt):
    local = to_myt(dt)
    h = local.hour + local.minute / 60
    return max(0.0, min(100.0, (h - TL_START_H) / (TL_END_H - TL_START_H) * 100))


def session_row(ws, cache=None):
    e = evaluate_ws(ws, cache)
    short, full = session_title(ws)
    cin, cout = as_utc(ws.clock_in_at), as_utc(ws.clock_out_at)
    local = to_myt(cin)
    row = {
        'id': ws.id, 'user_id': ws.user_id, 'mode': ws.mode, 'short': short, 'title': full,
        'date': local.date(), 'date_iso': local.date().isoformat(),
        'dow': DAY_SHORT[local.weekday()], 'day_label': f"{local.day} {local.strftime('%b')}",
        'in': fmt_time(cin), 'out': fmt_time(cout) if cout else '',
        'in_at': cin, 'out_at': cout, 'eval': e,
        'app_hours': round((e['app_minutes'] or 0) / 60, 2) if e.get('app_minutes') is not None else None,
        'zoom_hours': round(e['zoom_minutes'] / 60, 2) if e.get('zoom_minutes') is not None else None,
        'paid_hours': round(e['paid_minutes'] / 60, 2),
        'zoom_in': fmt_time(e.get('zoom_first_join')) if e.get('zoom_first_join') else '',
        'zoom_out': fmt_time(e.get('zoom_last_leave')) if e.get('zoom_last_leave') else '',
        'task': ws.task or '', 'source': ws.source, 'auto_closed': ws.auto_closed,
        'zoom_meeting_id': ws.zoom_meeting_id, 'distance_m': ws.distance_m,
    }
    left = _pos(cin)
    right = _pos(cout or utcnow())
    row['bar_left'], row['bar_width'] = round(left, 2), round(max(9.0, right - left), 2)
    if e.get('zoom_first_join') and e.get('zoom_last_leave'):
        zl, zr = _pos(e['zoom_first_join']), _pos(e['zoom_last_leave'])
        row['zbar_left'], row['zbar_width'] = round(zl, 2), round(max(0.5, zr - zl), 2)
    return row


def sessions_query(user_id, year, month):
    start, end = month_bounds_utc(year, month)
    return (WorkSession.query.filter(WorkSession.user_id == user_id,
                                     WorkSession.clock_in_at >= start, WorkSession.clock_in_at < end)
            .order_by(WorkSession.clock_in_at.desc()))


def month_summary(user_id, year, month):
    """Everything the My Attendance page shows, for one user."""
    user = User.query.get(user_id)
    prof = profile_for(user_id)
    rate = float(prof.hourly_rate) if prof else 0.0
    cap = float(prof.monthly_cap_hours) if prof else 0.0
    cache = ReportCache()
    rows = [session_row(ws, cache) for ws in sessions_query(user_id, year, month).all()]
    paid = sum(r['paid_hours'] for r in rows)
    flagged = sum(1 for r in rows if r['eval']['flagged'])
    waiting = sum(1 for r in rows if r['eval']['status'] == ev.AWAITING)
    rank = {'bad': 3, 'warn': 2, 'wait': 1, 'ok': 0}
    first, last = month_bounds(year, month)
    today = today_myt()
    dots = []
    d = first
    while d <= last:
        tones = [r['eval']['tone'] for r in rows if r['date'] == d]
        tone = max(tones, key=lambda t: rank[t]) if tones else None
        dots.append({'date': d, 'iso': d.isoformat(), 'day': d.day, 'dow': DAY_SHORT[d.weekday()],
                     'tone': tone, 'today': d == today})
        d += timedelta(days=1)
    cohorts = Cohort.query.filter(Cohort.teacher_id == user_id, Cohort.schedule.isnot(None)).all()
    return {
        'user': user, 'profile': prof, 'rate': rate, 'cap': cap, 'rows': rows, 'dots': dots,
        'paid_hours': round(paid, 2), 'sessions': len(rows), 'flagged': flagged, 'waiting': waiting,
        'pay': round(paid * rate, 2),
        'cap_pct': round(paid / cap * 100, 1) if cap else None,
        'classes': ', '.join(sorted({c.name for c in cohorts})) or 'Office only',
    }


def payroll(year, month, user_ids=None):
    users = staff_users() if user_ids is None else User.query.filter(User.id.in_(user_ids)).all()
    out = []
    for u in users:
        s = month_summary(u.id, year, month)
        if user_ids is None and not s['profile'] and not s['rows']:
            continue
        cap = s['cap']
        s['cap_state'] = ('over' if cap and s['paid_hours'] > cap else
                          'warn' if cap and s['paid_hours'] >= 0.9 * cap else 'ok')
        out.append(s)
    return out


CSV_HEADER = ['date', 'staff', 'email', 'type', 'class_or_task', 'app_in', 'app_out', 'app_hours',
              'zoom_hours', 'paid_hours', 'status', 'rate', 'pay']


def csv_rows(summaries):
    lines = []
    for s in summaries:
        for r in sorted(s['rows'], key=lambda r: r['in_at']):
            lines.append([r['date_iso'], s['user'].name, s['user'].email, r['mode'], r['title'],
                          to_myt(r['in_at']).strftime('%H:%M'),
                          to_myt(r['out_at']).strftime('%H:%M') if r['out_at'] else '',
                          '' if r['app_hours'] is None else f"{r['app_hours']:.2f}",
                          '' if r['zoom_hours'] is None else f"{r['zoom_hours']:.2f}",
                          f"{r['paid_hours']:.2f}", r['eval']['label'], f"{s['rate']:.2f}",
                          f"{r['paid_hours'] * s['rate']:.2f}"])
    return lines


# ── Clock in / out ──────────────────────────────────────────

def open_session(user_id):
    return WorkSession.query.filter_by(user_id=user_id, clock_out_at=None).first()


def current_occurrence(user_id, now, cohort_id=None, kind='zoom'):
    """The occurrence whose window (15 min before start until the scheduled
    end) contains `now`."""
    d = myt_date(now)
    for o in occurrences(user_id, d - timedelta(days=1), d):
        if o['kind'] != kind or (cohort_id is not None and o['cohort_id'] != cohort_id):
            continue
        if o['start_at'] - timedelta(minutes=START_EARLY_MIN) <= now <= o['end_at']:
            return o
    return None


def _insert_session(ws):
    try:
        db.session.add(ws)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ClockError('You are already clocked in. Clock out first.', 409)
    return ws


def clock_in(user, data, now=None):
    now = now or utcnow()
    mode = (data.get('mode') or '').strip()
    if open_session(user.id):
        raise ClockError('You are already clocked in. Clock out first.', 409)

    if mode == 'zoom':
        try:
            cohort_id = int(data.get('cohort_id'))
        except (TypeError, ValueError):
            raise ClockError('Choose a class.')
        cohort = Cohort.query.get(cohort_id)
        if not cohort or cohort.teacher_id != user.id:
            raise ClockError('You are not the teacher of this class.', 403)
        occ = current_occurrence(user.id, now, cohort_id=cohort_id, kind='zoom')
        if not occ:
            raise ClockError('This class is not running now. You can start it from 15 minutes before the start time.')
        if not cohort.zoom_meeting_id:
            raise ClockError('This class has no Zoom meeting ID yet. Ask admin to add one.')
        ws = _insert_session(WorkSession(
            user_id=user.id, mode='zoom', cohort_id=cohort.id, zoom_meeting_id=cohort.zoom_meeting_id,
            clock_in_at=now, scheduled_start_at=occ['start_at'], scheduled_end_at=occ['end_at'], source='app'))
        return ws, {'zoom_link': occ['zoom_link']}

    if mode == 'office':
        olat, olng = cfg('OFFICE_LAT'), cfg('OFFICE_LNG')
        if olat is None or olng is None:
            raise ClockError('The office location is not configured. Ask admin to set OFFICE_LAT and OFFICE_LNG.', 503)
        try:
            lat, lng = float(data.get('lat')), float(data.get('lng'))
        except (TypeError, ValueError):
            raise ClockError('Your location is required to clock in at the office.')
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ClockError('That location is not valid.')
        try:
            acc = float(data.get('accuracy')) if data.get('accuracy') is not None else None
        except (TypeError, ValueError):
            acc = None
        if acc is not None and acc > 100:
            raise ClockError(f'GPS accuracy is {round(acc)} m. Move near a window or outside and try again (needs 100 m or better).')
        # Distance is always computed here, never taken from the browser.
        dist = haversine_m(float(olat), float(olng), lat, lng)
        radius = float(cfg('OFFICE_RADIUS_M') or 200)
        if dist > radius:
            raise ClockError(f'You are {round(dist)} m from the office. Clock-in is only allowed within {round(radius)} m.')
        occ = current_occurrence(user.id, now, kind='office')
        task = (data.get('task') or '').strip()[:500] or (occ['title'] if occ else 'Office work')
        ws = _insert_session(WorkSession(
            user_id=user.id, mode='office', task=task, clock_in_at=now, lat=lat, lng=lng,
            distance_m=round(dist, 1), shift_id=occ['shift_id'] if occ else None,
            scheduled_start_at=occ['start_at'] if occ else None,
            scheduled_end_at=occ['end_at'] if occ else None, source='app'))
        return ws, {'distance_m': round(dist)}

    raise ClockError('Unknown clock-in type.')


def clock_out(user, now=None):
    now = now or utcnow()
    ws = open_session(user.id)
    if not ws:
        raise ClockError('You are not clocked in.', 409)
    ws.clock_out_at = max(now, as_utc(ws.clock_in_at))
    db.session.commit()
    check_cap(user.id, now)
    return ws


# ── Cap warning ─────────────────────────────────────────────

def check_cap(user_id, now=None):
    now = now or utcnow()
    prof = profile_for(user_id)
    if not prof or not prof.monthly_cap_hours or float(prof.monthly_cap_hours) <= 0:
        return
    local = to_myt(now)
    s = month_summary(user_id, local.year, local.month)
    if s['paid_hours'] >= 0.9 * s['cap']:
        from staff.notify import notify, notify_admins
        key = f'{local.year}-{local.month:02d}'
        user = s['user']
        msg = f"{user.name} has {s['paid_hours']:.1f} of {s['cap']:.0f} approved hours this month (90% of the cap)."
        notify(user_id, 'cap90', key, f"You have used {s['paid_hours']:.1f} of your {s['cap']:.0f}-hour monthly cap.", '/staff/pay')
        notify_admins('cap90', f'{user_id}:{key}', msg, '/staff/admin/payroll')


# ── Reports matched ─────────────────────────────────────────

def after_report_matched(meeting_id, local_date):
    """Tell admin about Zoom sessions that came back with a gap or without the teacher."""
    from staff.notify import notify_admins
    start = MYT_day_start(local_date)
    sessions = WorkSession.query.filter(WorkSession.zoom_meeting_id == str(meeting_id),
                                        WorkSession.clock_in_at >= start,
                                        WorkSession.clock_in_at < start + timedelta(days=1)).all()
    for ws in sessions:
        e = evaluate_ws(ws)
        if e['status'] in (ev.GAP, ev.NO_TEACHER) and not ws.review_status:
            short, _ = session_title(ws)
            notify_admins('report_flag', f'ws{ws.id}',
                          f"{ws.user.name} · {short} on {local_date:%d %b}: {e['label']}. Review it.",
                          '/staff/admin/review')


def MYT_day_start(d):
    from staff.timeutil import day_bounds_utc
    return day_bounds_utc(d)[0]


# ── Scheduled jobs ──────────────────────────────────────────

def run_reminders(now=None):
    """Every 5 minutes: start reminders, no-show, forgot-to-clock-out and auto-close."""
    from staff.notify import notify, notify_admins
    now = now or utcnow()
    d = myt_date(now)
    sent = 0
    teacher_ids = {c.teacher_id for c in Cohort.query.filter(Cohort.teacher_id.isnot(None)).all()}
    teacher_ids |= {s.user_id for s in StaffShift.query.filter_by(status='active').all()}
    for uid in teacher_ids:
        user = User.query.get(uid)
        if not user or user.role not in ('teacher', 'admin'):
            continue
        for o in occurrences(uid, d - timedelta(days=1), d):
            start, end = o['start_at'], o['end_at']
            label = o['code'] if o['kind'] == 'zoom' else o['title']
            when = fmt_time(start)
            # 15 minutes before the start
            if start - timedelta(minutes=15) <= now < start:
                verb = 'Tap to start class.' if o['kind'] == 'zoom' else 'Tap to clock in.'
                sent += notify(uid, 'start15', o['key'], f'{label} starts at {when}. {verb}', '/staff/classes')
            # 10 minutes after the start with no clock-in
            if start + timedelta(minutes=10) <= now < end:
                has = WorkSession.query.filter(WorkSession.user_id == uid,
                                               WorkSession.clock_in_at >= start - timedelta(minutes=START_EARLY_MIN),
                                               WorkSession.clock_in_at <= end).first()
                if not has:
                    sent += notify(uid, 'noshow', o['key'], f'{label} started at {when} and you have not clocked in.', '/staff/classes')
                    notify_admins('noshow', f"{uid}:{o['key']}", f'{user.name} has not clocked in for {label} ({when}).', '/staff')
    # Still clocked in 30 minutes after the scheduled end, and auto-close after 12 hours.
    for ws in WorkSession.query.filter(WorkSession.clock_out_at.is_(None)).all():
        cin = as_utc(ws.clock_in_at)
        end = as_utc(ws.scheduled_end_at)
        if end and now >= end + timedelta(minutes=30):
            sent += notify(ws.user_id, 'forgot_out', f'ws{ws.id}', 'Forgot to clock out? You are still clocked in.', '/staff/clock')
        if now >= cin + timedelta(hours=12):
            auto_close(ws, now)
            sent += 1
    return sent


def auto_close(ws, now):
    """Close at the scheduled end (or at clock-in when there was no schedule,
    i.e. 0 hours) and flag it for admin review."""
    from staff.notify import notify_admins
    before = ws.snapshot()
    end = as_utc(ws.scheduled_end_at)
    cin = as_utc(ws.clock_in_at)
    ws.clock_out_at = end if end and end >= cin else cin
    ws.auto_closed = True
    audit(None, 'auto_close', 'work_session', ws.id, before, ws.snapshot(),
          'Open more than 12 hours; closed at the scheduled end.', commit=False)
    db.session.commit()
    short, _ = session_title(ws)
    notify_admins('auto_close', f'ws{ws.id}', f'{ws.user.name}\'s session ({short}) was auto-closed after 12 hours. Review it.',
                  '/staff/admin/review')


def monthly_payroll_notice(now=None):
    from staff.notify import notify_admins
    now = now or utcnow()
    local = to_myt(now)
    prev = (local.replace(day=1) - timedelta(days=1))
    notify_admins('payroll_ready', f'{prev.year}-{prev.month:02d}',
                  f"{prev.strftime('%B')} payroll ready. Pay by the 7th.",
                  f'/staff/admin/payroll?month={prev.year}-{prev.month:02d}')


def pending_counts():
    return {
        'schedule': StaffShift.query.filter_by(status='pending').count()
                    + CohortScheduleRequest.query.filter_by(status='pending').count(),
    }


def money(v):
    return f'{Decimal(str(v)).quantize(Decimal("0.01")):,}'
