"""Zoom: webhook signature and URL validation, the participant CSV parser,
UUID encoding, and the report job queue."""
import hashlib
import hmac
import io
import json
import os
import time
from datetime import date, timedelta

from staff import zoom_reports
from staff.models import ZoomReportJob, ZoomParticipantReport, WorkSession
from staff.timeutil import myt_to_utc, utcnow
from tests.conftest import make_user, make_cohort, make_session, login

SECRET = 'zoom-test-secret'
FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'zoom_participants_export.csv')


def signed_post(client, payload, ts=None, secret=SECRET, path='/zoom/staff-webhook'):
    body = json.dumps(payload)
    ts = str(ts if ts is not None else int(time.time() * 1000))
    sig = 'v0=' + hmac.new(secret.encode(), f'v0:{ts}:{body}'.encode(), hashlib.sha256).hexdigest()
    return client.post(path, data=body, content_type='application/json',
                       headers={'x-zm-request-timestamp': ts, 'x-zm-signature': sig})


def ended_payload(uuid='abc/def==', mid='84455667788'):
    return {'event': 'meeting.ended', 'payload': {'object': {
        'uuid': uuid, 'id': int(mid), 'start_time': '2026-10-20T11:28:41Z', 'end_time': '2026-10-20T14:33:05Z'}}}


def test_url_validation_handshake(client):
    r = client.post('/zoom/staff-webhook', json={'event': 'endpoint.url_validation',
                                                 'payload': {'plainToken': 'qgg8vlvZRS6UYooatFL8Aw'}})
    assert r.status_code == 200
    expect = hmac.new(SECRET.encode(), b'qgg8vlvZRS6UYooatFL8Aw', hashlib.sha256).hexdigest()
    assert r.get_json() == {'plainToken': 'qgg8vlvZRS6UYooatFL8Aw', 'encryptedToken': expect}


def test_valid_signature_queues_report_job_10_minutes_later(client):
    r = signed_post(client, ended_payload())
    assert r.status_code == 200
    job = ZoomReportJob.query.one()
    assert job.meeting_uuid == 'abc/def==' and job.zoom_meeting_id == '84455667788'
    delay = (zoom_reports.as_utc(job.due_at) - utcnow()).total_seconds()
    assert 9 * 60 < delay <= 10 * 60


def test_bad_signature_rejected(client):
    r = signed_post(client, ended_payload(), secret='wrong')
    assert r.status_code == 401
    assert ZoomReportJob.query.count() == 0


def test_tampered_body_rejected(client):
    body = json.dumps(ended_payload())
    ts = str(int(time.time() * 1000))
    sig = 'v0=' + hmac.new(SECRET.encode(), f'v0:{ts}:{body}'.encode(), hashlib.sha256).hexdigest()
    r = client.post('/zoom/staff-webhook', data=body.replace('84455667788', '89999999999'),
                    content_type='application/json', headers={'x-zm-request-timestamp': ts, 'x-zm-signature': sig})
    assert r.status_code == 401


def test_stale_timestamp_rejected(client):
    r = signed_post(client, ended_payload(), ts=int((time.time() - 6 * 60) * 1000))
    assert r.status_code == 401
    assert ZoomReportJob.query.count() == 0


def test_existing_webhook_path_also_accepts_meeting_ended(client):
    assert signed_post(client, ended_payload(uuid='u2'), path='/api/integrations/zoom/webhook').status_code == 200
    assert ZoomReportJob.query.count() == 1


def test_csv_parser_reads_zoom_export():
    with open(FIXTURE, encoding='utf-8') as f:
        rep = zoom_reports.parse_zoom_csv(f.read())
    assert rep['meeting_id'] == '84455667788'
    assert rep['local_date'] == date(2026, 10, 20)
    assert len(rep['participants']) == 5
    t = rep['participants'][0]
    assert t['email'] == 'codencodemy@gmail.com' and t['join_at'].startswith('2026-10-20T19:28:41+08')
    assert rep['participants'][3]['name'] == 'Tan, Mei Ling'     # quoted comma survives


def test_csv_parser_rejects_files_without_meeting_block():
    import pytest
    with pytest.raises(ValueError):
        zoom_reports.parse_zoom_csv('Name (Original Name),User Email,Join Time,Leave Time\nA,,10/20/2026 07:00:00 PM,10/20/2026 08:00:00 PM\n')
    with pytest.raises(ValueError):
        zoom_reports.parse_zoom_csv('just,some,csv\n1,2,3\n')


def test_csv_upload_matches_session_and_reports_unreadable_files(client):
    admin, teacher = make_user('admin'), make_user('teacher')
    cohort = make_cohort(teacher, [('Tuesday', '19:30', '22:30')], meeting='84455667788')
    ws = make_session(teacher, myt_to_utc(date(2026, 10, 20), '19:29'), myt_to_utc(date(2026, 10, 20), '22:32'),
                      mode='zoom', cohort_id=cohort.id, zoom_meeting_id='84455667788')
    login(client, admin)
    with open(FIXTURE, 'rb') as f:
        data = {'files': [(io.BytesIO(f.read()), 'py101.csv'), (io.BytesIO(b'nonsense'), 'bad.csv')]}
    r = client.post('/staff/api/admin/reports/upload', data=data, content_type='multipart/form-data')
    body = r.get_json()
    assert r.status_code == 200
    assert [x['file'] for x in body['ok']] == ['py101.csv']
    assert [x['file'] for x in body['failed']] == ['bad.csv']
    rep = ZoomParticipantReport.query.one()
    assert rep.source == 'csv' and rep.local_date == date(2026, 10, 20)
    s = client.get(f'/staff/api/sessions/{ws.id}').get_json()
    # Teacher: two segments, 72.5 + 110.1 = 182.5 min; app 19:29–22:32 = 183 min -> verified,
    # paid at the shorter (Zoom) time.
    assert s['status'] == 'verified'
    assert s['zoom_hours'] == 3.04 and s['paid_hours'] == 3.04 and s['app_hours'] == 3.05


def test_csv_upload_is_admin_only(client):
    login(client, make_user('teacher'))
    r = client.post('/staff/api/admin/reports/upload', data={'files': [(io.BytesIO(b'x'), 'a.csv')]},
                    content_type='multipart/form-data')
    assert r.status_code == 403


def test_uuid_double_encoding():
    assert zoom_reports.encode_uuid('abc123==') == 'abc123%3D%3D'
    assert zoom_reports.encode_uuid('/abc==') == '%252Fabc%253D%253D'
    assert zoom_reports.encode_uuid('ab//c') == 'ab%252F%252Fc'


def test_job_runner_fetches_paginated_report_and_retries(monkeypatch):
    calls = []

    def fake_get(deps, path, params=None):
        calls.append((path, dict(params or {})))
        if 'fail' in path:
            raise RuntimeError('404 report not ready')
        if not (params or {}).get('next_page_token'):
            return {'participants': [{'name': 'Host', 'user_email': 'codencodemy@gmail.com',
                                      'join_time': '2026-10-20T11:30:00Z', 'leave_time': '2026-10-20T14:30:00Z'}],
                    'next_page_token': 'p2'}
        return {'participants': [{'name': 'Student', 'user_email': '', 'join_time': '2026-10-20T11:31:00Z',
                                  'leave_time': '2026-10-20T14:29:00Z'}], 'next_page_token': ''}

    monkeypatch.setattr(zoom_reports, '_api_get', fake_get)
    from models import db
    past = utcnow() - timedelta(minutes=1)
    db.session.add(ZoomReportJob(meeting_uuid='ok-uuid', zoom_meeting_id='84455667788', due_at=past,
                                 meeting_start_at=myt_to_utc(date(2026, 10, 20), '19:30')))
    db.session.add(ZoomReportJob(meeting_uuid='fail/uuid', zoom_meeting_id='81234500011', due_at=past))
    db.session.commit()
    assert zoom_reports.process_due_jobs(None) == 1
    rep = ZoomParticipantReport.query.one()
    assert rep.local_date == date(2026, 10, 20) and len(rep.participants) == 2 and rep.source == 'api'
    assert calls[0][1]['page_size'] == 300
    failed = ZoomReportJob.query.filter_by(meeting_uuid='fail/uuid').one()
    assert failed.tries == 1 and not failed.done and 'not ready' in failed.last_error
    assert zoom_reports.as_utc(failed.due_at) > utcnow()          # backed off
    # After the 6th failure it is no longer picked up.
    failed.tries, failed.due_at = 6, past
    db.session.commit()
    n = len(calls)
    zoom_reports.process_due_jobs(None)
    assert len(calls) == n
