from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), nullable=False)   # 'student' | 'teacher' | 'admin'
    phone         = db.Column(db.String(30))
    ic_number     = db.Column(db.String(50))                   # IC or passport
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    language_pref = db.Column(db.String(5), default='en')
    is_active     = db.Column(db.Boolean, default=True)
    last_login    = db.Column(db.DateTime)
    temp_password = db.Column(db.String(100), nullable=True)   # plain-text, stored for welcome email only

    # ── Teacher profile fields ──────────────────────────────────
    title            = db.Column(db.String(120))   # e.g. "Lead Instructor", "Senior Data Scientist"
    bio              = db.Column(db.Text)            # short intro shown on student card
    education        = db.Column(db.Text)            # e.g. "BSc CS, UPM | MSc AI, UM"
    experience       = db.Column(db.Text)            # years / background paragraph
    specializations  = db.Column(db.String(300))     # comma-separated, e.g. "Python, ML, NLP"
    website          = db.Column(db.String(300))     # portfolio URL
    linkedin         = db.Column(db.String(300))     # LinkedIn URL
    avatar_filename  = db.Column(db.String(300))     # uploaded profile photo filename

    # relationships
    enrollments   = db.relationship('Enrollment', back_populates='student', foreign_keys='Enrollment.student_id')
    submissions   = db.relationship('Submission', back_populates='student')
    watch_logs    = db.relationship('WatchLog', back_populates='student')
    attendances   = db.relationship('Attendance', back_populates='student')
    notifications = db.relationship('Notification', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, pw):  self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

    def initials(self):
        parts = self.name.split()
        return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else self.name[:2].upper()

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'email': self.email,
            'role': self.role, 'initials': self.initials(),
            'phone': self.phone or '', 'ic_number': self.ic_number or '',
            'created_at': self.created_at.strftime('%b %d, %Y'),
            'last_login': self.last_login.strftime('%b %d, %Y · %I:%M %p') if self.last_login else None,
            'language_pref': self.language_pref or 'en',
            # profile fields (relevant for teachers, present for all users)
            'title':           self.title or '',
            'bio':             self.bio or '',
            'education':       self.education or '',
            'experience':      self.experience or '',
            'specializations': self.specializations or '',
            'website':         self.website or '',
            'linkedin':        self.linkedin or '',
            'avatar_filename': self.avatar_filename or '',
        }


class Course(db.Model):
    __tablename__ = 'courses'
    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text)
    total_sessions  = db.Column(db.Integer, default=6)
    current_session = db.Column(db.Integer, default=1)   # controls student visibility
    start_date   = db.Column(db.Date)
    programme    = db.Column(db.String(100))   # e.g. "Python Bootcamp", "Machine Learning"
    language     = db.Column(db.String(5), default='en')   # 'en', 'zh', 'bm'
    seat_cap     = db.Column(db.Integer)                   # max enrolment seats (NULL = unlimited)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    teacher_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # assigned instructor

    teacher      = db.relationship('User', foreign_keys=[teacher_id])

    enrollments  = db.relationship('Enrollment', back_populates='course')
    cohorts      = db.relationship('Cohort', back_populates='course', cascade='all, delete-orphan', order_by='Cohort.start_date')
    recordings   = db.relationship('Recording', back_populates='course', order_by='Recording.week, Recording.session_num')
    materials    = db.relationship('Material', back_populates='course', order_by='Material.session')
    assignments  = db.relationship('Assignment', back_populates='course', order_by='Assignment.session')
    attendances  = db.relationship('Attendance', back_populates='course')
    timetable_sessions = db.relationship('TimetableSession', back_populates='course', cascade='all, delete-orphan')
    sessions     = db.relationship('Session', back_populates='course', cascade='all, delete-orphan')
    announcements = db.relationship('Announcement', back_populates='course', cascade='all, delete-orphan')

    def to_dict(self):
        t = self.teacher
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'total_sessions': self.total_sessions, 'current_session': self.current_session,
            'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
            'programme': self.programme or '',
            'language': self.language or 'en',
            'seat_cap': self.seat_cap,
            'teacher_id': self.teacher_id,
            'teacher_name': t.name if t else '',
            'teacher_title': t.title if t else '',
            'teacher_bio': t.bio if t else '',
            'teacher_education': t.education if t else '',
            'teacher_experience': t.experience if t else '',
            'teacher_specializations': t.specializations if t else '',
            'teacher_website': t.website if t else '',
            'teacher_linkedin': t.linkedin if t else '',
            'teacher_avatar': t.avatar_filename if t else '',
            'teacher_initials': t.initials() if t else '',
        }


class Cohort(db.Model):
    """A specific intake/run of a course (e.g. Jan 2026, May 2026, Sep 2026)."""
    __tablename__ = 'cohorts'
    id           = db.Column(db.Integer, primary_key=True)
    course_id    = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    name         = db.Column(db.String(100), nullable=False)   # e.g. "Jan 2026", "Cohort 2"
    start_date   = db.Column(db.Date)
    end_date     = db.Column(db.Date)
    current_session = db.Column(db.Integer, default=1)
    # JSON array: [{"day":"Friday","start":"20:00","end":"22:00"}, ...]
    schedule     = db.Column(db.Text)
    notes        = db.Column(db.Text)   # free-form notes (e.g. "CNY break session 5")
    teacher_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    course      = db.relationship('Course', back_populates='cohorts')
    enrollments = db.relationship('Enrollment', back_populates='cohort')
    teacher     = db.relationship('User', foreign_keys=[teacher_id])

    def to_dict(self):
        import json as _json
        return {
            'id': self.id,
            'course_id': self.course_id,
            'name': self.name,
            'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
            'end_date': self.end_date.strftime('%Y-%m-%d') if self.end_date else None,
            'current_session': self.current_session,
            'schedule': _json.loads(self.schedule) if self.schedule else [],
            'notes': self.notes or '',
            'teacher_id': self.teacher_id,
            'teacher_name': self.teacher.name if self.teacher else '',
            'teacher_title': self.teacher.title if self.teacher else '',
            'created_at': self.created_at.strftime('%b %d, %Y'),
            'enrollment_count': len(self.enrollments)
        }


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id               = db.Column(db.Integer, primary_key=True)
    student_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id        = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    enrolled_at      = db.Column(db.DateTime, default=datetime.utcnow)
    payment_status   = db.Column(db.String(20), default='pending')  # pending | paid | overdue
    payment_remarks  = db.Column(db.Text)
    receipt_file     = db.Column(db.String(300))   # stored filename of uploaded receipt
    document_number  = db.Column(db.Integer)       # shared serial for invoice/receipt/certificate, e.g. 111
    class_timing     = db.Column(db.String(300))   # e.g. "Friday 20:00-22:00, Saturday 09:00-11:00"
    class_format     = db.Column(db.String(20))    # e.g. "1v1", "2v1", "5v1", "cohort"
    cohort_id        = db.Column(db.Integer, db.ForeignKey('cohorts.id'), nullable=True)
    payment_amount   = db.Column(db.Float,   nullable=True)   # e.g. 1200.00
    payment_method   = db.Column(db.String(50), nullable=True) # e.g. "Bank Transfer"
    paid_at          = db.Column(db.DateTime, nullable=True)   # timestamp when marked paid

    student = db.relationship('User', back_populates='enrollments', foreign_keys=[student_id])
    course  = db.relationship('Course', back_populates='enrollments')
    cohort  = db.relationship('Cohort', back_populates='enrollments')
    __table_args__ = (db.UniqueConstraint('student_id', 'course_id'),)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name if self.student else '(deleted)',
            'student_email': self.student.email if self.student else '',
            'course_id': self.course_id,
            'course_title': self.course.title,
            'enrolled_at': self.enrolled_at.strftime('%b %d, %Y'),
            'payment_status': self.payment_status or 'pending',
            'payment_remarks': self.payment_remarks or '',
            'receipt_file': self.receipt_file or '',
            'document_number': self.document_number,
            'class_timing': self.class_timing or '',
            'class_format': self.class_format or '',
            'cohort_id':    self.cohort_id,
            'cohort_name':  self.cohort.name if self.cohort else None,
            'payment_amount': self.payment_amount,
            'payment_method': self.payment_method or '',
            'paid_at': self.paid_at.strftime('%b %d, %Y') if self.paid_at else None,
        }


class Recording(db.Model):
    __tablename__ = 'recordings'
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    cohort_id   = db.Column(db.Integer, db.ForeignKey('cohorts.id'), nullable=True)
    week        = db.Column(db.Integer, nullable=False)  # calendar week within the schedule
    session_num = db.Column(db.Integer, nullable=False)  # which meeting within that week
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    filename    = db.Column(db.String(300))
    recording_url = db.Column(db.String(1000))
    source_type = db.Column(db.String(20), default='upload')
    duration    = db.Column(db.String(20))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    course     = db.relationship('Course', back_populates='recordings')
    cohort     = db.relationship('Cohort')
    watch_logs = db.relationship('WatchLog', back_populates='recording')

    def to_dict(self, watched=False):
        return {
            'id': self.id, 'week': self.week, 'session_num': self.session_num,
            'title': self.title, 'description': self.description,
            'course_id': self.course_id,
            'cohort_id': self.cohort_id,
            'cohort_name': self.cohort.name if self.cohort else '',
            'filename': self.filename, 'recording_url': self.recording_url,
            'source_type': self.source_type or ('link' if self.recording_url else 'upload'),
            'duration': self.duration,
            'uploaded_at': self.uploaded_at.strftime('%b %d, %Y'),
            'watched': watched
        }


class WatchLog(db.Model):
    __tablename__ = 'watch_logs'
    id           = db.Column(db.Integer, primary_key=True)
    student_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recording_id = db.Column(db.Integer, db.ForeignKey('recordings.id'), nullable=False)
    watched_at   = db.Column(db.DateTime, default=datetime.utcnow)

    student   = db.relationship('User', back_populates='watch_logs')
    recording = db.relationship('Recording', back_populates='watch_logs')
    __table_args__ = (db.UniqueConstraint('student_id', 'recording_id'),)


class Material(db.Model):
    __tablename__ = 'materials'
    id           = db.Column(db.Integer, primary_key=True)
    course_id    = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    session      = db.Column(db.Integer, default=0)   # 0 = general (always visible)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text)
    filename     = db.Column(db.String(300), nullable=False)
    file_type    = db.Column(db.String(20))
    file_size    = db.Column(db.String(20))
    uploaded_at  = db.Column(db.DateTime, default=datetime.utcnow)
    is_published = db.Column(db.Boolean, default=True)
    publish_at   = db.Column(db.DateTime)   # NULL means publish immediately
    order_index  = db.Column(db.Integer, default=0)

    course = db.relationship('Course', back_populates='materials')

    def to_dict(self):
        return {
            'id': self.id, 'session': self.session, 'title': self.title,
            'description': self.description, 'filename': self.filename,
            'file_type': self.file_type, 'file_size': self.file_size,
            'uploaded_at': self.uploaded_at.strftime('%b %d, %Y'),
            'is_published': self.is_published if self.is_published is not None else True,
            'publish_at': self.publish_at.strftime('%Y-%m-%dT%H:%M') if self.publish_at else None,
            'order_index': self.order_index or 0
        }


class Assignment(db.Model):
    __tablename__ = 'assignments'
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    session     = db.Column(db.Integer, nullable=False)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    due_date    = db.Column(db.DateTime)
    max_points  = db.Column(db.Integer, default=100)
    brief_file  = db.Column(db.String(300))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    course      = db.relationship('Course', back_populates='assignments')
    submissions = db.relationship('Submission', back_populates='assignment')

    def to_dict(self, submission=None):
        d = {
            'id': self.id, 'session': self.session, 'title': self.title,
            'description': self.description,
            'due_date': self.due_date.strftime('%b %d, %Y · %I:%M %p') if self.due_date else None,
            'max_points': self.max_points,
            'brief_file': self.brief_file,
            'submission_count': len(self.submissions)
        }
        if submission:
            d['submission'] = submission.to_dict()
        return d


class Submission(db.Model):
    __tablename__ = 'submissions'
    id            = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    student_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename      = db.Column(db.String(300), nullable=False)
    notes         = db.Column(db.Text)
    submitted_at  = db.Column(db.DateTime, default=datetime.utcnow)

    score         = db.Column(db.Integer)
    feedback      = db.Column(db.Text)
    graded_at     = db.Column(db.DateTime)

    assignment = db.relationship('Assignment', back_populates='submissions')
    student    = db.relationship('User', back_populates='submissions')

    def status(self):
        if self.score is not None: return 'graded'
        return 'submitted'

    def to_dict(self):
        return {
            'id': self.id,
            'assignment_id': self.assignment_id,
            'assignment_title': self.assignment.title,
            'student_id': self.student_id,
            'student_name': self.student.name,
            'filename': self.filename,
            'notes': self.notes,
            'submitted_at': self.submitted_at.strftime('%b %d, %Y · %I:%M %p'),
            'score': self.score,
            'feedback': self.feedback,
            'graded_at': self.graded_at.strftime('%b %d, %Y') if self.graded_at else None,
            'status': self.status(),
            'max_points': self.assignment.max_points
        }


class Attendance(db.Model):
    __tablename__ = 'attendance'
    id          = db.Column(db.Integer, primary_key=True)
    student_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    session     = db.Column(db.Integer, nullable=False)
    status      = db.Column(db.String(10), nullable=False, default='absent')  # present | absent | late
    notes       = db.Column(db.Text)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', back_populates='attendances')
    course  = db.relationship('Course', back_populates='attendances')
    __table_args__ = (db.UniqueConstraint('student_id', 'course_id', 'session'),)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name,
            'course_id': self.course_id,
            'session': self.session,
            'status': self.status,
            'notes': self.notes or '',
            'recorded_at': self.recorded_at.strftime('%b %d, %Y')
        }


class TimetableSession(db.Model):
    __tablename__ = 'timetable_sessions'
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    cohort_id   = db.Column(db.Integer, db.ForeignKey('cohorts.id'), nullable=True)
    week        = db.Column(db.Integer, nullable=False)  # calendar week within the schedule
    session_num = db.Column(db.Integer, nullable=False)  # 1=Fri  2=Sat  3=Sun
    day_name    = db.Column(db.String(20))
    time_start  = db.Column(db.String(5))
    time_end    = db.Column(db.String(5))
    day_offset  = db.Column(db.Integer)
    topic       = db.Column(db.String(300))
    notes       = db.Column(db.Text)

    course = db.relationship('Course', back_populates='timetable_sessions')
    cohort = db.relationship('Cohort')
    __table_args__ = (db.UniqueConstraint('course_id', 'cohort_id', 'week', 'session_num'),)


class Session(db.Model):
    """Live class / group / private tutoring slot."""
    __tablename__ = 'sessions'
    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(200), nullable=False)
    session_type     = db.Column(db.String(20), nullable=False)  # 'cohort' | 'group' | 'private'
    course_id        = db.Column(db.Integer, db.ForeignKey('courses.id'))
    start_datetime   = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    zoom_link        = db.Column(db.String(500))
    recording_url    = db.Column(db.String(500))
    created_by       = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    participants = db.relationship('SessionParticipant', back_populates='session', cascade='all, delete-orphan')
    course       = db.relationship('Course', back_populates='sessions')
    creator      = db.relationship('User', foreign_keys=[created_by])

    def to_dict(self):
        teacher = self.creator
        if self.course and self.course.teacher:
            teacher = self.course.teacher
        return {
            'id': self.id,
            'title': self.title,
            'session_type': self.session_type,
            'course_id': self.course_id,
            'course_title': self.course.title if self.course else None,
            'teacher_id': teacher.id if teacher else None,
            'teacher_name': teacher.name if teacher else '',
            'created_by_name': self.creator.name if self.creator else '',
            'start_datetime': self.start_datetime.strftime('%Y-%m-%dT%H:%M'),
            'start_display': self.start_datetime.strftime('%a, %d %b %Y · %I:%M %p'),
            'duration_minutes': self.duration_minutes,
            'zoom_link': self.zoom_link or '',
            'recording_url': self.recording_url or '',
            'has_recording': bool(self.recording_url),
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%b %d, %Y'),
            'participant_ids': [p.student_id for p in self.participants],
        }


class SessionParticipant(db.Model):
    __tablename__ = 'session_participants'
    id         = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    session = db.relationship('Session', back_populates='participants')
    student = db.relationship('User')
    __table_args__ = (db.UniqueConstraint('session_id', 'student_id'),)


class Notification(db.Model):
    __tablename__ = 'notifications'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message    = db.Column(db.String(500), nullable=False)
    link       = db.Column(db.String(300))
    read_at    = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='notifications')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'message': self.message,
            'link': self.link or '',
            'read_at': self.read_at.strftime('%b %d, %Y · %I:%M %p') if self.read_at else None,
            'created_at': self.created_at.strftime('%b %d, %Y · %I:%M %p'),
        }


class Announcement(db.Model):
    __tablename__ = 'announcements'
    id         = db.Column(db.Integer, primary_key=True)
    course_id  = db.Column(db.Integer, db.ForeignKey('courses.id'))  # NULL = global
    title      = db.Column(db.String(300), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    course  = db.relationship('Course', back_populates='announcements')
    creator = db.relationship('User', foreign_keys=[created_by])

    def to_dict(self):
        import math
        delta_secs = (datetime.utcnow() - self.created_at).total_seconds()
        if delta_secs < 3600:
            ago = f"{int(delta_secs//60)} min ago"
        elif delta_secs < 86400:
            ago = f"{int(delta_secs//3600)} hr ago"
        else:
            ago = f"{int(delta_secs//86400)} days ago"
        return {
            'id': self.id,
            'course_id': self.course_id,
            'course_title': self.course.title if self.course else 'All Courses',
            'title': self.title,
            'content': self.content,
            'created_by': self.created_by,
            'creator_name': self.creator.name if self.creator else 'System',
            'created_at': self.created_at.strftime('%b %d, %Y'),
            'ago': ago,
        }


# ─────────────────────────────────────────────
# A6 — Login Activity Log
# ─────────────────────────────────────────────
class LoginLog(db.Model):
    __tablename__ = 'login_logs'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    login_at   = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))

    user = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else '',
            'login_at': self.login_at.strftime('%b %d, %Y · %I:%M %p'),
            'ip_address': self.ip_address or ''
        }


# ─────────────────────────────────────────────
# A8+S10 — Certificates
# ─────────────────────────────────────────────
class Certificate(db.Model):
    __tablename__ = 'certificates'
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    course_id  = db.Column(db.Integer, db.ForeignKey('courses.id'))
    issued_at  = db.Column(db.DateTime, default=datetime.utcnow)
    issued_by  = db.Column(db.Integer, db.ForeignKey('users.id'))  # admin who issued
    cert_number = db.Column(db.String(50), unique=True)  # e.g. CC-2026-100

    student = db.relationship('User', foreign_keys=[student_id])
    course  = db.relationship('Course')
    issuer  = db.relationship('User', foreign_keys=[issued_by])

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name if self.student else '',
            'course_id': self.course_id,
            'course_title': self.course.title if self.course else '',
            'issued_at': self.issued_at.strftime('%b %d, %Y'),
            'issued_by': self.issued_by,
            'issuer_name': self.issuer.name if self.issuer else 'System',
            'cert_number': self.cert_number or ''
        }


# ─────────────────────────────────────────────
# S5+T2 — Quizzes
# ─────────────────────────────────────────────
class Quiz(db.Model):
    __tablename__ = 'quizzes'
    id              = db.Column(db.Integer, primary_key=True)
    course_id       = db.Column(db.Integer, db.ForeignKey('courses.id'))
    title           = db.Column(db.String(200), nullable=False)
    description     = db.Column(db.Text)
    session         = db.Column(db.Integer)
    pass_score      = db.Column(db.Integer, default=70)  # percentage
    max_attempts    = db.Column(db.Integer, default=2)
    time_limit_mins = db.Column(db.Integer)  # NULL = no limit
    is_published    = db.Column(db.Boolean, default=False)
    created_by      = db.Column(db.Integer, db.ForeignKey('users.id'))

    questions = db.relationship('QuizQuestion', back_populates='quiz',
                                cascade='all, delete-orphan',
                                order_by='QuizQuestion.order_index')
    course    = db.relationship('Course')

    def to_dict(self, include_questions=False, hide_correct=False):
        d = {
            'id': self.id,
            'course_id': self.course_id,
            'title': self.title,
            'description': self.description or '',
            'session': self.session,
            'pass_score': self.pass_score,
            'max_attempts': self.max_attempts,
            'time_limit_mins': self.time_limit_mins,
            'is_published': self.is_published,
            'question_count': len(self.questions)
        }
        if include_questions:
            d['questions'] = [q.to_dict(hide_correct=hide_correct) for q in self.questions]
        return d


class QuizQuestion(db.Model):
    __tablename__ = 'quiz_questions'
    id            = db.Column(db.Integer, primary_key=True)
    quiz_id       = db.Column(db.Integer, db.ForeignKey('quizzes.id'))
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), default='mcq')  # 'mcq' or 'short'
    points        = db.Column(db.Integer, default=1)
    explanation   = db.Column(db.Text)  # shown after submission
    order_index   = db.Column(db.Integer, default=0)

    quiz    = db.relationship('Quiz', back_populates='questions')
    choices = db.relationship('QuizChoice', back_populates='question',
                              cascade='all, delete-orphan')

    def to_dict(self, hide_correct=False):
        d = {
            'id': self.id,
            'quiz_id': self.quiz_id,
            'question_text': self.question_text,
            'question_type': self.question_type,
            'points': self.points,
            'explanation': self.explanation or '',
            'order_index': self.order_index,
            'choices': [c.to_dict(hide_correct=hide_correct) for c in self.choices]
        }
        return d


class QuizChoice(db.Model):
    __tablename__ = 'quiz_choices'
    id          = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_questions.id'))
    choice_text = db.Column(db.String(500), nullable=False)
    is_correct  = db.Column(db.Boolean, default=False)

    question = db.relationship('QuizQuestion', back_populates='choices')

    def to_dict(self, hide_correct=False):
        d = {'id': self.id, 'choice_text': self.choice_text}
        if not hide_correct:
            d['is_correct'] = self.is_correct
        return d


class QuizAttempt(db.Model):
    __tablename__ = 'quiz_attempts'
    id           = db.Column(db.Integer, primary_key=True)
    quiz_id      = db.Column(db.Integer, db.ForeignKey('quizzes.id'))
    student_id   = db.Column(db.Integer, db.ForeignKey('users.id'))
    score        = db.Column(db.Float)  # percentage
    passed       = db.Column(db.Boolean)
    started_at   = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)

    answers = db.relationship('QuizAnswer', back_populates='attempt', cascade='all, delete-orphan')
    quiz    = db.relationship('Quiz')
    student = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'quiz_id': self.quiz_id,
            'student_id': self.student_id,
            'score': self.score,
            'passed': self.passed,
            'started_at': self.started_at.strftime('%b %d, %Y · %I:%M %p'),
            'submitted_at': self.submitted_at.strftime('%b %d, %Y · %I:%M %p') if self.submitted_at else None
        }


class QuizAnswer(db.Model):
    __tablename__ = 'quiz_answers'
    id                 = db.Column(db.Integer, primary_key=True)
    attempt_id         = db.Column(db.Integer, db.ForeignKey('quiz_attempts.id'))
    question_id        = db.Column(db.Integer, db.ForeignKey('quiz_questions.id'))
    selected_choice_id = db.Column(db.Integer, db.ForeignKey('quiz_choices.id'), nullable=True)
    short_answer_text  = db.Column(db.Text, nullable=True)
    is_correct         = db.Column(db.Boolean)

    attempt         = db.relationship('QuizAttempt', back_populates='answers')
    question        = db.relationship('QuizQuestion')
    selected_choice = db.relationship('QuizChoice')

    def to_dict(self):
        return {
            'id': self.id,
            'question_id': self.question_id,
            'selected_choice_id': self.selected_choice_id,
            'short_answer_text': self.short_answer_text,
            'is_correct': self.is_correct,
            'explanation': self.question.explanation if self.question else ''
        }


# ─────────────────────────────────────────────
# S8+T8 — Discussion / Q&A
# ─────────────────────────────────────────────
class DiscussionPost(db.Model):
    __tablename__ = 'discussion_posts'
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'))
    session     = db.Column(db.Integer)
    author_id   = db.Column(db.Integer, db.ForeignKey('users.id'))
    title       = db.Column(db.String(300))
    body        = db.Column(db.Text, nullable=False)
    is_resolved = db.Column(db.Boolean, default=False)
    is_pinned   = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    author  = db.relationship('User', foreign_keys=[author_id])
    replies = db.relationship('DiscussionReply', back_populates='post',
                              cascade='all, delete-orphan',
                              order_by='DiscussionReply.created_at')
    upvotes = db.relationship('PostUpvote', back_populates='post', cascade='all, delete-orphan')

    def time_ago(self):
        delta = (datetime.utcnow() - self.created_at).total_seconds()
        if delta < 60: return 'just now'
        if delta < 3600: return f"{int(delta//60)}m ago"
        if delta < 86400: return f"{int(delta//3600)}h ago"
        return f"{int(delta//86400)}d ago"

    def to_dict(self, current_user_id=None):
        return {
            'id': self.id,
            'course_id': self.course_id,
            'session': self.session,
            'author_id': self.author_id,
            'author_name': self.author.name if self.author else '',
            'author_initials': self.author.initials() if self.author else '',
            'title': self.title or '',
            'body': self.body,
            'is_resolved': self.is_resolved,
            'is_pinned': self.is_pinned,
            'created_at': self.created_at.strftime('%b %d, %Y'),
            'time_ago': self.time_ago(),
            'reply_count': len(self.replies),
            'upvote_count': len(self.upvotes),
            'upvoted_by_me': any(u.user_id == current_user_id for u in self.upvotes) if current_user_id else False
        }


class DiscussionReply(db.Model):
    __tablename__ = 'discussion_replies'
    id            = db.Column(db.Integer, primary_key=True)
    post_id       = db.Column(db.Integer, db.ForeignKey('discussion_posts.id'))
    author_id     = db.Column(db.Integer, db.ForeignKey('users.id'))
    body          = db.Column(db.Text, nullable=False)
    is_instructor = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    post   = db.relationship('DiscussionPost', back_populates='replies')
    author = db.relationship('User')

    def time_ago(self):
        delta = (datetime.utcnow() - self.created_at).total_seconds()
        if delta < 60: return 'just now'
        if delta < 3600: return f"{int(delta//60)}m ago"
        if delta < 86400: return f"{int(delta//3600)}h ago"
        return f"{int(delta//86400)}d ago"

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'author_id': self.author_id,
            'author_name': self.author.name if self.author else '',
            'author_initials': self.author.initials() if self.author else '',
            'body': self.body,
            'is_instructor': self.is_instructor,
            'created_at': self.created_at.strftime('%b %d, %Y'),
            'time_ago': self.time_ago()
        }


class PostUpvote(db.Model):
    __tablename__ = 'post_upvotes'
    id      = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('discussion_posts.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    post = db.relationship('DiscussionPost', back_populates='upvotes')
    __table_args__ = (db.UniqueConstraint('post_id', 'user_id'),)


# ─────────────────────────────────────────────
# Public Registration (from register.html)
# ─────────────────────────────────────────────
class Registration(db.Model):
    __tablename__ = 'registrations'
    id                 = db.Column(db.Integer, primary_key=True)
    full_name          = db.Column(db.String(100), nullable=False)
    whatsapp           = db.Column(db.String(30), nullable=False)
    email              = db.Column(db.String(150), nullable=False)
    occupation         = db.Column(db.String(150))
    language           = db.Column(db.String(20))
    experience_level   = db.Column(db.String(50))
    referral_source    = db.Column(db.String(100))
    learning_goals     = db.Column(db.Text)
    course             = db.Column(db.String(200))
    class_format       = db.Column(db.String(100))
    total_fee          = db.Column(db.String(50))
    payment_preference = db.Column(db.String(50))
    instalment_week1   = db.Column(db.String(50))
    instalment_week3   = db.Column(db.String(50))
    timing             = db.Column(db.String(200))
    submitted_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'whatsapp': self.whatsapp,
            'email': self.email,
            'occupation': self.occupation or '',
            'language': self.language or '',
            'experience_level': self.experience_level or '',
            'referral_source': self.referral_source or '',
            'learning_goals': self.learning_goals or '',
            'course': self.course or '',
            'class_format': self.class_format or '',
            'total_fee': self.total_fee or '',
            'payment_preference': self.payment_preference or '',
            'instalment_week1': self.instalment_week1 or '',
            'instalment_week3': self.instalment_week3 or '',
            'timing': self.timing or '',
            'submitted_at': self.submitted_at.strftime('%b %d, %Y · %I:%M %p'),
        }


# ─────────────────────────────────────────────
# S11 — Resume Last Lesson
# ─────────────────────────────────────────────
class LastLesson(db.Model):
    __tablename__ = 'last_lessons'
    id          = db.Column(db.Integer, primary_key=True)
    student_id  = db.Column(db.Integer, db.ForeignKey('users.id'))
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'))
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'))
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student  = db.relationship('User')
    course   = db.relationship('Course')
    material = db.relationship('Material')
    __table_args__ = (db.UniqueConstraint('student_id', 'course_id'),)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'course_id': self.course_id,
            'material_id': self.material_id,
            'material_title': self.material.title if self.material else '',
            'material_filename': self.material.filename if self.material else '',
            'updated_at': self.updated_at.strftime('%b %d, %Y · %I:%M %p') if self.updated_at else ''
        }


# ─────────────────────────────────────────────
# Workshops — one-off in-person events (distinct from multi-session Courses)
# ─────────────────────────────────────────────
class Workshop(db.Model):
    """The catalogue entry, e.g. 'AI for Marketing'. A Workshop can run many times
    (WorkshopRun) on different dates/venues with different attendees."""
    __tablename__ = 'workshops'
    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(200), nullable=False)
    description    = db.Column(db.Text)
    duration_hours = db.Column(db.Float, default=4)
    price_per_pax  = db.Column(db.Float)  # default rate; a run can override it
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    runs = db.relationship('WorkshopRun', back_populates='workshop', cascade='all, delete-orphan',
                            order_by='WorkshopRun.start_datetime')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description or '',
            'duration_hours': self.duration_hours,
            'price_per_pax': self.price_per_pax,
            'run_count': len(self.runs),
            'created_at': self.created_at.strftime('%b %d, %Y'),
        }


class WorkshopRun(db.Model):
    """One scheduled occurrence of a Workshop — a specific date/time/venue/teacher."""
    __tablename__ = 'workshop_runs'
    id                 = db.Column(db.Integer, primary_key=True)
    workshop_id        = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)
    start_datetime     = db.Column(db.DateTime, nullable=False)
    end_datetime       = db.Column(db.DateTime)
    venue              = db.Column(db.String(300))   # free text — changes per run
    capacity           = db.Column(db.Integer)
    price_per_pax      = db.Column(db.Float)          # overrides Workshop.price_per_pax when set
    teacher_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    google_review_url  = db.Column(db.String(500))    # overrides the business-wide default when set
    feedback_token     = db.Column(db.String(32), unique=True)  # public feedback-form link, not a guessable ID
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)

    workshop  = db.relationship('Workshop', back_populates='runs')
    teacher   = db.relationship('User', foreign_keys=[teacher_id])
    attendees = db.relationship('WorkshopAttendee', back_populates='run', cascade='all, delete-orphan')
    feedback  = db.relationship('WorkshopFeedback', back_populates='run', cascade='all, delete-orphan')

    def effective_price(self):
        return self.price_per_pax if self.price_per_pax is not None else (self.workshop.price_per_pax if self.workshop else None)

    def to_dict(self):
        attended_count = sum(1 for a in self.attendees if a.attended)
        ratings = [f for f in self.feedback if f.event_rating is not None]
        avg_event = round(sum(f.event_rating for f in ratings) / len(ratings), 1) if ratings else None
        t_ratings = [f.teacher_rating for f in self.feedback if f.teacher_rating is not None]
        avg_teacher = round(sum(t_ratings) / len(t_ratings), 1) if t_ratings else None
        paid_count = sum(1 for a in self.attendees if a.payment_status == 'paid')
        price = self.effective_price()
        return {
            'id': self.id,
            'workshop_id': self.workshop_id,
            'workshop_title': self.workshop.title if self.workshop else '',
            'start_datetime': self.start_datetime.strftime('%Y-%m-%dT%H:%M') if self.start_datetime else None,
            'start_display': self.start_datetime.strftime('%a, %d %b %Y · %I:%M %p') if self.start_datetime else '',
            'end_datetime': self.end_datetime.strftime('%Y-%m-%dT%H:%M') if self.end_datetime else None,
            'venue': self.venue or '',
            'capacity': self.capacity,
            'price_per_pax': price,
            'teacher_id': self.teacher_id,
            'teacher_name': self.teacher.name if self.teacher else '',
            'google_review_url': self.google_review_url or '',
            'feedback_token': self.feedback_token,
            'attendee_count': len(self.attendees),
            'attended_count': attended_count,
            'paid_count': paid_count,
            'feedback_count': len(self.feedback),
            'avg_event_rating': avg_event,
            'avg_teacher_rating': avg_teacher,
            'revenue': round(paid_count * price, 2) if price is not None else None,
        }


class WorkshopAttendee(db.Model):
    """A person registered for a specific WorkshopRun. Reuses the existing User
    table (no duplicate client records) — attendees may or may not have an LMS
    student login; either way they're just a User row."""
    __tablename__ = 'workshop_attendees'
    id              = db.Column(db.Integer, primary_key=True)
    run_id          = db.Column(db.Integer, db.ForeignKey('workshop_runs.id'), nullable=False)
    client_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    attended        = db.Column(db.Boolean, default=False)
    payment_status  = db.Column(db.String(20), default='pending')  # pending | paid | overdue
    payment_amount  = db.Column(db.Float)
    payment_method  = db.Column(db.String(50))
    paid_at         = db.Column(db.DateTime)
    document_number = db.Column(db.Integer)  # shared serial with invoices/receipts/certificates
    registered_at   = db.Column(db.DateTime, default=datetime.utcnow)

    run    = db.relationship('WorkshopRun', back_populates='attendees')
    client = db.relationship('User')
    __table_args__ = (db.UniqueConstraint('run_id', 'client_id'),)

    def to_dict(self):
        return {
            'id': self.id,
            'run_id': self.run_id,
            'client_id': self.client_id,
            'client_name': self.client.name if self.client else '(deleted)',
            'client_email': self.client.email if self.client else '',
            'client_phone': self.client.phone if self.client else '',
            'attended': self.attended,
            'payment_status': self.payment_status or 'pending',
            'payment_amount': self.payment_amount,
            'payment_method': self.payment_method or '',
            'paid_at': self.paid_at.strftime('%b %d, %Y') if self.paid_at else None,
            'document_number': self.document_number,
            'registered_at': self.registered_at.strftime('%b %d, %Y'),
        }


class WorkshopFeedback(db.Model):
    """Post-workshop feedback — event rating + teacher rating, submitted via a
    public no-login form. attendee_id is nullable to allow anonymous feedback."""
    __tablename__ = 'workshop_feedback'
    id             = db.Column(db.Integer, primary_key=True)
    run_id         = db.Column(db.Integer, db.ForeignKey('workshop_runs.id'), nullable=False)
    attendee_id    = db.Column(db.Integer, db.ForeignKey('workshop_attendees.id'), nullable=True)
    event_rating   = db.Column(db.Integer)    # 1-5
    teacher_rating = db.Column(db.Integer)    # 1-5
    comment        = db.Column(db.Text)
    submitted_at   = db.Column(db.DateTime, default=datetime.utcnow)

    run      = db.relationship('WorkshopRun', back_populates='feedback')
    attendee = db.relationship('WorkshopAttendee')

    def to_dict(self):
        return {
            'id': self.id,
            'run_id': self.run_id,
            'attendee_id': self.attendee_id,
            'attendee_name': self.attendee.client.name if self.attendee and self.attendee.client else 'Anonymous',
            'event_rating': self.event_rating,
            'teacher_rating': self.teacher_rating,
            'comment': self.comment or '',
            'submitted_at': self.submitted_at.strftime('%b %d, %Y · %I:%M %p'),
        }
