"""pytest setup: the real LMS app on a throwaway SQLite database.

Run from codencode_deploy_v2/codencode_lms:  python -m pytest tests -q
"""
import json
import os
import sys
import tempfile
import uuid

import pytest

_TMP = tempfile.mkdtemp(prefix='staff-tests-')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(_TMP, 'test.db').replace('\\', '/')
os.environ['DISABLE_SCHEDULER'] = '1'
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.pop('RAILWAY_ENVIRONMENT', None)
os.environ['ZOOM_WEBHOOK_SECRET_TOKEN'] = 'zoom-test-secret'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OFFICE = (1.5615, 103.7790)


@pytest.fixture(scope='session')
def app():
    import app as app_module
    a = app_module.app
    a.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=True,
                    OFFICE_LAT=OFFICE[0], OFFICE_LNG=OFFICE[1], OFFICE_RADIUS_M=200.0,
                    ZOOM_HOST_EMAIL='codencodemy@gmail.com', ZOOM_MAX_CONCURRENT=2)
    from staff.extensions import limiter
    limiter.enabled = False
    return a


@pytest.fixture(autouse=True)
def ctx(app):
    from models import db
    with app.app_context():
        yield
        db.session.rollback()
        from staff import models as sm
        for m in (sm.AuditLog, sm.WorkSession, sm.ZoomParticipantReport, sm.ZoomReportJob, sm.StaffNotifyKey,
                  sm.PushSubscription, sm.CohortSkipDate, sm.CohortScheduleRequest, sm.StaffShift, sm.StaffProfile):
            m.query.delete()
        from models import Cohort, Notification
        Cohort.query.filter(Cohort.name.like('T-%')).delete(synchronize_session=False)
        Notification.query.delete()
        db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(role, name=None):
    from models import db, User
    u = User(name=name or f'{role.title()} {uuid.uuid4().hex[:5]}', email=f'{uuid.uuid4().hex[:10]}@t.example',
             role=role)
    u.set_password('pw-123456')
    db.session.add(u)
    db.session.commit()
    return u


def login(client, user):
    # Requests reuse the test's app context, so Flask-Login's per-context
    # user cache (g._login_user) must be cleared when switching accounts.
    from flask import g
    g.pop('_login_user', None)
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)
        s['_fresh'] = True


def make_course():
    from models import db, Course
    c = Course.query.filter_by(title='T-Course').first()
    if not c:
        c = Course(title='T-Course')
        db.session.add(c)
        db.session.commit()
    return c


def make_cohort(teacher, slots, start=None, end=None, meeting='84455667788', name=None, every=1):
    from models import db, Cohort
    c = Cohort(course_id=make_course().id, name=name or f'T-{uuid.uuid4().hex[:5]}', teacher_id=teacher.id,
               schedule=json.dumps([{'day': d, 'start': s, 'end': e} for d, s, e in slots]),
               start_date=start, end_date=end, zoom_meeting_id=meeting,
               zoom_link=f'https://zoom.us/j/{meeting}' if meeting else None, every_n_weeks=every)
    db.session.add(c)
    db.session.commit()
    return c


def make_session(user, cin, cout, mode='office', **kw):
    from models import db
    from staff.models import WorkSession
    ws = WorkSession(user_id=user.id, mode=mode, clock_in_at=cin, clock_out_at=cout,
                     distance_m=kw.pop('distance_m', 10 if mode == 'office' else None), **kw)
    db.session.add(ws)
    db.session.commit()
    return ws
