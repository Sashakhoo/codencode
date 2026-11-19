"""Occurrence expansion: weekly, every 2 weeks, skip dates, date range
edges and MYT midnight edges."""
from datetime import date, datetime, timezone

from staff.occurrences import expand_rule, occurrences, rules_overlap
from tests.conftest import make_cohort, make_user


def rule(**kw):
    base = {'kind': 'zoom', 'source': 'cohort', 'ref_id': 1, 'weekday': 1, 'start': '19:30', 'end': '22:30',
            'start_date': date(2026, 10, 1), 'end_date': date(2026, 10, 31), 'every_n_weeks': 1,
            'skip_dates': set(), 'title': 'PY-101'}
    base.update(kw)
    return base


def dates(r, a=date(2026, 9, 1), b=date(2026, 12, 31)):
    return [o['date'] for o in expand_rule(r, a, b)]


def test_weekly_tuesdays_in_october_2026():
    assert dates(rule()) == [date(2026, 10, d) for d in (6, 13, 20, 27)]


def test_every_two_weeks_counts_from_first_matching_weekday():
    # Start on Thu 1 Oct; first Tuesday on/after is 6 Oct, then every 2 weeks.
    assert dates(rule(every_n_weeks=2)) == [date(2026, 10, 6), date(2026, 10, 20)]


def test_every_two_weeks_anchor_when_start_is_the_weekday():
    r = rule(every_n_weeks=2, start_date=date(2026, 10, 13), end_date=date(2026, 11, 30))
    assert dates(r) == [date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 10), date(2026, 11, 24)]


def test_skip_dates_are_removed():
    assert date(2026, 10, 13) not in dates(rule(skip_dates={date(2026, 10, 13)}))


def test_date_range_edges_are_inclusive():
    r = rule(start_date=date(2026, 10, 6), end_date=date(2026, 10, 27))
    assert dates(r) == [date(2026, 10, 6), date(2026, 10, 13), date(2026, 10, 20), date(2026, 10, 27)]
    assert dates(r, a=date(2026, 10, 7), b=date(2026, 10, 26)) == [date(2026, 10, 13), date(2026, 10, 20)]


def test_open_ended_rule_without_dates():
    r = rule(start_date=None, end_date=None)
    assert len(dates(r, date(2026, 10, 1), date(2026, 10, 31))) == 4


def test_times_are_myt_converted_to_utc():
    o = expand_rule(rule(), date(2026, 10, 6), date(2026, 10, 6))[0]
    assert o['start_at'] == datetime(2026, 10, 6, 11, 30, tzinfo=timezone.utc)
    assert o['end_at'] == datetime(2026, 10, 6, 14, 30, tzinfo=timezone.utc)


def test_myt_midnight_edge_early_morning_class_is_previous_utc_day():
    # 00:30 MYT Wed 7 Oct is 16:30 UTC Tue 6 Oct; it still belongs to the MYT Wednesday.
    r = rule(weekday=2, start='00:30', end='01:30')
    o = expand_rule(r, date(2026, 10, 7), date(2026, 10, 7))[0]
    assert o['date'] == date(2026, 10, 7)
    assert o['start_at'] == datetime(2026, 10, 6, 16, 30, tzinfo=timezone.utc)


def test_slot_ending_at_midnight_runs_into_next_day():
    o = expand_rule(rule(start='22:00', end='00:00'), date(2026, 10, 6), date(2026, 10, 6))[0]
    assert o['end_at'] == datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc)


def test_occurrences_reads_cohorts_and_shifts_from_db():
    from models import db
    from staff.models import StaffShift, CohortSkipDate
    t = make_user('teacher')
    c = make_cohort(t, [('Tuesday', '19:30', '22:30')], date(2026, 10, 1), date(2026, 10, 31))
    db.session.add(CohortSkipDate(cohort_id=c.id, date=date(2026, 10, 20)))
    db.session.add(StaffShift(user_id=t.id, title='Admin', days=[2], start_time='14:00', end_time='18:00',
                              start_date=date(2026, 10, 1), end_date=date(2026, 10, 31), status='active'))
    db.session.add(StaffShift(user_id=t.id, title='Pending', days=[3], start_time='14:00', end_time='18:00',
                              start_date=date(2026, 10, 1), end_date=date(2026, 10, 31), status='pending'))
    db.session.commit()
    occ = occurrences(t, date(2026, 10, 1), date(2026, 10, 31))
    zoom = [o['date'].day for o in occ if o['kind'] == 'zoom']
    office = [o['date'].day for o in occ if o['kind'] == 'office']
    assert zoom == [6, 13, 27]
    assert office == [7, 14, 21, 28]      # the pending shift is not included


def test_rules_overlap():
    a = rule(start='19:30', end='22:30')
    assert rules_overlap(a, rule(start='22:00', end='23:00'))
    assert not rules_overlap(a, rule(start='22:30', end='23:00'))        # touching is fine
    assert not rules_overlap(a, rule(weekday=2))
    assert not rules_overlap(a, rule(start_date=date(2026, 11, 1), end_date=date(2026, 11, 30)))
