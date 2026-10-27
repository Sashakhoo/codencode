"""Role isolation: students get 403 everywhere; teacher A cannot read or
change teacher B's sessions, pay, schedules or shifts through any route or
API, including by changing ids in URLs or JSON; admin can."""
from datetime import date, timedelta

import pytest

from models import db
from staff.models import StaffShift, StaffProfile, CohortScheduleRequest, WorkSession, CohortSkipDate
from staff.timeutil import utcnow, today_myt
from tests.conftest import make_user, make_cohort, make_session, login

PAGES = ['/staff/', '/staff/classes', '/staff/schedule', '/staff/clock', '/staff/pay', '/staff/pay?format=csv']
ADMIN_PAGES = ['/staff/admin/schedule', '/staff/admin/reports', '/staff/admin/payroll',
               '/staff/admin/payroll?format=csv', '/staff/admin/review', '/staff/admin/team']
APIS_GET = ['/staff/api/status', '/staff/api/sessions', '/staff/api/pay', '/staff/api/schedules']
APIS_POST = ['/staff/api/clock-in', '/staff/api/clock-out', '/staff/api/shifts', '/staff/api/cohort-requests',
             '/staff/api/push/subscribe', '/staff/api/admin/reports/pull', '/staff/api/admin/team/1']


@pytest.fixture
def world():
    a, b, admin = make_user('teacher', 'Alice'), make_user('teacher', 'Bob'), make_user('admin', 'Nat')
    for u in (a, b):
        db.session.add(StaffProfile(user_id=u.id, hourly_rate=40, monthly_cap_hours=60))
    db.session.commit()
    now = utcnow()
    wa = make_session(a, now - timedelta(hours=3), now - timedelta(hours=1))
    wb = make_session(b, now - timedelta(hours=5), now - timedelta(hours=2))
    sb = StaffShift(user_id=b.id, title='Bob shift', days=[0], start_time='09:00', end_time='12:00',
                    start_date=today_myt(), end_date=today_myt() + timedelta(days=30), status='pending')
    cb = make_cohort(b, [('Monday', '20:00', '22:00')], meeting='81111111111')
    rb = CohortScheduleRequest(requested_by=b.id, course_id=cb.course_id,
                               payload={'title': 'Bob class', 'days': [3], 'start': '20:00', 'end': '22:00',
                                        'start_date': '2026-11-01', 'end_date': '2026-12-01', 'every_n_weeks': 1})
    db.session.add_all([sb, rb])
    db.session.commit()
    return {'a': a, 'b': b, 'admin': admin, 'wa': wa, 'wb': wb, 'sb': sb, 'cb': cb, 'rb': rb}


def test_anonymous_is_sent_to_login(client):
    r = client.get('/staff/')
    assert r.status_code == 302 and '/staff/login' in r.headers['Location']
    assert client.get('/staff/api/sessions').status_code == 401


@pytest.mark.parametrize('path', PAGES + ADMIN_PAGES + APIS_GET)
def test_student_gets_403_on_every_get(client, path):
    login(client, make_user('student'))
    assert client.get(path).status_code == 403


@pytest.mark.parametrize('path', APIS_POST)
def test_student_gets_403_on_every_post(client, path):
    login(client, make_user('student'))
    assert client.post(path, json={}).status_code == 403


def test_student_lms_ui_has_no_staff_link(client):
    login(client, make_user('student'))
    html = client.get('/lms').get_data(as_text=True)
    assert '/staff' not in html


@pytest.mark.parametrize('path', ADMIN_PAGES)
def test_teacher_cannot_open_admin_pages(client, world, path):
    login(client, world['a'])
    assert client.get(path).status_code == 403


def test_teacher_sees_only_own_sessions(client, world):
    login(client, world['a'])
    data = client.get('/staff/api/sessions').get_json()
    assert {s['id'] for s in data['sessions']} == {world['wa'].id}
    page = client.get('/staff/').get_data(as_text=True)
    assert 'Alice' in page and 'Bob' not in page


@pytest.mark.parametrize('path', ['/staff/?user={b}', '/staff/api/sessions?user={b}', '/staff/api/pay?user={b}'])
def test_teacher_cannot_read_other_teacher_by_changing_user_param(client, world, path):
    login(client, world['a'])
    assert client.get(path.format(b=world['b'].id)).status_code == 403


def test_teacher_cannot_read_other_session_by_id(client, world):
    login(client, world['a'])
    assert client.get(f"/staff/api/sessions/{world['wb'].id}").status_code == 404
    assert client.get(f"/staff/api/sessions/{world['wa'].id}").status_code == 200


def test_teacher_pay_is_own_only(client, world):
    login(client, world['a'])
    csv = client.get('/staff/pay?format=csv').get_data(as_text=True)
    assert world['a'].email in csv and world['b'].email not in csv
    assert client.get(f"/staff/admin/payroll?format=csv&only={world['b'].id}").status_code == 403


def test_teacher_schedules_list_is_own_only(client, world):
    login(client, world['a'])
    data = client.get('/staff/api/schedules').get_json()
    assert data['shifts'] == [] and data['requests'] == []
    html = client.get('/staff/schedule').get_data(as_text=True)
    assert 'Bob shift' not in html and 'Bob class' not in html


def test_teacher_cannot_act_on_other_teachers_shift_or_request(client, world):
    login(client, world['a'])
    sid, rid, cid = world['sb'].id, world['rb'].id, world['cb'].id
    for action in ('withdraw', 'approve', 'reject', 'skip', 'remove'):
        assert client.post(f'/staff/api/shifts/{sid}/{action}', json={'date': '2026-11-02'}).status_code == 404
    for action in ('withdraw', 'approve', 'reject', 'create-zoom'):
        assert client.post(f'/staff/api/cohort-requests/{rid}/{action}', json={}).status_code == 404
    assert client.post(f'/staff/api/cohorts/{cid}/skip', json={'date': '2026-11-02'}).status_code == 404
    assert StaffShift.query.get(sid).status == 'pending'
    assert CohortScheduleRequest.query.get(rid).status == 'pending'
    assert CohortSkipDate.query.count() == 0


def test_teacher_cannot_create_schedule_for_someone_else_via_json(client, world):
    login(client, world['a'])
    body = {'title': 'Sneaky', 'days': [4], 'start': '09:00', 'end': '10:00', 'start_date': '2026-11-01',
            'end_date': '2026-11-30', 'user_id': world['b'].id}
    r = client.post('/staff/api/shifts', json=body)
    assert r.status_code == 200
    assert StaffShift.query.get(r.get_json()['id']).user_id == world['a'].id       # user_id ignored
    r = client.post('/staff/api/cohort-requests', json={**body, 'cohort_id': world['cb'].id})
    assert r.status_code == 403                                                     # not their cohort


def test_teacher_cannot_start_another_teachers_class(client, world):
    login(client, world['a'])
    r = client.post('/staff/api/clock-in', json={'mode': 'zoom', 'cohort_id': world['cb'].id})
    assert r.status_code == 403


def test_teacher_cannot_review_or_edit_sessions(client, world):
    login(client, world['a'])
    for sid in (world['wa'].id, world['wb'].id):
        r = client.post(f'/staff/api/admin/sessions/{sid}/review',
                        json={'action': 'adjust', 'reason': 'x', 'clock_out': '2030-01-01T10:00'})
        assert r.status_code == 403
    assert client.delete(f"/staff/api/sessions/{world['wa'].id}").status_code == 405


def test_admin_sees_everyone(client, world):
    login(client, world['admin'])
    for who in ('a', 'b'):
        data = client.get(f"/staff/api/sessions?user={world[who].id}").get_json()
        assert {s['id'] for s in data['sessions']} == {world['w' + who].id}
    assert client.get(f"/staff/?user={world['b'].id}").status_code == 200
    csv = client.get('/staff/admin/payroll?format=csv').get_data(as_text=True)
    assert world['a'].email in csv and world['b'].email in csv
    assert client.get(f"/staff/api/sessions/{world['wb'].id}").status_code == 200
    data = client.get('/staff/api/schedules').get_json()
    assert len(data['shifts']) == 1 and len(data['requests']) == 1


def test_admin_can_approve_and_audit_is_written(client, world):
    from staff.models import AuditLog
    login(client, world['admin'])
    r = client.post(f"/staff/api/admin/sessions/{world['wb'].id}/review", json={'action': 'override', 'paid_hours': 2})
    assert r.status_code == 400                       # reason required
    r = client.post(f"/staff/api/admin/sessions/{world['wb'].id}/review",
                    json={'action': 'override', 'paid_hours': 2, 'reason': 'Checked with Bob'})
    assert r.status_code == 200 and r.get_json()['session']['paid_hours'] == 2
    log = AuditLog.query.filter_by(entity='work_session', entity_id=world['wb'].id).one()
    assert log.actor_id == world['admin'].id and log.reason == 'Checked with Bob'
    assert log.before['override_paid_minutes'] is None and log.after['override_paid_minutes'] == 120


def test_admin_adjust_writes_before_and_after(client, world):
    from staff.models import AuditLog
    login(client, world['admin'])
    r = client.post(f"/staff/api/admin/sessions/{world['wa'].id}/review",
                    json={'action': 'adjust', 'reason': 'Forgot to clock out', 'clock_in': '2026-10-20T14:00',
                          'clock_out': '2026-10-20T17:00'})
    assert r.status_code == 200
    ws = WorkSession.query.get(world['wa'].id)
    assert ws.source == 'admin_adjusted'
    log = AuditLog.query.filter_by(action='session_adjust').one()
    assert log.after['clock_in_at'] == '2026-10-20T06:00:00+00:00' and log.before['clock_in_at'] != log.after['clock_in_at']


def test_csrf_is_enforced_on_staff_posts(app, client, world):
    login(client, world['a'])
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        r = client.post('/staff/api/clock-out', json={})
        assert r.status_code == 400 and b'CSRF' in r.data
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_staff_host_root_redirects_to_staff(client):
    r = client.get('/', headers={'Host': 'staff.codencode.my'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/staff')
    r = client.get('/', headers={'Host': 'learn.codencode.my'})
    assert r.status_code == 200
