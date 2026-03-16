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

    # relationships
    enrollments   = db.relationship('Enrollment', back_populates='student', foreign_keys='Enrollment.student_id')
    submissions   = db.relationship('Submission', back_populates='student')
    watch_logs    = db.relationship('WatchLog', back_populates='student')
    attendances   = db.relationship('Attendance', back_populates='student')

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
            'created_at': self.created_at.strftime('%b %d, %Y')
        }


class Course(db.Model):
    __tablename__ = 'courses'
    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text)
    weeks        = db.Column(db.Integer, default=6)
    current_week = db.Column(db.Integer, default=1)   # controls student visibility
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments  = db.relationship('Enrollment', back_populates='course')
    recordings   = db.relationship('Recording', back_populates='course', order_by='Recording.week, Recording.session_num')
    materials    = db.relationship('Material', back_populates='course', order_by='Material.week')
    assignments  = db.relationship('Assignment', back_populates='course', order_by='Assignment.week')
    attendances  = db.relationship('Attendance', back_populates='course')

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'weeks': self.weeks, 'current_week': self.current_week
        }


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id               = db.Column(db.Integer, primary_key=True)
    student_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id        = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    enrolled_at      = db.Column(db.DateTime, default=datetime.utcnow)
    payment_status   = db.Column(db.String(20), default='pending')  # pending | paid | overdue
    payment_remarks  = db.Column(db.Text)

    student = db.relationship('User', back_populates='enrollments', foreign_keys=[student_id])
    course  = db.relationship('Course', back_populates='enrollments')
    __table_args__ = (db.UniqueConstraint('student_id', 'course_id'),)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name,
            'student_email': self.student.email,
            'course_id': self.course_id,
            'course_title': self.course.title,
            'enrolled_at': self.enrolled_at.strftime('%b %d, %Y'),
            'payment_status': self.payment_status or 'pending',
            'payment_remarks': self.payment_remarks or ''
        }


class Recording(db.Model):
    __tablename__ = 'recordings'
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    week        = db.Column(db.Integer, nullable=False)
    session_num = db.Column(db.Integer, nullable=False)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    filename    = db.Column(db.String(300))
    duration    = db.Column(db.String(20))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    course     = db.relationship('Course', back_populates='recordings')
    watch_logs = db.relationship('WatchLog', back_populates='recording')

    def to_dict(self, watched=False):
        return {
            'id': self.id, 'week': self.week, 'session_num': self.session_num,
            'title': self.title, 'description': self.description,
            'filename': self.filename, 'duration': self.duration,
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
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    week        = db.Column(db.Integer, default=0)   # 0 = general (always visible)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    filename    = db.Column(db.String(300), nullable=False)
    file_type   = db.Column(db.String(20))
    file_size   = db.Column(db.String(20))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    course = db.relationship('Course', back_populates='materials')

    def to_dict(self):
        return {
            'id': self.id, 'week': self.week, 'title': self.title,
            'description': self.description, 'filename': self.filename,
            'file_type': self.file_type, 'file_size': self.file_size,
            'uploaded_at': self.uploaded_at.strftime('%b %d, %Y')
        }


class Assignment(db.Model):
    __tablename__ = 'assignments'
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    week        = db.Column(db.Integer, nullable=False)
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
            'id': self.id, 'week': self.week, 'title': self.title,
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
    week        = db.Column(db.Integer, nullable=False)
    status      = db.Column(db.String(10), nullable=False, default='absent')  # present | absent | late
    notes       = db.Column(db.Text)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', back_populates='attendances')
    course  = db.relationship('Course', back_populates='attendances')
    __table_args__ = (db.UniqueConstraint('student_id', 'course_id', 'week'),)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name,
            'course_id': self.course_id,
            'week': self.week,
            'status': self.status,
            'notes': self.notes or '',
            'recorded_at': self.recorded_at.strftime('%b %d, %Y')
        }
