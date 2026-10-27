"""Staff Attendance & Payroll module, mounted on the LMS app under /staff.

Same database, users table, Flask-Login session and roles as the LMS.
Served on learn.codencode.my/staff and on staff.codencode.my (where / goes
straight to /staff)."""
import os

from flask import redirect, request


def _env_float(name):
    v = os.environ.get(name)
    try:
        return float(v) if v not in (None, '') else None
    except ValueError:
        return None


def init_staff(app, **helpers):
    from staff import deps
    from staff import models  # noqa: F401  (registers the tables before create_all)
    from staff.routes import bp
    from staff.extensions import csrf, limiter

    deps.set_deps(**helpers)

    c = app.config
    c.setdefault('OFFICE_LAT', _env_float('OFFICE_LAT'))
    c.setdefault('OFFICE_LNG', _env_float('OFFICE_LNG'))
    c.setdefault('OFFICE_RADIUS_M', _env_float('OFFICE_RADIUS_M') or 200.0)
    c.setdefault('OFFICE_NAME', os.environ.get('OFFICE_NAME', 'Mount Austin'))
    c.setdefault('ZOOM_HOST_EMAIL', (os.environ.get('ZOOM_HOST_EMAIL') or 'codencodemy@gmail.com').lower())
    c.setdefault('ZOOM_MAX_CONCURRENT', int(os.environ.get('ZOOM_MAX_CONCURRENT') or 2))
    c.setdefault('STAFF_HOST', (os.environ.get('STAFF_HOST') or 'staff.codencode.my').lower())
    c.setdefault('VAPID_PUBLIC_KEY', os.environ.get('VAPID_PUBLIC_KEY', ''))
    c.setdefault('VAPID_PRIVATE_KEY', os.environ.get('VAPID_PRIVATE_KEY', ''))
    c.setdefault('VAPID_SUBJECT', os.environ.get('VAPID_SUBJECT', 'mailto:codencodemy@gmail.com'))
    # CSRF is enforced on the staff blueprint only (see routes.before_request);
    # the existing LMS JSON API does not send tokens yet.
    c.setdefault('WTF_CSRF_CHECK_DEFAULT', False)
    c.setdefault('WTF_CSRF_TIME_LIMIT', None)
    csrf.init_app(app)
    # In-memory by default (per gunicorn worker); set RATELIMIT_STORAGE_URI=redis://… to share.
    c.setdefault('RATELIMIT_STORAGE_URI', os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'))
    c.setdefault('RATELIMIT_HEADERS_ENABLED', True)
    if not getattr(limiter, '_app_initialized', False):
        limiter.init_app(app)
        limiter._app_initialized = True

    app.register_blueprint(bp)

    @app.before_request
    def _staff_host_root():
        host = (request.host or '').split(':')[0].lower()
        if host == app.config['STAFF_HOST'] and request.path in ('/', '/login', '/lms'):
            return redirect('/staff', code=302)

    @app.cli.command('staff-seed-demo')
    def staff_seed_demo():
        """Sample staff profiles, shifts and sessions (development only)."""
        from staff.seed import seed_demo
        print(seed_demo())

    @app.cli.command('staff-run-jobs')
    def staff_run_jobs():
        """Run the 5-minute staff job once (Zoom report queue + reminders)."""
        from staff.jobs import tick
        tick(app)
        print('done')
