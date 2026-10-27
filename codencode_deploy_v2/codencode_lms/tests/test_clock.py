"""Clock-in/out: geofence (inside, outside, forged distance), GPS accuracy,
the Zoom start window, one open session per user, auto-close."""
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from models import db
from staff import service
from staff.models import WorkSession, AuditLog
from staff.timeutil import myt_to_utc, utcnow
from tests.conftest import OFFICE, make_user, make_cohort, make_session, login

INSIDE = (1.5618, 103.7792)      # ~40 m from the office
OUTSIDE = (1.5440, 103.7650)     # ~2.5 km away


def test_office_clock_in_inside_geofence(client):
    t = make_user('teacher')
    login(client, t)
    r = client.post('/staff/api/clock-in', json={'mode': 'office', 'lat': INSIDE[0], 'lng': INSIDE[1],
                                                 'accuracy': 12, 'task': 'Content editing'})
    assert r.status_code == 200, r.get_json()
    ws = WorkSession.query.one()
    assert ws.user_id == t.id and ws.task == 'Content editing' and 20 < ws.distance_m < 60


def test_office_clock_in_outside_geofence_rejected(client):
    login(client, make_user('teacher'))
    r = client.post('/staff/api/clock-in', json={'mode': 'office', 'lat': OUTSIDE[0], 'lng': OUTSIDE[1]})
    assert r.status_code == 400 and 'm from the office' in r.get_json()['error']
    assert WorkSession.query.count() == 0


def test_forged_distance_from_browser_is_ignored(client):
    login(client, make_user('teacher'))
    r = client.post('/staff/api/clock-in', json={'mode': 'office', 'lat': OUTSIDE[0], 'lng': OUTSIDE[1],
                                                 'distance_m': 5, 'distance': 5})
    assert r.status_code == 400
    r = client.post('/staff/api/clock-in', json={'mode': 'office', 'lat': INSIDE[0], 'lng': INSIDE[1],
                                                 'distance_m': 9999})
    assert r.status_code == 200
    assert WorkSession.query.one().distance_m < 100


def test_poor_gps_accuracy_rejected(client):
    login(client, make_user('teacher'))
    r = client.post('/staff/api/clock-in', json={'mode': 'office', 'lat': OFFICE[0], 'lng': OFFICE[1], 'accuracy': 350})
    assert r.status_code == 400 and 'accuracy' in r.get_json()['error']


def test_missing_location_rejected(client):
    login(client, make_user('teacher'))
    assert client.post('/staff/api/clock-in', json={'mode': 'office'}).status_code == 400


def test_one_open_session_per_user_api(client):
    login(client, make_user('teacher'))
    body = {'mode': 'office', 'lat': INSIDE[0], 'lng': INSIDE[1]}
    assert client.post('/staff/api/clock-in', json=body).status_code == 200
    assert client.post('/staff/api/clock-in', json=body).status_code == 409
    assert client.post('/staff/api/clock-out').status_code == 200
    assert client.post('/staff/api/clock-out').status_code == 409
    assert client.post('/staff/api/clock-in', json=body).status_code == 200
    assert WorkSession.query.count() == 2


def test_one_open_session_per_user_database_index():
    t = make_user('teacher')
    now = utcnow()
    db.session.add(WorkSession(user_id=t.id, mode='office', clock_in_at=now))
    db.session.commit()
    db.session.add(WorkSession(user_id=t.id, mode='office', clock_in_at=now + timedelta(minutes=1)))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    # Closed sessions do not count.
    other = make_user('teacher')
    make_session(other, now - timedelta(hours=2), now - timedelta(hours=1))
    db.session.add(WorkSession(user_id=other.id, mode='office', clock_in_at=now))
    db.session.commit()


def _tuesday_class(t):
    return make_cohort(t, [('Tuesday', '19:30', '22:30')], date(2026, 10, 1), date(2026, 12, 31))


def test_zoom_start_window(client):
    t = make_user('teacher')
    c = _tuesday_class(t)
    d = date(2026, 10, 20)   # a Tuesday
    with pytest.raises(service.ClockError):
        service.clock_in(t, {'mode': 'zoom', 'cohort_id': c.id}, now=myt_to_utc(d, '19:10'))   # 20 min early
    with pytest.raises(service.ClockError):
        service.clock_in(t, {'mode': 'zoom', 'cohort_id': c.id}, now=myt_to_utc(d, '22:31'))   # after the end
    with pytest.raises(service.ClockError):
        service.clock_in(t, {'mode': 'zoom', 'cohort_id': c.id}, now=myt_to_utc(date(2026, 10, 21), '19:30'))
    ws, extra = service.clock_in(t, {'mode': 'zoom', 'cohort_id': c.id}, now=myt_to_utc(d, '19:16'))
    assert extra['zoom_link'] == 'https://zoom.us/j/84455667788'
    assert ws.zoom_meeting_id == '84455667788'
    assert service.as_utc(ws.scheduled_end_at) == myt_to_utc(d, '22:30')


def test_zoom_start_respects_skip_dates():
    from staff.models import CohortSkipDate
    t = make_user('teacher')
    c = _tuesday_class(t)
    db.session.add(CohortSkipDate(cohort_id=c.id, date=date(2026, 10, 20)))
    db.session.commit()
    with pytest.raises(service.ClockError):
        service.clock_in(t, {'mode': 'zoom', 'cohort_id': c.id}, now=myt_to_utc(date(2026, 10, 20), '19:45'))


def test_teacher_cannot_edit_or_delete_own_clock_record(client):
    t = make_user('teacher')
    login(client, t)
    client.post('/staff/api/clock-in', json={'mode': 'office', 'lat': INSIDE[0], 'lng': INSIDE[1]})
    ws = WorkSession.query.one()
    assert client.put(f'/staff/api/sessions/{ws.id}', json={'clock_in': '2020-01-01'}).status_code == 405
    assert client.delete(f'/staff/api/sessions/{ws.id}').status_code == 405
    assert client.post(f'/staff/api/admin/sessions/{ws.id}/review',
                       json={'action': 'adjust', 'reason': 'x', 'clock_out': '2030-01-01T00:00'}).status_code == 403


def test_auto_close_after_12_hours_at_scheduled_end_with_audit():
    t = make_user('teacher')
    d = date(2026, 10, 20)
    ws = WorkSession(user_id=t.id, mode='office', clock_in_at=myt_to_utc(d, '14:00'), distance_m=10,
                     scheduled_start_at=myt_to_utc(d, '14:00'), scheduled_end_at=myt_to_utc(d, '18:00'))
    db.session.add(ws)
    db.session.commit()
    service.run_reminders(now=myt_to_utc(d, '18:40'))      # forgot-to-clock-out reminder only
    assert WorkSession.query.get(ws.id).clock_out_at is None
    from models import Notification
    assert Notification.query.filter_by(user_id=t.id).count() == 1
    service.run_reminders(now=myt_to_utc(d, '18:45'))      # deduplicated
    assert Notification.query.filter_by(user_id=t.id).count() == 1
    service.run_reminders(now=myt_to_utc(date(2026, 10, 21), '02:05'))
    ws = WorkSession.query.get(ws.id)
    assert ws.auto_closed and service.as_utc(ws.clock_out_at) == myt_to_utc(d, '18:00')
    assert AuditLog.query.filter_by(action='auto_close', entity_id=ws.id).count() == 1
    assert service.evaluate_ws(ws)['flagged']


def test_start_reminder_and_no_show_are_sent_once():
    from models import Notification
    t = make_user('teacher')
    admin = make_user('admin')
    _tuesday_class(t)
    d = date(2026, 10, 20)
    service.run_reminders(now=myt_to_utc(d, '19:16'))
    service.run_reminders(now=myt_to_utc(d, '19:21'))
    msgs = [n.message for n in Notification.query.filter_by(user_id=t.id)]
    assert len(msgs) == 1 and 'starts at 7:30 pm' in msgs[0]
    service.run_reminders(now=myt_to_utc(d, '19:41'))
    assert Notification.query.filter_by(user_id=t.id).count() == 2
    assert Notification.query.filter_by(user_id=admin.id).count() == 1
