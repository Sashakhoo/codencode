"""Background jobs, run by the LMS's existing APScheduler.

gunicorn runs two workers and each starts its own scheduler, so every job
takes a Postgres advisory lock first; the worker that does not get it skips
that run. (SQLite in local dev has one process, so no lock is needed.)"""
from contextlib import contextmanager

from sqlalchemy import text

from models import db

LOCK_TICK, LOCK_NIGHTLY, LOCK_MONTHLY = 7421001, 7421002, 7421003


@contextmanager
def single_runner(key):
    if db.engine.dialect.name != 'postgresql':
        yield True
        return
    conn = db.engine.connect()
    got = False
    try:
        got = bool(conn.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': key}).scalar())
        yield got
    finally:
        if got:
            conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})
        conn.close()


def tick(app):
    """Every 5 minutes: due Zoom report jobs, then reminders and auto-close."""
    from staff import deps, service, zoom_reports
    with app.app_context():
        with single_runner(LOCK_TICK) as mine:
            if not mine:
                return
            try:
                zoom_reports.process_due_jobs(deps)
            except Exception:
                db.session.rollback()
                app.logger.exception('[staff] zoom report jobs failed')
            try:
                service.run_reminders()
            except Exception:
                db.session.rollback()
                app.logger.exception('[staff] reminders failed')


def nightly(app):
    """02:00 MYT: pull reports for Zoom sessions from the last 14 days that still have none."""
    from staff import deps, zoom_reports
    with app.app_context():
        with single_runner(LOCK_NIGHTLY) as mine:
            if not mine:
                return
            try:
                res = zoom_reports.backfill(deps)
                app.logger.info('[staff] backfill: %s', res)
            except Exception:
                db.session.rollback()
                app.logger.exception('[staff] backfill failed')


def monthly(app):
    from staff import service
    with app.app_context():
        with single_runner(LOCK_MONTHLY) as mine:
            if mine:
                service.monthly_payroll_notice()


def register_jobs(scheduler, app):
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    tz = 'Asia/Kuala_Lumpur'
    scheduler.add_job(tick, IntervalTrigger(minutes=5), args=[app], id='staff_tick',
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(nightly, CronTrigger(hour=2, minute=0, timezone=tz), args=[app], id='staff_nightly',
                      replace_existing=True, misfire_grace_time=3600)
    scheduler.add_job(monthly, CronTrigger(day=1, hour=9, minute=0, timezone=tz), args=[app], id='staff_monthly',
                      replace_existing=True, misfire_grace_time=3600)
