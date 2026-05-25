"""
codencode LMS — Workshop Portal Routes
=======================================
Add these routes to your existing Flask app.py (learn.codencode.my).

Prerequisites (already in your LMS):
  - Flask session-based auth (session['user_id'] / session['user_name'] / session['user_email'])
  - PostgreSQL via psycopg2
  - CORS already configured

New tables required — run workshop_schema.sql first.

Endpoints added:
  GET  /materials              → student portal (login-gated HTML page)
  GET  /api/workshops          → list all published workshops (JSON)
  GET  /api/workshops/<id>     → single workshop + materials (JSON)
  POST /api/workshops/<id>/register → register student for a workshop
  POST /api/workshops/<id>/materials/<mid>/complete → toggle material complete
  GET  /api/workshops/<id>/progress → get student's progress

Admin endpoints (require admin role):
  GET    /admin/workshops            → admin manager UI
  POST   /api/admin/workshops        → create workshop
  PUT    /api/admin/workshops/<id>   → update workshop
  DELETE /api/admin/workshops/<id>   → delete workshop
  POST   /api/admin/workshops/<id>/materials        → add material
  PUT    /api/admin/workshops/<id>/materials/<mid>  → edit material
  DELETE /api/admin/workshops/<id>/materials/<mid>  → delete material
  PUT    /api/admin/workshops/<id>/schedule         → replace full schedule
  GET    /api/admin/registrations    → all registrations (export-ready)
"""

import os, json
from datetime import datetime
from functools import wraps
from flask import (
    Blueprint, request, jsonify, session,
    render_template_string, send_from_directory, redirect, url_for
)
import psycopg2, psycopg2.extras

# ── Blueprint ──────────────────────────────────────────────────────────────
workshop_bp = Blueprint('workshops', __name__)

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost/codencode_lms')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

# ── Auth decorators ────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            # For API calls return 401; for page requests redirect to login
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required', 'redirect': '/login'}), 401
            return redirect('/login?next=' + request.path)
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login?next=' + request.path)
        if session.get('user_role') not in ('admin', 'teacher'):
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

# ── Helper ────────────────────────────────────────────────────────────────
def serialize(row):
    """Convert RealDictRow to plain dict, handling datetime serialization."""
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d

# ══════════════════════════════════════════════════════════════════════════
# STUDENT ROUTES
# ══════════════════════════════════════════════════════════════════════════

@workshop_bp.route('/materials')
@login_required
def materials_portal():
    """
    Serves the student-facing workshop portal.
    The actual HTML is in templates/materials.html (student_materials.html file).
    Session user data is injected so the frontend knows who's logged in.
    """
    user = {
        'id': session['user_id'],
        'name': session.get('user_name', ''),
        'email': session.get('user_email', ''),
        'role': session.get('user_role', 'student'),
    }
    # Render the standalone HTML file — it calls /api/workshops on load
    return render_template_string(
        open(os.path.join(os.path.dirname(__file__), 'templates', 'materials.html')).read(),
        user=user,
        user_json=json.dumps(user)
    )


@workshop_bp.route('/api/workshops')
@login_required
def api_list_workshops():
    """All published workshops + whether the current student is registered."""
    uid = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            w.*,
            (SELECT COUNT(*) FROM workshop_materials wm WHERE wm.workshop_id = w.id) AS material_count,
            (SELECT id FROM workshop_registrations wr
             WHERE wr.workshop_id = w.id AND wr.student_id = %s) AS registration_id
        FROM workshops w
        WHERE w.published = TRUE
        ORDER BY w.workshop_date ASC
    """, (uid,))
    rows = [serialize(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@workshop_bp.route('/api/workshops/<int:wid>')
@login_required
def api_get_workshop(wid):
    """Single workshop with full materials list and student progress."""
    uid = session['user_id']
    conn = get_db()
    cur = conn.cursor()

    # Workshop
    cur.execute("SELECT * FROM workshops WHERE id = %s AND published = TRUE", (wid,))
    ws = cur.fetchone()
    if not ws:
        conn.close()
        return jsonify({'error': 'Workshop not found'}), 404

    # Materials
    cur.execute("""
        SELECT wm.*,
            (SELECT 1 FROM workshop_progress wp
             WHERE wp.material_id = wm.id AND wp.student_id = %s) AS completed
        FROM workshop_materials wm
        WHERE wm.workshop_id = %s
        ORDER BY wm.sort_order ASC, wm.id ASC
    """, (uid, wid))
    materials = [serialize(r) for r in cur.fetchall()]

    # Schedule
    cur.execute("""
        SELECT * FROM workshop_schedule
        WHERE workshop_id = %s ORDER BY sort_order ASC
    """, (wid,))
    schedule = [serialize(r) for r in cur.fetchall()]

    # Announcements
    cur.execute("""
        SELECT * FROM workshop_announcements
        WHERE workshop_id = %s ORDER BY created_at DESC
    """, (wid,))
    announcements = [serialize(r) for r in cur.fetchall()]

    conn.close()
    return jsonify({
        **serialize(ws),
        'materials': materials,
        'schedule': schedule,
        'announcements': announcements,
    })


@workshop_bp.route('/api/workshops/<int:wid>/register', methods=['POST'])
@login_required
def api_register_workshop(wid):
    """Register current student for a workshop (stores registration form data)."""
    uid = session['user_id']
    data = request.json or {}
    conn = get_db()
    cur = conn.cursor()

    # Check not already registered
    cur.execute("""
        SELECT id FROM workshop_registrations
        WHERE workshop_id = %s AND student_id = %s
    """, (wid, uid))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'Already registered'}), 409

    cur.execute("""
        INSERT INTO workshop_registrations
          (workshop_id, student_id, occupation, industry, experience_level,
           motivation, preferred_language, referral_source, registered_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
    """, (
        wid, uid,
        data.get('occupation'), data.get('industry'),
        data.get('experience'), data.get('motivation'),
        data.get('language'), data.get('referral'),
    ))
    reg_id = cur.fetchone()['id']
    conn.commit()
    conn.close()
    return jsonify({'registration_id': reg_id, 'status': 'registered'}), 201


@workshop_bp.route('/api/workshops/<int:wid>/materials/<int:mid>/complete', methods=['POST'])
@login_required
def api_toggle_complete(wid, mid):
    """Toggle a material as complete/incomplete for the current student."""
    uid = session['user_id']
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id FROM workshop_progress
        WHERE workshop_id = %s AND material_id = %s AND student_id = %s
    """, (wid, mid, uid))
    existing = cur.fetchone()

    if existing:
        cur.execute("DELETE FROM workshop_progress WHERE id = %s", (existing['id'],))
        completed = False
    else:
        cur.execute("""
            INSERT INTO workshop_progress (workshop_id, material_id, student_id, completed_at)
            VALUES (%s, %s, %s, NOW())
        """, (wid, mid, uid))
        completed = True

    conn.commit()
    conn.close()
    return jsonify({'completed': completed})


@workshop_bp.route('/api/workshops/<int:wid>/progress')
@login_required
def api_get_progress(wid):
    """Get current student's progress for a workshop."""
    uid = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT material_id, completed_at
        FROM workshop_progress
        WHERE workshop_id = %s AND student_id = %s
    """, (wid, uid))
    rows = [serialize(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({'completed_material_ids': [r['material_id'] for r in rows]})


# ══════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════════════

@workshop_bp.route('/admin/workshops')
@admin_required
def admin_workshops_ui():
    """Serves the admin workshop manager HTML page."""
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), 'templates'),
        'admin_workshops.html'
    )


@workshop_bp.route('/api/admin/workshops', methods=['GET'])
@admin_required
def api_admin_list():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT w.*,
            (SELECT COUNT(*) FROM workshop_registrations wr WHERE wr.workshop_id = w.id) AS registrant_count,
            (SELECT COUNT(*) FROM workshop_materials wm WHERE wm.workshop_id = w.id) AS material_count
        FROM workshops w ORDER BY w.workshop_date DESC
    """)
    rows = [serialize(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@workshop_bp.route('/api/admin/workshops', methods=['POST'])
@admin_required
def api_admin_create():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workshops
          (title, emoji, description, workshop_date, time_start, time_end,
           location, location_type, language, published, color_theme, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        RETURNING *
    """, (
        data['title'], data.get('emoji','📚'), data.get('description',''),
        data['workshop_date'], data.get('time_start','09:00'), data.get('time_end','17:00'),
        data.get('location',''), data.get('location_type','physical'),
        data.get('language','English'), data.get('published', False),
        data.get('color_theme','python'),
    ))
    row = serialize(cur.fetchone())
    conn.commit()
    conn.close()
    return jsonify(row), 201


@workshop_bp.route('/api/admin/workshops/<int:wid>', methods=['PUT'])
@admin_required
def api_admin_update(wid):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE workshops SET
          title=%s, emoji=%s, description=%s, workshop_date=%s,
          time_start=%s, time_end=%s, location=%s, location_type=%s,
          language=%s, published=%s, color_theme=%s, updated_at=NOW()
        WHERE id=%s RETURNING *
    """, (
        data['title'], data.get('emoji','📚'), data.get('description',''),
        data['workshop_date'], data.get('time_start','09:00'), data.get('time_end','17:00'),
        data.get('location',''), data.get('location_type','physical'),
        data.get('language','English'), data.get('published', False),
        data.get('color_theme','python'), wid,
    ))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(serialize(row))


@workshop_bp.route('/api/admin/workshops/<int:wid>', methods=['DELETE'])
@admin_required
def api_admin_delete(wid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM workshops WHERE id = %s", (wid,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': True})


# ── Materials CRUD ─────────────────────────────────────────────────────────

@workshop_bp.route('/api/admin/workshops/<int:wid>/materials', methods=['POST'])
@admin_required
def api_admin_add_material(wid):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workshop_materials
          (workshop_id, name, material_type, icon, file_size, duration,
           section, download_url, sort_order)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,
          COALESCE((SELECT MAX(sort_order)+1 FROM workshop_materials WHERE workshop_id=%s), 1))
        RETURNING *
    """, (
        wid, data['name'], data.get('material_type','pdf'),
        data.get('icon','📄'), data.get('file_size',''),
        data.get('duration',''), data.get('section','Materials'),
        data.get('download_url','#'), wid,
    ))
    row = serialize(cur.fetchone())
    conn.commit()
    conn.close()
    return jsonify(row), 201


@workshop_bp.route('/api/admin/workshops/<int:wid>/materials/<int:mid>', methods=['PUT'])
@admin_required
def api_admin_update_material(wid, mid):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE workshop_materials SET
          name=%s, material_type=%s, icon=%s, file_size=%s,
          duration=%s, section=%s, download_url=%s, sort_order=%s
        WHERE id=%s AND workshop_id=%s RETURNING *
    """, (
        data['name'], data.get('material_type','pdf'),
        data.get('icon','📄'), data.get('file_size',''),
        data.get('duration',''), data.get('section','Materials'),
        data.get('download_url','#'), data.get('sort_order', 1),
        mid, wid,
    ))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    return jsonify(serialize(row)) if row else (jsonify({'error': 'Not found'}), 404)


@workshop_bp.route('/api/admin/workshops/<int:wid>/materials/<int:mid>', methods=['DELETE'])
@admin_required
def api_admin_delete_material(wid, mid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM workshop_materials WHERE id=%s AND workshop_id=%s", (mid, wid))
    conn.commit()
    conn.close()
    return jsonify({'deleted': True})


# ── Schedule CRUD ─────────────────────────────────────────────────────────

@workshop_bp.route('/api/admin/workshops/<int:wid>/schedule', methods=['PUT'])
@admin_required
def api_admin_replace_schedule(wid):
    """Replace entire schedule (send full array from admin UI)."""
    items = request.json  # list of {time_slot, title, description}
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM workshop_schedule WHERE workshop_id=%s", (wid,))
    for i, item in enumerate(items):
        cur.execute("""
            INSERT INTO workshop_schedule (workshop_id, time_slot, title, description, sort_order)
            VALUES (%s,%s,%s,%s,%s)
        """, (wid, item['time_slot'], item['title'], item.get('description',''), i+1))
    conn.commit()
    conn.close()
    return jsonify({'updated': len(items)})


# ── Announcements ─────────────────────────────────────────────────────────

@workshop_bp.route('/api/admin/workshops/<int:wid>/announcements', methods=['POST'])
@admin_required
def api_admin_add_announcement(wid):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workshop_announcements (workshop_id, icon, title, body, created_at)
        VALUES (%s,%s,%s,%s,NOW()) RETURNING *
    """, (wid, data.get('icon','📢'), data['title'], data['body']))
    row = serialize(cur.fetchone())
    conn.commit()
    conn.close()
    return jsonify(row), 201


@workshop_bp.route('/api/admin/workshops/<int:wid>/announcements/<int:aid>', methods=['DELETE'])
@admin_required
def api_admin_delete_announcement(wid, aid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM workshop_announcements WHERE id=%s AND workshop_id=%s", (aid, wid))
    conn.commit()
    conn.close()
    return jsonify({'deleted': True})


# ── Registrations export ──────────────────────────────────────────────────

@workshop_bp.route('/api/admin/workshop-registrations')
@admin_required
def api_admin_registrations():
    wid = request.args.get('workshop_id')
    conn = get_db()
    cur = conn.cursor()
    query = """
        SELECT
            wr.id, wr.registered_at,
            w.title AS workshop_title, w.workshop_date,
            u.name AS student_name, u.email,
            wr.occupation, wr.industry, wr.experience_level,
            wr.motivation, wr.preferred_language, wr.referral_source
        FROM workshop_registrations wr
        JOIN workshops w ON w.id = wr.workshop_id
        JOIN users u ON u.id = wr.student_id
    """
    if wid:
        query += " WHERE wr.workshop_id = %s ORDER BY wr.registered_at DESC"
        cur.execute(query, (wid,))
    else:
        query += " ORDER BY wr.registered_at DESC"
        cur.execute(query)
    rows = [serialize(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


# ══════════════════════════════════════════════════════════════════════════
# REGISTER BLUEPRINT IN app.py
# ══════════════════════════════════════════════════════════════════════════
#
# In your existing app.py, add:
#
#   from lms_workshop_routes import workshop_bp
#   app.register_blueprint(workshop_bp)
#
# That's it. All routes are now live.
