"""`flask staff-seed-demo`: sample staff profiles, schedules, sessions and a
Zoom report for local development. Refuses to run in production."""
import json
import os
from datetime import timedelta

from models import db, User, Course, Cohort
from staff.models import StaffProfile, StaffShift, WorkSession, ZoomParticipantReport
from staff.timeutil import myt_to_utc, today_myt, MYT

DEMO_MEETING = '84455667788'


def _is_production():
    return bool(os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('FLASK_ENV') == 'production'
                or os.environ.get('DATABASE_URL', '').startswith(('postgres://', 'postgresql://')))


def seed_demo(force=False):
    if _is_production() and not force:
        return 'Refusing to seed demo data in production.'
    teacher = User.query.filter_by(email='teacher@codencode.my').first()
    admin = User.query.filter_by(email='admin@codencode.my').first()
    if not teacher or not admin:
        return 'Demo LMS accounts (teacher@ / admin@codencode.my) are missing; start the app once first.'
    for u, rate, cap, etype in ((teacher, 40, 60, 'part_time'), (admin, 0, 0, 'full_time')):
        if not StaffProfile.query.filter_by(user_id=u.id).first():
            db.session.add(StaffProfile(user_id=u.id, hourly_rate=rate, monthly_cap_hours=cap, employment_type=etype))

    today = today_myt()
    first = today.replace(day=1)
    course = Course.query.order_by(Course.id).first()
    if course is None:
        course = Course(title='Python Foundations', total_sessions=12)
        db.session.add(course)
        db.session.flush()
    cohort = Cohort.query.filter_by(name='PY-101 (demo)').first()
    if cohort is None:
        cohort = Cohort(course_id=course.id, name='PY-101 (demo)', teacher_id=teacher.id,
                        start_date=first - timedelta(days=30), end_date=first + timedelta(days=120),
                        schedule=json.dumps([{'day': 'Tuesday', 'start': '19:30', 'end': '22:30'},
                                             {'day': 'Thursday', 'start': '20:00', 'end': '22:00'}]),
                        zoom_meeting_id=DEMO_MEETING, zoom_link=f'https://zoom.us/j/{DEMO_MEETING}',
                        every_n_weeks=1)
        db.session.add(cohort)
        db.session.flush()
    if not StaffShift.query.filter_by(user_id=teacher.id, title='Admin & content (demo)').first():
        db.session.add(StaffShift(user_id=teacher.id, title='Admin & content (demo)', days=[2], start_time='14:00',
                                  end_time='18:00', start_date=first - timedelta(days=30),
                                  end_date=first + timedelta(days=120), status='active',
                                  requested_by=teacher.id, approved_by=admin.id))
    db.session.commit()

    if WorkSession.query.filter_by(user_id=teacher.id).count():
        db.session.commit()
        return 'Profiles and schedules ready; sessions already seeded.'
    made = 0
    d = first
    while d < today:
        if d.weekday() in (1, 3):
            start, end = ('19:30', '22:30') if d.weekday() == 1 else ('20:00', '22:00')
            cin = myt_to_utc(d, start) - timedelta(minutes=d.day % 4)
            cout = myt_to_utc(d, end) + timedelta(minutes=d.day % 3)
            db.session.add(WorkSession(user_id=teacher.id, mode='zoom', cohort_id=cohort.id,
                                       zoom_meeting_id=DEMO_MEETING, clock_in_at=cin, clock_out_at=cout,
                                       scheduled_start_at=myt_to_utc(d, start), scheduled_end_at=myt_to_utc(d, end)))
            if d < today - timedelta(days=3):        # newest classes: report not in yet
                leave = cout - timedelta(minutes=28 if d.day % 5 == 0 else 0)
                parts = [{'name': 'Teacher', 'email': 'codencodemy@gmail.com', 'join_at': cin.astimezone(MYT).isoformat(),
                          'leave_at': leave.astimezone(MYT).isoformat(), 'minutes': round((leave - cin).total_seconds() / 60, 2)}]
                parts += [{'name': f'Student {i}', 'email': '', 'join_at': cin.astimezone(MYT).isoformat(),
                           'leave_at': cout.astimezone(MYT).isoformat(), 'minutes': 170} for i in range(8 + d.day % 6)]
                db.session.add(ZoomParticipantReport(zoom_meeting_id=DEMO_MEETING, local_date=d, participants=parts, source='csv'))
            made += 1
        elif d.weekday() == 2:
            db.session.add(WorkSession(user_id=teacher.id, mode='office', task='Content editing',
                                       clock_in_at=myt_to_utc(d, '14:00'), clock_out_at=myt_to_utc(d, '17:30'),
                                       lat=0, lng=0, distance_m=15 + d.day))
            made += 1
        d += timedelta(days=1)
    db.session.commit()
    return f'Seeded profiles, a demo cohort and shift, and {made} sessions for {teacher.email}.'
