"""staff/evaluate.py: every status, the shorter-of rule, multi-segment
join/leave and the renamed "Teacher" participant."""
from datetime import datetime, timedelta, timezone

from staff import evaluate as ev

HOST = 'codencodemy@gmail.com'
T0 = datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)   # 7:30 pm MYT


def seg(name, email, start_min, end_min):
    j, l = T0 + timedelta(minutes=start_min), T0 + timedelta(minutes=end_min)
    return {'name': name, 'email': email, 'join_at': j.isoformat(), 'leave_at': l.isoformat(),
            'minutes': end_min - start_min}


def students(n):
    return [seg(f'Student {i}', f's{i}@x.com', 2, 170) for i in range(n)]


def sess(app_min, mode='zoom', **kw):
    return {'mode': mode, 'clock_in_at': T0, 'clock_out_at': T0 + timedelta(minutes=app_min), **kw}


def test_verified_within_10_minutes_pays_shorter():
    parts = [seg('Host', HOST, 0, 175)] + students(5)
    r = ev.evaluate_session(sess(180), parts, HOST, 200)
    assert r['status'] == ev.VERIFIED
    assert r['paid_minutes'] == 175            # shorter of 180 app and 175 zoom
    assert r['students'] == 5 and not r['flagged']


def test_gap_over_10_minutes_is_flagged_but_paid_at_shorter():
    parts = [seg('Host', HOST, 0, 150)] + students(3)
    r = ev.evaluate_session(sess(180), parts, HOST, 200)
    assert r['status'] == ev.GAP and r['flagged']
    assert r['paid_minutes'] == 150
    assert r['label'] == 'Gap 30 min'


def test_gap_where_zoom_is_longer_still_pays_app_time():
    parts = [seg('Host', HOST, 0, 180)]
    r = ev.evaluate_session(sess(120), parts, HOST, 200)
    assert r['status'] == ev.GAP and r['paid_minutes'] == 120


def test_exactly_10_minutes_is_verified():
    r = ev.evaluate_session(sess(180), [seg('Host', HOST, 0, 170)], HOST, 200)
    assert r['status'] == ev.VERIFIED


def test_no_teacher_in_report_pays_zero():
    r = ev.evaluate_session(sess(180), students(6), HOST, 200)
    assert r['status'] == ev.NO_TEACHER and r['paid_minutes'] == 0 and r['flagged']
    assert r['students'] == 6


def test_awaiting_report_pays_zero_and_is_not_flagged():
    r = ev.evaluate_session(sess(180), None, HOST, 200, has_report=False)
    assert r['status'] == ev.AWAITING and r['paid_minutes'] == 0 and not r['flagged']


def test_multi_segment_join_leave_is_summed():
    parts = [seg('Host', HOST, 0, 60), seg('Host', HOST, 70, 175)] + students(2)
    r = ev.evaluate_session(sess(180), parts, HOST, 200)
    assert r['zoom_minutes'] == 165            # 60 + 105
    assert r['status'] == ev.GAP and r['paid_minutes'] == 165
    assert r['zoom_first_join'] == T0 and r['zoom_last_leave'] == T0 + timedelta(minutes=175)


def test_teacher_renamed_participant_used_when_host_absent():
    parts = [seg('Darren – Teacher', 'darren@x.com', 1, 178)] + students(4)
    r = ev.evaluate_session(sess(180), parts, HOST, 200)
    assert r['status'] == ev.VERIFIED and r['paid_minutes'] == 177
    assert r['students'] == 4                  # the teacher is not counted as a student


def test_host_email_wins_over_teacher_name():
    parts = [seg('Host', HOST, 0, 180), seg('Someone teacher-ish', 'a@x.com', 0, 30)]
    r = ev.evaluate_session(sess(180), parts, HOST, 200)
    assert r['zoom_minutes'] == 180 and r['students'] == 1


def test_host_email_match_is_case_insensitive():
    r = ev.evaluate_session(sess(60), [seg('Host', 'CodenCodeMY@Gmail.com', 0, 60)], HOST, 200)
    assert r['status'] == ev.VERIFIED


def test_office_inside_and_outside_geofence():
    inside = ev.evaluate_session(sess(240, mode='office', distance_m=42), None, HOST, 200)
    assert inside['status'] == ev.VERIFIED and inside['paid_minutes'] == 240
    outside = ev.evaluate_session(sess(240, mode='office', distance_m=880), None, HOST, 200)
    assert outside['status'] == ev.OUTSIDE and outside['paid_minutes'] == 0 and outside['flagged']


def test_open_session_is_not_paid_or_flagged():
    r = ev.evaluate_session({'mode': 'office', 'clock_in_at': T0, 'clock_out_at': None, 'distance_m': 5},
                            None, HOST, 200)
    assert r['status'] == ev.OPEN and r['paid_minutes'] == 0 and not r['flagged']


def test_admin_override_replaces_pay_and_clears_flag():
    r = ev.evaluate_session(sess(180, override_paid_minutes=170, review_status='overridden'),
                            students(3), HOST, 200)
    assert r['status'] == ev.NO_TEACHER and r['paid_minutes'] == 170 and not r['flagged']


def test_admin_approval_clears_flag_keeps_calculated_pay():
    r = ev.evaluate_session(sess(180, review_status='approved'), [seg('Host', HOST, 0, 150)], HOST, 200)
    assert r['status'] == ev.GAP and r['paid_minutes'] == 150 and not r['flagged']


def test_auto_closed_session_is_flagged():
    r = ev.evaluate_session(sess(60, mode='office', distance_m=10, auto_closed=True), None, HOST, 200)
    assert r['flagged'] and 'auto-closed' in r['label']
