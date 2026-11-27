"""
Google Calendar sync for class sessions.

When a student is enrolled into a Class (cohort) - via Approve & enrol or
Assign Course - every upcoming session of that Class is put on the business
Google Calendar (codencodemy@gmail.com by default), with the student and the
teacher invited so it appears in their calendars too.

One event per session per Class: the first student creates it, later
students are added as guests of the same event (CalendarEvent remembers the
event id). Guests can't see each other's emails.

Switched off until these are set (see tools/google_calendar_setup.py):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
  GOOGLE_CALENDAR_ID   (optional, default "primary" = the account's own calendar)

Uses plain urllib (no extra dependencies). Never raises: returns a short
note for logs.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
TIMEZONE = "Asia/Kuala_Lumpur"

_token = {"value": None, "expires": 0}
_lock = threading.Lock()


def _cfg(name, default=""):
    return (os.environ.get(name) or default).strip()


def enabled() -> bool:
    return bool(_cfg("GOOGLE_CLIENT_ID") and _cfg("GOOGLE_CLIENT_SECRET") and _cfg("GOOGLE_REFRESH_TOKEN"))


def _access_token() -> str:
    with _lock:
        if _token["value"] and time.time() < _token["expires"] - 60:
            return _token["value"]
        body = urllib.parse.urlencode({
            "client_id": _cfg("GOOGLE_CLIENT_ID"), "client_secret": _cfg("GOOGLE_CLIENT_SECRET"),
            "refresh_token": _cfg("GOOGLE_REFRESH_TOKEN"), "grant_type": "refresh_token",
        }).encode()
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body, method="POST"), timeout=15) as r:
            data = json.loads(r.read().decode())
        _token["value"] = data["access_token"]
        _token["expires"] = time.time() + int(data.get("expires_in", 3600))
        return _token["value"]


def _call(method, path, payload=None, query=None):
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode() if payload is not None else None, method=method,
        headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else {}


def _calendar_path():
    return f"/calendars/{urllib.parse.quote(_cfg('GOOGLE_CALENDAR_ID', 'primary'), safe='')}/events"


def _event_body(course, cohort, n, sess, zoom_link, attendees):
    topic = (sess.get("topic") or "").strip()
    title = f"{course.title}: Class {n}" + (f" - {topic}" if topic else "")
    desc = [title + (f" ({cohort.name})" if cohort.name else "")]
    if zoom_link:
        desc.append(f"Join on Zoom: {zoom_link}")
    desc.append("Student portal: https://learn.codencode.my")
    return {
        "summary": title,
        "description": "\n\n".join(desc),
        "location": zoom_link or "",
        "start": {"dateTime": f"{sess['date_iso']}T{sess['time_start']}:00", "timeZone": TIMEZONE},
        "end": {"dateTime": f"{sess['date_iso']}T{sess['time_end']}:00", "timeZone": TIMEZONE},
        "attendees": [{"email": a} for a in attendees],
        "guestsCanSeeOtherGuests": False,
        "guestsCanInviteOthers": False,
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 60},
                                                          {"method": "email", "minutes": 24 * 60}]},
    }


def sync_enrollment(enrollment, *, db, models, build_timetable, today=None) -> str:
    """Put this enrollment's upcoming class sessions on Google Calendar and
    invite the student (and teacher). Returns a short note; never raises."""
    if not enabled():
        return "calendar: not configured"
    if not enrollment.cohort_id:
        return "calendar: skipped (no Class picked)"
    try:
        cohort = models.Cohort.query.get(enrollment.cohort_id)
        student = models.User.query.get(enrollment.student_id)
        course = cohort.course if cohort else None
        if not (cohort and student and course and student.email):
            return "calendar: skipped (missing class, course or student email)"
        teacher = enrollment.teacher or cohort.teacher or course.teacher
        people = [student.email] + ([teacher.email] if teacher and teacher.email else [])
        today_iso = (today or time.strftime("%Y-%m-%d"))
        tt = build_timetable(course, cohort_id=cohort.id)
        sessions, n = [], 0
        for week in tt["weeks"]:
            for s in week["sessions"]:
                n += 1
                if s.get("date_iso") and s.get("time_start") and s.get("time_end") and s["date_iso"] >= today_iso:
                    sessions.append((n, s))
        if not sessions:
            return "calendar: no upcoming dated sessions"

        created = added = 0
        for n, s in sessions:
            row = models.CalendarEvent.query.filter_by(
                cohort_id=cohort.id, session_date=s["date_iso"], time_start=s["time_start"]).first()
            if row:
                try:
                    ev = _call("GET", f"{_calendar_path()}/{row.google_event_id}")
                except urllib.error.HTTPError as exc:
                    if exc.code in (404, 410):          # deleted in Google: recreate below
                        db.session.delete(row)
                        db.session.commit()
                        row = None
                    else:
                        raise
                if row:
                    have = {a.get("email", "").lower() for a in ev.get("attendees", [])}
                    missing = [p for p in people if p.lower() not in have]
                    if missing:
                        _call("PATCH", f"{_calendar_path()}/{row.google_event_id}",
                              {"attendees": ev.get("attendees", []) + [{"email": p} for p in missing]},
                              {"sendUpdates": "all"})
                        added += 1
                    continue
            ev = _call("POST", _calendar_path(),
                       _event_body(course, cohort, n, s, cohort.zoom_link, people), {"sendUpdates": "all"})
            db.session.add(models.CalendarEvent(cohort_id=cohort.id, session_date=s["date_iso"],
                                                time_start=s["time_start"], google_event_id=ev["id"]))
            db.session.commit()
            created += 1
        return f"calendar: {created} class(es) added, {added} existing class(es) updated"
    except urllib.error.HTTPError as exc:
        db.session.rollback()
        try:
            detail = json.loads(exc.read().decode()).get("error", {})
            detail = detail.get("message") if isinstance(detail, dict) else detail
        except Exception:
            detail = exc.reason
        return f"calendar error {exc.code}: {detail}"
    except Exception as exc:
        db.session.rollback()
        return f"calendar error: {exc}"
