"""
codencode.my LMS — Flask Backend
=================================
  - Single app.py  (no blueprints needed at this scale)
  - SQLAlchemy ORM + PostgreSQL (falls back to SQLite for local dev)
  - Flask-Login for session auth
  - All file uploads go to /uploads on disk
  - JSON API consumed by the frontend
  - Roles: student | teacher | admin
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
                    WatchLog, Material, Assignment, Submission, Attendance,
                    TimetableSession)

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
app = Flask(__name__, static_folder='static', template_folder='templates')

# Railway supplies DATABASE_URL as "postgres://…" but SQLAlchemy 2.x requires "postgresql://…"
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///codencode_lms.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'db9564268b5109bb02c25a568feaaeb8f'),
    SQLALCHEMY_DATABASE_URI=_db_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=os.path.join(os.path.dirname(__file__), 'uploads'),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024 * 1024,
    ALLOWED_VIDEO={'mp4', 'mov', 'mkv', 'webm'},
    ALLOWED_MATERIAL={'pdf', 'py', 'ipynb', 'zip', 'csv', 'txt', 'docx'},
    ALLOWED_SUBMISSION={'py', 'ipynb', 'zip', 'pdf', 'txt'},
    ALLOWED_RECEIPT={'pdf', 'jpg', 'jpeg', 'png', 'heic'},
)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'serve_frontend'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'receipts'), exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def allowed(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def save_upload(file, subfolder, allowed_set):
    if not file or file.filename == '':
        raise ValueError('No file provided')
    if not allowed(file.filename, allowed_set):
        raise ValueError(f'File type not allowed. Allowed: {allowed_set}')
    ext = file.filename.rsplit('.', 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(dest, exist_ok=True)
    file.save(os.path.join(dest, stored_name))
    return stored_name, file.filename


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
        if current_user.role not in ('teacher', 'admin'):
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


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != 'admin':
            return jsonify({'error': 'Admins only'}), 403
        return f(*args, **kwargs)
    return wrapper


def enrolled_or_staff(course_id):
    """Return True if current user is teacher, admin, or enrolled student."""
    if current_user.role in ('teacher', 'admin'):
        return True
    return Enrollment.query.filter_by(
        student_id=current_user.id, course_id=course_id).first() is not None


# Keep old name as alias for backwards compat
enrolled_or_teacher = enrolled_or_staff


# ─────────────────────────────────────────────
# Serve frontends
# ─────────────────────────────────────────────
@app.route('/')
@app.route('/lms')
def serve_frontend():
    return send_from_directory('templates', 'lms.html')


@app.route('/admin')
@login_required
def serve_admin():
    if current_user.role != 'admin':
        return send_from_directory('templates', 'lms.html')
    return send_from_directory('templates', 'admin.html')


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
    if current_user.role in ('teacher', 'admin'):
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
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    course = Course.query.get_or_404(cid)
    recs = Recording.query.filter_by(course_id=cid).order_by(
        Recording.week, Recording.session_num).all()

    # Gate by current_week for students
    if current_user.role == 'student':
        recs = [r for r in recs if r.week <= course.current_week]
        watched_ids = {w.recording_id for w in
                       WatchLog.query.filter_by(student_id=current_user.id).all()}
        data = [r.to_dict(watched=r.id in watched_ids) for r in recs]
    else:
        data = [r.to_dict() for r in recs]

    weeks = {}
    for r in data:
        w = r['week']
        weeks.setdefault(w, []).append(r)
    return jsonify({'weeks': weeks, 'current_week': course.current_week})


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
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    course = Course.query.get_or_404(cid)
    mats = Material.query.filter_by(course_id=cid).order_by(
        Material.week, Material.uploaded_at).all()

    # Gate by current_week for students: week 0 (general) always visible
    if current_user.role == 'student':
        mats = [m for m in mats if m.week == 0 or m.week <= course.current_week]

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


@app.route('/uploads/briefs/<path:filename>')
@login_required
def serve_brief(filename):
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'briefs'),
        filename, as_attachment=True)


# ─────────────────────────────────────────────
# ASSIGNMENTS
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/assignments')
@login_required
def api_assignments(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    course = Course.query.get_or_404(cid)
    assignments = Assignment.query.filter_by(course_id=cid).order_by(
        Assignment.week).all()

    # Gate by current_week for students
    if current_user.role == 'student':
        assignments = [a for a in assignments if a.week <= course.current_week]
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
        for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d'):
            try:
                due_date = datetime.strptime(due_str, fmt)
                break
            except ValueError:
                continue

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
    existing = Submission.query.filter_by(
        assignment_id=aid, student_id=current_user.id).first()

    try:
        stored, original = save_upload(
            request.files.get('file'), 'submissions',
            app.config['ALLOWED_SUBMISSION'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if existing:
        old = os.path.join(app.config['UPLOAD_FOLDER'], 'submissions', existing.filename)
        if os.path.exists(old):
            os.remove(old)
        existing.filename     = stored
        existing.notes        = request.form.get('notes', '')
        existing.submitted_at = datetime.utcnow()
        existing.score        = None
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
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    total_recordings  = Recording.query.filter_by(course_id=cid).count()
    total_materials   = Material.query.filter_by(course_id=cid).count()
    total_assignments = Assignment.query.filter_by(course_id=cid).count()

    if current_user.role == 'student':
        watched = WatchLog.query.join(Recording).filter(
            Recording.course_id == cid,
            WatchLog.student_id == current_user.id).count()
        subs = Submission.query.join(Assignment).filter(
            Assignment.course_id == cid,
            Submission.student_id == current_user.id).all()
        graded  = [s for s in subs if s.score is not None]
        avg     = round(sum(s.score for s in graded) / len(graded), 1) if graded else None
        pending = total_assignments - len(subs)

        # Build recent activity feed
        activity = []
        recent_recordings = (Recording.query.filter_by(course_id=cid)
            .order_by(Recording.uploaded_at.desc()).limit(3).all())
        for r in recent_recordings:
            activity.append({'type': 'cyan', 'text': f'<strong>{r.title}</strong> — video uploaded',
                             'time': r.uploaded_at.strftime('%b %d, %Y')})
        recent_materials = (Material.query.filter_by(course_id=cid)
            .order_by(Material.uploaded_at.desc()).limit(2).all())
        for m in recent_materials:
            activity.append({'type': 'purple', 'text': f'New material: <strong>{m.title}</strong> added',
                             'time': m.uploaded_at.strftime('%b %d, %Y')})
        for s in sorted(graded, key=lambda x: x.graded_at or x.submitted_at, reverse=True)[:3]:
            activity.append({'type': 'green',
                             'text': f'<strong>{s.assignment.title}</strong> graded — {s.score}/{s.assignment.max_points}',
                             'time': (s.graded_at or s.submitted_at).strftime('%b %d, %Y')})
        activity.sort(key=lambda x: x['time'], reverse=True)

        return jsonify({
            'videos_watched': watched,
            'total_recordings': total_recordings,
            'assignments_pending': max(pending, 0),
            'total_assignments': total_assignments,
            'assignments_submitted': len(subs),
            'avg_grade': avg,
            'submissions_graded': len(graded),
            'recent_activity': activity[:5]
        })
    else:
        enrolled_count = Enrollment.query.filter_by(course_id=cid).count()
        ungraded = Submission.query.join(Assignment).filter(
            Assignment.course_id == cid,
            Submission.score == None).count()

        enrollments = Enrollment.query.filter_by(course_id=cid).all()
        student_progress = []
        for e in enrollments:
            s = e.student
            watched = WatchLog.query.join(Recording).filter(
                Recording.course_id == cid,
                WatchLog.student_id == s.id).count()
            subs   = Submission.query.join(Assignment).filter(
                Assignment.course_id == cid,
                Submission.student_id == s.id).all()
            graded = [x for x in subs if x.score is not None]
            avg    = round(sum(x.score for x in graded) / len(graded), 1) if graded else None
            pct    = round((watched / total_recordings * 100)) if total_recordings else 0
            student_progress.append({
                'id': s.id, 'name': s.name, 'email': s.email,
                'initials': s.initials(),
                'videos_watched': watched, 'total_recordings': total_recordings,
                'submissions': len(subs), 'total_assignments': total_assignments,
                'avg_grade': avg, 'progress_pct': pct
            })

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


# ═════════════════════════════════════════════
# ADMIN API
# ═════════════════════════════════════════════

# ── Students ──────────────────────────────────
@app.route('/api/admin/students', methods=['GET'])
@admin_required
def admin_list_students():
    students = User.query.filter_by(role='student').order_by(User.name).all()
    result = []
    for s in students:
        d = s.to_dict()
        d['enrollments'] = [e.to_dict() for e in s.enrollments]
        result.append(d)
    return jsonify(result)


@app.route('/api/admin/students', methods=['POST'])
@admin_required
def admin_create_student():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    if not email or not data.get('name'):
        return jsonify({'error': 'name and email are required'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 409

    u = User(
        name      = data['name'].strip(),
        email     = email,
        role      = 'student',
        phone     = data.get('phone', '').strip(),
        ic_number = data.get('ic_number', '').strip()
    )
    u.set_password(data.get('password', 'codencode123'))
    db.session.add(u)
    db.session.commit()
    return jsonify({'student': u.to_dict()}), 201


@app.route('/api/admin/students/<int:uid>', methods=['GET'])
@admin_required
def admin_get_student(uid):
    s = User.query.get_or_404(uid)
    d = s.to_dict()
    d['enrollments'] = [e.to_dict() for e in s.enrollments]
    return jsonify(d)


@app.route('/api/admin/students/<int:uid>', methods=['PUT'])
@admin_required
def admin_update_student(uid):
    s = User.query.get_or_404(uid)
    data = request.get_json()
    if 'name'      in data: s.name      = data['name'].strip()
    if 'phone'     in data: s.phone     = data['phone'].strip()
    if 'ic_number' in data: s.ic_number = data['ic_number'].strip()
    if 'email'     in data:
        new_email = data['email'].strip().lower()
        existing  = User.query.filter_by(email=new_email).first()
        if existing and existing.id != uid:
            return jsonify({'error': 'Email already in use'}), 409
        s.email = new_email
    if 'password'  in data and data['password']:
        s.set_password(data['password'])
    db.session.commit()
    return jsonify({'student': s.to_dict()})


# ── Enrollments ───────────────────────────────
@app.route('/api/admin/students/<int:uid>/enroll', methods=['POST'])
@admin_required
def admin_enroll_student(uid):
    data      = request.get_json()
    course_id = data.get('course_id')
    if not course_id:
        return jsonify({'error': 'course_id required'}), 400

    existing = Enrollment.query.filter_by(student_id=uid, course_id=course_id).first()
    if existing:
        return jsonify({'error': 'Already enrolled'}), 409

    e = Enrollment(
        student_id      = uid,
        course_id       = course_id,
        payment_status  = data.get('payment_status', 'pending'),
        payment_remarks = data.get('payment_remarks', '')
    )
    db.session.add(e)
    db.session.commit()
    return jsonify({'enrollment': e.to_dict()}), 201


@app.route('/api/admin/enrollments/<int:eid>', methods=['DELETE'])
@admin_required
def admin_unenroll(eid):
    e = Enrollment.query.get_or_404(eid)
    db.session.delete(e)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/enrollments/<int:eid>/payment', methods=['PUT'])
@admin_required
def admin_update_payment(eid):
    e    = Enrollment.query.get_or_404(eid)
    data = request.get_json()
    if 'payment_status'  in data: e.payment_status  = data['payment_status']
    if 'payment_remarks' in data: e.payment_remarks = data['payment_remarks']
    db.session.commit()
    return jsonify({'enrollment': e.to_dict()})


@app.route('/api/admin/enrollments/<int:eid>/receipt', methods=['POST'])
@admin_required
def admin_upload_receipt(eid):
    e = Enrollment.query.get_or_404(eid)
    try:
        stored, _ = save_upload(
            request.files.get('file'), 'receipts',
            app.config['ALLOWED_RECEIPT'])
    except ValueError as ex:
        return jsonify({'error': str(ex)}), 400
    # Delete old receipt if one exists
    if e.receipt_file:
        old = os.path.join(app.config['UPLOAD_FOLDER'], 'receipts', e.receipt_file)
        if os.path.exists(old):
            os.remove(old)
    e.receipt_file = stored
    db.session.commit()
    return jsonify({'enrollment': e.to_dict()})


@app.route('/uploads/receipts/<path:filename>')
@login_required
def serve_receipt(filename):
    if current_user.role not in ('admin', 'teacher'):
        return jsonify({'error': 'Forbidden'}), 403
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'receipts'),
        filename, as_attachment=True)


@app.route('/api/admin/enrollments/<int:eid>/invoice')
@admin_required
def admin_invoice(eid):
    """Return a printable HTML invoice page."""
    e = Enrollment.query.get_or_404(eid)
    s = e.student
    c = e.course
    inv_num = f'INV-{e.id:05d}'
    issued  = datetime.utcnow().strftime('%d %B %Y')
    enr_date = e.enrolled_at.strftime('%d %B %Y')

    status_colour = {'paid': '#28ca41', 'pending': '#e3b341', 'overdue': '#f85149'}.get(
        e.payment_status, '#7d8590')

    receipt_html = ''
    if e.receipt_file:
        receipt_html = f'<p><strong>Receipt File:</strong> <a href="/uploads/receipts/{e.receipt_file}" target="_blank">View Receipt</a></p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{inv_num} — codencode.my</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Mono:wght@400;700&display=swap');
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:'Space Mono',monospace; background:#fff; color:#111; font-size:13px; padding:40px; max-width:720px; margin:auto; }}
    .header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:40px; border-bottom:3px solid #00dcb4; padding-bottom:24px; }}
    .brand {{ font-family:'Syne',sans-serif; font-size:28px; font-weight:800; color:#080c10; letter-spacing:-1px; }}
    .brand span {{ color:#00dcb4; }}
    .inv-meta {{ text-align:right; }}
    .inv-num {{ font-size:18px; font-weight:700; color:#080c10; }}
    .inv-date {{ color:#555; margin-top:4px; }}
    .section {{ margin-bottom:28px; }}
    .section-title {{ font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#888; margin-bottom:10px; border-bottom:1px solid #eee; padding-bottom:6px; }}
    .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
    p {{ margin:5px 0; line-height:1.6; }}
    strong {{ color:#080c10; }}
    .status-badge {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#fff; background:{status_colour}; }}
    .footer {{ margin-top:48px; padding-top:20px; border-top:1px solid #eee; font-size:11px; color:#888; text-align:center; }}
    @media print {{
      body {{ padding:20px; }}
      .no-print {{ display:none !important; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <div class="brand">code<span>ncode</span>.my</div>
      <div style="color:#555;margin-top:4px;font-size:12px">Learning Management System</div>
    </div>
    <div class="inv-meta">
      <div class="inv-num">{inv_num}</div>
      <div class="inv-date">Issued: {issued}</div>
    </div>
  </div>

  <div class="grid-2">
    <div class="section">
      <div class="section-title">Bill To</div>
      <p><strong>{s.name}</strong></p>
      <p>{s.email}</p>
      {'<p>' + s.phone + '</p>' if s.phone else ''}
      {'<p>IC/Passport: ' + s.ic_number + '</p>' if s.ic_number else ''}
    </div>
    <div class="section">
      <div class="section-title">Course</div>
      <p><strong>{c.title}</strong></p>
      <p>Duration: {c.weeks} weeks</p>
      <p>Enrolled: {enr_date}</p>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Payment Details</div>
    <p><strong>Status:</strong> <span class="status-badge">{e.payment_status.upper()}</span></p>
    {'<p><strong>Remarks:</strong> ' + (e.payment_remarks or '—') + '</p>'}
    {receipt_html}
  </div>

  <div class="footer">
    <p>codencode.my · {inv_num} · Generated {issued}</p>
    <p style="margin-top:4px">Thank you for learning with us!</p>
  </div>

  <div class="no-print" style="margin-top:32px;text-align:center">
    <button onclick="window.print()" style="background:#00dcb4;color:#080c10;border:none;padding:10px 28px;border-radius:6px;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer;">
      🖨 Print / Save as PDF
    </button>
    <button onclick="window.close()" style="background:#eee;color:#333;border:none;padding:10px 24px;border-radius:6px;font-family:inherit;font-size:13px;cursor:pointer;margin-left:8px;">
      Close
    </button>
  </div>
</body>
</html>"""
    from flask import Response
    return Response(html, mimetype='text/html')


# ── Courses ───────────────────────────────────
@app.route('/api/admin/courses', methods=['GET'])
@admin_required
def admin_list_courses():
    courses = Course.query.order_by(Course.title).all()
    result  = []
    for c in courses:
        d = c.to_dict()
        d['enrolled_count'] = Enrollment.query.filter_by(course_id=c.id).count()
        result.append(d)
    return jsonify(result)


@app.route('/api/admin/courses', methods=['POST'])
@admin_required
def admin_create_course():
    data = request.get_json()
    if not data.get('title'):
        return jsonify({'error': 'title is required'}), 400
    c = Course(
        title        = data['title'].strip(),
        description  = data.get('description', ''),
        weeks        = int(data.get('weeks', 6)),
        current_week = 1,
        start_date   = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None,
        programme    = data.get('programme', '').strip(),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({'course': c.to_dict()}), 201


@app.route('/api/admin/courses/<int:cid>/week', methods=['PUT'])
@admin_required
def admin_set_week(cid):
    c    = Course.query.get_or_404(cid)
    data = request.get_json()
    week = int(data.get('current_week', c.current_week))
    week = max(1, min(week, c.weeks))
    c.current_week = week
    db.session.commit()
    return jsonify({'course': c.to_dict()})


@app.route('/api/admin/courses/<int:cid>', methods=['PUT'])
@admin_required
def admin_update_course(cid):
    c    = Course.query.get_or_404(cid)
    data = request.get_json()
    if 'title'       in data: c.title       = data['title'].strip()
    if 'description' in data: c.description = data['description'].strip()
    if 'weeks'       in data: c.weeks       = int(data['weeks'])
    if 'programme'   in data: c.programme   = data['programme'].strip()
    if 'start_date'  in data and data['start_date']:
        c.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    elif 'start_date' in data and not data['start_date']:
        c.start_date = None
    db.session.commit()
    d = c.to_dict()
    d['enrolled_count'] = Enrollment.query.filter_by(course_id=c.id).count()
    return jsonify({'course': d})


@app.route('/api/admin/courses/<int:cid>/students', methods=['GET'])
@admin_required
def admin_course_students(cid):
    enrollments = Enrollment.query.filter_by(course_id=cid).all()
    return jsonify([e.to_dict() for e in enrollments])


# ── Materials upload (admin) ───────────────────
@app.route('/api/admin/courses/<int:cid>/materials', methods=['POST'])
@admin_required
def admin_upload_material(cid):
    try:
        stored, original = save_upload(
            request.files.get('file'), 'materials',
            app.config['ALLOWED_MATERIAL'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    ext   = original.rsplit('.', 1)[1].lower() if '.' in original else ''
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


@app.route('/api/admin/materials/<int:mid>', methods=['DELETE'])
@admin_required
def admin_delete_material(mid):
    mat   = Material.query.get_or_404(mid)
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'materials', mat.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(mat)
    db.session.commit()
    return jsonify({'ok': True})


# ── Attendance ────────────────────────────────
@app.route('/api/admin/courses/<int:cid>/attendance', methods=['GET'])
@admin_required
def admin_get_attendance(cid):
    course      = Course.query.get_or_404(cid)
    enrollments = Enrollment.query.filter_by(course_id=cid).all()
    records     = Attendance.query.filter_by(course_id=cid).all()

    # Index by (student_id, week)
    att_map = {(a.student_id, a.week): a for a in records}

    students_data = []
    for e in enrollments:
        s = e.student
        weeks_data = {}
        for w in range(1, course.current_week + 1):
            att = att_map.get((s.id, w))
            weeks_data[str(w)] = att.status if att else 'absent'
        students_data.append({
            'student_id':   s.id,
            'student_name': s.name,
            'weeks':        weeks_data
        })

    return jsonify({
        'course_id':    cid,
        'current_week': course.current_week,
        'students':     students_data
    })


@app.route('/api/admin/courses/<int:cid>/attendance', methods=['POST'])
@admin_required
def admin_set_attendance(cid):
    data       = request.get_json()
    student_id = data.get('student_id')
    week       = data.get('week')
    status     = data.get('status', 'present')
    notes      = data.get('notes', '')

    if not student_id or not week:
        return jsonify({'error': 'student_id and week required'}), 400
    if status not in ('present', 'absent', 'late'):
        return jsonify({'error': 'status must be present/absent/late'}), 400

    att = Attendance.query.filter_by(
        student_id=student_id, course_id=cid, week=week).first()
    if att:
        att.status      = status
        att.notes       = notes
        att.recorded_at = datetime.utcnow()
    else:
        att = Attendance(student_id=student_id, course_id=cid,
                         week=week, status=status, notes=notes)
        db.session.add(att)
    db.session.commit()
    return jsonify({'attendance': att.to_dict()})


# ── Bulk attendance (whole week at once) ──────
@app.route('/api/admin/courses/<int:cid>/attendance/bulk', methods=['POST'])
@admin_required
def admin_bulk_attendance(cid):
    """Expects { week: int, records: [{student_id, status, notes}] }"""
    data    = request.get_json()
    week    = data.get('week')
    records = data.get('records', [])
    if not week:
        return jsonify({'error': 'week required'}), 400

    for r in records:
        sid    = r.get('student_id')
        status = r.get('status', 'absent')
        notes  = r.get('notes', '')
        att    = Attendance.query.filter_by(
            student_id=sid, course_id=cid, week=week).first()
        if att:
            att.status      = status
            att.notes       = notes
            att.recorded_at = datetime.utcnow()
        else:
            att = Attendance(student_id=sid, course_id=cid,
                             week=week, status=status, notes=notes)
            db.session.add(att)
    db.session.commit()
    return jsonify({'ok': True, 'updated': len(records)})


# ── Payment overview ──────────────────────────
@app.route('/api/admin/payments', methods=['GET'])
@admin_required
def admin_payments():
    enrollments = Enrollment.query.all()
    return jsonify([e.to_dict() for e in enrollments])


# ─────────────────────────────────────────────
# RESET ADMIN (one-time recovery route)
# ─────────────────────────────────────────────
@app.route('/api/reset-admin')
def reset_admin():
    secret = request.args.get('secret', '')
    if secret != 'codencode-reset-2026':
        return jsonify({'error': 'forbidden'}), 403
    admin = User.query.filter_by(email='admin@codencode.my').first()
    if not admin:
        admin = User(name='Admin', email='admin@codencode.my', role='admin',
                     phone='010-0000000', ic_number='')
        db.session.add(admin)
    admin.set_password('admin1234')
    db.session.commit()
    return jsonify({'ok': True, 'email': 'admin@codencode.my', 'password': 'admin1234'})


# ─────────────────────────────────────────────
# SEED
# ─────────────────────────────────────────────
def seed_demo():
    if User.query.first():
        return

    from datetime import timedelta
    now = datetime.utcnow()

    # ── Users ──────────────────────────────────
    admin = User(name='Admin', email='admin@codencode.my', role='admin',
                 phone='010-0000000', ic_number='')
    admin.set_password('admin1234')

    teacher = User(name='Michael Chang', email='teacher@codencode.my', role='teacher',
                   phone='011-2345678', ic_number='')
    teacher.set_password('demo1234')

    demo_students = [
        ('Alex Tan',    'student@codencode.my', '012-3456789', '900101-14-1234'),
        ('Jamie Lim',   'jamie@codencode.my',   '013-4567890', '950215-10-5678'),
        ('Rahim Nor',   'rahim@codencode.my',   '014-5678901', '980320-08-9012'),
        ('Wei Ling',    'weiling@codencode.my', '016-6789012', '910712-04-3456'),
        ('Zara Hassan', 'zara@codencode.my',    '017-7890123', '970825-12-7890'),
        ('Kai Chen',    'kai@codencode.my',     '018-8901234', '930930-02-2345'),
    ]
    students = []
    for name, email, phone, ic in demo_students:
        u = User(name=name, email=email, role='student', phone=phone, ic_number=ic)
        u.set_password('demo1234')
        students.append(u)

    db.session.add_all([admin, teacher] + students)
    db.session.flush()

    # ── Courses ────────────────────────────────
    python_course = Course(
        title='Python Programming Bootcamp',
        description='6-week hands-on Python course from beginner to advanced.',
        weeks=6, current_week=3, programme='Python Bootcamp')
    python_course.start_date = datetime(2026, 5, 8).date()
    ml_course = Course(
        title='Machine Learning Fundamentals',
        description='Practical ML: NumPy, Pandas, scikit-learn, and real projects.',
        weeks=6, current_week=2, programme='Machine Learning')
    db.session.add_all([python_course, ml_course])
    db.session.flush()

    # ── Enrollments with payment status ────────
    payment_data = {
        # student_index: (py_status, py_remarks, ml_status, ml_remarks)
        0: ('paid',    'Full payment received',        'paid',    'Full payment received'),
        1: ('paid',    'Paid via bank transfer',        'pending', 'Awaiting payment'),
        2: ('overdue', 'Payment overdue — follow up',  'overdue', 'Reminder sent 3x'),
        3: ('paid',    'Installment plan completed',   'paid',    'Paid in full'),
        4: ('pending', 'Partial payment RM200 received','pending', 'Pending balance RM300'),
        5: ('paid',    'Scholarship — full waiver',    'paid',    'Scholarship student'),
    }
    for si, (py_st, py_rm, ml_st, ml_rm) in payment_data.items():
        db.session.add(Enrollment(
            student_id=students[si].id, course_id=python_course.id,
            payment_status=py_st, payment_remarks=py_rm))
        db.session.add(Enrollment(
            student_id=students[si].id, course_id=ml_course.id,
            payment_status=ml_st, payment_remarks=ml_rm))
    db.session.flush()

    # ── Recordings ─────────────────────────────
    py_sessions = [
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
    for wk, sn, title, dur in py_sessions:
        db.session.add(Recording(
            course_id=python_course.id, week=wk, session_num=sn,
            title=title, duration=dur, filename='demo_placeholder.mp4'))

    ml_sessions = [
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
    for wk, sn, title, dur in ml_sessions:
        db.session.add(Recording(
            course_id=ml_course.id, week=wk, session_num=sn,
            title=title, duration=dur, filename='demo_placeholder.mp4'))
    db.session.flush()

    # ── Materials ──────────────────────────────
    py_materials = [
        (0, 'Lecture Slides — All Sessions', 'py_slides.zip',            'zip', '2.9 MB'),
        (0, 'Python Cheat Sheet',            'py_cheat_sheet.py',        'py',  '5.4 KB'),
        (1, 'Week 1 — Variables, Loops & Lists', 'py_week1_exercises.py','py',  '3.0 KB'),
        (2, 'Week 2 — Functions',            'py_week2_exercises.py',    'py',  '3.6 KB'),
        (3, 'Week 3 — OOP: Classes & Objects','py_week3_exercises.py',   'py',  '4.8 KB'),
        (4, 'Week 4 — Files & Error Handling','py_week4_exercises.py',   'py',  '3.9 KB'),
        (5, 'Week 5 — Modules & Pythonic Code','py_week5_exercises.py',  'py',  '5.3 KB'),
        (6, 'Week 6 — Building Real Projects','py_week6_exercises.py',   'py',  '8.8 KB'),
        (6, 'Week 6 — Mini Project Starter', 'py_week6_project_starter.py','py','6.9 KB'),
    ]
    for wk, title, fname, ftype, fsize in py_materials:
        db.session.add(Material(course_id=python_course.id, week=wk,
            title=title, filename=fname, file_type=ftype, file_size=fsize))

    ml_materials = [
        (0, 'Lecture Slides — All Sessions',   'ml_slides.zip',                 'zip', '4.7 MB'),
        (0, 'ML Cheat Sheet',                  'ml_cheat_sheet.py',             'py',  '4.6 KB'),
        (1, 'Week 1 — NumPy Fundamentals',     'ml_week1_exercises.py',         'py',  '4.3 KB'),
        (2, 'Week 2 — Pandas Data Wrangling',  'ml_week2_exercises.py',         'py',  '4.7 KB'),
        (3, 'Week 3 — Your First ML Model',    'ml_week3_exercises.py',         'py',  '4.7 KB'),
        (4, 'Week 4 — Classification',         'ml_week4_exercises.py',         'py',  '4.5 KB'),
        (5, 'Week 5 — Random Forest & Eval',   'ml_week5_exercises.py',         'py',  '4.9 KB'),
        (6, 'Week 6 — Feature Engineering',    'ml_week6_feature_engineering.py','py', '6.3 KB'),
        (6, 'Week 6 — Capstone Starter',       'ml_week6_capstone.py',          'py',  '7.6 KB'),
    ]
    for wk, title, fname, ftype, fsize in ml_materials:
        db.session.add(Material(course_id=ml_course.id, week=wk,
            title=title, filename=fname, file_type=ftype, file_size=fsize))
    db.session.flush()

    # ── Assignments ────────────────────────────
    py_assignments = [
        (2, 'Assignment 1 — My Digital Life in Python',
         'Build a Python script that captures and displays your digital life stats.',
         'py_assignment1.py', now + timedelta(days=-20)),
        (4, 'Assignment 2 — Build a Mini Contact Book',
         'Create a command-line contact book with add, search, update and delete.',
         'py_assignment2.py', now + timedelta(days=10)),
    ]
    asgn_objs = []
    for wk, title, desc, brief, due in py_assignments:
        a = Assignment(course_id=python_course.id, week=wk, title=title,
                       description=desc, brief_file=brief, due_date=due, max_points=100)
        db.session.add(a)
        asgn_objs.append(a)

    ml_assignments = [
        (3, 'Assignment 1 — Predict Who Passes the Course',
         'Use a classification model to predict student pass/fail outcomes.',
         'ml_assignment1.py', now + timedelta(days=-10)),
        (6, 'Assignment 2 — JB House Price Predictor',
         'Build a regression model to predict house prices in Johor Bahru.',
         'ml_assignment2.py', now + timedelta(days=14)),
    ]
    ml_asgn_objs = []
    for wk, title, desc, brief, due in ml_assignments:
        a = Assignment(course_id=ml_course.id, week=wk, title=title,
                       description=desc, brief_file=brief, due_date=due, max_points=100)
        db.session.add(a)
        ml_asgn_objs.append(a)
    db.session.flush()

    # ── Submissions & Grades ───────────────────
    py_a1_grades = {0:80, 1:95, 2:60, 3:75, 4:88, 5:92}
    for si, score in py_a1_grades.items():
        db.session.add(Submission(
            assignment_id=asgn_objs[0].id, student_id=students[si].id,
            filename='assignment1_submission.py', notes='',
            submitted_at=now + timedelta(days=-18+si),
            score=score,
            feedback='Good work!' if score >= 80 else 'Needs improvement.',
            graded_at=now + timedelta(days=-15)))

    for si in range(4):
        db.session.add(Submission(
            assignment_id=asgn_objs[1].id, student_id=students[si].id,
            filename='assignment2_submission.py',
            submitted_at=now + timedelta(days=-3+si)))

    ml_a1_grades = {0:78, 1:90, 2:55, 3:82, 4:91, 5:96}
    for si, score in ml_a1_grades.items():
        db.session.add(Submission(
            assignment_id=ml_asgn_objs[0].id, student_id=students[si].id,
            filename='ml_assignment1_submission.py', notes='',
            submitted_at=now + timedelta(days=-8+si),
            score=score,
            feedback='Good work!' if score >= 80 else 'Needs improvement.',
            graded_at=now + timedelta(days=-6)))

    # ── Watch logs ─────────────────────────────
    recs = Recording.query.filter_by(course_id=python_course.id).all()
    watch_map = {0:8, 1:10, 2:5, 3:7, 4:9, 5:10}
    for si, count in watch_map.items():
        for rec in recs[:min(count, len(recs))]:
            db.session.add(WatchLog(student_id=students[si].id, recording_id=rec.id))

    # ── Attendance ─────────────────────────────
    # Python course: weeks 1–3; ML course: weeks 1–2
    py_att = [
        # (student_index, week, status)
        (0,1,'present'),(0,2,'present'),(0,3,'present'),
        (1,1,'present'),(1,2,'present'),(1,3,'late'),
        (2,1,'absent'), (2,2,'present'),(2,3,'absent'),
        (3,1,'present'),(3,2,'late'),   (3,3,'present'),
        (4,1,'present'),(4,2,'present'),(4,3,'present'),
        (5,1,'present'),(5,2,'present'),(5,3,'present'),
    ]
    for si, wk, status in py_att:
        db.session.add(Attendance(
            student_id=students[si].id, course_id=python_course.id,
            week=wk, status=status))

    ml_att = [
        (0,1,'present'),(0,2,'present'),
        (1,1,'present'),(1,2,'present'),
        (2,1,'late'),   (2,2,'absent'),
        (3,1,'present'),(3,2,'present'),
        (4,1,'present'),(4,2,'late'),
        (5,1,'present'),(5,2,'present'),
    ]
    for si, wk, status in ml_att:
        db.session.add(Attendance(
            student_id=students[si].id, course_id=ml_course.id,
            week=wk, status=status))

    db.session.commit()
    print('✓ Demo data seeded')


# ─────────────────────────────────────────────
# TIMETABLE
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/timetable')
@login_required
def api_get_timetable(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403
    from datetime import timedelta, date as date_type
    course = Course.query.get_or_404(cid)
    sessions_db = {(s.week, s.session_num): s
                   for s in TimetableSession.query.filter_by(course_id=cid).all()}
    # Fixed weekly schedule
    SCHEDULE = [
        (1, 'Friday',   '8:00 PM',  '10:00 PM', 0),
        (2, 'Saturday', '9:00 AM',  '11:00 AM', 1),
        (3, 'Sunday',   '9:00 AM',  '11:00 AM', 2),
    ]
    today = date_type.today()
    weeks = []
    for w in range(1, course.weeks + 1):
        sessions = []
        for snum, day_name, t_start, t_end, day_offset in SCHEDULE:
            if course.start_date:
                sd = course.start_date + timedelta(weeks=w - 1, days=day_offset)
                date_str  = sd.strftime('%d %b %Y')
                is_past   = sd < today
                is_today  = sd == today
            else:
                date_str  = None
                is_past   = False
                is_today  = False
            db_s = sessions_db.get((w, snum))
            sessions.append({
                'session_num': snum,
                'day':        day_name,
                'date':       date_str,
                'time_start': t_start,
                'time_end':   t_end,
                'topic':      db_s.topic if db_s else None,
                'notes':      db_s.notes if db_s else None,
                'is_past':    is_past,
                'is_today':   is_today,
            })
        weeks.append({'week': w, 'sessions': sessions})
    return jsonify({'weeks': weeks, 'current_week': course.current_week,
                    'start_date': course.start_date.strftime('%Y-%m-%d') if course.start_date else None})


@app.route('/api/courses/<int:cid>/timetable', methods=['PUT'])
@login_required
def api_save_timetable_session(cid):
    if current_user.role not in ('teacher', 'admin'):
        return jsonify({'error': 'Teachers only'}), 403
    data    = request.get_json()
    week    = data.get('week')
    snum    = data.get('session_num')
    topic   = (data.get('topic')   or '').strip()
    notes   = (data.get('notes')   or '').strip()
    s = TimetableSession.query.filter_by(course_id=cid, week=week, session_num=snum).first()
    if s:
        s.topic = topic; s.notes = notes
    else:
        s = TimetableSession(course_id=cid, week=week, session_num=snum, topic=topic, notes=notes)
        db.session.add(s)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/courses/<int:cid>/start_date', methods=['PUT'])
@login_required
def api_set_start_date(cid):
    if current_user.role not in ('teacher', 'admin'):
        return jsonify({'error': 'Teachers only'}), 403
    data     = request.get_json()
    date_str = data.get('start_date', '')
    course   = Course.query.get_or_404(cid)
    if date_str:
        course.start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        db.session.commit()
    return jsonify({'ok': True, 'start_date': date_str})


# ─────────────────────────────────────────────
# Init DB & run
# ─────────────────────────────────────────────
with app.app_context():
    db.create_all()
    # Safe column migrations (SQLite doesn't support ALTER TABLE ADD IF NOT EXISTS)
    from sqlalchemy import text, inspect as sa_inspect
    try:
        insp = sa_inspect(db.engine)
        existing = {c['name'] for c in insp.get_columns('enrollments')}
        with db.engine.connect() as conn:
            if 'receipt_file' not in existing:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN receipt_file VARCHAR(300)'))
                conn.commit()
    except Exception:
        pass
    try:
        insp2 = sa_inspect(db.engine)
        course_cols = {c['name'] for c in insp2.get_columns('courses')}
        with db.engine.connect() as conn:
            if 'start_date' not in course_cols:
                conn.execute(text('ALTER TABLE courses ADD COLUMN start_date DATE'))
                conn.commit()
    except Exception:
        pass
    try:
        insp3 = sa_inspect(db.engine)
        course_cols2 = {c['name'] for c in insp3.get_columns('courses')}
        with db.engine.connect() as conn:
            if 'programme' not in course_cols2:
                conn.execute(text('ALTER TABLE courses ADD COLUMN programme VARCHAR(100)'))
                conn.commit()
    except Exception:
        pass
    seed_demo()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
