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
            'language_pref': self.language_pref or 'en'
        }


class Course(db.Model):
    __tablename__ = 'courses'
    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text)
    weeks        = db.Column(db.Integer, default=6)
    current_week = db.Column(db.Integer, default=1)   # controls student visibility
    start_date   = db.Column(db.Date)
    programme    = db.Column(db.String(100))   # e.g. "Python Bootcamp", "Machine Learning"
    language     = db.Column(db.String(5), default='en')   # 'en', 'zh', 'bm'
    seat_cap     = db.Column(db.Integer)                   # max enrolment seats (NULL = unlimited)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments  = db.relationship('Enrollment', back_populates='course')
    recordings   = db.relationship('Recording', back_populates='course', order_by='Recording.week, Recording.session_num')
    materials    = db.relationship('Material', back_populates='course', order_by='Material.week')
    assignments  = db.relationship('Assignment', back_populates='course', order_by='Assignment.week')
    attendances  = db.relationship('Attendance', back_populates='course')
    timetable_sessions = db.relationship('TimetableSession', back_populates='course', cascade='all, delete-orphan')
    sessions     = db.relationship('Session', back_populates='course', cascade='all, delete-orphan')
    announcements = db.relationship('Announcement', back_populates='course', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'weeks': self.weeks, 'current_week': self.current_week,
            'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
            'programme': self.programme or '',
            'language': self.language or 'en',
            'seat_cap': self.seat_cap
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
    class_timing     = db.Column(db.String(100))   # e.g. "Fri 8-10pm, Sat 9-11am"

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
            'payment_remarks': self.payment_remarks or '',
            'receipt_file': self.receipt_file or '',
            'class_timing': self.class_timing or ''
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
    id           = db.Column(db.Integer, primary_key=True)
    course_id    = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    week         = db.Column(db.Integer, default=0)   # 0 = general (always visible)
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
            'id': self.id, 'week': self.week, 'title': self.title,
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


class TimetableSession(db.Model):
    __tablename__ = 'timetable_sessions'
    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    week        = db.Column(db.Integer, nullable=False)
    session_num = db.Column(db.Integer, nullable=False)  # 1=Fri  2=Sat  3=Sun
    topic       = db.Column(db.String(300))
    notes       = db.Column(db.Text)

    course = db.relationship('Course', back_populates='timetable_sessions')
    __table_args__ = (db.UniqueConstraint('course_id', 'week', 'session_num'),)


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
        return {
            'id': self.id,
            'title': self.title,
            'session_type': self.session_type,
            'course_id': self.course_id,
            'course_title': self.course.title if self.course else None,
            'start_datetime': self.start_datetime.strftime('%Y-%m-%dT%H:%M'),
            'start_display': self.start_datetime.strftime('%a, %d %b %Y · %I:%M %p'),
            'duration_minutes': self.duration_minutes,
            'zoom_link': self.zoom_link or '',
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
    cert_number = db.Column(db.String(50), unique=True)  # e.g. CC-2026-001

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
    week            = db.Column(db.Integer)
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
            'week': self.week,
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
    week        = db.Column(db.Integer)
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
            'week': self.week,
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
