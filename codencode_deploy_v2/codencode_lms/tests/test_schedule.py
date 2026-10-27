"""Schedule requests: field validation, teacher clashes across cohorts and
shifts, the Zoom concurrency limit, approval writing the cohort, payroll."""
import json
from datetime import date

import pytest

from models import db, Cohort
from staff.models import StaffShift, CohortScheduleRequest, StaffProfile
from staff.timeutil import myt_to_utc
from staff.validation import ScheduleError, normalize
from tests.conftest import make_user, make_cohort, make_course, make_session, login

BASE = {'title': 'PY-102', 'days': [1], 'start': '20:00', 'end': '22:00',
        'start_date': '2026-11-01', 'end_date': '2027-01-31', 'every_n_weeks': 1}


@pytest.mark.parametrize('change,msg', [
    ({'end': '19:00'}, 'End time must be after'),
    ({'end_date': '2026-10-01'}, 'Until'),
    ({'days': []}, 'at least one day'),
    ({'zoom_meeting_id': '12345'}, '9–11 digits'),
    ({'every_n_weeks': 3}, 'every 1 or 2 weeks'),
    ({'title': ' '}, 'title'),
])
def test_field_validation(change, msg):
    with pytest.raises(ScheduleError, match=msg):
        normalize({**BASE, **change}, 'zoom')


def test_meeting_id_spaces_are_stripped():
    assert normalize({**BASE, 'zoom_meeting_id': '845 1234 5678'}, 'zoom')['zoom_meeting_id'] == '84512345678'


def test_teacher_clash_with_own_cohort_names_the_class(client):
    t = make_user('teacher', 'Darren')
    make_cohort(t, [('Tuesday', '19:30', '22:30')], date(2026, 9, 1), date(2026, 12, 31), name='T-PY101')
    login(client, t)
    r = client.post('/staff/api/cohort-requests', json={**BASE, 'course_id': make_course().id})
    assert r.status_code == 400
    assert 'Darren already has' in r.get_json()['error'] and 'T-PY101' in r.get_json()['error']


def test_teacher_clash_between_shift_and_class(client):
    t = make_user('teacher')
    make_cohort(t, [('Tuesday', '19:30', '22:30')], date(2026, 9, 1), date(2026, 12, 31))
    login(client, t)
    r = client.post('/staff/api/shifts', json={**BASE, 'title': 'Admin', 'start': '21:00', 'end': '23:00'})
    assert r.status_code == 400 and 'already has' in r.get_json()['error']
    # Same time on another day is fine.
    r = client.post('/staff/api/shifts', json={**BASE, 'title': 'Admin', 'days': [2]})
    assert r.status_code == 200 and r.get_json()['status'] == 'pending'


def test_no_clash_when_date_ranges_do_not_overlap(client):
    t = make_user('teacher')
    make_cohort(t, [('Tuesday', '19:30', '22:30')], date(2026, 9, 1), date(2026, 10, 31))
    login(client, t)
    r = client.post('/staff/api/cohort-requests', json={**BASE, 'course_id': make_course().id})
    assert r.status_code == 200


def test_zoom_concurrency_limit_of_two(client):
    t1, t2, t3 = make_user('teacher'), make_user('teacher'), make_user('teacher')
    make_cohort(t1, [('Tuesday', '19:30', '22:30')], date(2026, 9, 1), date(2026, 12, 31), name='T-A')
    login(client, t2)
    assert client.post('/staff/api/cohort-requests', json={**BASE, 'course_id': make_course().id}).status_code == 200
    login(client, t3)
    r = client.post('/staff/api/cohort-requests', json={**BASE, 'title': 'ML', 'course_id': make_course().id})
    assert r.status_code == 400
    err = r.get_json()['error']
    assert 'Zoom limit' in err and 'T-A' in err and 'PY-102' in err
    # Office shifts do not count towards the Zoom limit.
    assert client.post('/staff/api/shifts', json={**BASE, 'title': 'Office'}).status_code == 200


def test_zoom_concurrency_limit_is_configurable(app, client):
    t1, t2 = make_user('teacher'), make_user('teacher')
    make_cohort(t1, [('Tuesday', '19:30', '22:30')], date(2026, 9, 1), date(2026, 12, 31))
    app.config['ZOOM_MAX_CONCURRENT'] = 1
    try:
        login(client, t2)
        r = client.post('/staff/api/cohort-requests', json={**BASE, 'course_id': make_course().id})
        assert r.status_code == 400 and 'Zoom limit' in r.get_json()['error']
    finally:
        app.config['ZOOM_MAX_CONCURRENT'] = 2


def test_approval_writes_cohort_schedule(client):
    t, admin = make_user('teacher'), make_user('admin')
    login(client, t)
    r = client.post('/staff/api/cohort-requests', json={**BASE, 'days': [1, 3], 'every_n_weeks': 2,
                                                         'title': 'T-PY102', 'zoom_meeting_id': '87766554433',
                                                         'course_id': make_course().id})
    rid = r.get_json()['id']
    assert client.post(f'/staff/api/cohort-requests/{rid}/approve').status_code == 403
    login(client, admin)
    r = client.post(f'/staff/api/cohort-requests/{rid}/approve')
    assert r.status_code == 200
    c = Cohort.query.get(r.get_json()['cohort_id'])
    assert c.teacher_id == t.id and c.every_n_weeks == 2 and c.zoom_meeting_id == '87766554433'
    assert json.loads(c.schedule) == [{'day': 'Tuesday', 'start': '20:00', 'end': '22:00'},
                                      {'day': 'Thursday', 'start': '20:00', 'end': '22:00'}]
    assert c.start_date == date(2026, 11, 1) and c.end_date == date(2027, 1, 31)
    assert CohortScheduleRequest.query.get(rid).status == 'approved'


def test_teacher_can_withdraw_pending_and_skip_own_dates(client):
    t = make_user('teacher')
    login(client, t)
    sid = client.post('/staff/api/shifts', json={**BASE, 'title': 'Admin'}).get_json()['id']
    assert client.post(f'/staff/api/shifts/{sid}/approve').status_code == 403
    assert client.post(f'/staff/api/shifts/{sid}/withdraw').status_code == 200
    assert StaffShift.query.get(sid).status == 'withdrawn'
    c = make_cohort(t, [('Tuesday', '19:30', '22:30')], date(2026, 9, 1), date(2026, 12, 31))
    assert client.post(f'/staff/api/cohorts/{c.id}/skip', json={'date': '2026-11-03'}).status_code == 200
    assert client.post(f'/staff/api/cohorts/{c.id}/skip', json={'date': '2027-03-03'}).status_code == 400


def test_payroll_month_summary_and_cap_warning(client):
    from models import Notification
    t, admin = make_user('teacher'), make_user('admin')
    db.session.add(StaffProfile(user_id=t.id, hourly_rate=40, monthly_cap_hours=10))
    db.session.commit()
    d = date(2026, 10, 7)
    make_session(t, myt_to_utc(d, '09:00'), myt_to_utc(d, '18:00'))             # 9 h office, verified
    make_session(t, myt_to_utc(date(2026, 10, 8), '09:00'), myt_to_utc(date(2026, 10, 8), '12:00'),
                 distance_m=900)                                                   # outside: paid 0, flagged
    make_session(t, myt_to_utc(date(2026, 11, 1), '00:10'), myt_to_utc(date(2026, 11, 1), '02:10'))  # November (MYT)
    login(client, t)
    pay = client.get('/staff/api/pay?month=2026-10').get_json()
    assert pay['paid_hours'] == 9 and pay['pay'] == 360 and pay['flagged'] == 1 and pay['sessions'] == 2
    from staff import service
    service.check_cap(t.id, now=myt_to_utc(d, '18:05'))
    assert Notification.query.filter_by(user_id=t.id).count() == 1
    assert Notification.query.filter_by(user_id=admin.id).count() == 1
    login(client, admin)
    csv = client.get('/staff/admin/payroll?format=csv&month=2026-10').get_data(as_text=True).splitlines()
    assert csv[0] == 'date,staff,email,type,class_or_task,app_in,app_out,app_hours,zoom_hours,paid_hours,status,rate,pay'
    assert any(line.startswith('2026-10-07') and line.endswith(',9.00,Verified · 10 m,40.00,360.00') for line in csv)
