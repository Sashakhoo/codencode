"""
codencode.my LMS — Simple Backend
===================================
One file. PostgreSQL via psycopg2 (raw SQL, no ORM).
File uploads saved to disk.
Session-based auth (Flask sessions).

Setup:
    pip install flask psycopg2-binary

Configure:
    Set DATABASE_URL env var, e.g.:
    export DATABASE_URL="postgresql://postgres:password@localhost:5432/codencode_lms"
    
    Or just use SQLite fallback (default, no config needed):
    Will create codencode_lms.db in current directory.

Run:
    python app_simple.py

Demo logins:
    student@codencode.my / demo1234
    teacher@codencode.my / demo1234
"""

import os, uuid, sqlite3
from datetime import datetime
from functools import wraps
from flask import (Flask, request, jsonify, session,
                   send_from_directory, send_file)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# ── /lms path prefix for Railway ─────────────────────────
# Set APP_PREFIX=/lms in Railway environment variables
# Leave blank for local dev
PREFIX = os.environ.get('APP_PREFIX', '')
if PREFIX:
    app.wsgi_app = DispatcherMiddleware(
        Response('Not Found', status=404),
        {PREFIX: app.wsgi_app}
    )

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = os.environ.get('DB_PATH', 'codencode_lms.db')

# ─────────────────────────────────────────────
# DB helpers (SQLite — swap for psycopg2 for Postgres)
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# To use PostgreSQL instead, replace get_db() with:
#
# import psycopg2, psycopg2.extras
# DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost/codencode_lms')
# def get_db():
#     conn = psycopg2.connect(DATABASE_URL)
#     conn.cursor_factory = psycopg2.extras.RealDictCursor
#     return conn

def query(sql, args=(), one=False):
    db = get_db()
    cur = db.execute(sql, args)
    rv = cur.fetchall()
    db.commit()
    db.close()
    if one:
        return dict(rv[0]) if rv else None
    return [dict(r) for r in rv]

def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    last_id = cur.lastrowid
    db.commit()
    db.close()
    return last_id

# ─────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK(role IN ('student','teacher'))
);

CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    weeks       INTEGER DEFAULT 6
);

CREATE TABLE IF NOT EXISTS enrollments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER REFERENCES users(id),
    course_id  INTEGER REFERENCES courses(id),
    UNIQUE(student_id, course_id)
);

CREATE TABLE IF NOT EXISTS recordings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id   INTEGER REFERENCES courses(id),
    week        INTEGER NOT NULL,
    session_num INTEGER NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    filename    TEXT,
    duration    TEXT,
    uploaded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS watch_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER REFERENCES users(id),
    recording_id INTEGER REFERENCES recordings(id),
    UNIQUE(student_id, recording_id)
);

CREATE TABLE IF NOT EXISTS materials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id   INTEGER REFERENCES courses(id),
    week        INTEGER DEFAULT 0,
    title       TEXT NOT NULL,
    description TEXT,
    filename    TEXT NOT NULL,
    orig_name   TEXT,
    file_type   TEXT,
    file_size   TEXT,
    uploaded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assignments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id   INTEGER REFERENCES courses(id),
    week        INTEGER NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    due_date    TEXT,
    max_points  INTEGER DEFAULT 100,
    brief_file  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS submissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id INTEGER REFERENCES assignments(id),
    student_id    INTEGER REFERENCES users(id),
    filename      TEXT NOT NULL,
    orig_name     TEXT,
    notes         TEXT,
    submitted_at  TEXT DEFAULT (datetime('now')),
    score         INTEGER,
    feedback      TEXT,
    graded_at     TEXT,
    UNIQUE(assignment_id, student_id)
);
"""

def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
    db.close()

# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return query("SELECT * FROM users WHERE id=?", [uid], one=True)

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return wrapper

def teacher_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or u['role'] != 'teacher':
            return jsonify({'error': 'Teachers only'}), 403
        return f(*args, **kwargs)
    return wrapper

# ─────────────────────────────────────────────
# File upload helper
# ─────────────────────────────────────────────

ALLOWED = {'mp4','mov','mkv','webm','pdf','py','ipynb','zip','csv','txt','docx'}

def save_file(file, subfolder):
    if not file or not file.filename:
        raise ValueError('No file')
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED:
        raise ValueError(f'File type .{ext} not allowed')
    stored = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(UPLOAD_FOLDER, subfolder)
    os.makedirs(dest, exist_ok=True)
    file.save(os.path.join(dest, stored))
    size = os.path.getsize(os.path.join(dest, stored))
    human = f"{size/1024/1024:.1f} MB" if size > 1024*1024 else f"{size//1024} KB"
    return stored, file.filename, human

# ─────────────────────────────────────────────
# Frontend
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('templates', 'lms2.html')

# ── Aliases needed by new gamified frontend ───
@app.route('/api/me')
def api_me():
    u = current_user()
    if not u:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify({'id': u['id'], 'name': u['name'],
                    'email': u['email'], 'role': u['role']})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/my-submissions')
@login_required
def my_submissions():
    u = current_user()
    subs = query("""SELECT s.*, a.title as assignment_title, a.course_id
                    FROM submissions s JOIN assignments a ON a.id=s.assignment_id
                    WHERE s.student_id=?""", [u['id']])
    return jsonify(subs)

@app.route('/api/students')
@login_required
def students_list():
    u = current_user()
    if u['role'] != 'teacher':
        return jsonify({'error': 'Forbidden'}), 403
    students = query("SELECT id, name, email FROM users WHERE role='student'")
    return jsonify(students)

# ─────────────────────────────────────────────
# AUTH routes
# ─────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json()
    u = query("SELECT * FROM users WHERE email=?",
              [d.get('email','').lower()], one=True)
    if not u or not check_password_hash(u['password_hash'], d.get('password','')):
        return jsonify({'error': 'Invalid email or password'}), 401
    session['user_id'] = u['id']
    return jsonify({'id': u['id'], 'name': u['name'],
                    'email': u['email'], 'role': u['role']})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/me')
def me():
    u = current_user()
    if not u:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify({'id': u['id'], 'name': u['name'],
                    'email': u['email'], 'role': u['role']})

# ─────────────────────────────────────────────
# COURSES
# ─────────────────────────────────────────────

@app.route('/api/courses')
@login_required
def courses():
    u = current_user()
    if u['role'] == 'teacher':
        rows = query("SELECT * FROM courses")
    else:
        rows = query("""SELECT c.* FROM courses c
                        JOIN enrollments e ON e.course_id=c.id
                        WHERE e.student_id=?""", [u['id']])
    return jsonify(rows)

# ─────────────────────────────────────────────
# RECORDINGS
# ─────────────────────────────────────────────

@app.route('/api/courses/<int:cid>/recordings')
@login_required
def get_recordings(cid):
    u = current_user()
    rows = query("SELECT * FROM recordings WHERE course_id=? ORDER BY week, session_num", [cid])
    if u['role'] == 'student':
        watched = {r['recording_id'] for r in
                   query("SELECT recording_id FROM watch_logs WHERE student_id=?", [u['id']])}
        for r in rows:
            r['watched'] = r['id'] in watched
    # group by week
    weeks = {}
    for r in rows:
        weeks.setdefault(str(r['week']), []).append(r)
    return jsonify(weeks)

@app.route('/api/courses/<int:cid>/recordings', methods=['POST'])
@teacher_required
def upload_recording(cid):
    try:
        stored, orig, _ = save_file(request.files.get('file'), 'videos')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    execute("""INSERT INTO recordings (course_id,week,session_num,title,description,filename,duration)
               VALUES (?,?,?,?,?,?,?)""",
            [cid,
             int(request.form.get('week', 1)),
             int(request.form.get('session_num', 1)),
             request.form.get('title', orig),
             request.form.get('description', ''),
             stored,
             request.form.get('duration', '')])
    return jsonify({'ok': True}), 201

@app.route('/api/recordings/<int:rid>', methods=['DELETE'])
@teacher_required
def delete_recording(rid):
    r = query("SELECT * FROM recordings WHERE id=?", [rid], one=True)
    if r and r['filename']:
        fpath = os.path.join(UPLOAD_FOLDER, 'videos', r['filename'])
        if os.path.exists(fpath): os.remove(fpath)
    execute("DELETE FROM recordings WHERE id=?", [rid])
    return jsonify({'ok': True})

@app.route('/api/recordings/<int:rid>/watch', methods=['POST'])
@login_required
def mark_watched(rid):
    u = current_user()
    execute("INSERT OR IGNORE INTO watch_logs (student_id,recording_id) VALUES (?,?)",
            [u['id'], rid])
    return jsonify({'ok': True})

@app.route('/uploads/videos/<filename>')
@login_required
def serve_video(filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, 'videos'), filename)

# ─────────────────────────────────────────────
# MATERIALS
# ─────────────────────────────────────────────

@app.route('/api/courses/<int:cid>/materials')
@login_required
def get_materials(cid):
    rows = query("SELECT * FROM materials WHERE course_id=? ORDER BY week, uploaded_at", [cid])
    return jsonify(rows)

@app.route('/api/courses/<int:cid>/materials', methods=['POST'])
@teacher_required
def upload_material(cid):
    try:
        stored, orig, size = save_file(request.files.get('file'), 'materials')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    ext = orig.rsplit('.', 1)[-1].lower() if '.' in orig else ''
    execute("""INSERT INTO materials (course_id,week,title,description,filename,orig_name,file_type,file_size)
               VALUES (?,?,?,?,?,?,?,?)""",
            [cid,
             int(request.form.get('week', 0)),
             request.form.get('title', orig),
             request.form.get('description', ''),
             stored, orig, ext, size])
    return jsonify({'ok': True}), 201

@app.route('/api/materials/<int:mid>', methods=['DELETE'])
@teacher_required
def delete_material(mid):
    m = query("SELECT * FROM materials WHERE id=?", [mid], one=True)
    if m:
        fpath = os.path.join(UPLOAD_FOLDER, 'materials', m['filename'])
        if os.path.exists(fpath): os.remove(fpath)
    execute("DELETE FROM materials WHERE id=?", [mid])
    return jsonify({'ok': True})

@app.route('/uploads/materials/<filename>')
@login_required
def download_material(filename):
    m = query("SELECT orig_name FROM materials WHERE filename=?", [filename], one=True)
    return send_from_directory(os.path.join(UPLOAD_FOLDER, 'materials'),
                               filename, as_attachment=True,
                               download_name=m['orig_name'] if m else filename)

# ─────────────────────────────────────────────
# ASSIGNMENTS
# ─────────────────────────────────────────────

@app.route('/api/courses/<int:cid>/assignments')
@login_required
def get_assignments(cid):
    u = current_user()
    rows = query("SELECT * FROM assignments WHERE course_id=? ORDER BY week", [cid])
    if u['role'] == 'student':
        for a in rows:
            sub = query("SELECT * FROM submissions WHERE assignment_id=? AND student_id=?",
                        [a['id'], u['id']], one=True)
            a['submission'] = sub
    else:
        for a in rows:
            a['submission_count'] = query(
                "SELECT COUNT(*) as c FROM submissions WHERE assignment_id=?",
                [a['id']], one=True)['c']
    return jsonify(rows)

@app.route('/api/courses/<int:cid>/assignments', methods=['POST'])
@teacher_required
def create_assignment(cid):
    brief_file = None
    if 'file' in request.files and request.files['file'].filename:
        try:
            brief_file, _, _ = save_file(request.files['file'], 'briefs')
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
    execute("""INSERT INTO assignments (course_id,week,title,description,due_date,max_points,brief_file)
               VALUES (?,?,?,?,?,?,?)""",
            [cid,
             int(request.form.get('week', 1)),
             request.form.get('title', 'Untitled'),
             request.form.get('description', ''),
             request.form.get('due_date'),
             int(request.form.get('max_points', 100)),
             brief_file])
    return jsonify({'ok': True}), 201

@app.route('/api/assignments/<int:aid>', methods=['DELETE'])
@teacher_required
def delete_assignment(aid):
    execute("DELETE FROM assignments WHERE id=?", [aid])
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# SUBMISSIONS
# ─────────────────────────────────────────────

@app.route('/api/assignments/<int:aid>/submit', methods=['POST'])
@login_required
def submit_assignment(aid):
    u = current_user()
    try:
        stored, orig, _ = save_file(request.files.get('file'), 'submissions')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    # upsert — replace on resubmit
    execute("""INSERT INTO submissions (assignment_id,student_id,filename,orig_name,notes,submitted_at)
               VALUES (?,?,?,?,?,datetime('now'))
               ON CONFLICT(assignment_id,student_id) DO UPDATE SET
                   filename=excluded.filename, orig_name=excluded.orig_name,
                   notes=excluded.notes, submitted_at=excluded.submitted_at,
                   score=NULL, feedback=NULL, graded_at=NULL""",
            [aid, u['id'], stored, orig, request.form.get('notes', '')])
    return jsonify({'ok': True}), 201

@app.route('/api/assignments/<int:aid>/submissions')
@teacher_required
def get_submissions(aid):
    rows = query("""SELECT s.*, u.name as student_name, u.email as student_email
                    FROM submissions s JOIN users u ON u.id=s.student_id
                    WHERE s.assignment_id=?
                    ORDER BY s.submitted_at""", [aid])
    return jsonify(rows)

@app.route('/api/submissions/<int:sid>/grade', methods=['POST'])
@teacher_required
def grade_submission(sid):
    d = request.get_json()
    execute("""UPDATE submissions SET score=?, feedback=?, graded_at=datetime('now')
               WHERE id=?""",
            [int(d['score']), d.get('feedback', ''), sid])
    return jsonify({'ok': True})

@app.route('/uploads/submissions/<filename>')
@login_required
def download_submission(filename):
    u = current_user()
    if u['role'] == 'student':
        row = query("SELECT * FROM submissions WHERE filename=? AND student_id=?",
                    [filename, u['id']], one=True)
        if not row:
            return jsonify({'error': 'Forbidden'}), 403
    s = query("SELECT orig_name FROM submissions WHERE filename=?", [filename], one=True)
    return send_from_directory(os.path.join(UPLOAD_FOLDER, 'submissions'),
                               filename, as_attachment=True,
                               download_name=s['orig_name'] if s else filename)

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

@app.route('/api/courses/<int:cid>/dashboard')
@login_required
def dashboard(cid):
    u = current_user()
    total_rec  = query("SELECT COUNT(*) as c FROM recordings WHERE course_id=?", [cid], one=True)['c']
    total_asgn = query("SELECT COUNT(*) as c FROM assignments WHERE course_id=?", [cid], one=True)['c']

    if u['role'] == 'student':
        watched = query("""SELECT COUNT(*) as c FROM watch_logs w
                           JOIN recordings r ON r.id=w.recording_id
                           WHERE r.course_id=? AND w.student_id=?""",
                        [cid, u['id']], one=True)['c']
        subs = query("""SELECT score FROM submissions s
                        JOIN assignments a ON a.id=s.assignment_id
                        WHERE a.course_id=? AND s.student_id=?""",
                     [cid, u['id']])
        graded   = [s for s in subs if s['score'] is not None]
        avg      = round(sum(s['score'] for s in graded) / len(graded), 1) if graded else None
        submitted = len(subs)
        return jsonify({
            'videos_watched': watched, 'total_recordings': total_rec,
            'assignments_submitted': submitted, 'total_assignments': total_asgn,
            'avg_grade': avg
        })
    else:
        enrolled = query("SELECT COUNT(*) as c FROM enrollments WHERE course_id=?",
                         [cid], one=True)['c']
        ungraded = query("""SELECT COUNT(*) as c FROM submissions s
                            JOIN assignments a ON a.id=s.assignment_id
                            WHERE a.course_id=? AND s.score IS NULL""",
                         [cid], one=True)['c']
        # per-student progress
        students = query("""SELECT u.id, u.name, u.email FROM users u
                            JOIN enrollments e ON e.student_id=u.id
                            WHERE e.course_id=?""", [cid])
        for s in students:
            w = query("""SELECT COUNT(*) as c FROM watch_logs wl
                         JOIN recordings r ON r.id=wl.recording_id
                         WHERE r.course_id=? AND wl.student_id=?""",
                      [cid, s['id']], one=True)['c']
            sub_scores = query("""SELECT score FROM submissions sb
                                  JOIN assignments a ON a.id=sb.assignment_id
                                  WHERE a.course_id=? AND sb.student_id=?""",
                               [cid, s['id']])
            graded = [x for x in sub_scores if x['score'] is not None]
            s['videos_watched']    = w
            s['total_recordings']  = total_rec
            s['submissions']       = len(sub_scores)
            s['total_assignments'] = total_asgn
            s['avg_grade']         = round(sum(x['score'] for x in graded)/len(graded),1) if graded else None
            s['progress_pct']      = round(w/total_rec*100) if total_rec else 0
            s['initials']          = ''.join(p[0] for p in s['name'].split()[:2]).upper()

        recent_ungraded = query("""SELECT s.id, s.filename, s.orig_name, s.submitted_at,
                                          u.name as student_name, a.title as assignment_title
                                   FROM submissions s
                                   JOIN users u ON u.id=s.student_id
                                   JOIN assignments a ON a.id=s.assignment_id
                                   WHERE a.course_id=? AND s.score IS NULL
                                   ORDER BY s.submitted_at DESC LIMIT 5""", [cid])
        return jsonify({
            'enrolled_students': enrolled,
            'ungraded_submissions': ungraded,
            'total_recordings': total_rec,
            'total_materials': query("SELECT COUNT(*) as c FROM materials WHERE course_id=?",
                                     [cid], one=True)['c'],
            'student_progress': students,
            'recent_ungraded': recent_ungraded
        })

# ─────────────────────────────────────────────
# SEED demo data
# ─────────────────────────────────────────────

def seed():
    if query("SELECT 1 FROM users LIMIT 1"):
        return

    UPLOADS = os.path.join(os.path.dirname(__file__), 'uploads')

    def mat_size(fname, sub):
        path = os.path.join(UPLOADS, sub, fname)
        if not os.path.exists(path): return '—'
        b = os.path.getsize(path)
        return f"{b/1024:.0f} KB" if b < 1024*1024 else f"{b/1024/1024:.1f} MB"

    # ── Users ────────────────────────────────────────────
    users = [
        ('Michael Chang', 'teacher@codencode.my', 'teacher'),
        ('Alex Tan',      'student@codencode.my', 'student'),
        ('Jamie Lim',     'jamie@codencode.my',   'student'),
        ('Rahim Nor',     'rahim@codencode.my',   'student'),
        ('Wei Ling',      'weiling@codencode.my', 'student'),
        ('Zara Hassan',   'zara@codencode.my',    'student'),
        ('Kai Chen',      'kai@codencode.my',     'student'),
    ]
    for name, email, role in users:
        execute("INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,?)",
                [name, email, generate_password_hash('demo1234'), role])

    # ── Courses ──────────────────────────────────────────
    py_id = execute("INSERT INTO courses (title,description,weeks) VALUES (?,?,?)",
                    ['Python for Beginners',
                     'Go from zero to writing real Python programs in 6 weeks. No experience needed!', 6])
    ml_id = execute("INSERT INTO courses (title,description,weeks) VALUES (?,?,?)",
                    ['Machine Learning Fundamentals',
                     'Learn how machines learn. Build models that predict, classify, and understand data.', 8])

    for sid in range(2, 8):
        execute("INSERT OR IGNORE INTO enrollments (student_id,course_id) VALUES (?,?)", [sid, py_id])
        execute("INSERT OR IGNORE INTO enrollments (student_id,course_id) VALUES (?,?)", [sid, ml_id])

    # ══════════════════════════════════════════════════════
    #  PYTHON FOR BEGINNERS
    # ══════════════════════════════════════════════════════

    # ── Recordings ───────────────────────────────────────
    py_sessions = [
        (1,1,"Welcome! Setting Up Python & VS Code",          "32:10",
         "Install Python, VS Code, run your first print('hello world'). We do it together."),
        (1,2,"Variables & Data Types — Storing Information",  "41:25",
         "int, float, string, bool. Learn how Python stores data in memory."),
        (1,3,"Making Decisions — If, Elif, Else",             "38:50",
         "Your code thinks! Write programs that react to different inputs."),
        (1,4,"Loops — For & While (Stop Repeating Yourself)", "45:05",
         "Automate repetitive tasks. Loop over lists, use range(), break and continue."),
        (2,1,"Lists — Your First Collection",                 "39:20",
         "Store multiple values. Append, remove, slice, sort. The most-used data structure."),
        (2,2,"Dictionaries — Key-Value Power",                "44:15",
         "Think of it as a contacts list. Perfect for structured data."),
        (2,3,"Functions — Write Once, Use Anywhere",          "52:30",
         "def, return, arguments, defaults. Stop copy-pasting code."),
        (2,4,"Scope, *args & **kwargs",                       "38:45",
         "Advanced function tricks. Pass any number of arguments."),
        (3,1,"OOP Part 1 — Classes & Objects",                "55:10",
         "Bundle data and behaviour together. Build a Student class from scratch."),
        (3,2,"OOP Part 2 — Inheritance",                      "49:35",
         "Teacher inherits from Person. Reuse code, don't repeat it."),
        (4,1,"Files — Reading & Writing Data",                "42:00",
         "Read txt, write CSV, load JSON. Your programs now remember things."),
        (4,2,"Error Handling — Try, Except, Finally",         "36:20",
         "Stop your program from crashing. Handle errors like a pro."),
        (5,1,"Modules & pip — Using Other People's Code",     "33:40",
         "Import math, random, datetime. Install packages with pip."),
        (5,2,"List Comprehensions & Lambdas",                 "40:55",
         "One-liner magic. Write cleaner, more Pythonic code."),
        (6,1,"Mini Project — Build a Contact Book",           "61:20",
         "We build Assignment 2 together, step by step. Watch this before submitting!"),
        (6,2,"Wrap Up — What's Next?",                        "28:05",
         "You did it! What to learn next: web, data science, automation."),
    ]
    for wk, sn, title, dur, desc in py_sessions:
        execute("INSERT INTO recordings (course_id,week,session_num,title,description,duration,filename) VALUES (?,?,?,?,?,?,?)",
                [py_id, wk, sn, title, desc, dur, 'demo_placeholder.mp4'])

    # ── Materials ─────────────────────────────────────────
    py_materials = [
        # (week, title, stored_filename, orig_name, file_type, subfolder)
        (0, '🗒️ Python Cheat Sheet — Everything in One File',
             'py_cheatsheet.py',       'py_cheatsheet.py',              'py',  'materials'),
        (1, '📝 Week 1 Exercises — Variables, Loops & Lists',
             'py_week1_exercises.py',  'week1_exercises.py',            'py',  'materials'),
        (2, '📝 Week 2 Exercises — Functions',
             'py_week2_exercises.py',  'week2_exercises.py',            'py',  'materials'),
        (3, '📝 Week 3 Exercises — OOP Classes & Objects',
             'py_week3_exercises.py',  'week3_exercises.py',            'py',  'materials'),
        (4, '📝 Week 4 Exercises — Files & Error Handling',
             'py_week4_exercises.py',  'week4_exercises.py',            'py',  'materials'),
        (5, '📝 Week 5 Exercises — Modules, pip & Pythonic Code',
             'py_week5_exercises.py',  'week5_exercises.py',            'py',  'materials'),
        (6, '📝 Week 6 Exercises — Building Real Projects',
             'py_week6_exercises.py',  'week6_exercises.py',            'py',  'materials'),
    ]
    for wk, title, fname, orig, ftype, sub in py_materials:
        size = mat_size(fname, sub)
        execute("INSERT INTO materials (course_id,week,title,filename,orig_name,file_type,file_size) VALUES (?,?,?,?,?,?,?)",
                [py_id, wk, title, fname, orig, ftype, size])

    # ── Assignments ──────────────────────────────────────
    py_asgn = []
    for wk, title, desc, due, brief in [
        (2,
         '🎯 Assignment 1 — My Digital Life in Python',
         'Build your first real Python program! Introduce yourself, make a grade calculator, '
         'and build a number guessing game. Use variables, loops, functions, and lists. '
         'Starter file is attached — fill in the TODOs and submit.',
         '2026-03-14',
         'py_assignment1_starter.py'),
        (5,
         '🎯 Assignment 2 — Build a Mini Contact Book',
         'Build a terminal app that lets users add, view, search, and delete contacts. '
         'Uses functions, dictionaries, loops, and file handling (JSON). '
         'Starter file attached — complete all tasks. Bonus: save/load from file.',
         '2026-04-04',
         'py_assignment2_starter.py'),
    ]:
        brief_path = os.path.join(UPLOADS, 'briefs', brief)
        brief_stored = brief if os.path.exists(brief_path) else None
        aid = execute("INSERT INTO assignments (course_id,week,title,description,due_date,max_points,brief_file) VALUES (?,?,?,?,?,?,?)",
                      [py_id, wk, title, desc, due, 100, brief_stored])
        py_asgn.append(aid)

    # ── Demo grades for Python assignments ───────────────
    py_grades = [
        (2, [85, None]),   # Alex:  A1 graded, A2 pending
        (3, [95, None]),   # Jamie
        (4, [60, None]),   # Rahim
        (5, [78, None]),   # Wei Ling
        (6, [88, None]),   # Zara
        (7, [92, None]),   # Kai
    ]
    py_feedback = {
        95: "Excellent work! Really creative guessing game 🏆",
        92: "Clean code and great comments. Well done!",
        88: "Good effort! Small bug in Task 3 but overall solid.",
        85: "Nice work. Try to add more comments next time.",
        78: "Completed all tasks. Grade calculator needs a small fix.",
        60: "Tasks 1 & 2 done but guessing game is incomplete. See me after class.",
    }
    for sid, scores in py_grades:
        for i, score in enumerate(scores):
            if score is None:
                # Ungraded submission for assignment 2
                execute("INSERT OR IGNORE INTO submissions (assignment_id,student_id,filename,orig_name,submitted_at) VALUES (?,?,?,?,datetime('now'))",
                        [py_asgn[1], sid, 'py_assignment2_starter.py', 'my_contact_book.py'])
            else:
                fb = py_feedback.get(score, 'Good work!')
                execute("""INSERT INTO submissions
                           (assignment_id,student_id,filename,orig_name,submitted_at,score,feedback,graded_at)
                           VALUES (?,?,?,?,datetime('now'),?,?,datetime('now'))""",
                        [py_asgn[0], sid, 'py_assignment1_starter.py', 'assignment1.py', score, fb])

    # ── Watch logs ───────────────────────────────────────
    py_rec_ids = [r['id'] for r in query("SELECT id FROM recordings WHERE course_id=? ORDER BY id", [py_id])]
    for sid, count in [(2,10),(3,16),(4,7),(5,12),(6,14),(7,16)]:
        for rid in py_rec_ids[:min(count, len(py_rec_ids))]:
            execute("INSERT OR IGNORE INTO watch_logs (student_id,recording_id) VALUES (?,?)", [sid, rid])

    # ══════════════════════════════════════════════════════
    #  MACHINE LEARNING FUNDAMENTALS
    # ══════════════════════════════════════════════════════

    # ── Recordings ───────────────────────────────────────
    ml_sessions = [
        (1,1,"What IS Machine Learning? (No Maths Yet)",      "35:40",
         "Intuition first. What can ML do? What can't it? Real examples from your daily life."),
        (1,2,"Python for ML — NumPy Crash Course",            "52:15",
         "Arrays, math, broadcasting. The foundation everything else is built on."),
        (2,1,"Pandas — Wrangling Messy Real Data",            "58:30",
         "Load CSVs, clean nulls, filter rows, groupby. The skill you'll use every single day."),
        (2,2,"Data Visualisation — Matplotlib & Seaborn",     "44:10",
         "See your data before modelling. Histograms, scatter plots, heatmaps."),
        (3,1,"Supervised Learning — The Big Picture",         "40:25",
         "Features vs labels. Training vs testing. The core ML workflow explained simply."),
        (3,2,"Linear Regression — Predicting Numbers",        "55:50",
         "Predict house prices, salaries, temperatures. Gradient descent without the pain."),
        (4,1,"Logistic Regression — Predicting Yes/No",       "48:35",
         "Spam or not spam? Pass or fail? Classification fundamentals."),
        (4,2,"Decision Trees — ML You Can Actually Explain",  "51:20",
         "Build a tree, visualise it, understand every decision. Great for beginners."),
        (5,1,"Random Forest — When One Tree Isn't Enough",    "46:05",
         "Ensemble learning: 100 trees vote. Usually beats a single tree easily."),
        (5,2,"Model Evaluation — Are You Actually Good?",     "42:55",
         "Accuracy, precision, recall, F1, confusion matrix. Don't fool yourself."),
        (6,1,"Overfitting — The Enemy of Good Models",        "38:40",
         "When your model memorises instead of learning. Train/val/test splits."),
        (6,2,"Feature Engineering — Better Data = Better Model","50:10",
         "The secret skill of ML practitioners. Create features that matter."),
        (7,1,"K-Nearest Neighbours & Naive Bayes",            "44:30",
         "Simple but surprisingly powerful algorithms explained visually."),
        (7,2,"Support Vector Machines (Intuition Only)",      "39:15",
         "Hyperplanes and margins — what SVM does without the heavy maths."),
        (8,1,"Intro to Neural Networks",                      "62:40",
         "Neurons, layers, activation functions. The building blocks of deep learning."),
        (8,2,"Wrap Up — Career Paths in ML & What's Next",    "31:20",
         "Data scientist? ML engineer? AI researcher? Your roadmap from here."),
    ]
    for wk, sn, title, dur, desc in ml_sessions:
        execute("INSERT INTO recordings (course_id,week,session_num,title,description,duration,filename) VALUES (?,?,?,?,?,?,?)",
                [ml_id, wk, sn, title, desc, dur, 'demo_placeholder.mp4'])

    # ── Materials ─────────────────────────────────────────
    ml_materials = [
        (0, '🗒️ ML Cheat Sheet — Concepts & Code Reference',
             'ml_cheatsheet.py',      'ml_cheatsheet.py',              'py',  'materials'),
        (1, '📝 Week 1 Exercises — NumPy Fundamentals',
             'ml_week1_exercises.py', 'week1_numpy_exercises.py',      'py',  'materials'),
        (2, '📝 Week 2 Exercises — Pandas Data Wrangling',
             'ml_week2_exercises.py', 'week2_pandas_exercises.py',     'py',  'materials'),
        (3, '📝 Week 3 Exercises — Your First ML Model',
             'ml_week3_exercises.py', 'week3_first_model.py',          'py',  'materials'),
        (4, '📝 Week 4 Exercises — Classification',
             'ml_week4_exercises.py', 'week4_classification.py',       'py',  'materials'),
        (5, '📝 Week 5 Exercises — Random Forest & Evaluation',
             'ml_week5_exercises.py', 'week5_random_forest.py',        'py',  'materials'),
        (6, '📝 Week 6 Exercises — Feature Engineering',
             'ml_week6_exercises.py', 'week6_feature_engineering.py',  'py',  'materials'),
    ]
    for wk, title, fname, orig, ftype, sub in ml_materials:
        size = mat_size(fname, sub)
        execute("INSERT INTO materials (course_id,week,title,filename,orig_name,file_type,file_size) VALUES (?,?,?,?,?,?,?)",
                [ml_id, wk, title, fname, orig, ftype, size])

    # ── Assignments ──────────────────────────────────────
    ml_asgn = []
    for wk, title, desc, due, brief in [
        (4,
         '🎯 Assignment 1 — Predict Who Passes the Course',
         'Build a classifier that predicts whether a student will pass or fail '
         'based on study hours, attendance, and assignment scores. '
         'You will explore the data, train Logistic Regression and Decision Tree models, '
         'compare them, and make a prediction for a new student. Starter file attached.',
         '2026-03-21',
         'ml_assignment1_starter.py'),
        (7,
         '🎯 Assignment 2 — JB House Price Predictor',
         'Regression challenge: predict monthly rental prices for JB properties. '
         'Dataset includes rooms, size, location, and amenities. '
         'Build Linear Regression and Random Forest models, compare them, '
         'and predict the rent for your dream apartment. Starter file attached.',
         '2026-04-11',
         'ml_assignment2_starter.py'),
    ]:
        brief_path = os.path.join(UPLOADS, 'briefs', brief)
        brief_stored = brief if os.path.exists(brief_path) else None
        aid = execute("INSERT INTO assignments (course_id,week,title,description,due_date,max_points,brief_file) VALUES (?,?,?,?,?,?,?)",
                      [ml_id, wk, title, desc, due, 100, brief_stored])
        ml_asgn.append(aid)

    # ── Demo grades for ML assignments ───────────────────
    ml_grades = [
        (2, [88, None]),
        (3, [96, None]),
        (4, [55, None]),
        (5, [82, None]),
        (6, [91, None]),
        (7, [79, None]),
    ]
    ml_feedback = {
        96: "Incredible work! Your feature analysis was really insightful 🏆",
        91: "Great model comparison. Really clean code.",
        88: "Solid all round. Try tuning the hyperparameters for bonus marks.",
        82: "Good effort! Reflection section was honest and thoughtful.",
        79: "Completed all tasks. R² could be better — try scaling your features.",
        55: "Tasks 1 & 2 done but model training is incomplete. Let's chat.",
    }
    for sid, scores in ml_grades:
        for i, score in enumerate(scores):
            if score is None:
                execute("INSERT OR IGNORE INTO submissions (assignment_id,student_id,filename,orig_name,submitted_at) VALUES (?,?,?,?,datetime('now'))",
                        [ml_asgn[1], sid, 'ml_assignment2_starter.py', 'house_price_predictor.py'])
            else:
                fb = ml_feedback.get(score, 'Good work!')
                execute("""INSERT INTO submissions
                           (assignment_id,student_id,filename,orig_name,submitted_at,score,feedback,graded_at)
                           VALUES (?,?,?,?,datetime('now'),?,?,datetime('now'))""",
                        [ml_asgn[0], sid, 'ml_assignment1_starter.py', 'pass_fail_predictor.py', score, fb])

    # ── Watch logs ───────────────────────────────────────
    ml_rec_ids = [r['id'] for r in query("SELECT id FROM recordings WHERE course_id=? ORDER BY id", [ml_id])]
    for sid, count in [(2,8),(3,14),(4,5),(5,10),(6,12),(7,14)]:
        for rid in ml_rec_ids[:min(count, len(ml_rec_ids))]:
            execute("INSERT OR IGNORE INTO watch_logs (student_id,recording_id) VALUES (?,?)", [sid, rid])

    print('✓ Full course content seeded — Python for Beginners + ML Fundamentals')

# ─────────────────────────────────────────────
# Init on startup (runs when gunicorn imports this file)
# ─────────────────────────────────────────────

init_db()
seed()

if __name__ == '__main__':
    init_db()
    seed()
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug, host='0.0.0.0', port=port)
