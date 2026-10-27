"""Staff portal pages (/staff/...) and JSON API (/staff/api/...).

Identity is always current_user. Teachers only ever see their own rows: every
query for a teacher filters on current_user.id; a teacher who sends another
user's id gets 403. Admins see everyone.
"""
import csv
import io
import json
from datetime import timedelta
from functools import wraps

from flask import (Blueprint, abort, current_app, jsonify, make_response, redirect,
                   render_template, request, url_for, send_from_directory)
from flask_login import current_user, logout_user

from models import db, User, Course, Cohort
from staff import deps, service, zoom_reports
from staff import evaluate as ev
from staff.extensions import csrf, limiter
from staff.models import (StaffProfile, StaffShift, CohortScheduleRequest, CohortSkipDate,
                          WorkSession, PushSubscription, AuditLog)
from staff.occurrences import DAY_NAMES, DAY_SHORT, occurrences
from staff.timeutil import (utcnow, as_utc, to_myt, myt_date, parse_date, parse_month, today_myt,
                            fmt_time, fmt_hhmm, MYT, UTC)
from staff.validation import ScheduleError, check_conflicts, normalize

bp = Blueprint('staff', __name__, url_prefix='/staff')

PUBLIC_ENDPOINTS = {'staff.login_page', 'staff.service_worker', 'staff.manifest'}


# ── Access control ──────────────────────────────────────────

def _is_api():
    return request.path.startswith('/staff/api/')


def _deny(status, message):
    if _is_api():
        return jsonify({'error': message}), status
    return render_template('staff/denied.html', message=message, status=status), status


@bp.before_request
def _guard():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        if _is_api():
            return jsonify({'error': 'Sign in first'}), 401
        return redirect(url_for('staff.login_page', next=request.full_path.rstrip('?')))
    if not service.is_staff(current_user):
        return _deny(403, 'The Staff Portal is only for Codencode staff and admin.')
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and current_app.config.get('WTF_CSRF_ENABLED', True):
        csrf.protect()
    return None


def admin_only(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if current_user.role != 'admin':
            return _deny(403, 'Admins only.')
        return f(*a, **kw)
    return wrapper


def is_admin():
    return current_user.is_authenticated and current_user.role == 'admin'


def target_user_id():
    """Whose records to show. Admin: ?user=<id> (default self). Teacher:
    always self; asking for anyone else is refused."""
    raw = request.args.get('user')
    if raw in (None, '', 'me'):
        return current_user.id
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        abort(400)
    if uid != current_user.id and not is_admin():
        abort(403)
    if uid != current_user.id:
        u = User.query.get(uid)
        if not u or u.role not in ('teacher', 'admin'):
            abort(404)
    return uid


@bp.errorhandler(403)
def _e403(e):
    return _deny(403, 'You can only see your own records.')


@bp.errorhandler(404)
def _e404(e):
    return _deny(404, 'Not found.')


@bp.errorhandler(400)
def _e400(e):
    return _deny(400, getattr(e, 'description', None) or 'Bad request.')


def _json():
    return request.get_json(silent=True) or {}


def _err(msg, status=400):
    return jsonify({'error': msg}), status


@bp.app_template_filter('daynames')
def _daynames(days):
    return ', '.join(DAY_SHORT[int(d)] for d in sorted(days or []))


@bp.app_template_filter('staff_dt')
def _staff_dt(dt):
    local = to_myt(dt)
    return f"{local.day} {local:%b} {fmt_time(dt)}" if local else ''


@bp.app_context_processor
def _ctx():
    if not request.path.startswith('/staff'):
        return {}
    ctx = {'is_admin': is_admin(), 'DAY_SHORT': DAY_SHORT, 'fmt_hhmm': fmt_hhmm,
           'vapid_public_key': current_app.config.get('VAPID_PUBLIC_KEY', ''),
           'office_name': current_app.config.get('OFFICE_NAME', 'office'),
           'radius_m': int(current_app.config.get('OFFICE_RADIUS_M') or 200)}
    if current_user.is_authenticated and service.is_staff(current_user):
        ws = service.open_session(current_user.id)
        ctx['open_ws'] = service.session_row(ws) if ws else None
        if is_admin():
            ctx['pending_schedule'] = service.pending_counts()['schedule']
            ctx['awaiting_reports'] = _awaiting_report_count()
            ctx['flagged_count'] = _flagged_count()
    return ctx


def _awaiting_report_count():
    since = utcnow() - timedelta(days=45)
    cache = service.ReportCache()
    return sum(1 for ws in WorkSession.query.filter(WorkSession.mode == 'zoom', WorkSession.clock_out_at.isnot(None),
                                                    WorkSession.clock_in_at >= since).all()
               if service.evaluate_ws(ws, cache)['status'] == ev.AWAITING)


def _flagged_count():
    since = utcnow() - timedelta(days=62)
    cache = service.ReportCache()
    return sum(1 for ws in WorkSession.query.filter(WorkSession.clock_in_at >= since,
                                                    WorkSession.review_status.is_(None)).all()
               if service.evaluate_ws(ws, cache)['flagged'])


def _month_ctx():
    y, m = parse_month(request.args.get('month'))
    months = []
    t = today_myt()
    yy, mm = t.year, t.month
    for _ in range(12):
        months.append((f'{yy}-{mm:02d}', f"{['January','February','March','April','May','June','July','August','September','October','November','December'][mm-1]} {yy}"))
        yy, mm = (yy - 1, 12) if mm == 1 else (yy, mm - 1)
    cur = f'{y}-{m:02d}'
    if cur not in [k for k, _ in months]:
        months.insert(0, (cur, cur))
    return y, m, cur, months


# ── PWA bits and sign-in ────────────────────────────────────

@bp.route('/sw.js')
def service_worker():
    resp = make_response(send_from_directory(current_app.static_folder, 'js/staff-sw.js'))
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Service-Worker-Allowed'] = '/staff/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@bp.route('/manifest.webmanifest')
def manifest():
    body = {
        'name': 'Codencode Staff', 'short_name': 'Staff', 'start_url': '/staff', 'scope': '/staff/',
        'display': 'standalone', 'background_color': '#eef2f7', 'theme_color': '#1f7ae0',
        'icons': [{'src': '/static/img/favicon-192.png', 'sizes': '192x192', 'type': 'image/png'},
                  {'src': '/static/img/favicon-180.png', 'sizes': '180x180', 'type': 'image/png'}],
    }
    resp = make_response(json.dumps(body))
    resp.headers['Content-Type'] = 'application/manifest+json'
    return resp


@bp.route('/login')
def login_page():
    if current_user.is_authenticated and service.is_staff(current_user):
        return redirect(_safe_next())
    student = current_user.is_authenticated and not service.is_staff(current_user)
    return render_template('staff/login.html', next=_safe_next(), student=student)


def _safe_next():
    nxt = request.args.get('next') or '/staff'
    return nxt if nxt.startswith('/staff') and not nxt.startswith('//') else '/staff'


@bp.route('/logout', methods=['POST'])
def logout():
    logout_user()
    return redirect(url_for('staff.login_page'))


# ── Pages: everyone on staff ────────────────────────────────

@bp.route('/')
def dashboard():
    uid = target_user_id()
    y, m, cur, months = _month_ctx()
    s = service.month_summary(uid, y, m)
    staff = service.staff_users() if is_admin() else []
    return render_template('staff/dashboard.html', s=s, month=cur, months=months, staff=staff,
                           uid=uid, page='dash')


@bp.route('/classes')
def classes():
    today = today_myt()
    now = utcnow()
    if is_admin() and request.args.get('all') != '0':
        uids = sorted({c.teacher_id for c in Cohort.query.filter(Cohort.teacher_id.isnot(None)).all()}
                      | {sh.user_id for sh in StaffShift.query.filter_by(status='active').all()} | {current_user.id})
    else:
        uids = [current_user.id]
    names = {u.id: u.name for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}
    items, seen = [], set()
    for uid in uids:
        for o in occurrences(uid, today - timedelta(days=1), today + timedelta(days=21)):
            if o['end_at'] < now:
                continue
            k = (uid, o['source'], o['ref_id'], o['start'])
            if k in seen:      # list each recurring slot once, at its next occurrence
                continue
            seen.add(k)
            live = o['start_at'] - timedelta(minutes=service.START_EARLY_MIN) <= now <= o['end_at']
            items.append({**o, 'teacher': names.get(uid, ''), 'mine': uid == current_user.id, 'live': live,
                          'next_label': f"{DAY_SHORT[o['date'].weekday()]} {o['date'].day} {o['date']:%b}",
                          'is_today': o['date'] == today})
    items.sort(key=lambda o: o['start_at'])
    return render_template('staff/classes.html', items=items, page='classes', today=today)


@bp.route('/clock')
def clock():
    now = utcnow()
    occ = service.current_occurrence(current_user.id, now, kind='office')
    return render_template('staff/clock.html', page='clock', occ=occ,
                           configured=current_app.config.get('OFFICE_LAT') is not None)


@bp.route('/schedule')
def schedule():
    return render_template('staff/schedule.html', page='sched', **_schedule_ctx(admin_view=False))


@bp.route('/pay')
def pay():
    uid = current_user.id
    y, m, cur, months = _month_ctx()
    if request.args.get('format') == 'csv':
        return _csv_response(service.payroll(y, m, [uid]), f'my-pay-{cur}.csv')
    rows = service.payroll(y, m, [uid])
    return render_template('staff/payroll.html', rows=rows, month=cur, months=months, page='pay', admin_view=False)


# ── Pages: admin ────────────────────────────────────────────

@bp.route('/admin/schedule')
@admin_only
def admin_schedule():
    return render_template('staff/schedule.html', page='admin_sched', **_schedule_ctx(admin_view=True))


@bp.route('/admin/reports')
@admin_only
def admin_reports():
    since = utcnow() - timedelta(days=45)
    cache = service.ReportCache()
    waiting = []
    for ws in WorkSession.query.filter(WorkSession.mode == 'zoom', WorkSession.clock_out_at.isnot(None),
                                       WorkSession.clock_in_at >= since).order_by(WorkSession.clock_in_at.desc()).all():
        if service.evaluate_ws(ws, cache)['status'] == ev.AWAITING:
            waiting.append(service.session_row(ws, cache) | {'user': ws.user})
    from staff.models import ZoomReportJob, ZoomParticipantReport
    jobs = ZoomReportJob.query.filter_by(done=False).order_by(ZoomReportJob.due_at).limit(20).all()
    recent = ZoomParticipantReport.query.order_by(ZoomParticipantReport.fetched_at.desc()).limit(15).all()
    return render_template('staff/reports.html', page='reports', waiting=waiting, jobs=jobs, recent=recent,
                           zoom_ready=bool(deps.zoom_configured and deps.zoom_configured()))


@bp.route('/admin/payroll')
@admin_only
def admin_payroll():
    y, m, cur, months = _month_ctx()
    if request.args.get('format') == 'csv':
        only = request.args.get('only', type=int)
        return _csv_response(service.payroll(y, m, [only] if only else None),
                             f'timesheet-{only}-{cur}.csv' if only else f'payroll-{cur}.csv')
    rows = service.payroll(y, m)
    return render_template('staff/payroll.html', rows=rows, month=cur, months=months, page='payroll', admin_view=True)


@bp.route('/admin/review')
@admin_only
def admin_review():
    since = utcnow() - timedelta(days=93)
    cache = service.ReportCache()
    flagged = []
    for ws in WorkSession.query.filter(WorkSession.clock_in_at >= since).order_by(WorkSession.clock_in_at.desc()).all():
        e = service.evaluate_ws(ws, cache)
        if e['flagged']:
            flagged.append(service.session_row(ws, cache) | {'user': ws.user})
    log = AuditLog.query.order_by(AuditLog.at.desc()).limit(25).all()
    users = {u.id: u.name for u in User.query.filter(User.id.in_({a.actor_id for a in log if a.actor_id})).all()} if log else {}
    return render_template('staff/review.html', page='review', flagged=flagged, log=log, actor_names=users,
                           to_myt=to_myt)


@bp.route('/admin/team')
@admin_only
def admin_team():
    people = [(u, service.profile_for(u.id)) for u in service.staff_users()]
    return render_template('staff/team.html', page='team', people=people)


@bp.route('/admin/sessions/<int:sid>')
@admin_only
def admin_session(sid):
    ws = WorkSession.query.get_or_404(sid)
    row = service.session_row(ws) | {'user': ws.user}
    log = AuditLog.query.filter_by(entity='work_session', entity_id=sid).order_by(AuditLog.at.desc()).all()
    return render_template('staff/session.html', page='review', r=row, ws=ws, log=log, to_myt=to_myt)


# ── Schedule page data ──────────────────────────────────────

def _schedule_ctx(admin_view):
    q_shifts = StaffShift.query
    q_reqs = CohortScheduleRequest.query
    if admin_view:
        cohorts = Cohort.query.filter(Cohort.schedule.isnot(None)).order_by(Cohort.id.desc()).all()
    else:
        q_shifts = q_shifts.filter(StaffShift.user_id == current_user.id)
        q_reqs = q_reqs.filter(CohortScheduleRequest.requested_by == current_user.id)
        cohorts = Cohort.query.filter(Cohort.teacher_id == current_user.id).order_by(Cohort.id.desc()).all()
    shifts = q_shifts.filter(StaffShift.status != 'withdrawn').order_by(StaffShift.status != 'pending',
                                                                       StaffShift.id.desc()).all()
    reqs = q_reqs.filter(CohortScheduleRequest.status.in_(('pending', 'rejected'))) \
        .order_by(CohortScheduleRequest.status != 'pending', CohortScheduleRequest.id.desc()).all()
    skips = {}
    if cohorts:
        for sk in CohortSkipDate.query.filter(CohortSkipDate.cohort_id.in_([c.id for c in cohorts])).order_by(CohortSkipDate.date):
            skips.setdefault(sk.cohort_id, []).append(sk.date)
    from staff.occurrences import cohort_slots
    cohort_rows = []
    for c in cohorts:
        slots = cohort_slots(c)
        if not slots:
            continue
        cohort_rows.append({'c': c, 'slots': slots, 'skips': skips.get(c.id, [])})
    teachers = service.staff_users() if admin_view else []
    courses = Course.query.order_by(Course.title).all()
    my_cohorts = cohorts if not admin_view else Cohort.query.order_by(Cohort.id.desc()).all()
    return {'shifts': shifts, 'reqs': reqs, 'cohort_rows': cohort_rows, 'teachers': teachers,
            'courses': courses, 'my_cohorts': my_cohorts, 'admin_view': admin_view,
            'today': today_myt(), 'zoom_ready': bool(deps.zoom_configured and deps.zoom_configured())}


def _csv_response(summaries, filename):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(service.CSV_HEADER)
    for line in service.csv_rows(summaries):
        w.writerow([_csv_safe(v) for v in line])
    resp = make_response(buf.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


def _csv_safe(v):
    s = str(v)
    return "'" + s if s[:1] in ('=', '+', '-', '@') and not s.replace('.', '', 1).lstrip('-').isdigit() else s


# ── API: read ───────────────────────────────────────────────

@bp.route('/api/status')
def api_status():
    ws = service.open_session(current_user.id)
    return jsonify({'open': _ws_json(service.session_row(ws)) if ws else None})


@bp.route('/api/sessions')
def api_sessions():
    uid = target_user_id()
    y, m = parse_month(request.args.get('month'))
    s = service.month_summary(uid, y, m)
    return jsonify({'user_id': uid, 'paid_hours': s['paid_hours'], 'pay': s['pay'],
                    'sessions': [_ws_json(r) for r in s['rows']]})


@bp.route('/api/sessions/<int:sid>')
def api_session(sid):
    q = WorkSession.query.filter(WorkSession.id == sid)
    if not is_admin():
        q = q.filter(WorkSession.user_id == current_user.id)
    ws = q.first()
    if not ws:
        return _err('Not found', 404)
    return jsonify(_ws_json(service.session_row(ws)))


@bp.route('/api/pay')
def api_pay():
    uid = target_user_id()
    y, m = parse_month(request.args.get('month'))
    s = service.payroll(y, m, [uid])[0]
    return jsonify({'user_id': uid, 'paid_hours': s['paid_hours'], 'pay': s['pay'], 'cap': s['cap'],
                    'flagged': s['flagged'], 'waiting': s['waiting'], 'sessions': s['sessions']})


@bp.route('/api/schedules')
def api_schedules():
    q = StaffShift.query
    rq = CohortScheduleRequest.query
    if not is_admin():
        q = q.filter(StaffShift.user_id == current_user.id)
        rq = rq.filter(CohortScheduleRequest.requested_by == current_user.id)
    return jsonify({
        'shifts': [{'id': s.id, 'user_id': s.user_id, 'title': s.title, 'days': s.days, 'start': s.start_time,
                    'end': s.end_time, 'status': s.status, 'skip_dates': s.skip_dates} for s in q.all()],
        'requests': [{'id': r.id, 'requested_by': r.requested_by, 'cohort_id': r.cohort_id, 'status': r.status,
                      'payload': r.payload} for r in rq.all()],
    })


def _ws_json(r):
    e = r['eval']
    return {'id': r['id'], 'user_id': r['user_id'], 'mode': r['mode'], 'title': r['title'], 'date': r['date_iso'],
            'clock_in': r['in_at'].isoformat(), 'clock_out': r['out_at'].isoformat() if r['out_at'] else None,
            'status': e['status'], 'label': e['label'], 'flagged': e['flagged'], 'paid_hours': r['paid_hours'],
            'app_hours': r['app_hours'], 'zoom_hours': r['zoom_hours']}


# ── API: clock ──────────────────────────────────────────────

@bp.route('/api/clock-in', methods=['POST'])
@limiter.limit('10 per minute')
def api_clock_in():
    try:
        ws, extra = service.clock_in(current_user, _json())
    except service.ClockError as e:
        return _err(str(e), e.status)
    return jsonify({'ok': True, 'session': _ws_json(service.session_row(ws)), **extra})


@bp.route('/api/clock-out', methods=['POST'])
def api_clock_out():
    try:
        ws = service.clock_out(current_user)
    except service.ClockError as e:
        return _err(str(e), e.status)
    return jsonify({'ok': True, 'session': _ws_json(service.session_row(ws))})


# ── API: office shifts ──────────────────────────────────────

def _shift_for_owner_or_admin(sid):
    q = StaffShift.query.filter(StaffShift.id == sid)
    if not is_admin():
        q = q.filter(StaffShift.user_id == current_user.id)
    return q.first()


@bp.route('/api/shifts', methods=['POST'])
def api_shift_create():
    data = _json()
    owner = current_user.id
    if is_admin() and data.get('user_id'):
        owner = int(data['user_id'])
        u = User.query.get(owner)
        if not u or u.role not in ('teacher', 'admin'):
            return _err('Choose a staff member.')
    try:
        p = normalize(data, 'office')
        check_conflicts(p, 'office', owner, zoom_max=current_app.config['ZOOM_MAX_CONCURRENT'])
    except ScheduleError as e:
        return _err(str(e))
    direct = is_admin()
    sh = StaffShift(user_id=owner, title=p['title'], days=p['days'], start_time=p['start'], end_time=p['end'],
                    start_date=parse_date(p['start_date']), end_date=parse_date(p['end_date']),
                    every_n_weeks=p['every_n_weeks'], skip_dates=[], requested_by=current_user.id,
                    status='active' if direct else 'pending',
                    approved_by=current_user.id if direct else None, approved_at=utcnow() if direct else None)
    db.session.add(sh)
    db.session.commit()
    if not direct:
        from staff.notify import notify_admins
        notify_admins('sched_request', f'shift{sh.id}',
                      f'{current_user.name} requested an office shift: {sh.title}.', '/staff/admin/schedule')
    return jsonify({'ok': True, 'id': sh.id, 'status': sh.status})


@bp.route('/api/shifts/<int:sid>/<action>', methods=['POST'])
def api_shift_action(sid, action):
    sh = _shift_for_owner_or_admin(sid)
    if not sh:
        return _err('Not found', 404)
    data = _json()
    from staff.notify import notify, notify_admins
    if action == 'withdraw':
        if sh.user_id != current_user.id and not is_admin():
            return _err('Not found', 404)
        if sh.status != 'pending':
            return _err('Only pending requests can be withdrawn.')
        sh.status = 'withdrawn'
        db.session.commit()
        return jsonify({'ok': True})
    if action == 'skip':
        if sh.status != 'active':
            return _err('Only active shifts can skip a date.')
        try:
            d = parse_date(data.get('date'))
        except ValueError:
            d = None
        if not d or d < sh.start_date or d > sh.end_date:
            return _err('Pick a date within the shift period.')
        if d.isoformat() not in (sh.skip_dates or []):
            sh.skip_dates = sorted((sh.skip_dates or []) + [d.isoformat()])
            db.session.commit()
            if not is_admin():
                notify_admins('skip', f'shift{sh.id}:{d}', f'{current_user.name} skipped {sh.title} on {d:%d %b %Y}.',
                              '/staff/admin/schedule')
        return jsonify({'ok': True, 'skip_dates': sh.skip_dates})
    if not is_admin():
        return _err('Admins only.', 403)
    if action == 'approve':
        if sh.status != 'pending':
            return _err('Only pending shifts can be approved.')
        p = {'title': sh.title, 'days': sh.days, 'start': sh.start_time, 'end': sh.end_time,
             'start_date': sh.start_date.isoformat(), 'end_date': sh.end_date.isoformat(),
             'every_n_weeks': sh.every_n_weeks}
        try:
            check_conflicts(p, 'office', sh.user_id, exclude_shift_id=sh.id,
                            zoom_max=current_app.config['ZOOM_MAX_CONCURRENT'])
        except ScheduleError as e:
            return _err(str(e))
        sh.status, sh.approved_by, sh.approved_at = 'active', current_user.id, utcnow()
        db.session.commit()
        notify(sh.user_id, 'sched_approved', f'shift{sh.id}', f'Your office shift "{sh.title}" was approved.', '/staff/schedule')
        return jsonify({'ok': True})
    if action in ('reject', 'remove'):
        if action == 'reject' and sh.status != 'pending':
            return _err('Only pending shifts can be rejected.')
        before = {'status': sh.status}
        sh.status, sh.note = 'rejected', (data.get('note') or '')[:500] or None
        service.audit(current_user.id, f'shift_{action}', 'staff_shift', sh.id, before, {'status': sh.status},
                      data.get('note'), commit=False)
        db.session.commit()
        notify(sh.user_id, 'sched_rejected', f'shift{sh.id}',
               f'Your office shift "{sh.title}" was {"rejected" if action == "reject" else "removed"}.', '/staff/schedule')
        return jsonify({'ok': True})
    return _err('Unknown action', 404)


# ── API: Zoom class schedules (cohorts) ─────────────────────

def _cohort_payload_rules(p):
    return json.dumps([{'day': DAY_NAMES[d], 'start': p['start'], 'end': p['end']} for d in p['days']])


def _apply_cohort_request(req, reviewer_id):
    """Write the approved request onto the cohort (creating it if new)."""
    p = req.payload
    cohort = Cohort.query.get(req.cohort_id) if req.cohort_id else None
    if cohort is None:
        cohort = Cohort(course_id=req.course_id, name=p['title'], teacher_id=req.requested_by)
        db.session.add(cohort)
    before = cohort.to_dict() if cohort.id else None
    cohort.name = p['title']
    cohort.schedule = _cohort_payload_rules(p)
    cohort.start_date = parse_date(p['start_date'])
    cohort.end_date = parse_date(p['end_date'])
    cohort.every_n_weeks = p['every_n_weeks']
    if p.get('zoom_meeting_id') and p['zoom_meeting_id'] != cohort.zoom_meeting_id:
        cohort.zoom_meeting_id = p['zoom_meeting_id']
        cohort.zoom_link = p.get('zoom_link') or f"https://zoom.us/j/{p['zoom_meeting_id']}"
    elif p.get('zoom_link'):
        cohort.zoom_link = p['zoom_link']
    db.session.flush()
    req.cohort_id = cohort.id
    req.status, req.reviewed_by, req.reviewed_at = 'approved', reviewer_id, utcnow()
    service.audit(reviewer_id, 'cohort_schedule_approve', 'cohort', cohort.id,
                  {k: before[k] for k in ('schedule', 'start_date', 'end_date')} if before else None,
                  {'schedule': json.loads(cohort.schedule), 'start_date': p['start_date'], 'end_date': p['end_date'],
                   'every_n_weeks': p['every_n_weeks'], 'zoom_meeting_id': cohort.zoom_meeting_id},
                  f'request #{req.id}', commit=False)
    db.session.commit()
    return cohort


@bp.route('/api/cohort-requests', methods=['POST'])
def api_cohort_request_create():
    data = _json()
    teacher_id = current_user.id
    if is_admin() and data.get('user_id'):
        teacher_id = int(data['user_id'])
        u = User.query.get(teacher_id)
        if not u or u.role not in ('teacher', 'admin'):
            return _err('Choose a teacher.')
    cohort = None
    if data.get('cohort_id'):
        cohort = Cohort.query.get(int(data['cohort_id']))
        if not cohort or (not is_admin() and cohort.teacher_id != current_user.id):
            return _err('You can only change your own classes.', 403)
        course_id = cohort.course_id
        if is_admin() and not data.get('user_id'):
            teacher_id = cohort.teacher_id or teacher_id
    else:
        try:
            course_id = int(data.get('course_id'))
        except (TypeError, ValueError):
            return _err('Choose a course.')
        if not Course.query.get(course_id):
            return _err('Choose a course.')
    try:
        p = normalize(data, 'zoom')
        check_conflicts(p, 'zoom', teacher_id, exclude_cohort_id=cohort.id if cohort else None,
                        zoom_max=current_app.config['ZOOM_MAX_CONCURRENT'])
    except ScheduleError as e:
        return _err(str(e))
    req = CohortScheduleRequest(requested_by=teacher_id, cohort_id=cohort.id if cohort else None,
                                course_id=course_id, payload=p, status='pending')
    db.session.add(req)
    db.session.commit()
    if is_admin():
        c = _apply_cohort_request(req, current_user.id)
        return jsonify({'ok': True, 'id': req.id, 'status': 'approved', 'cohort_id': c.id})
    from staff.notify import notify_admins
    notify_admins('sched_request', f'cohortreq{req.id}',
                  f'{current_user.name} requested a Zoom class schedule: {p["title"]}.', '/staff/admin/schedule')
    return jsonify({'ok': True, 'id': req.id, 'status': 'pending'})


@bp.route('/api/cohort-requests/<int:rid>/<action>', methods=['POST'])
def api_cohort_request_action(rid, action):
    q = CohortScheduleRequest.query.filter(CohortScheduleRequest.id == rid)
    if not is_admin():
        q = q.filter(CohortScheduleRequest.requested_by == current_user.id)
    req = q.first()
    if not req:
        return _err('Not found', 404)
    from staff.notify import notify
    if action == 'withdraw':
        if req.status != 'pending':
            return _err('Only pending requests can be withdrawn.')
        req.status = 'withdrawn'
        db.session.commit()
        return jsonify({'ok': True})
    if not is_admin():
        return _err('Admins only.', 403)
    if req.status != 'pending':
        return _err('This request is no longer pending.')
    if action == 'approve':
        p = req.payload
        try:
            check_conflicts(p, 'zoom', req.requested_by, exclude_cohort_id=req.cohort_id,
                            exclude_request_id=req.id, zoom_max=current_app.config['ZOOM_MAX_CONCURRENT'])
        except ScheduleError as e:
            return _err(str(e))
        c = _apply_cohort_request(req, current_user.id)
        notify(req.requested_by, 'sched_approved', f'cohortreq{req.id}',
               f'Your class schedule "{p["title"]}" was approved.', '/staff/classes')
        return jsonify({'ok': True, 'cohort_id': c.id})
    if action == 'reject':
        req.status, req.reviewed_by, req.reviewed_at = 'rejected', current_user.id, utcnow()
        req.note = (_json().get('note') or '')[:500] or None
        db.session.commit()
        notify(req.requested_by, 'sched_rejected', f'cohortreq{req.id}',
               f'Your class schedule "{req.payload.get("title")}" was rejected.', '/staff/schedule')
        return jsonify({'ok': True})
    if action == 'create-zoom':
        if not (deps.zoom_configured and deps.zoom_configured()):
            return _err('Zoom is not configured on the server.', 503)
        p = dict(req.payload)
        if p.get('zoom_meeting_id'):
            return _err('This request already has a meeting ID.')
        sd, ed = parse_date(p['start_date']), parse_date(p['end_date'])
        first = next((sd + timedelta(days=i) for i in range(7) if (sd + timedelta(days=i)).weekday() in p['days']), sd)
        weeks = max(1, ((ed - sd).days // 7) + 1)
        from datetime import datetime as _dt
        zoom_days = sorted({(d + 1) % 7 + 1 for d in p['days']})   # Zoom: 1=Sun … 7=Sat
        try:
            meeting = deps.create_recurring_zoom_meeting(
                p['title'], _dt.combine(first, service_time(p['start'])), zoom_days, p['start'], p['end'],
                weeks * len(p['days']))
        except Exception as e:
            return _err(f'Zoom said: {e}', 502)
        if not meeting or not meeting.get('id'):
            return _err('Zoom did not return a meeting.', 502)
        p['zoom_meeting_id'] = str(meeting['id'])
        p['zoom_link'] = meeting.get('join_url')
        req.payload = p
        db.session.commit()
        return jsonify({'ok': True, 'zoom_meeting_id': p['zoom_meeting_id'], 'zoom_link': p['zoom_link']})
    return _err('Unknown action', 404)


def service_time(hhmm):
    from staff.timeutil import parse_hhmm
    return parse_hhmm(hhmm)


@bp.route('/api/cohorts/<int:cid>/skip', methods=['POST'])
def api_cohort_skip(cid):
    q = Cohort.query.filter(Cohort.id == cid)
    if not is_admin():
        q = q.filter(Cohort.teacher_id == current_user.id)
    cohort = q.first()
    if not cohort:
        return _err('Not found', 404)
    data = _json()
    try:
        d = parse_date(data.get('date'))
    except ValueError:
        d = None
    if not d:
        return _err('Pick a date to skip.')
    if (cohort.start_date and d < cohort.start_date) or (cohort.end_date and d > cohort.end_date):
        return _err('That date is outside the class period.')
    if not CohortSkipDate.query.filter_by(cohort_id=cid, date=d).first():
        db.session.add(CohortSkipDate(cohort_id=cid, date=d, reason=(data.get('reason') or '')[:300] or None,
                                      created_by=current_user.id))
        db.session.commit()
        if not is_admin():
            from staff.notify import notify_admins
            notify_admins('skip', f'cohort{cid}:{d}', f'{current_user.name} skipped {cohort.name} on {d:%d %b %Y}.',
                          '/staff/admin/schedule')
    return jsonify({'ok': True})


# ── API: admin ──────────────────────────────────────────────

@bp.route('/api/admin/reports/upload', methods=['POST'])
@admin_only
@limiter.limit('20 per minute')
def api_reports_upload():
    files = request.files.getlist('files')
    if not files:
        return _err('Choose one or more CSV files.')
    ok, bad = [], []
    for f in files[:40]:
        try:
            raw = f.read(5 * 1024 * 1024)
            text = raw.decode('utf-8-sig', errors='replace')
            rep = zoom_reports.parse_zoom_csv(text)
            zoom_reports.upsert_report(rep['meeting_id'], rep['local_date'], rep['participants'], 'csv')
            ok.append({'file': f.filename, 'meeting_id': rep['meeting_id'], 'date': rep['local_date'].isoformat(),
                       'participants': len(rep['participants'])})
        except Exception as e:
            db.session.rollback()
            bad.append({'file': f.filename, 'error': str(e)})
    return jsonify({'ok': ok, 'failed': bad})


@bp.route('/api/admin/reports/pull', methods=['POST'])
@admin_only
def api_reports_pull():
    if not (deps.zoom_configured and deps.zoom_configured()):
        return _err('Zoom is not configured on the server.', 503)
    processed = zoom_reports.process_due_jobs(deps)
    res = zoom_reports.backfill(deps)
    res['queue_processed'] = processed
    return jsonify(res)


def _parse_local_dt(value):
    from datetime import datetime as _dt
    if not value:
        return None
    return _dt.strptime(value[:16], '%Y-%m-%dT%H:%M').replace(tzinfo=MYT).astimezone(UTC)


@bp.route('/api/admin/sessions/<int:sid>/review', methods=['POST'])
@admin_only
def api_session_review(sid):
    ws = WorkSession.query.get(sid)
    if not ws:
        return _err('Not found', 404)
    data = _json()
    action = data.get('action')
    reason = (data.get('reason') or '').strip()
    if not reason:
        return _err('A reason is required.')
    before = ws.snapshot()
    if action == 'approve':
        ws.review_status, ws.override_paid_minutes = 'approved', None
    elif action == 'override':
        try:
            hours = float(data.get('paid_hours'))
        except (TypeError, ValueError):
            return _err('Enter the paid hours.')
        if hours < 0 or hours > 24:
            return _err('Paid hours must be between 0 and 24.')
        ws.review_status, ws.override_paid_minutes = 'overridden', round(hours * 60, 2)
    elif action == 'adjust':
        try:
            cin = _parse_local_dt(data.get('clock_in')) or as_utc(ws.clock_in_at)
            cout = _parse_local_dt(data.get('clock_out'))
        except ValueError:
            return _err('Enter times as YYYY-MM-DDTHH:MM.')
        if cout is None:
            return _err('Enter the clock-out time.')
        if cout <= cin:
            return _err('Clock-out must be after clock-in.')
        ws.clock_in_at, ws.clock_out_at, ws.source = cin, cout, 'admin_adjusted'
        if data.get('task') is not None:
            ws.task = (data.get('task') or '').strip()[:500] or ws.task
    else:
        return _err('Unknown action.')
    ws.reviewed_by, ws.reviewed_at = current_user.id, utcnow()
    service.audit(current_user.id, f'session_{action}', 'work_session', ws.id, before, ws.snapshot(), reason, commit=False)
    db.session.commit()
    return jsonify({'ok': True, 'session': _ws_json(service.session_row(ws))})


@bp.route('/api/admin/team/<int:uid>', methods=['POST'])
@admin_only
def api_team_save(uid):
    u = User.query.get(uid)
    if not u or u.role not in ('teacher', 'admin'):
        return _err('Only teacher or admin accounts can have a staff profile.')
    data = _json()
    try:
        rate = round(float(data.get('hourly_rate')), 2)
        cap = round(float(data.get('monthly_cap_hours')), 2)
    except (TypeError, ValueError):
        return _err('Enter the rate and cap as numbers.')
    if rate < 0 or cap < 0 or rate > 10000 or cap > 744:
        return _err('Rate or cap is out of range.')
    etype = data.get('employment_type')
    if etype not in ('part_time', 'full_time'):
        return _err('Choose part-time or full-time.')
    prof = service.profile_for(uid)
    before = prof.to_dict() if prof else None
    if not prof:
        prof = StaffProfile(user_id=uid)
        db.session.add(prof)
    prof.employment_type, prof.hourly_rate, prof.monthly_cap_hours = etype, rate, cap
    prof.active = bool(data.get('active', True))
    db.session.flush()
    service.audit(current_user.id, 'staff_profile_save', 'staff_profile', uid, before, prof.to_dict(), None, commit=False)
    db.session.commit()
    return jsonify({'ok': True, 'profile': prof.to_dict()})


# ── API: Web Push ───────────────────────────────────────────

@bp.route('/api/push/subscribe', methods=['POST'])
def api_push_subscribe():
    data = _json()
    sub = data.get('subscription') or data
    endpoint = sub.get('endpoint')
    keys = sub.get('keys') or {}
    if not endpoint or not keys.get('p256dh') or not keys.get('auth') or not endpoint.startswith('https://'):
        return _err('Invalid subscription.')
    row = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if row is None:
        row = PushSubscription(endpoint=endpoint)
        db.session.add(row)
    row.user_id, row.p256dh, row.auth = current_user.id, keys['p256dh'][:200], keys['auth'][:100]
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/api/push/unsubscribe', methods=['POST'])
def api_push_unsubscribe():
    endpoint = _json().get('endpoint')
    PushSubscription.query.filter_by(endpoint=endpoint, user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'ok': True})
