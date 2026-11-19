"""LMS helpers the staff module reuses, handed over by app.py at start-up
(staff.init_staff) so the staff package never imports app.py directly."""
zoom_configured = None
zoom_access_token = None
zoom_token_cache = {}
create_recurring_zoom_meeting = None
send_email = None
email_wrapper = None


def set_deps(**kwargs):
    g = globals()
    for k, v in kwargs.items():
        if k not in g:
            raise KeyError(k)
        g[k] = v
