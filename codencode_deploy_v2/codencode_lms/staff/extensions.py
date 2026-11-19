"""CSRF and rate limiting, shared by the LMS login and the staff module."""
from flask import request
from flask_limiter import Limiter
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()


def client_key():
    """Signed-in users are limited per account; everyone else per client IP
    (the first X-Forwarded-For hop, since Railway sits behind a proxy)."""
    try:
        if current_user.is_authenticated:
            return f'user:{current_user.id}'
    except Exception:
        pass
    fwd = request.headers.get('X-Forwarded-For', '')
    return 'ip:' + (fwd.split(',')[0].strip() or request.remote_addr or 'unknown')


limiter = Limiter(key_func=client_key, default_limits=[])
