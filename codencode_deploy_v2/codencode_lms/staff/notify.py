"""In-app notifications (the LMS Notification table) plus Web Push, with
email as the fallback when the user has no working push subscription.

Every alert carries a dedupe key per (user, type, occurrence) so a job that
runs every five minutes never sends the same alert twice."""
import json

from flask import current_app
from sqlalchemy.exc import IntegrityError

from models import db, Notification, User
from staff import deps
from staff.models import PushSubscription, StaffNotifyKey


def _claim(key):
    """True the first time a key is seen."""
    try:
        db.session.add(StaffNotifyKey(key=key[:200]))
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def push_enabled():
    c = current_app.config
    return bool(c.get('VAPID_PUBLIC_KEY') and c.get('VAPID_PRIVATE_KEY'))


def _send_push(user_id, title, body, link):
    if not push_enabled():
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return 0
    c = current_app.config
    sent = 0
    for sub in PushSubscription.query.filter_by(user_id=user_id).all():
        try:
            webpush(
                subscription_info={'endpoint': sub.endpoint, 'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                data=json.dumps({'title': title, 'body': body, 'url': link or '/staff'}),
                vapid_private_key=c['VAPID_PRIVATE_KEY'],
                vapid_claims={'sub': c.get('VAPID_SUBJECT') or 'mailto:codencodemy@gmail.com'},
                ttl=3600,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status in (404, 410):          # subscription expired
                db.session.delete(sub)
                db.session.commit()
            else:
                current_app.logger.warning('[staff push] %s', exc)
        except Exception as exc:
            current_app.logger.warning('[staff push] %s', exc)
    return sent


def notify(user_id, kind, occurrence_key, message, link='/staff', title='Codencode Staff', email=True):
    """Send once per (user, kind, occurrence). Returns True if sent now."""
    if not _claim(f'{user_id}:{kind}:{occurrence_key}'):
        return False
    db.session.add(Notification(user_id=user_id, message=message[:500], link=link))
    db.session.commit()
    if _send_push(user_id, title, message, link):
        return True
    if email and deps.send_email:
        user = User.query.get(user_id)
        if user and user.email:
            try:
                host = current_app.config.get('STAFF_HOST') or 'staff.codencode.my'
                url = f'https://{host}{link}' if link and link.startswith('/') else (link or '')
                body = f'<p>{message}</p>' + (f'<p><a href="{url}">Open the Staff Portal</a></p>' if url else '')
                deps.send_email(user.email, title, deps.email_wrapper(title, body) if deps.email_wrapper else body)
            except Exception as exc:
                current_app.logger.warning('[staff email] %s', exc)
    return True


def admin_ids():
    return [u.id for u in User.query.filter_by(role='admin').all()]


def notify_admins(kind, occurrence_key, message, link='/staff', title='Codencode Staff'):
    for uid in admin_ids():
        notify(uid, kind, occurrence_key, message, link, title)
