"""Zoom participant reports: CSV upload parser, Report API fetch, the
webhook-fed job queue and the nightly backfill."""
import csv
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from staff.timeutil import MYT, UTC, utcnow, as_utc, myt_date

MAX_TRIES = 6


# ── CSV upload ──────────────────────────────────────────────

def _parse_csv_time(value):
    """Zoom exports local times as 'MM/DD/YYYY hh:mm:ss AM/PM' (sometimes
    24-hour, sometimes without seconds). Interpreted as Malaysia time."""
    value = (value or '').strip()
    for fmt in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M'):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=MYT)
        except ValueError:
            continue
    raise ValueError(f'Unrecognised time {value!r}')


def parse_zoom_csv(text):
    """Parse Zoom's "Export with meeting data" participant CSV.

    Returns {'meeting_id', 'local_date', 'participants'}; raises ValueError
    when the file is not in that format."""
    text = text.lstrip('﻿')
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text))]
    rows = [r for r in rows if any(r)]
    head = next((i for i, r in enumerate(rows) if r and re.search(r'meeting id', r[0], re.I)), None)
    if head is None or head + 1 >= len(rows):
        raise ValueError('No meeting header block. Export with "Show meeting data" ticked.')
    header, values = [h.lower() for h in rows[head]], rows[head + 1]
    meeting_id = re.sub(r'\D', '', values[0])
    if not re.fullmatch(r'\d{9,11}', meeting_id):
        raise ValueError('Meeting ID in the header block is not 9–11 digits.')
    meeting_start = None
    if 'start time' in header and len(values) > header.index('start time'):
        try:
            meeting_start = _parse_csv_time(values[header.index('start time')])
        except ValueError:
            pass

    ph = next((i for i, r in enumerate(rows) if i > head and any(re.search(r'join time', c, re.I) for c in r)), None)
    if ph is None:
        raise ValueError('No participant table (no "Join Time" column).')
    cols = [c.lower() for c in rows[ph]]

    def ix(key):
        return next((i for i, c in enumerate(cols) if key in c), None)
    i_name, i_email, i_join, i_leave, i_dur = ix('name'), ix('email'), ix('join time'), ix('leave time'), ix('duration')
    if i_join is None or i_leave is None:
        raise ValueError('Participant table has no Join/Leave Time columns.')

    participants = []
    for r in rows[ph + 1:]:
        if len(r) <= max(i_join, i_leave) or not r[i_join]:
            continue
        try:
            j, l = _parse_csv_time(r[i_join]), _parse_csv_time(r[i_leave])
        except ValueError:
            continue
        minutes = max(0.0, (l - j).total_seconds() / 60)
        participants.append({
            'name': r[i_name] if i_name is not None and i_name < len(r) else '',
            'email': (r[i_email] if i_email is not None and i_email < len(r) else '').lower(),
            'join_at': j.isoformat(), 'leave_at': l.isoformat(), 'minutes': round(minutes, 2),
        })
    if not participants:
        raise ValueError('The participant table is empty.')
    local_date = (meeting_start or min(_parse_csv_time_iso(p['join_at']) for p in participants)).date()
    return {'meeting_id': meeting_id, 'local_date': local_date, 'participants': participants}


def _parse_csv_time_iso(v):
    return datetime.fromisoformat(v)


# ── Storage ─────────────────────────────────────────────────

def upsert_report(meeting_id, local_date, participants, source, meeting_uuid=None):
    from models import db
    from staff.models import ZoomParticipantReport
    meeting_id = str(meeting_id)
    rep = ZoomParticipantReport.query.filter_by(zoom_meeting_id=meeting_id, local_date=local_date).first()
    if rep is None:
        rep = ZoomParticipantReport(zoom_meeting_id=meeting_id, local_date=local_date)
        db.session.add(rep)
    elif (source == 'api' and rep.source == 'api' and meeting_uuid and rep.meeting_uuid
          and meeting_uuid not in rep.meeting_uuid.split(',')):
        # The meeting was restarted the same day: a second instance (new UUID).
        seen = {(p.get('email'), p.get('name'), p.get('join_at')) for p in rep.participants or []}
        participants = list(rep.participants or []) + [
            p for p in participants if (p.get('email'), p.get('name'), p.get('join_at')) not in seen]
        meeting_uuid = f'{rep.meeting_uuid},{meeting_uuid}'
    rep.participants = participants
    rep.source = source
    rep.meeting_uuid = meeting_uuid or rep.meeting_uuid
    rep.fetched_at = utcnow()
    db.session.commit()
    try:
        from staff import service
        service.after_report_matched(meeting_id, local_date)
    except Exception:  # notifications never block storing a report
        db.session.rollback()
    return rep


# ── Zoom Report API ─────────────────────────────────────────

def encode_uuid(uuid):
    """Zoom wants UUIDs that start with '/' or contain '//' double-encoded."""
    once = urllib.parse.quote(uuid, safe='')
    if uuid.startswith('/') or '//' in uuid:
        return urllib.parse.quote(once, safe='')
    return once


def _api_get(deps, path, params=None):
    token = deps.zoom_access_token()
    if not token:
        raise RuntimeError('Zoom is not configured (ZOOM_ACCOUNT_ID / ZOOM_CLIENT_ID / ZOOM_CLIENT_SECRET).')
    api_url = deps.zoom_token_cache.get('api_url') or 'https://api.zoom.us'
    url = f'{api_url}/v2{path}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode())


def _api_time_to_myt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(MYT)


def fetch_participants(deps, meeting_uuid):
    out, token = [], ''
    while True:
        params = {'page_size': 300}
        if token:
            params['next_page_token'] = token
        body = _api_get(deps, f'/report/meetings/{encode_uuid(meeting_uuid)}/participants', params)
        for p in body.get('participants') or []:
            j, l = _api_time_to_myt(p.get('join_time')), _api_time_to_myt(p.get('leave_time'))
            if not j or not l:
                continue
            out.append({'name': p.get('name') or '', 'email': (p.get('user_email') or '').lower(),
                        'join_at': j.isoformat(), 'leave_at': l.isoformat(),
                        'minutes': round(max(0.0, (l - j).total_seconds() / 60), 2)})
        token = body.get('next_page_token') or ''
        if not token:
            return out


def _local_date_for(meeting_start_at, participants):
    if meeting_start_at:
        return myt_date(meeting_start_at)
    joins = [datetime.fromisoformat(p['join_at']) for p in participants]
    return min(joins).astimezone(MYT).date() if joins else None


# ── Webhook queue ───────────────────────────────────────────

def enqueue_from_webhook(payload):
    """meeting.ended -> fetch the participant report 10 minutes later."""
    from models import db
    from staff.models import ZoomReportJob
    obj = (payload.get('payload') or {}).get('object') or {}
    uuid, mid = obj.get('uuid'), str(obj.get('id') or '')
    if not uuid or not mid:
        return None
    start = obj.get('start_time')
    start_at = datetime.fromisoformat(start.replace('Z', '+00:00')) if start else None
    if ZoomReportJob.query.filter_by(meeting_uuid=uuid, done=False).first():
        return None
    job = ZoomReportJob(meeting_uuid=uuid, zoom_meeting_id=mid, meeting_start_at=start_at,
                        due_at=utcnow() + timedelta(minutes=10))
    db.session.add(job)
    db.session.commit()
    return job


def process_due_jobs(deps, now=None):
    from models import db
    from staff.models import ZoomReportJob
    now = now or utcnow()
    jobs = (ZoomReportJob.query.filter(ZoomReportJob.done.is_(False), ZoomReportJob.tries < MAX_TRIES)
            .order_by(ZoomReportJob.due_at).limit(50).all())
    processed = 0
    for job in jobs:
        if as_utc(job.due_at) > now:
            continue
        try:
            parts = fetch_participants(deps, job.meeting_uuid)
            local_date = _local_date_for(as_utc(job.meeting_start_at), parts)
            if local_date is None:
                raise RuntimeError('Report has no participants yet')
            job.done = True
            job.last_error = None
            db.session.commit()
            upsert_report(job.zoom_meeting_id, local_date, parts, 'api', job.meeting_uuid)
            processed += 1
        except Exception as exc:  # retry with backoff: 5, 10, 20, 40, 80 min
            db.session.rollback()
            job.tries = (job.tries or 0) + 1
            job.last_error = str(exc)[:1000]
            job.due_at = now + timedelta(minutes=5 * 2 ** (job.tries - 1))
            db.session.commit()
    return processed


# ── Nightly backfill ────────────────────────────────────────

def backfill(deps, days=14, now=None):
    """For Zoom sessions in the last `days` days that still have no report,
    list the meeting's past instances and pull the matching ones."""
    from staff.models import WorkSession, ZoomParticipantReport
    now = now or utcnow()
    since = now - timedelta(days=days)
    sessions = WorkSession.query.filter(WorkSession.mode == 'zoom', WorkSession.clock_in_at >= since,
                                        WorkSession.zoom_meeting_id.isnot(None)).all()
    need = {}
    for s in sessions:
        d = myt_date(s.clock_in_at)
        if not ZoomParticipantReport.query.filter_by(zoom_meeting_id=s.zoom_meeting_id, local_date=d).first():
            need.setdefault(s.zoom_meeting_id, set()).add(d)
    pulled, errors = 0, []
    for mid, dates in need.items():
        try:
            body = _api_get(deps, f'/past_meetings/{mid}/instances')
        except Exception as exc:
            errors.append(f'{mid}: {exc}')
            continue
        for inst in body.get('meetings') or []:
            start = _api_time_to_myt(inst.get('start_time'))
            if not start or start.date() not in dates:
                continue
            try:
                parts = fetch_participants(deps, inst['uuid'])
                if parts:
                    upsert_report(mid, start.date(), parts, 'api', inst['uuid'])
                    pulled += 1
            except Exception as exc:
                errors.append(f'{mid} {start.date()}: {exc}')
    return {'pulled': pulled, 'errors': errors, 'meetings_checked': len(need)}
