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

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

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
    return send_from_directory('templates', 'lms.html')

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

    # Users
    users = [
        ('Michael Chang', 'teacher@codencode.my', 'teacher'),
        ('Alex Tan',       'student@codencode.my', 'student'),
        ('Jamie Lim',      'jamie@codencode.my',   'student'),
        ('Rahim Nor',      'rahim@codencode.my',   'student'),
        ('Wei Ling',       'weiling@codencode.my', 'student'),
        ('Zara Hassan',    'zara@codencode.my',    'student'),
        ('Kai Chen',       'kai@codencode.my',     'student'),
    ]
    for name, email, role in users:
        execute("INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,?)",
                [name, email, generate_password_hash('demo1234'), role])

    # Courses
    python_id = execute("INSERT INTO courses (title,description,weeks) VALUES (?,?,?)",
                        ['Python Programming Bootcamp','6-week course from beginner to advanced.',6])
    ml_id = execute("INSERT INTO courses (title,description,weeks) VALUES (?,?,?)",
                    ['Machine Learning Fundamentals','10-week ML course.',10])

    # Enroll students (id 2-7) in both courses
    for sid in range(2, 8):
        execute("INSERT OR IGNORE INTO enrollments (student_id,course_id) VALUES (?,?)", [sid, python_id])
        execute("INSERT OR IGNORE INTO enrollments (student_id,course_id) VALUES (?,?)", [sid, ml_id])

    # Recordings
    for wk, sn, title, dur in [
        (1,1,'Intro to Python & Environment Setup','45:12'),
        (1,2,'Variables, Data Types & Operators','38:44'),
        (1,3,'Control Flow: If, Loops, Break & Continue','52:01'),
        (1,4,'Lists, Tuples, Dictionaries','41:30'),
        (2,1,'Functions Deep Dive — Args, Kwargs, Scope','58:20'),
        (2,2,'Reading & Writing Files — CSV, JSON, TXT','44:50'),
        (3,1,'OOP Part 1 — Classes & Objects','55:40'),
        (3,2,'OOP Part 2 — Inheritance & Polymorphism','49:30'),
        (4,1,'Pandas: DataFrames, Series, Indexing','62:05'),
        (4,2,'Data Cleaning — Nulls, Duplicates, Dtypes','55:18'),
    ]:
        execute("INSERT INTO recordings (course_id,week,session_num,title,duration,filename) VALUES (?,?,?,?,?,?)",
                [python_id, wk, sn, title, dur, 'demo_placeholder.mp4'])

    # Materials
    for wk, title, ftype, fsize in [
        (1,'Week 1 — Python Basics Slides.pdf','pdf','2.4 MB'),
        (1,'week1_exercises.py','py','18 KB'),
        (4,'Pandas Cheat Sheet.pdf','pdf','890 KB'),
        (4,'datasets_week4.zip','zip','3.1 MB'),
        (0,'Course Outline & Schedule.pdf','pdf','145 KB'),
    ]:
        execute("INSERT INTO materials (course_id,week,title,filename,orig_name,file_type,file_size) VALUES (?,?,?,?,?,?,?)",
                [python_id, wk, title, f'demo_{title}', title, ftype, fsize])

    # Assignments
    asgn_ids = []
    for wk, title, desc, due in [
        (1,'Python Basics — Loops & Lists','Write a script that processes a list of numbers.','2025-01-19'),
        (2,'Functions & Recursion','Build utility functions including recursive algorithms.','2025-01-28'),
        (3,'File Handling & Data Processing','Read a CSV, process data, output a summary report.','2025-02-05'),
        (4,'Web Scraping with BeautifulSoup','Scrape product listings from a given site.','2025-02-28'),
        (5,'Pandas Data Analysis Report','Analyse the provided sales dataset using Pandas.','2025-03-07'),
    ]:
        aid = execute("INSERT INTO assignments (course_id,week,title,description,due_date) VALUES (?,?,?,?,?)",
                      [python_id, wk, title, desc, due])
        asgn_ids.append(aid)

    # Grades for assignments 1-3
    grade_data = [
        (2, [80, 92, 88]),
        (3, [95, 90, 93]),
        (4, [60, 65, None]),
        (5, [75, 80, 78]),
        (6, [88, 85, 90]),
        (7, [92, 98, 91]),
    ]
    for sid, scores in grade_data:
        for i, score in enumerate(scores):
            if score is None: continue
            execute("""INSERT INTO submissions (assignment_id,student_id,filename,orig_name,submitted_at,score,feedback,graded_at)
                       VALUES (?,?,?,?,datetime('now'),?,?,datetime('now'))""",
                    [asgn_ids[i], sid, 'demo.py', 'demo.py', score,
                     'Good work!' if score >= 80 else 'Needs improvement.'])

    # Ungraded submissions for assignment 4
    for sid in [2, 3, 4, 5]:
        execute("INSERT OR IGNORE INTO submissions (assignment_id,student_id,filename,orig_name) VALUES (?,?,?,?)",
                [asgn_ids[3], sid, 'demo.py', 'submission.py'])

    # Watch logs
    rec_ids = [r['id'] for r in query("SELECT id FROM recordings WHERE course_id=? ORDER BY id", [python_id])]
    for sid, count in [(2,8),(3,10),(4,5),(5,7),(6,9),(7,10)]:
        for rid in rec_ids[:count]:
            execute("INSERT OR IGNORE INTO watch_logs (student_id,recording_id) VALUES (?,?)", [sid, rid])

    print('✓ Demo data seeded')

# ─────────────────────────────────────────────
# Start
# ─────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    seed()
    app.run(debug=True, host='0.0.0.0', port=5000)
