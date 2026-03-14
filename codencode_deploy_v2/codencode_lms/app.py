"""
codencode.my LMS — Flask Backend
=================================
Kept deliberately simple:
  - Single app.py  (no blueprints needed at this scale)
  - SQLAlchemy ORM + PostgreSQL (falls back to SQLite for local dev)
  - Flask-Login for session auth
  - All file uploads go to /uploads on disk
  - JSON API consumed by the frontend
"""

import os
import uuid
from datetime import datetime
from functools import wraps

from flask import (Flask, request, jsonify, send_from_directory,
                   session, g)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from werkzeug.utils import secure_filename

from models import (db, User, Course, Enrollment, Recording,
                    WatchLog, Material, Assignment, Submission)

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
app = Flask(__name__, static_folder='static', template_folder='templates')

app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-secret-change-in-production'),

    # PostgreSQL:  postgresql://user:pass@localhost:5432/codencode_lms
    # SQLite fallback for local dev without Postgres:
    SQLALCHEMY_DATABASE_URI=os.environ.get(
        'DATABASE_URL',
        'sqlite:///codencode_lms.db'
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,

    UPLOAD_FOLDER=os.path.join(os.path.dirname(__file__), 'uploads'),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024 * 1024,   # 2 GB (for videos)

    # Allowed extensions per category
    ALLOWED_VIDEO={'mp4', 'mov', 'mkv', 'webm'},
    ALLOWED_MATERIAL={'pdf', 'py', 'ipynb', 'zip', 'csv', 'txt', 'docx'},
    ALLOWED_SUBMISSION={'py', 'ipynb', 'zip', 'pdf', 'txt'},
)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'serve_frontend'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def allowed(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def save_upload(file, subfolder, allowed_set):
    """Save an uploaded file, return stored filename or raise ValueError."""
    if not file or file.filename == '':
        raise ValueError('No file provided')
    if not allowed(file.filename, allowed_set):
        raise ValueError(f'File type not allowed. Allowed: {allowed_set}')
    ext = file.filename.rsplit('.', 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(dest, exist_ok=True)
    file.save(os.path.join(dest, stored_name))
    return stored_name, file.filename   # (stored, original)


def human_size(path):
    try:
        b = os.path.getsize(path)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except Exception:
        return '—'


def teacher_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != 'teacher':
            return jsonify({'error': 'Teachers only'}), 403
        return f(*args, **kwargs)
    return wrapper


def student_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != 'student':
            return jsonify({'error': 'Students only'}), 403
        return f(*args, **kwargs)
    return wrapper


def enrolled_or_teacher(course_id):
    """Return True if current user is teacher or enrolled in course."""
    if current_user.role == 'teacher':
        return True
    return Enrollment.query.filter_by(
        student_id=current_user.id, course_id=course_id).first() is not None


# ─────────────────────────────────────────────
# Serve the frontend (single HTML file)
# ─────────────────────────────────────────────
@app.route('/')
@app.route('/lms')
def serve_frontend():
    return send_from_directory('templates', 'lms.html')


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data  = request.get_json()
    email = data.get('email', '').strip().lower()
    pw    = data.get('password', '')

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(pw):
        return jsonify({'error': 'Invalid email or password'}), 401

    login_user(user, remember=True)
    return jsonify({'user': user.to_dict()})


@app.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    logout_user()
    return jsonify({'ok': True})


@app.route('/api/auth/me')
@login_required
def api_me():
    return jsonify({'user': current_user.to_dict()})


# ─────────────────────────────────────────────
# COURSES
# ─────────────────────────────────────────────
@app.route('/api/courses')
@login_required
def api_courses():
    if current_user.role == 'teacher':
        courses = Course.query.all()
    else:
        courses = [e.course for e in current_user.enrollments]
    return jsonify([c.to_dict() for c in courses])


# ─────────────────────────────────────────────
# RECORDINGS
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/recordings')
@login_required
def api_recordings(cid):
    if not enrolled_or_teacher(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    recs = Recording.query.filter_by(course_id=cid).order_by(
        Recording.week, Recording.session_num).all()

    if current_user.role == 'student':
        watched_ids = {w.recording_id for w in
                       WatchLog.query.filter_by(student_id=current_user.id).all()}
        data = [r.to_dict(watched=r.id in watched_ids) for r in recs]
    else:
        data = [r.to_dict() for r in recs]

    # Group by week
    weeks = {}
    for r in data:
        w = r['week']
        weeks.setdefault(w, []).append(r)
    return jsonify({'weeks': weeks})


@app.route('/api/courses/<int:cid>/recordings', methods=['POST'])
@teacher_required
def api_upload_recording(cid):
    try:
        stored, original = save_upload(
            request.files.get('file'), 'videos',
            app.config['ALLOWED_VIDEO'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    rec = Recording(
        course_id   = cid,
        week        = int(request.form.get('week', 1)),
        session_num = int(request.form.get('session_num', 1)),
        title       = request.form.get('title', original),
        description = request.form.get('description', ''),
        filename    = stored,
        duration    = request.form.get('duration', '')
    )
    db.session.add(rec)
    db.session.commit()
    return jsonify({'recording': rec.to_dict()}), 201


@app.route('/api/recordings/<int:rid>', methods=['DELETE'])
@teacher_required
def api_delete_recording(rid):
    rec = Recording.query.get_or_404(rid)
    # Remove file from disk
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', rec.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(rec)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/recordings/<int:rid>/watch', methods=['POST'])
@student_required
def api_mark_watched(rid):
    exists = WatchLog.query.filter_by(
        student_id=current_user.id, recording_id=rid).first()
    if not exists:
        db.session.add(WatchLog(student_id=current_user.id, recording_id=rid))
        db.session.commit()
    return jsonify({'ok': True})


@app.route('/uploads/videos/<path:filename>')
@login_required
def serve_video(filename):
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), filename)


# ─────────────────────────────────────────────
# MATERIALS
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/materials')
@login_required
def api_materials(cid):
    if not enrolled_or_teacher(cid):
        return jsonify({'error': 'Not enrolled'}), 403
    mats = Material.query.filter_by(course_id=cid).order_by(
        Material.week, Material.uploaded_at).all()
    return jsonify([m.to_dict() for m in mats])


@app.route('/api/courses/<int:cid>/materials', methods=['POST'])
@teacher_required
def api_upload_material(cid):
    try:
        stored, original = save_upload(
            request.files.get('file'), 'materials',
            app.config['ALLOWED_MATERIAL'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    ext  = original.rsplit('.', 1)[1].lower() if '.' in original else ''
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'materials', stored)

    mat = Material(
        course_id   = cid,
        week        = int(request.form.get('week', 0)),
        title       = request.form.get('title', original),
        description = request.form.get('description', ''),
        filename    = stored,
        file_type   = ext,
        file_size   = human_size(fpath)
    )
    db.session.add(mat)
    db.session.commit()
    return jsonify({'material': mat.to_dict()}), 201


@app.route('/api/materials/<int:mid>', methods=['DELETE'])
@teacher_required
def api_delete_material(mid):
    mat = Material.query.get_or_404(mid)
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'materials', mat.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(mat)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/uploads/materials/<path:filename>')
@login_required
def serve_material(filename):
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'materials'),
        filename, as_attachment=True)


# ─────────────────────────────────────────────
# ASSIGNMENTS
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/assignments')
@login_required
def api_assignments(cid):
    if not enrolled_or_teacher(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    assignments = Assignment.query.filter_by(course_id=cid).order_by(
        Assignment.week).all()

    if current_user.role == 'student':
        result = []
        for a in assignments:
            sub = Submission.query.filter_by(
                assignment_id=a.id, student_id=current_user.id).first()
            result.append(a.to_dict(submission=sub))
    else:
        result = [a.to_dict() for a in assignments]

    return jsonify(result)


@app.route('/api/courses/<int:cid>/assignments', methods=['POST'])
@teacher_required
def api_create_assignment(cid):
    # optional brief file
    brief_file = None
    if 'file' in request.files and request.files['file'].filename:
        try:
            stored, _ = save_upload(request.files['file'], 'briefs',
                                    app.config['ALLOWED_MATERIAL'])
            brief_file = stored
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    due_str = request.form.get('due_date')
    due_date = None
    if due_str:
        try:
            due_date = datetime.strptime(due_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            try:
                due_date = datetime.strptime(due_str, '%Y-%m-%d')
            except ValueError:
                pass

    a = Assignment(
        course_id   = cid,
        week        = int(request.form.get('week', 1)),
        title       = request.form.get('title', 'Untitled Assignment'),
        description = request.form.get('description', ''),
        due_date    = due_date,
        max_points  = int(request.form.get('max_points', 100)),
        brief_file  = brief_file
    )
    db.session.add(a)
    db.session.commit()
    return jsonify({'assignment': a.to_dict()}), 201


@app.route('/api/assignments/<int:aid>', methods=['DELETE'])
@teacher_required
def api_delete_assignment(aid):
    a = Assignment.query.get_or_404(aid)
    db.session.delete(a)
    db.session.commit()
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# SUBMISSIONS
# ─────────────────────────────────────────────
@app.route('/api/assignments/<int:aid>/submit', methods=['POST'])
@student_required
def api_submit(aid):
    a = Assignment.query.get_or_404(aid)

    # One submission per student per assignment — allow resubmit
    existing = Submission.query.filter_by(
        assignment_id=aid, student_id=current_user.id).first()

    try:
        stored, original = save_upload(
            request.files.get('file'), 'submissions',
            app.config['ALLOWED_SUBMISSION'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if existing:
        # Replace old file
        old = os.path.join(app.config['UPLOAD_FOLDER'], 'submissions', existing.filename)
        if os.path.exists(old):
            os.remove(old)
        existing.filename     = stored
        existing.notes        = request.form.get('notes', '')
        existing.submitted_at = datetime.utcnow()
        existing.score        = None   # reset grade on resubmit
        existing.feedback     = None
        existing.graded_at    = None
        db.session.commit()
        return jsonify({'submission': existing.to_dict()})

    sub = Submission(
        assignment_id = aid,
        student_id    = current_user.id,
        filename      = stored,
        notes         = request.form.get('notes', '')
    )
    db.session.add(sub)
    db.session.commit()
    return jsonify({'submission': sub.to_dict()}), 201


@app.route('/api/assignments/<int:aid>/submissions')
@teacher_required
def api_submissions(aid):
    subs = Submission.query.filter_by(assignment_id=aid).order_by(
        Submission.submitted_at).all()
    return jsonify([s.to_dict() for s in subs])


@app.route('/api/submissions/<int:sid>/grade', methods=['POST'])
@teacher_required
def api_grade(sid):
    sub = Submission.query.get_or_404(sid)
    data = request.get_json()
    score = data.get('score')
    if score is None or not (0 <= int(score) <= sub.assignment.max_points):
        return jsonify({'error': 'Invalid score'}), 400
    sub.score     = int(score)
    sub.feedback  = data.get('feedback', '')
    sub.graded_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'submission': sub.to_dict()})


@app.route('/uploads/submissions/<path:filename>')
@login_required
def serve_submission(filename):
    # Students can only download their own; teachers can download any
    if current_user.role == 'student':
        sub = Submission.query.filter_by(
            filename=filename, student_id=current_user.id).first()
        if not sub:
            return jsonify({'error': 'Forbidden'}), 403
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'submissions'),
        filename, as_attachment=True)


# ─────────────────────────────────────────────
# DASHBOARD stats
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/dashboard')
@login_required
def api_dashboard(cid):
    if not enrolled_or_teacher(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    total_recordings = Recording.query.filter_by(course_id=cid).count()
    total_materials  = Material.query.filter_by(course_id=cid).count()
    total_assignments = Assignment.query.filter_by(course_id=cid).count()

    if current_user.role == 'student':
        watched = WatchLog.query.join(Recording).filter(
            Recording.course_id == cid,
            WatchLog.student_id == current_user.id).count()
        subs = Submission.query.join(Assignment).filter(
            Assignment.course_id == cid,
            Submission.student_id == current_user.id).all()
        graded   = [s for s in subs if s.score is not None]
        avg      = round(sum(s.score for s in graded) / len(graded), 1) if graded else None
        pending  = total_assignments - len(subs)
        return jsonify({
            'videos_watched': watched,
            'total_recordings': total_recordings,
            'assignments_pending': max(pending, 0),
            'total_assignments': total_assignments,
            'avg_grade': avg,
            'submissions_graded': len(graded)
        })
    else:
        # Teacher view
        enrolled_count = Enrollment.query.filter_by(course_id=cid).count()
        ungraded = Submission.query.join(Assignment).filter(
            Assignment.course_id == cid,
            Submission.score == None).count()

        # Per-student progress
        enrollments = Enrollment.query.filter_by(course_id=cid).all()
        student_progress = []
        for e in enrollments:
            s = e.student
            watched = WatchLog.query.join(Recording).filter(
                Recording.course_id == cid,
                WatchLog.student_id == s.id).count()
            subs = Submission.query.join(Assignment).filter(
                Assignment.course_id == cid,
                Submission.student_id == s.id).all()
            graded = [x for x in subs if x.score is not None]
            avg = round(sum(x.score for x in graded) / len(graded), 1) if graded else None
            pct = round((watched / total_recordings * 100)) if total_recordings else 0
            student_progress.append({
                'id': s.id, 'name': s.name, 'email': s.email,
                'initials': s.initials(),
                'videos_watched': watched, 'total_recordings': total_recordings,
                'submissions': len(subs), 'total_assignments': total_assignments,
                'avg_grade': avg, 'progress_pct': pct
            })

        # Recent ungraded submissions
        recent_subs = (Submission.query
            .join(Assignment).filter(Assignment.course_id == cid)
            .filter(Submission.score == None)
            .order_by(Submission.submitted_at.desc())
            .limit(5).all())

        return jsonify({
            'enrolled_students': enrolled_count,
            'ungraded_submissions': ungraded,
            'total_recordings': total_recordings,
            'total_materials': total_materials,
            'student_progress': student_progress,
            'recent_ungraded': [s.to_dict() for s in recent_subs]
        })


# ─────────────────────────────────────────────
# SEED — create demo data (run once)
# ─────────────────────────────────────────────
def seed_demo():
    if User.query.first():
        return  # already seeded

    # Users
    teacher = User(name='Michael Chang', email='teacher@codencode.my', role='teacher')
    teacher.set_password('demo1234')

    students = []
    demo_students = [
        ('Alex Tan',    'student@codencode.my'),
        ('Jamie Lim',   'jamie@codencode.my'),
        ('Rahim Nor',   'rahim@codencode.my'),
        ('Wei Ling',    'weiling@codencode.my'),
        ('Zara Hassan', 'zara@codencode.my'),
        ('Kai Chen',    'kai@codencode.my'),
    ]
    for name, email in demo_students:
        u = User(name=name, email=email, role='student')
        u.set_password('demo1234')
        students.append(u)

    db.session.add(teacher)
    db.session.add_all(students)
    db.session.flush()

    # Courses
    python_course = Course(
        title='Python Programming Bootcamp',
        description='6-week course from beginner to advanced.', weeks=6)
    ml_course = Course(
        title='Machine Learning Fundamentals',
        description='10-week ML course.', weeks=10)
    db.session.add_all([python_course, ml_course])
    db.session.flush()

    # Enroll all students in both courses
    for s in students:
        db.session.add(Enrollment(student_id=s.id, course_id=python_course.id))
        db.session.add(Enrollment(student_id=s.id, course_id=ml_course.id))
    db.session.flush()

    # Recordings (demo — no actual files)
    sessions_data = [
        (1,1,'Intro to Python & Environment Setup','45:12'),
        (1,2,'Variables, Data Types & Operators','38:44'),
        (1,3,'Control Flow: If, Loops, Break & Continue','52:01'),
        (1,4,'Lists, Tuples, Dictionaries','41:30'),
        (2,1,'Functions Deep Dive — Args, Kwargs, Scope','58:20'),
        (2,2,'Reading & Writing Files — CSV, JSON, TXT','44:50'),
        (2,3,'Modules & Packages — pip & virtualenv','39:15'),
        (2,4,'Error Handling & Debugging','47:05'),
        (3,1,'OOP Part 1 — Classes & Objects','55:40'),
        (3,2,'OOP Part 2 — Inheritance & Polymorphism','49:30'),
        (4,1,'Pandas: DataFrames, Series, Indexing','62:05'),
        (4,2,'Data Cleaning — Nulls, Duplicates, Dtypes','55:18'),
    ]
    for wk, sn, title, dur in sessions_data:
        db.session.add(Recording(
            course_id=python_course.id, week=wk, session_num=sn,
            title=title, duration=dur, filename='demo_placeholder.mp4'))

    ml_sessions_data = [
        (1,1,'Introduction to ML & the Data Science Workflow','48:30'),
        (1,2,'NumPy Arrays & Vectorised Operations','42:15'),
        (2,1,'Pandas: DataFrames, Series & Indexing','55:10'),
        (2,2,'Data Cleaning — Nulls, Duplicates & Dtypes','50:05'),
        (3,1,'Your First Model: Linear Regression','60:20'),
        (3,2,'Model Evaluation: MSE, R², Cross-Validation','44:45'),
        (4,1,'Classification: Logistic Regression','53:00'),
        (4,2,'Decision Trees & Overfitting','47:30'),
        (5,1,'Random Forests & Ensemble Methods','58:15'),
        (5,2,'Evaluation Metrics: Precision, Recall, AUC','41:50'),
        (6,1,'Feature Engineering & Selection','56:40'),
        (6,2,'Capstone Project Kickoff & Q&A','38:00'),
    ]
    for wk, sn, title, dur in ml_sessions_data:
        db.session.add(Recording(
            course_id=ml_course.id, week=wk, session_num=sn,
            title=title, duration=dur, filename='demo_placeholder.mp4'))
    db.session.flush()

    # Materials — Python for Beginners
    py_materials_data = [
        # (week, display_title, stored_filename, file_type, file_size)
        (0, 'Lecture Slides — All 15 Sessions', 'py_slides.zip', 'zip', '2.9 MB'),
        (0, 'Python Cheat Sheet', 'py_cheat_sheet.py', 'py', '5.4 KB'),
        (1, 'Week 1 — Variables, Loops & Lists', 'py_week1_exercises.py', 'py', '3.0 KB'),
        (2, 'Week 2 — Functions', 'py_week2_exercises.py', 'py', '3.6 KB'),
        (3, 'Week 3 — OOP: Classes & Objects', 'py_week3_exercises.py', 'py', '4.8 KB'),
        (4, 'Week 4 — Files & Error Handling', 'py_week4_exercises.py', 'py', '3.9 KB'),
        (5, 'Week 5 — Modules & Pythonic Code', 'py_week5_exercises.py', 'py', '5.3 KB'),
        (6, 'Week 6 — Building Real Projects', 'py_week6_exercises.py', 'py', '8.8 KB'),
        (6, 'Week 6 — Mini Project Starter', 'py_week6_project_starter.py', 'py', '6.9 KB'),
    ]
    for wk, title, fname, ftype, fsize in py_materials_data:
        db.session.add(Material(
            course_id=python_course.id, week=wk, title=title,
            filename=fname, file_type=ftype, file_size=fsize))
    db.session.flush()

    # Materials — Machine Learning
    ml_materials_data = [
        (0, 'Lecture Slides — All 15 Sessions', 'ml_slides.zip', 'zip', '4.7 MB'),
        (0, 'ML Cheat Sheet', 'ml_cheat_sheet.py', 'py', '4.6 KB'),
        (1, 'Week 1 — NumPy Fundamentals', 'ml_week1_exercises.py', 'py', '4.3 KB'),
        (2, 'Week 2 — Pandas Data Wrangling', 'ml_week2_exercises.py', 'py', '4.7 KB'),
        (3, 'Week 3 — Your First ML Model', 'ml_week3_exercises.py', 'py', '4.7 KB'),
        (4, 'Week 4 — Classification', 'ml_week4_exercises.py', 'py', '4.5 KB'),
        (5, 'Week 5 — Random Forest & Evaluation', 'ml_week5_exercises.py', 'py', '4.9 KB'),
        (6, 'Week 6 — Feature Engineering', 'ml_week6_feature_engineering.py', 'py', '6.3 KB'),
        (6, 'Week 6 — Capstone Project Starter', 'ml_week6_capstone.py', 'py', '7.6 KB'),
    ]
    for wk, title, fname, ftype, fsize in ml_materials_data:
        db.session.add(Material(
            course_id=ml_course.id, week=wk, title=title,
            filename=fname, file_type=ftype, file_size=fsize))
    db.session.flush()

    # Assignments — Python for Beginners
    from datetime import timedelta
    now = datetime.utcnow()
    py_assignments_data = [
        (2, 'Assignment 1 — My Digital Life in Python',
         'Build a Python script that captures and displays your digital life stats.',
         'py_assignment1.py', now+timedelta(days=-20)),
        (4, 'Assignment 2 — Build a Mini Contact Book',
         'Create a command-line contact book with add, search, update and delete.',
         'py_assignment2.py', now+timedelta(days=10)),
    ]
    asgn_objs = []
    for wk, title, desc, brief, due in py_assignments_data:
        a = Assignment(course_id=python_course.id, week=wk, title=title,
                       description=desc, brief_file=brief, due_date=due, max_points=100)
        db.session.add(a)
        asgn_objs.append(a)
    db.session.flush()

    # Assignments — Machine Learning
    ml_assignments_data = [
        (3, 'Assignment 1 — Predict Who Passes the Course',
         'Use a classification model to predict student pass/fail outcomes.',
         'ml_assignment1.py', now+timedelta(days=-10)),
        (6, 'Assignment 2 — JB House Price Predictor',
         'Build a regression model to predict house prices in Johor Bahru.',
         'ml_assignment2.py', now+timedelta(days=14)),
    ]
    ml_asgn_objs = []
    for wk, title, desc, brief, due in ml_assignments_data:
        a = Assignment(course_id=ml_course.id, week=wk, title=title,
                       description=desc, brief_file=brief, due_date=due, max_points=100)
        db.session.add(a)
        ml_asgn_objs.append(a)
    db.session.flush()

    # Submissions & grades — Python Assignment 1 (graded for all students)
    py_a1_grades = {0: 80, 1: 95, 2: 60, 3: 75, 4: 88, 5: 92}
    for si, score in py_a1_grades.items():
        db.session.add(Submission(
            assignment_id=asgn_objs[0].id,
            student_id=students[si].id,
            filename='assignment1_submission.py',
            notes='',
            submitted_at=now + timedelta(days=-18+si),
            score=score,
            feedback='Good work!' if score >= 80 else 'Needs improvement.',
            graded_at=now + timedelta(days=-15)
        ))

    # Python Assignment 2 — some submitted, not yet graded
    for si in range(4):
        db.session.add(Submission(
            assignment_id=asgn_objs[1].id,
            student_id=students[si].id,
            filename='assignment2_submission.py',
            submitted_at=now + timedelta(days=-3+si)
        ))

    # ML Assignment 1 — graded
    ml_a1_grades = {0: 78, 1: 90, 2: 55, 3: 82, 4: 91, 5: 96}
    for si, score in ml_a1_grades.items():
        db.session.add(Submission(
            assignment_id=ml_asgn_objs[0].id,
            student_id=students[si].id,
            filename='ml_assignment1_submission.py',
            notes='',
            submitted_at=now + timedelta(days=-8+si),
            score=score,
            feedback='Good work!' if score >= 80 else 'Needs improvement.',
            graded_at=now + timedelta(days=-6)
        ))

    # Watch logs — Alex watched first 18, others vary
    recs = Recording.query.filter_by(course_id=python_course.id).all()
    watch_map = {0:18, 1:22, 2:11, 3:16, 4:20, 5:24}
    for si, count in watch_map.items():
        for rec in recs[:min(count, len(recs))]:
            db.session.add(WatchLog(student_id=students[si].id, recording_id=rec.id))

    db.session.commit()
    print('✓ Demo data seeded')


# ─────────────────────────────────────────────
# Init DB & run
# ─────────────────────────────────────────────
with app.app_context():
    db.create_all()
    seed_demo()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
