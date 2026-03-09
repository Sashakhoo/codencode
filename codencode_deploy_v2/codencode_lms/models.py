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
    role          = db.Column(db.String(20), nullable=False)   # 'student' | 'teacher'
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    enrollments   = db.relationship('Enrollment', back_populates='student', foreign_keys='Enrollment.student_id')
    submissions   = db.relationship('Submission', back_populates='student')
    watch_logs    = db.relationship('WatchLog', back_populates='student')

    def set_password(self, pw):  self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

    def initials(self):
        parts = self.name.split()
        return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else self.name[:2].upper()

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'email': self.email,
                'role': self.role, 'initials': self.initials()}


class Course(db.Model):
    __tablename__ = 'courses'
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    weeks       = db.Column(db.Integer, default=6)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments  = db.relationship('Enrollment', back_populates='course')
    recordings   = db.relationship('Recording', back_populates='course', order_by='Recording.week, Recording.session_num')
    materials    = db.relationship('Material', back_populates='course', order_by='Material.week')
    assignments  = db.relationship('Assignment', back_populates='course', order_by='Assignment.week')

    def to_dict(self):
        return {'id': self.id, 'title': self.title, 'description': self.description, 'weeks': self.weeks}


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id  = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', back_populates='enrollments', foreign_keys=[student_id])
    course  = db.relationship('Course', back_populates='enrollments')
    __table_args__ = (db.UniqueConstraint('student_id', 'course_id'),)


class Recording(db.Model):
    __tablename__ = 'recordings'
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    week        = db.Column(db.Integer, nullable=False)
    session_num = db.Column(db.Integer, nullable=False)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    filename    = db.Column(db.String(300))          # stored file name
    duration    = db.Column(db.String(20))           # e.g. "45:12"
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
    """Tracks which student watched which recording."""
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
    week        = db.Column(db.Integer, default=0)   # 0 = general
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    filename    = db.Column(db.String(300), nullable=False)
    file_type   = db.Column(db.String(20))           # pdf | py | zip | ipynb | csv
    file_size   = db.Column(db.String(20))           # human-readable
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
    brief_file  = db.Column(db.String(300))          # optional attached brief
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

    # grading
    score         = db.Column(db.Integer)
    feedback      = db.Column(db.Text)
    graded_at     = db.Column(db.DateTime)

    assignment = db.relationship('Assignment', back_populates='submissions')
    student    = db.relationship('User', back_populates='submissions')

    def status(self):
        if self.score is not None:   return 'graded'
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
