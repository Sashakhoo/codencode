"""Staff Attendance & Payroll tables. Same database and `db` as the LMS.

Datetimes are timezone-aware UTC (see staff/timeutil.py).
"""
from sqlalchemy.dialects.postgresql import JSONB

from models import db
from staff.timeutil import utcnow, as_utc

JSONType = db.JSON().with_variant(JSONB(), 'postgresql')
TZDateTime = db.DateTime(timezone=True)


class StaffProfile(db.Model):
    __tablename__ = 'staff_profiles'
    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    employment_type   = db.Column(db.String(20), nullable=False, default='part_time')  # part_time | full_time
    hourly_rate       = db.Column(db.Numeric(10, 2), nullable=False, default=0)       # RM
    monthly_cap_hours = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    active            = db.Column(db.Boolean, nullable=False, default=True)
    created_at        = db.Column(TZDateTime, default=utcnow)
    updated_at        = db.Column(TZDateTime, default=utcnow, onupdate=utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    def to_dict(self):
        return {'user_id': self.user_id, 'employment_type': self.employment_type,
                'hourly_rate': float(self.hourly_rate or 0),
                'monthly_cap_hours': float(self.monthly_cap_hours or 0),
                'active': bool(self.active)}


class StaffShift(db.Model):
    """Recurring office shift."""
    __tablename__ = 'staff_shifts'
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title         = db.Column(db.String(200), nullable=False)
    days          = db.Column(JSONType, nullable=False, default=list)   # weekday ints, Mon=0
    start_time    = db.Column(db.String(5), nullable=False)             # 'HH:MM' MYT
    end_time      = db.Column(db.String(5), nullable=False)
    start_date    = db.Column(db.Date, nullable=False)
    end_date      = db.Column(db.Date, nullable=False)
    every_n_weeks = db.Column(db.Integer, nullable=False, default=1)
    skip_dates    = db.Column(JSONType, nullable=False, default=list)   # 'YYYY-MM-DD'
    status        = db.Column(db.String(20), nullable=False, default='pending')  # pending | active | rejected
    requested_by  = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by   = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at   = db.Column(TZDateTime)
    note          = db.Column(db.String(500))
    created_at    = db.Column(TZDateTime, default=utcnow)
    updated_at    = db.Column(TZDateTime, default=utcnow, onupdate=utcnow)

    user = db.relationship('User', foreign_keys=[user_id])


class CohortScheduleRequest(db.Model):
    """A teacher's request to create or change a Zoom class schedule."""
    __tablename__ = 'cohort_schedule_requests'
    id           = db.Column(db.Integer, primary_key=True)
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    cohort_id    = db.Column(db.Integer, db.ForeignKey('cohorts.id'), nullable=True)
    course_id    = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    # name, days (Mon=0 ints), start, end, start_date, end_date, every_n_weeks, zoom_meeting_id
    payload      = db.Column(JSONType, nullable=False, default=dict)
    status       = db.Column(db.String(20), nullable=False, default='pending')  # pending | approved | rejected | withdrawn
    reviewed_by  = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at  = db.Column(TZDateTime)
    note         = db.Column(db.String(500))
    created_at   = db.Column(TZDateTime, default=utcnow)

    requester = db.relationship('User', foreign_keys=[requested_by])
    course    = db.relationship('Course', foreign_keys=[course_id])
    cohort    = db.relationship('Cohort', foreign_keys=[cohort_id])


class CohortSkipDate(db.Model):
    __tablename__ = 'cohort_skip_dates'
    __table_args__ = (db.UniqueConstraint('cohort_id', 'date', name='uq_cohort_skip_date'),)
    id        = db.Column(db.Integer, primary_key=True)
    cohort_id = db.Column(db.Integer, db.ForeignKey('cohorts.id'), nullable=False, index=True)
    date      = db.Column(db.Date, nullable=False)
    reason    = db.Column(db.String(300))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(TZDateTime, default=utcnow)


class WorkSession(db.Model):
    __tablename__ = 'work_sessions'
    __table_args__ = (
        # At most one open session per user.
        db.Index('uq_work_sessions_one_open', 'user_id', unique=True,
                 postgresql_where=db.text('clock_out_at IS NULL'),
                 sqlite_where=db.text('clock_out_at IS NULL')),
    )
    id                 = db.Column(db.Integer, primary_key=True)
    user_id            = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    mode               = db.Column(db.String(10), nullable=False)   # zoom | office
    cohort_id          = db.Column(db.Integer, db.ForeignKey('cohorts.id'), nullable=True)
    zoom_meeting_id    = db.Column(db.String(50), nullable=True)
    shift_id           = db.Column(db.Integer, db.ForeignKey('staff_shifts.id'), nullable=True)
    task               = db.Column(db.Text)
    clock_in_at        = db.Column(TZDateTime, nullable=False, index=True)
    clock_out_at       = db.Column(TZDateTime, nullable=True)
    scheduled_start_at = db.Column(TZDateTime, nullable=True)
    scheduled_end_at   = db.Column(TZDateTime, nullable=True)
    lat                = db.Column(db.Float)
    lng                = db.Column(db.Float)
    distance_m         = db.Column(db.Float)
    source             = db.Column(db.String(20), nullable=False, default='app')  # app | admin_adjusted
    auto_closed        = db.Column(db.Boolean, nullable=False, default=False)
    review_status      = db.Column(db.String(20))      # None | approved | overridden
    override_paid_minutes = db.Column(db.Float)
    reviewed_by        = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at        = db.Column(TZDateTime)
    created_at         = db.Column(TZDateTime, default=utcnow)

    user   = db.relationship('User', foreign_keys=[user_id])
    cohort = db.relationship('Cohort', foreign_keys=[cohort_id])
    shift  = db.relationship('StaffShift', foreign_keys=[shift_id])

    def as_eval_dict(self):
        return {'mode': self.mode, 'clock_in_at': as_utc(self.clock_in_at),
                'clock_out_at': as_utc(self.clock_out_at), 'distance_m': self.distance_m,
                'auto_closed': self.auto_closed, 'review_status': self.review_status,
                'override_paid_minutes': self.override_paid_minutes}

    def snapshot(self):
        """For audit_log before/after."""
        def iso(v):
            v = as_utc(v)
            return v.isoformat() if v else None
        return {'clock_in_at': iso(self.clock_in_at), 'clock_out_at': iso(self.clock_out_at),
                'task': self.task, 'source': self.source, 'auto_closed': self.auto_closed,
                'review_status': self.review_status,
                'override_paid_minutes': self.override_paid_minutes}


class ZoomParticipantReport(db.Model):
    __tablename__ = 'zoom_participant_reports'
    __table_args__ = (db.UniqueConstraint('zoom_meeting_id', 'local_date', name='uq_zoom_report_meeting_date'),)
    id              = db.Column(db.Integer, primary_key=True)
    zoom_meeting_id = db.Column(db.String(50), nullable=False)
    meeting_uuid    = db.Column(db.String(100))
    local_date      = db.Column(db.Date, nullable=False)   # MYT date
    participants    = db.Column(JSONType, nullable=False, default=list)  # [{name,email,join_at,leave_at,minutes}]
    source          = db.Column(db.String(10), nullable=False, default='api')  # api | csv
    fetched_at      = db.Column(TZDateTime, default=utcnow)


class ZoomReportJob(db.Model):
    __tablename__ = 'zoom_report_jobs'
    id              = db.Column(db.Integer, primary_key=True)
    meeting_uuid    = db.Column(db.String(100), nullable=False)
    zoom_meeting_id = db.Column(db.String(50), nullable=False)
    meeting_start_at = db.Column(TZDateTime)
    due_at          = db.Column(TZDateTime, nullable=False, index=True)
    tries           = db.Column(db.Integer, nullable=False, default=0)
    last_error      = db.Column(db.Text)
    done            = db.Column(db.Boolean, nullable=False, default=False)
    created_at      = db.Column(TZDateTime, default=utcnow)


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id        = db.Column(db.Integer, primary_key=True)
    actor_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # None = system job
    action    = db.Column(db.String(60), nullable=False)
    entity    = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.Integer)
    before    = db.Column(JSONType)
    after     = db.Column(JSONType)
    reason    = db.Column(db.Text)
    at        = db.Column(TZDateTime, default=utcnow, nullable=False)


class PushSubscription(db.Model):
    __tablename__ = 'push_subscriptions'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    endpoint   = db.Column(db.Text, nullable=False, unique=True)
    p256dh     = db.Column(db.String(200), nullable=False)
    auth       = db.Column(db.String(100), nullable=False)
    created_at = db.Column(TZDateTime, default=utcnow)


class StaffNotifyKey(db.Model):
    """Dedupe: one row per (user, type, occurrence) that was already sent."""
    __tablename__ = 'staff_notify_keys'
    id      = db.Column(db.Integer, primary_key=True)
    key     = db.Column(db.String(200), nullable=False, unique=True)
    sent_at = db.Column(TZDateTime, default=utcnow)
