"""
codencode.my LMS — Flask Backend
=================================
  - Single app.py  (no blueprints needed at this scale)
  - SQLAlchemy ORM + PostgreSQL (falls back to SQLite for local dev)
  - Flask-Login for session auth
  - All file uploads go to /uploads on disk
  - JSON API consumed by the frontend
  - Roles: student | teacher | admin
"""

import os
import uuid
import smtplib
import ssl
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import (Flask, request, jsonify, send_from_directory,
                   session, g)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from werkzeug.utils import secure_filename

import io
import csv
from models import (db, User, Course, Enrollment, Recording,
                    WatchLog, Material, Assignment, Submission, Attendance,
                    TimetableSession, Session, SessionParticipant,
                    Notification, Announcement,
                    LoginLog, Certificate,
                    Quiz, QuizQuestion, QuizChoice, QuizAttempt, QuizAnswer,
                    DiscussionPost, DiscussionReply, PostUpvote,
                    LastLesson, Cohort)

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
app = Flask(__name__, static_folder='static', template_folder='templates')

# Railway supplies DATABASE_URL as "postgres://…" but SQLAlchemy 2.x requires "postgresql://…"
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///codencode_lms.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'db9564268b5109bb02c25a568feaaeb8f'),
    SQLALCHEMY_DATABASE_URI=_db_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=os.path.join(os.path.dirname(__file__), 'uploads'),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024 * 1024,
    ALLOWED_VIDEO={'mp4', 'mov', 'mkv', 'webm'},
    ALLOWED_MATERIAL={'pdf', 'py', 'ipynb', 'zip', 'csv', 'txt', 'docx', 'pptx'},
    ALLOWED_SUBMISSION={'py', 'ipynb', 'zip', 'pdf', 'txt'},
    ALLOWED_RECEIPT={'pdf', 'jpg', 'jpeg', 'png', 'heic'},
)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'serve_frontend'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'receipts'), exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────
# Email utility
# ─────────────────────────────────────────────
_SMTP_HOST      = os.environ.get('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
_SMTP_PORT      = 465
_EMAIL_FROM     = os.environ.get('EMAIL_FROM',  'codencode@gmail.com')
_EMAIL_USER     = os.environ.get('EMAIL_USER',  '')
_EMAIL_PASS     = os.environ.get('EMAIL_PASS',  '')
_BUSINESS_NAME  = os.environ.get('BUSINESS_NAME',    'CODE N CODE SOLUTION')
_BUSINESS_SSM   = os.environ.get('BUSINESS_SSM',     '202603072017 (AS0511861-M)')
_BUSINESS_ADDR  = os.environ.get('BUSINESS_ADDRESS', '16, Pengkalan Tiara 35, Taman Pengkalan Tiara, 31650 Ipoh, Perak')

# ─────────────────────────────────────────────
# Twilio / WhatsApp
# ─────────────────────────────────────────────
_TWILIO_SID   = os.environ.get('TWILIO_ACCOUNT_SID', '')
_TWILIO_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN',  '')
_TWILIO_FROM  = os.environ.get('TWILIO_WHATSAPP_FROM', 'whatsapp:+60xxxxxxxxxx')


def _normalize_phone(phone: str) -> str:
    """Convert Malaysian phone (011-2345678 / 0112345678) → +601xxxxxxxx"""
    digits = re.sub(r'\D', '', phone or '')
    if digits.startswith('60'):
        return '+' + digits
    if digits.startswith('0'):
        return '+6' + digits
    return '+60' + digits


def send_whatsapp(to_phone: str, body: str) -> bool:
    """Send a WhatsApp message via Twilio. Returns True on success."""
    if not _TWILIO_SID or not _TWILIO_TOKEN or 'xxxxxxxxxx' in _TWILIO_FROM:
        app.logger.warning('Twilio not configured — skipping WhatsApp to %s', to_phone)
        return False
    try:
        from twilio.rest import Client
        client = Client(_TWILIO_SID, _TWILIO_TOKEN)
        to_wa = 'whatsapp:' + _normalize_phone(to_phone)
        client.messages.create(from_=_TWILIO_FROM, to=to_wa, body=body)
        app.logger.info('WhatsApp sent to %s', to_phone)
        return True
    except Exception as exc:
        app.logger.error('WhatsApp failed to %s: %s', to_phone, exc)
        return False


def send_email(to: str, subject: str, html_body: str):
    """Send a single HTML email. Returns True on success, False on failure."""
    if not _EMAIL_USER or not _EMAIL_PASS:
        app.logger.warning('Email not configured — skipping send to %s', to)
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f'codencode.my <{_EMAIL_FROM}>'
        msg['To']      = to
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, context=ctx) as server:
            server.login(_EMAIL_USER, _EMAIL_PASS)
            server.sendmail(_EMAIL_FROM, to, msg.as_string())
        return True
    except Exception as exc:
        app.logger.error('Email send failed to %s: %s', to, exc)
        return False


def send_email_bulk(recipients: list[str], subject: str, html_body: str):
    """Send the same email to a list of addresses."""
    results = {r: send_email(r, subject, html_body) for r in recipients}
    return results


def send_email_with_attachment(to: str, subject: str, html_body: str,
                                attachment_bytes: bytes, attachment_filename: str) -> bool:
    """Send an HTML email with a single binary attachment (e.g. PDF receipt)."""
    if not _EMAIL_USER or not _EMAIL_PASS:
        app.logger.warning('Email not configured — skipping send to %s', to)
        return False
    try:
        from email.mime.base import MIMEBase
        from email import encoders as _enc

        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From']    = f'codencode.my <{_EMAIL_FROM}>'
        msg['To']      = to
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment_bytes)
        _enc.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=attachment_filename)
        msg.attach(part)

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, context=ctx) as server:
            server.login(_EMAIL_USER, _EMAIL_PASS)
            server.sendmail(_EMAIL_FROM, to, msg.as_string())
        return True
    except Exception as exc:
        app.logger.error('Email (with attachment) failed to %s: %s', to, exc)
        return False


def generate_receipt_pdf(enrollment) -> bytes:
    """Return bytes of an A4 PDF official receipt for a paid enrollment."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as _cv
    from reportlab.lib.colors import HexColor, white
    import io as _io

    buf  = _io.BytesIO()
    c    = _cv.Canvas(buf, pagesize=A4)
    W, H = A4

    green    = HexColor('#00c485')
    dk      = HexColor('#0a3d2a')
    muted   = HexColor('#666666')
    body    = HexColor('#222222')
    pale    = HexColor('#f0fdf4')

    s      = enrollment.student
    course = enrollment.course
    rcpt   = f'RCP-{enrollment.id:05d}'
    paid_d = (enrollment.paid_at or datetime.utcnow()).strftime('%d %B %Y')
    now_d  = datetime.utcnow().strftime('%d %B %Y')
    amt    = enrollment.payment_amount
    method = enrollment.payment_method or 'N/A'

    # ── Header ────────────────────────────────────────────────────────────────
    c.setFillColor(dk)
    c.rect(0, H - 52*mm, W, 52*mm, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont('Helvetica-Bold', 20)
    c.drawString(20*mm, H - 20*mm, _BUSINESS_NAME)
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#7ec8a0'))
    c.drawString(20*mm, H - 27*mm, 'OFFICIAL RECEIPT  ·  SSM NO. ' + _BUSINESS_SSM)
    c.setFont('Helvetica', 7)
    c.setFillColor(HexColor('#5a9e78'))
    c.drawString(20*mm, H - 33*mm, _BUSINESS_ADDR)

    c.setFillColor(white)
    c.setFont('Helvetica-Bold', 14)
    c.drawRightString(W - 20*mm, H - 20*mm, rcpt)
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#7ec8a0'))
    c.drawRightString(W - 20*mm, H - 27*mm, f'Issued: {now_d}')

    # Green divider
    c.setStrokeColor(green)
    c.setLineWidth(2)
    c.line(0, H - 55*mm, W, H - 55*mm)

    # ── Bill To ───────────────────────────────────────────────────────────────
    y = H - 72*mm
    c.setFillColor(pale)
    c.setStrokeColor(green)
    c.setLineWidth(0.5)
    c.roundRect(15*mm, y - 42*mm, 83*mm, 43*mm, 3, fill=1, stroke=1)

    c.setFillColor(dk)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(20*mm, y - 5*mm, 'BILL TO')
    c.setFillColor(body)
    c.setFont('Helvetica-Bold', 12)
    c.drawString(20*mm, y - 13*mm, s.name)
    c.setFont('Helvetica', 9)
    c.setFillColor(muted)
    c.drawString(20*mm, y - 20*mm, s.email)
    if s.phone:
        c.drawString(20*mm, y - 27*mm, s.phone)
    if s.ic_number:
        c.drawString(20*mm, y - 34*mm, f'IC / Passport: {s.ic_number}')

    # ── Course Details ────────────────────────────────────────────────────────
    c.setFillColor(pale)
    c.setStrokeColor(green)
    c.roundRect(103*mm, y - 42*mm, 92*mm, 43*mm, 3, fill=1, stroke=1)

    c.setFillColor(dk)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(108*mm, y - 5*mm, 'COURSE')
    c.setFillColor(body)
    c.setFont('Helvetica-Bold', 11)
    title = course.title
    if len(title) > 26:
        c.drawString(108*mm, y - 13*mm, title[:26])
        c.setFont('Helvetica', 9)
        c.drawString(108*mm, y - 19*mm, title[26:52])
        nr = y - 26*mm
    else:
        c.drawString(108*mm, y - 13*mm, title)
        nr = y - 20*mm
    c.setFont('Helvetica', 9)
    c.setFillColor(muted)
    if enrollment.class_format:
        c.drawString(108*mm, nr, f'Format: {enrollment.class_format.upper()}')
        nr -= 7*mm
    if enrollment.class_timing:
        c.drawString(108*mm, nr, ('Schedule: ' + enrollment.class_timing)[:38])

    # ── Payment Details ───────────────────────────────────────────────────────
    y2 = y - 58*mm
    c.setFillColor(HexColor('#f8f8f8'))
    c.setStrokeColor(HexColor('#dddddd'))
    c.roundRect(15*mm, y2 - 46*mm, 180*mm, 47*mm, 3, fill=1, stroke=1)

    c.setFillColor(dk)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(20*mm, y2 - 5*mm, 'PAYMENT DETAILS')

    c.setFillColor(muted)
    c.setFont('Helvetica', 7)
    c.drawString(20*mm, y2 - 13*mm, 'AMOUNT PAID')
    c.setFillColor(green)
    c.setFont('Helvetica-Bold', 24)
    amt_str = f'RM {amt:,.2f}' if amt is not None else 'RM  —'
    c.drawString(20*mm, y2 - 25*mm, amt_str)

    c.setFillColor(muted)
    c.setFont('Helvetica', 7)
    c.drawString(110*mm, y2 - 13*mm, 'PAYMENT METHOD')
    c.setFillColor(body)
    c.setFont('Helvetica-Bold', 11)
    c.drawString(110*mm, y2 - 21*mm, method)

    c.setFillColor(muted)
    c.setFont('Helvetica', 7)
    c.drawString(110*mm, y2 - 30*mm, 'DATE PAID')
    c.setFillColor(body)
    c.setFont('Helvetica-Bold', 11)
    c.drawString(110*mm, y2 - 38*mm, paid_d)

    # PAID badge
    c.setFillColor(green)
    c.roundRect(148*mm, y2 - 30*mm, 42*mm, 14*mm, 4, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont('Helvetica-Bold', 13)
    c.drawCentredString(169*mm, y2 - 23*mm, 'PAID')

    # ── Footer ────────────────────────────────────────────────────────────────
    c.setFillColor(HexColor('#eeeeee'))
    c.rect(0, 0, W, 22*mm, fill=1, stroke=0)
    c.setFillColor(muted)
    c.setFont('Helvetica', 7.5)
    c.drawCentredString(W / 2, 14*mm,
        f'{_BUSINESS_NAME}   ·   SSM: {_BUSINESS_SSM}   ·   learn.codencode.my')
    c.setFont('Helvetica', 7)
    c.setFillColor(HexColor('#aaaaaa'))
    c.drawCentredString(W / 2, 8*mm,
        'This is an official receipt. Please retain for your records.')

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


# ── Email templates ───────────────────────────────────────────────────────────

def _email_wrapper(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body{{font-family:'Lato',Arial,sans-serif;background:#0D2625;margin:0;padding:24px}}
  .card{{background:#1e3530;border:1px solid rgba(198,206,197,.18);border-radius:12px;
         max-width:560px;margin:0 auto;padding:36px 40px}}
  .logo{{font-size:20px;font-weight:700;color:#C6CEC5;letter-spacing:-.02em;margin-bottom:24px}}
  .logo span{{color:#7ec8a0}}
  h2{{color:#E8F0E9;margin:0 0 16px;font-size:22px}}
  p{{color:#A4B4A4;line-height:1.6;margin:0 0 14px}}
  .btn{{display:inline-block;background:#30463D;color:#C6CEC5;border:1px solid rgba(198,206,197,.3);
        border-radius:8px;padding:12px 24px;text-decoration:none;font-weight:700;margin-top:8px}}
  .footer{{color:#627160;font-size:11px;margin-top:24px;border-top:1px solid rgba(198,206,197,.1);
           padding-top:16px}}
  .badge{{display:inline-block;background:rgba(126,200,160,.15);color:#7ec8a0;
          border:1px solid rgba(126,200,160,.3);border-radius:4px;
          padding:2px 10px;font-size:12px;font-weight:700}}
</style></head>
<body><div class="card">
  <div class="logo">codencode<span>.my</span></div>
  <h2>{title}</h2>
  {body_html}
  <div class="footer">learn.codencode.my &nbsp;·&nbsp; This is an automated message, please do not reply.</div>
</div></body></html>"""


def email_welcome(student_name: str, email: str, course_title: str):
    body = f"""
    <p>Hi <strong>{student_name}</strong>,</p>
    <p>Welcome to <strong>{course_title}</strong> on codencode.my! Your account is ready.</p>
    <p>Log in now to access your course materials, timetable, and assignments.</p>
    <a class="btn" href="https://learn.codencode.my">Start Learning →</a>
    """
    return send_email(email, f'Welcome to {course_title} — codencode.my', _email_wrapper('Welcome aboard! 🎉', body))


def email_assignment_graded(student_name: str, email: str, assignment_title: str, score, feedback: str):
    body = f"""
    <p>Hi <strong>{student_name}</strong>,</p>
    <p>Your assignment <strong>{assignment_title}</strong> has been graded.</p>
    <p><span class="badge">Score: {score} / 100</span></p>
    {'<p><em>' + feedback + '</em></p>' if feedback else ''}
    <a class="btn" href="https://learn.codencode.my">View Feedback →</a>
    """
    return send_email(email, f'Assignment graded: {assignment_title}', _email_wrapper('Assignment Result', body))


def email_certificate_issued(student_name: str, email: str, course_title: str, cert_number: str, cert_id: int):
    body = f"""
    <p>Hi <strong>{student_name}</strong>,</p>
    <p>Congratulations! You have successfully completed <strong>{course_title}</strong>.</p>
    <p><span class="badge">{cert_number}</span></p>
    <p>Your certificate is ready to download and share on LinkedIn.</p>
    <a class="btn" href="https://learn.codencode.my/api/certificates/{cert_id}/download">Download Certificate →</a>
    """
    return send_email(email, f'Your Certificate for {course_title} is Ready!', _email_wrapper('Certificate Issued 🎓', body))


def email_new_material(student_name: str, email: str, course_title: str, material_title: str, week: int):
    body = f"""
    <p>Hi <strong>{student_name}</strong>,</p>
    <p>New content is available in <strong>{course_title}</strong>:</p>
    <p><strong>Week {week} — {material_title}</strong></p>
    <a class="btn" href="https://learn.codencode.my">View Material →</a>
    """
    return send_email(email, f'New material: {material_title} — codencode.my', _email_wrapper('New Content Available', body))


def email_session_reminder(student_name: str, email: str, session_title: str, session_dt: str, zoom_link: str):
    zoom_btn = f'<a class="btn" href="{zoom_link}">Join Session →</a>' if zoom_link else ''
    body = f"""
    <p>Hi <strong>{student_name}</strong>,</p>
    <p>Reminder: your session is starting soon.</p>
    <p><strong>{session_title}</strong><br><span class="badge">{session_dt}</span></p>
    {zoom_btn}
    """
    return send_email(email, f'Session reminder: {session_title}', _email_wrapper('Upcoming Session ⏰', body))


def email_announcement(student_name: str, email: str, announcement_title: str, announcement_body: str):
    body = f"""
    <p>Hi <strong>{student_name}</strong>,</p>
    <p>{announcement_body}</p>
    <a class="btn" href="https://learn.codencode.my">View on Portal →</a>
    """
    return send_email(email, announcement_title, _email_wrapper(announcement_title, body))


def email_payment_receipt(enrollment) -> bool:
    """Generate PDF receipt and send it to the student by email."""
    s = enrollment.student
    if not s or not s.email:
        return False
    try:
        pdf_bytes = generate_receipt_pdf(enrollment)
    except Exception as exc:
        app.logger.error('Receipt PDF generation failed for enrollment %s: %s', enrollment.id, exc)
        return False

    rcpt_no  = f'RCP-{enrollment.id:05d}'
    amt_str  = f'RM {enrollment.payment_amount:,.2f}' if enrollment.payment_amount else '—'
    paid_d   = (enrollment.paid_at or datetime.utcnow()).strftime('%d %B %Y')
    body = f"""
    <p>Hi <strong>{s.name}</strong>,</p>
    <p>Thank you! Your payment for <strong>{enrollment.course.title}</strong> has been received and confirmed.</p>
    <p>
      <span class="badge">{rcpt_no}</span>&nbsp;
      <span class="badge">{amt_str}</span>
    </p>
    <p>Your official receipt is attached to this email. Please keep it for your records.</p>
    <p style="color:#A4B4A4;font-size:13px">Payment date: {paid_d}</p>
    <a class="btn" href="https://learn.codencode.my">Go to Student Portal →</a>
    """
    return send_email_with_attachment(
        s.email,
        f'Payment Confirmed — {enrollment.course.title} | codencode.my',
        _email_wrapper('Payment Received! 🎉', body),
        pdf_bytes,
        f'{rcpt_no}.pdf'
    )


def email_invoice(enrollment) -> bool:
    """Send invoice to student by email."""
    s = enrollment.student
    if not s or not s.email:
        return False
    inv_num  = f'INV-{1110 + enrollment.id}'
    amt_str  = f'RM {enrollment.payment_amount:,.2f}' if enrollment.payment_amount else '—'
    issued   = datetime.utcnow().strftime('%d %B %Y')
    body = f"""
    <p>Hi <strong>{s.name}</strong>,</p>
    <p>Please find your invoice for <strong>{enrollment.course.title}</strong> below.</p>
    <div style="background:#0d2a1c;border-radius:8px;padding:16px;margin:16px 0">
      <p style="margin:4px 0"><strong>Invoice No:</strong> {inv_num}</p>
      <p style="margin:4px 0"><strong>Course:</strong> {enrollment.course.title}</p>
      <p style="margin:4px 0"><strong>Amount:</strong> {amt_str}</p>
      <p style="margin:4px 0"><strong>Status:</strong> {enrollment.payment_status.upper()}</p>
      <p style="margin:4px 0"><strong>Issued:</strong> {issued}</p>
    </div>
    <p>If you have any questions about this invoice, please reply to this email.</p>
    <a class="btn" href="https://learn.codencode.my">Go to Student Portal →</a>
    """
    return send_email(
        s.email,
        f'Invoice {inv_num} — {enrollment.course.title} | codencode.my',
        _email_wrapper('Your Invoice 🧾', body)
    )


def email_enrollment_confirmation(enrollment) -> bool:
    """Send class schedule and preparation guide to newly confirmed student."""
    s = enrollment.student
    if not s or not s.email:
        return False

    course = enrollment.course

    # Build schedule lines from class_timing or cohort schedule
    sched_lines = []
    if enrollment.class_timing:
        sched_lines.append(enrollment.class_timing)
    if enrollment.cohort and enrollment.cohort.schedule:
        import json as _json
        try:
            slots = _json.loads(enrollment.cohort.schedule)
            for sl in slots:
                day, st, en = sl.get('day',''), sl.get('start',''), sl.get('end','')
                if day and st:
                    sched_lines.append(f'{day}: {st}–{en}')
        except Exception:
            pass
    sched_html = ''.join(f'<li>{ln}</li>' for ln in sched_lines) if sched_lines \
                 else '<li>To be confirmed — check your student portal</li>'

    # First class date
    start_html = ''
    if enrollment.cohort and enrollment.cohort.start_date:
        start_html = f"<p><strong>First Class:</strong> {enrollment.cohort.start_date.strftime('%A, %d %B %Y')}</p>"
    elif course.start_date:
        start_html = f"<p><strong>First Class:</strong> {course.start_date.strftime('%A, %d %B %Y')}</p>"

    # What to prepare — tailored by programme keyword
    prog = (course.programme or course.title or '').lower()
    if any(k in prog for k in ('machine learning', ' ml', 'data science', 'deep learning', 'ai ')):
        prep = [
            'Laptop — Windows, Mac, or Linux',
            'Python 3.10+ installed',
            'Jupyter Notebook or VSCode with Python extension',
            'pip packages: numpy, pandas, matplotlib, scikit-learn (we will guide installation)',
            'Stable internet connection (min 5 Mbps)',
            'Notebook and pen',
        ]
    else:
        prep = [
            'Laptop — Windows, Mac, or Linux',
            'Python 3.10+ — <a href="https://www.python.org/downloads/" style="color:#7ec8a0">python.org/downloads</a>',
            'Visual Studio Code — <a href="https://code.visualstudio.com/" style="color:#7ec8a0">code.visualstudio.com</a>',
            'Stable internet connection (min 5 Mbps)',
            'Notebook and pen',
        ]
    prep_html = ''.join(f'<li style="margin-bottom:6px">{it}</li>' for it in prep)

    body = f"""
    <p>Hi <strong>{s.name}</strong>,</p>
    <p>You are officially enrolled in <strong>{course.title}</strong>. Here is everything you need before your first class.</p>
    {start_html}
    <p><strong>Class Schedule:</strong></p>
    <ul style="color:#A4B4A4;padding-left:18px;margin:6px 0 16px">{sched_html}</ul>
    <p><strong>What to Prepare:</strong></p>
    <ul style="color:#A4B4A4;padding-left:18px;margin:6px 0 16px">{prep_html}</ul>
    <p>Log in to your student portal to view your timetable, materials, and assignments.</p>
    <a class="btn" href="https://learn.codencode.my">Open Student Portal →</a>
    <p style="color:#627160;font-size:12px;margin-top:18px">
      Questions? Email us at <a href="mailto:codencode@gmail.com" style="color:#7ec8a0">codencode@gmail.com</a>
    </p>
    """
    return send_email(
        s.email,
        f'You\'re In! Class Details for {course.title} — codencode.my',
        _email_wrapper('Enrolment Confirmed ✅', body)
    )


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def allowed(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def save_upload(file, subfolder, allowed_set):
    if not file or file.filename == '':
        raise ValueError('No file provided')
    if not allowed(file.filename, allowed_set):
        raise ValueError(f'File type not allowed. Allowed: {allowed_set}')
    ext = file.filename.rsplit('.', 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(dest, exist_ok=True)
    file.save(os.path.join(dest, stored_name))
    return stored_name, file.filename


def human_size(path):
    try:
        b = os.path.getsize(path)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except Exception:
        return '—'


def teacher_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role not in ('teacher', 'admin'):
            return jsonify({'error': 'Teachers only'}), 403
        return f(*args, **kwargs)
    return wrapper


def student_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != 'student':
            return jsonify({'error': 'Students only'}), 403
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != 'admin':
            return jsonify({'error': 'Admins only'}), 403
        return f(*args, **kwargs)
    return wrapper


def enrolled_or_staff(course_id):
    """Return True if current user is teacher, admin, or enrolled student."""
    if current_user.role in ('teacher', 'admin'):
        return True
    return Enrollment.query.filter_by(
        student_id=current_user.id, course_id=course_id).first() is not None


# Keep old name as alias for backwards compat
enrolled_or_teacher = enrolled_or_staff


# ─────────────────────────────────────────────
# Serve frontends
# ─────────────────────────────────────────────
@app.route('/')
@app.route('/lms')
def serve_frontend():
    return send_from_directory('templates', 'lms.html')


@app.route('/admin')
@login_required
def serve_admin():
    if current_user.role != 'admin':
        return send_from_directory('templates', 'lms.html')
    return send_from_directory('templates', 'admin.html')


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data  = request.get_json()
    email = data.get('email', '').strip().lower()
    pw    = data.get('password', '')

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(pw):
        return jsonify({'error': 'Invalid email or password'}), 401

    login_user(user, remember=False)   # session expires when browser closes
    user.last_login = datetime.utcnow()
    # A6 — log login activity
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        db.session.add(LoginLog(user_id=user.id, ip_address=ip))
    except Exception:
        pass
    db.session.commit()
    return jsonify({'user': user.to_dict()})


@app.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    logout_user()
    return jsonify({'ok': True})


@app.route('/api/auth/me')
@login_required
def api_me():
    return jsonify({'user': current_user.to_dict()})


# ─────────────────────────────────────────────
# COURSES
# ─────────────────────────────────────────────
@app.route('/api/courses')
@login_required
def api_courses():
    if current_user.role in ('teacher', 'admin'):
        courses = Course.query.all()
    else:
        courses = [e.course for e in current_user.enrollments]
    return jsonify([c.to_dict() for c in courses])


# ─────────────────────────────────────────────
# RECORDINGS
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/recordings')
@login_required
def api_recordings(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    course = Course.query.get_or_404(cid)
    recs = Recording.query.filter_by(course_id=cid).order_by(
        Recording.week, Recording.session_num).all()

    # Gate by cohort week (or course week as fallback) for students
    if current_user.role == 'student':
        visible_week = _student_week(cid)
        recs = [r for r in recs if r.week <= visible_week]
        watched_ids = {w.recording_id for w in
                       WatchLog.query.filter_by(student_id=current_user.id).all()}
        data = [r.to_dict(watched=r.id in watched_ids) for r in recs]
    else:
        data = [r.to_dict() for r in recs]

    weeks = {}
    for r in data:
        w = r['week']
        weeks.setdefault(w, []).append(r)
    return jsonify({'weeks': weeks, 'current_week': course.current_week})


@app.route('/api/courses/<int:cid>/recordings', methods=['POST'])
@teacher_required
def api_upload_recording(cid):
    try:
        stored, original = save_upload(
            request.files.get('file'), 'videos',
            app.config['ALLOWED_VIDEO'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    rec = Recording(
        course_id   = cid,
        week        = int(request.form.get('week', 1)),
        session_num = int(request.form.get('session_num', 1)),
        title       = request.form.get('title', original),
        description = request.form.get('description', ''),
        filename    = stored,
        duration    = request.form.get('duration', '')
    )
    db.session.add(rec)
    db.session.commit()
    return jsonify({'recording': rec.to_dict()}), 201


@app.route('/api/recordings/<int:rid>', methods=['DELETE'])
@teacher_required
def api_delete_recording(rid):
    rec = Recording.query.get_or_404(rid)
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', rec.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(rec)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/recordings/<int:rid>/watch', methods=['POST'])
@student_required
def api_mark_watched(rid):
    exists = WatchLog.query.filter_by(
        student_id=current_user.id, recording_id=rid).first()
    if not exists:
        db.session.add(WatchLog(student_id=current_user.id, recording_id=rid))
        db.session.commit()
    return jsonify({'ok': True})


@app.route('/uploads/videos/<path:filename>')
@login_required
def serve_video(filename):
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), filename)


# ─────────────────────────────────────────────
# MATERIALS
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/materials')
@login_required
def api_materials(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    course = Course.query.get_or_404(cid)
    now = datetime.utcnow()
    mats = Material.query.filter_by(course_id=cid).order_by(
        Material.week, Material.order_index, Material.uploaded_at).all()

    if current_user.role == 'student':
        # Gate by cohort week (or course week as fallback) and publish state
        visible_week = _student_week(cid)
        mats = [m for m in mats
                if (m.week == 0 or m.week <= visible_week)
                and (m.is_published if m.is_published is not None else True)
                and (m.publish_at is None or m.publish_at <= now)]
    # teachers/admins see all materials including unpublished
    return jsonify([m.to_dict() for m in mats])


@app.route('/api/courses/<int:cid>/materials', methods=['POST'])
@teacher_required
def api_upload_material(cid):
    try:
        stored, original = save_upload(
            request.files.get('file'), 'materials',
            app.config['ALLOWED_MATERIAL'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    ext  = original.rsplit('.', 1)[1].lower() if '.' in original else ''
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'materials', stored)

    mat = Material(
        course_id   = cid,
        week        = int(request.form.get('week', 0)),
        title       = request.form.get('title', original),
        description = request.form.get('description', ''),
        filename    = stored,
        file_type   = ext,
        file_size   = human_size(fpath)
    )
    db.session.add(mat)
    db.session.commit()
    return jsonify({'material': mat.to_dict()}), 201


@app.route('/api/materials/<int:mid>', methods=['DELETE'])
@teacher_required
def api_delete_material(mid):
    mat = Material.query.get_or_404(mid)
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'materials', mat.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(mat)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/uploads/materials/<path:filename>')
@login_required
def serve_material(filename):
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'materials'),
        filename, as_attachment=True)


@app.route('/uploads/briefs/<path:filename>')
@login_required
def serve_brief(filename):
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'briefs'),
        filename, as_attachment=True)


# ─────────────────────────────────────────────
# ASSIGNMENTS
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/assignments')
@login_required
def api_assignments(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    course = Course.query.get_or_404(cid)
    assignments = Assignment.query.filter_by(course_id=cid).order_by(
        Assignment.week).all()

    # Gate by cohort week (or course week as fallback) for students
    if current_user.role == 'student':
        visible_week = _student_week(cid)
        assignments = [a for a in assignments if a.week <= visible_week]
        result = []
        for a in assignments:
            sub = Submission.query.filter_by(
                assignment_id=a.id, student_id=current_user.id).first()
            result.append(a.to_dict(submission=sub))
    else:
        result = [a.to_dict() for a in assignments]

    return jsonify(result)


@app.route('/api/courses/<int:cid>/assignments', methods=['POST'])
@teacher_required
def api_create_assignment(cid):
    brief_file = None
    if 'file' in request.files and request.files['file'].filename:
        try:
            stored, _ = save_upload(request.files['file'], 'briefs',
                                    app.config['ALLOWED_MATERIAL'])
            brief_file = stored
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    due_str = request.form.get('due_date')
    due_date = None
    if due_str:
        for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d'):
            try:
                due_date = datetime.strptime(due_str, fmt)
                break
            except ValueError:
                continue

    a = Assignment(
        course_id   = cid,
        week        = int(request.form.get('week', 1)),
        title       = request.form.get('title', 'Untitled Assignment'),
        description = request.form.get('description', ''),
        due_date    = due_date,
        max_points  = int(request.form.get('max_points', 100)),
        brief_file  = brief_file
    )
    db.session.add(a)
    db.session.commit()
    return jsonify({'assignment': a.to_dict()}), 201


@app.route('/api/assignments/<int:aid>', methods=['DELETE'])
@teacher_required
def api_delete_assignment(aid):
    a = Assignment.query.get_or_404(aid)
    db.session.delete(a)
    db.session.commit()
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# SUBMISSIONS
# ─────────────────────────────────────────────
@app.route('/api/assignments/<int:aid>/submit', methods=['POST'])
@student_required
def api_submit(aid):
    existing = Submission.query.filter_by(
        assignment_id=aid, student_id=current_user.id).first()

    try:
        stored, original = save_upload(
            request.files.get('file'), 'submissions',
            app.config['ALLOWED_SUBMISSION'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if existing:
        old = os.path.join(app.config['UPLOAD_FOLDER'], 'submissions', existing.filename)
        if os.path.exists(old):
            os.remove(old)
        existing.filename     = stored
        existing.notes        = request.form.get('notes', '')
        existing.submitted_at = datetime.utcnow()
        existing.score        = None
        existing.feedback     = None
        existing.graded_at    = None
        db.session.commit()
        return jsonify({'submission': existing.to_dict()})

    sub = Submission(
        assignment_id = aid,
        student_id    = current_user.id,
        filename      = stored,
        notes         = request.form.get('notes', '')
    )
    db.session.add(sub)
    db.session.commit()
    return jsonify({'submission': sub.to_dict()}), 201


@app.route('/api/assignments/<int:aid>/submissions')
@teacher_required
def api_submissions(aid):
    subs = Submission.query.filter_by(assignment_id=aid).order_by(
        Submission.submitted_at).all()
    return jsonify([s.to_dict() for s in subs])


@app.route('/api/submissions/<int:sid>/grade', methods=['POST'])
@teacher_required
def api_grade(sid):
    sub = Submission.query.get_or_404(sid)
    data = request.get_json()
    score = data.get('score')
    if score is None or not (0 <= int(score) <= sub.assignment.max_points):
        return jsonify({'error': 'Invalid score'}), 400
    sub.score     = int(score)
    sub.feedback  = data.get('feedback', '')
    sub.graded_at = datetime.utcnow()
    db.session.commit()
    # notify student by email
    student = sub.student
    if student and student.email:
        email_assignment_graded(
            student.name, student.email,
            sub.assignment.title if sub.assignment else 'Assignment',
            sub.score, sub.feedback
        )
    return jsonify({'submission': sub.to_dict()})


@app.route('/uploads/submissions/<path:filename>')
@login_required
def serve_submission(filename):
    if current_user.role == 'student':
        sub = Submission.query.filter_by(
            filename=filename, student_id=current_user.id).first()
        if not sub:
            return jsonify({'error': 'Forbidden'}), 403
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'submissions'),
        filename, as_attachment=True)


# ─────────────────────────────────────────────
# DASHBOARD stats
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/dashboard')
@login_required
def api_dashboard(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    total_recordings  = Recording.query.filter_by(course_id=cid).count()
    total_materials   = Material.query.filter_by(course_id=cid).count()
    total_assignments = Assignment.query.filter_by(course_id=cid).count()

    if current_user.role == 'student':
        watched = WatchLog.query.join(Recording).filter(
            Recording.course_id == cid,
            WatchLog.student_id == current_user.id).count()
        subs = Submission.query.join(Assignment).filter(
            Assignment.course_id == cid,
            Submission.student_id == current_user.id).all()
        graded  = [s for s in subs if s.score is not None]
        avg     = round(sum(s.score for s in graded) / len(graded), 1) if graded else None
        pending = total_assignments - len(subs)

        # Build recent activity feed
        activity = []
        recent_recordings = (Recording.query.filter_by(course_id=cid)
            .order_by(Recording.uploaded_at.desc()).limit(3).all())
        for r in recent_recordings:
            activity.append({'type': 'cyan', 'text': f'<strong>{r.title}</strong> — video uploaded',
                             'time': r.uploaded_at.strftime('%b %d, %Y')})
        recent_materials = (Material.query.filter_by(course_id=cid)
            .order_by(Material.uploaded_at.desc()).limit(2).all())
        for m in recent_materials:
            activity.append({'type': 'purple', 'text': f'New material: <strong>{m.title}</strong> added',
                             'time': m.uploaded_at.strftime('%b %d, %Y')})
        for s in sorted(graded, key=lambda x: x.graded_at or x.submitted_at, reverse=True)[:3]:
            activity.append({'type': 'green',
                             'text': f'<strong>{s.assignment.title}</strong> graded — {s.score}/{s.assignment.max_points}',
                             'time': (s.graded_at or s.submitted_at).strftime('%b %d, %Y')})
        activity.sort(key=lambda x: x['time'], reverse=True)

        return jsonify({
            'videos_watched': watched,
            'total_recordings': total_recordings,
            'assignments_pending': max(pending, 0),
            'total_assignments': total_assignments,
            'assignments_submitted': len(subs),
            'avg_grade': avg,
            'submissions_graded': len(graded),
            'recent_activity': activity[:5]
        })
    else:
        enrolled_count = Enrollment.query.filter_by(course_id=cid).count()
        ungraded = Submission.query.join(Assignment).filter(
            Assignment.course_id == cid,
            Submission.score == None).count()

        enrollments = Enrollment.query.filter_by(course_id=cid).all()
        student_progress = []
        for e in enrollments:
            s = e.student
            watched = WatchLog.query.join(Recording).filter(
                Recording.course_id == cid,
                WatchLog.student_id == s.id).count()
            subs   = Submission.query.join(Assignment).filter(
                Assignment.course_id == cid,
                Submission.student_id == s.id).all()
            graded = [x for x in subs if x.score is not None]
            avg    = round(sum(x.score for x in graded) / len(graded), 1) if graded else None
            pct    = round((watched / total_recordings * 100)) if total_recordings else 0
            student_progress.append({
                'id': s.id, 'name': s.name, 'email': s.email,
                'initials': s.initials(),
                'videos_watched': watched, 'total_recordings': total_recordings,
                'submissions': len(subs), 'total_assignments': total_assignments,
                'avg_grade': avg, 'progress_pct': pct
            })

        recent_subs = (Submission.query
            .join(Assignment).filter(Assignment.course_id == cid)
            .filter(Submission.score == None)
            .order_by(Submission.submitted_at.desc())
            .limit(5).all())

        return jsonify({
            'enrolled_students': enrolled_count,
            'ungraded_submissions': ungraded,
            'total_recordings': total_recordings,
            'total_materials': total_materials,
            'student_progress': student_progress,
            'recent_ungraded': [s.to_dict() for s in recent_subs]
        })


# ═════════════════════════════════════════════
# ADMIN API
# ═════════════════════════════════════════════

# ── Students ──────────────────────────────────
@app.route('/api/admin/students', methods=['GET'])
@admin_required
def admin_list_students():
    students = User.query.filter_by(role='student').order_by(User.name).all()
    result = []
    for s in students:
        d = s.to_dict()
        d['enrollments'] = [e.to_dict() for e in s.enrollments]
        result.append(d)
    return jsonify(result)


@app.route('/api/admin/students', methods=['POST'])
@admin_required
def admin_create_student():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    if not email or not data.get('name'):
        return jsonify({'error': 'name and email are required'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 409

    u = User(
        name          = data['name'].strip(),
        email         = email,
        role          = 'student',
        phone         = data.get('phone', '').strip(),
        ic_number     = data.get('ic_number', '').strip(),
        language_pref = data.get('language_pref', 'en'),
    )
    plain_pw = data.get('password') or 'codencode123'
    u.set_password(plain_pw)
    u.temp_password = plain_pw   # saved for welcome email
    db.session.add(u)
    db.session.commit()
    return jsonify({'student': u.to_dict()}), 201


@app.route('/api/admin/students/<int:uid>', methods=['GET'])
@admin_required
def admin_get_student(uid):
    s = User.query.get_or_404(uid)
    d = s.to_dict()
    d['enrollments'] = [e.to_dict() for e in s.enrollments]
    return jsonify(d)


@app.route('/api/admin/students/<int:uid>', methods=['PUT'])
@admin_required
def admin_update_student(uid):
    s = User.query.get_or_404(uid)
    data = request.get_json()
    if 'name'          in data: s.name          = data['name'].strip()
    if 'phone'         in data: s.phone         = data['phone'].strip()
    if 'ic_number'     in data: s.ic_number     = data['ic_number'].strip()
    if 'language_pref' in data: s.language_pref = data['language_pref']
    if 'email'         in data:
        new_email = data['email'].strip().lower()
        existing  = User.query.filter_by(email=new_email).first()
        if existing and existing.id != uid:
            return jsonify({'error': 'Email already in use'}), 409
        s.email = new_email
    if 'password'  in data and data['password']:
        s.set_password(data['password'])
    db.session.commit()
    return jsonify({'student': s.to_dict()})


# ── Enrollments ───────────────────────────────
@app.route('/api/admin/students/<int:uid>/enroll', methods=['POST'])
@admin_required
def admin_enroll_student(uid):
    data      = request.get_json()
    course_id = data.get('course_id')
    if not course_id:
        return jsonify({'error': 'course_id required'}), 400

    existing = Enrollment.query.filter_by(student_id=uid, course_id=course_id).first()
    if existing:
        return jsonify({'error': 'Already enrolled'}), 409

    e = Enrollment(
        student_id      = uid,
        course_id       = course_id,
        payment_status  = data.get('payment_status', 'pending'),
        payment_remarks = data.get('payment_remarks', ''),
        class_timing    = data.get('class_timing', ''),
        class_format    = data.get('class_format', ''),
        cohort_id       = data.get('cohort_id') or None
    )
    db.session.add(e)
    db.session.commit()
    return jsonify({'enrollment': e.to_dict()}), 201


@app.route('/api/admin/students/<int:uid>', methods=['DELETE'])
@admin_required
def admin_delete_student(uid):
    u = User.query.get_or_404(uid)
    if u.role == 'admin':
        return jsonify({'error': 'Cannot delete admin accounts'}), 403
    Enrollment.query.filter_by(student_id=uid).delete()
    db.session.delete(u)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/enrollments/<int:eid>', methods=['DELETE'])
@admin_required
def admin_unenroll(eid):
    e = Enrollment.query.get_or_404(eid)
    db.session.delete(e)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/enrollments/<int:eid>/payment', methods=['PUT'])
@admin_required
def admin_update_payment(eid):
    e          = Enrollment.query.get_or_404(eid)
    data       = request.get_json()
    old_status = e.payment_status

    if 'payment_status'  in data: e.payment_status  = data['payment_status']
    if 'payment_remarks' in data: e.payment_remarks = data['payment_remarks']
    if 'class_timing'    in data: e.class_timing    = data['class_timing']
    if 'class_format'    in data: e.class_format    = data['class_format']
    if 'payment_method'  in data: e.payment_method  = data['payment_method'] or None
    if 'payment_amount'  in data and data['payment_amount'] not in (None, '', 0, '0'):
        try:
            e.payment_amount = float(data['payment_amount'])
        except (ValueError, TypeError):
            pass

    just_paid = (old_status != 'paid' and e.payment_status == 'paid')
    if just_paid and not e.paid_at:
        e.paid_at = datetime.utcnow()

    db.session.commit()

    # Fire receipt PDF + enrollment confirmation when first marked as paid
    if just_paid:
        try:
            email_payment_receipt(e)
        except Exception as exc:
            app.logger.error('Receipt email failed for enrollment %s: %s', eid, exc)
        try:
            email_enrollment_confirmation(e)
        except Exception as exc:
            app.logger.error('Enrolment confirmation email failed for enrollment %s: %s', eid, exc)

    return jsonify({'enrollment': e.to_dict()})


@app.route('/api/admin/enrollments/<int:eid>/receipt', methods=['POST'])
@admin_required
def admin_upload_receipt(eid):
    e = Enrollment.query.get_or_404(eid)
    try:
        stored, _ = save_upload(
            request.files.get('file'), 'receipts',
            app.config['ALLOWED_RECEIPT'])
    except ValueError as ex:
        return jsonify({'error': str(ex)}), 400
    # Delete old receipt if one exists
    if e.receipt_file:
        old = os.path.join(app.config['UPLOAD_FOLDER'], 'receipts', e.receipt_file)
        if os.path.exists(old):
            os.remove(old)
    e.receipt_file = stored
    db.session.commit()
    return jsonify({'enrollment': e.to_dict()})


@app.route('/uploads/receipts/<path:filename>')
@login_required
def serve_receipt(filename):
    if current_user.role not in ('admin', 'teacher'):
        return jsonify({'error': 'Forbidden'}), 403
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'receipts'),
        filename, as_attachment=True)


@app.route('/api/admin/enrollments/<int:eid>/invoice')
@admin_required
def admin_invoice(eid):
    """Return a printable HTML invoice page."""
    e = Enrollment.query.get_or_404(eid)
    s = e.student
    c = e.course
    inv_num = f'INV-{1110 + e.id}'
    issued  = datetime.utcnow().strftime('%d %B %Y')
    enr_date = e.enrolled_at.strftime('%d %B %Y')

    status_colour = {'paid': '#28ca41', 'pending': '#e3b341', 'overdue': '#f85149'}.get(
        e.payment_status, '#7d8590')

    receipt_html = ''
    if e.receipt_file:
        receipt_html = f'<p><strong>Receipt File:</strong> <a href="/uploads/receipts/{e.receipt_file}" target="_blank">View Receipt</a></p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{inv_num} — codencode.my</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Mono:wght@400;700&display=swap');
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:'Space Mono',monospace; background:#fff; color:#111; font-size:13px; padding:40px; max-width:720px; margin:auto; }}
    .header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:40px; border-bottom:3px solid #00dcb4; padding-bottom:24px; }}
    .brand {{ font-family:'Syne',sans-serif; font-size:28px; font-weight:800; color:#080c10; letter-spacing:-1px; }}
    .brand span {{ color:#00dcb4; }}
    .inv-meta {{ text-align:right; }}
    .inv-num {{ font-size:18px; font-weight:700; color:#080c10; }}
    .inv-date {{ color:#555; margin-top:4px; }}
    .section {{ margin-bottom:28px; }}
    .section-title {{ font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#888; margin-bottom:10px; border-bottom:1px solid #eee; padding-bottom:6px; }}
    .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
    p {{ margin:5px 0; line-height:1.6; }}
    strong {{ color:#080c10; }}
    .status-badge {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#fff; background:{status_colour}; }}
    .footer {{ margin-top:48px; padding-top:20px; border-top:1px solid #eee; font-size:11px; color:#888; text-align:center; }}
    @media print {{
      body {{ padding:20px; }}
      .no-print {{ display:none !important; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <div class="brand">code<span>ncode</span>.my</div>
      <div style="color:#555;margin-top:4px;font-size:12px">Learning Management System</div>
    </div>
    <div class="inv-meta">
      <div class="inv-num">{inv_num}</div>
      <div class="inv-date">Issued: {issued}</div>
    </div>
  </div>

  <div class="grid-2">
    <div class="section">
      <div class="section-title">Bill To</div>
      <p><strong>{s.name}</strong></p>
      <p>{s.email}</p>
      {'<p>' + s.phone + '</p>' if s.phone else ''}
      {'<p>IC/Passport: ' + s.ic_number + '</p>' if s.ic_number else ''}
    </div>
    <div class="section">
      <div class="section-title">Course</div>
      <p><strong>{c.title}</strong></p>
      <p>Duration: {c.weeks} weeks</p>
      <p>Enrolled: {enr_date}</p>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Payment Details</div>
    <p><strong>Status:</strong> <span class="status-badge">{e.payment_status.upper()}</span></p>
    {'<p><strong>Remarks:</strong> ' + (e.payment_remarks or '—') + '</p>'}
    {receipt_html}
  </div>

  <div class="footer">
    <p>codencode.my · {inv_num} · Generated {issued}</p>
    <p style="margin-top:4px">Thank you for learning with us!</p>
  </div>

  <div class="no-print" style="margin-top:32px;text-align:center">
    <button onclick="window.print()" style="background:#00dcb4;color:#080c10;border:none;padding:10px 28px;border-radius:6px;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer;">
      🖨 Print / Save as PDF
    </button>
    <button onclick="window.close()" style="background:#eee;color:#333;border:none;padding:10px 24px;border-radius:6px;font-family:inherit;font-size:13px;cursor:pointer;margin-left:8px;">
      Close
    </button>
  </div>
</body>
</html>"""
    # Send invoice email to student
    try:
        email_invoice(e)
    except Exception as exc:
        app.logger.error('[Invoice] Email failed for enrollment %s: %s', eid, exc)

    from flask import Response
    return Response(html, mimetype='text/html')


# ── Courses ───────────────────────────────────
@app.route('/api/admin/courses', methods=['GET'])
@admin_required
def admin_list_courses():
    courses = Course.query.order_by(Course.title).all()
    result  = []
    for c in courses:
        d = c.to_dict()
        d['enrolled_count'] = Enrollment.query.filter_by(course_id=c.id).count()
        result.append(d)
    return jsonify(result)


@app.route('/api/admin/courses', methods=['POST'])
@admin_required
def admin_create_course():
    data = request.get_json()
    if not data.get('title'):
        return jsonify({'error': 'title is required'}), 400
    seat_cap_val = data.get('seat_cap')
    c = Course(
        title        = data['title'].strip(),
        description  = data.get('description', ''),
        weeks        = int(data.get('weeks', 6)),
        current_week = 1,
        start_date   = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None,
        programme    = data.get('programme', '').strip(),
        language     = data.get('language', 'en'),
        seat_cap     = int(seat_cap_val) if seat_cap_val else None,
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({'course': c.to_dict()}), 201


# ── Cohort routes ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/cohorts', methods=['GET'])
@login_required
def api_get_cohorts(cid):
    cohorts = Cohort.query.filter_by(course_id=cid).order_by(Cohort.start_date).all()
    return jsonify([c.to_dict() for c in cohorts])

@app.route('/api/courses/<int:cid>/cohorts', methods=['POST'])
@admin_required
def api_create_cohort(cid):
    Course.query.get_or_404(cid)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    sd = None
    if data.get('start_date'):
        from datetime import date as date_type
        sd = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    c = Cohort(course_id=cid, name=name, start_date=sd, current_week=1)
    db.session.add(c)
    db.session.commit()
    return jsonify({'cohort': c.to_dict()}), 201

@app.route('/api/admin/cohorts/<int:cohort_id>/week', methods=['PUT'])
@admin_required
def admin_set_cohort_week(cohort_id):
    cohort  = Cohort.query.get_or_404(cohort_id)
    course  = cohort.course
    data    = request.get_json()
    week    = int(data.get('current_week', cohort.current_week))
    week    = max(1, min(week, course.weeks))
    cohort.current_week = week
    db.session.commit()
    return jsonify({'cohort': cohort.to_dict()})

@app.route('/api/admin/cohorts/<int:cohort_id>', methods=['PUT'])
@admin_required
def admin_update_cohort(cohort_id):
    import json as _json
    cohort = Cohort.query.get_or_404(cohort_id)
    data   = request.get_json()
    if data.get('name'):
        cohort.name = data['name'].strip()
    if 'start_date' in data:
        cohort.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data['start_date'] else None
    if 'end_date' in data:
        cohort.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data['end_date'] else None
    if 'current_week' in data:
        cohort.current_week = max(1, min(cohort.course.weeks, int(data['current_week'])))
    if 'schedule' in data:
        cohort.schedule = _json.dumps(data['schedule']) if data['schedule'] else None
    if 'notes' in data:
        cohort.notes = data['notes']
    db.session.commit()
    return jsonify({'cohort': cohort.to_dict()})


@app.route('/api/admin/cohorts/<int:cohort_id>', methods=['DELETE'])
@admin_required
def admin_delete_cohort(cohort_id):
    cohort = Cohort.query.get_or_404(cohort_id)
    db.session.delete(cohort)
    db.session.commit()
    return jsonify({'ok': True})


def _student_week(course_id):
    """Return the current_week applicable to the logged-in student for this course.
    Uses the student's cohort week if assigned, otherwise falls back to course week."""
    enrollment = Enrollment.query.filter_by(
        course_id=course_id, student_id=current_user.id).first()
    if enrollment and enrollment.cohort:
        return enrollment.cohort.current_week
    return Course.query.get(course_id).current_week


@app.route('/api/admin/courses/<int:cid>/week', methods=['PUT'])
@admin_required
def admin_set_week(cid):
    c    = Course.query.get_or_404(cid)
    data = request.get_json()
    week = int(data.get('current_week', c.current_week))
    week = max(1, min(week, c.weeks))
    c.current_week = week
    db.session.commit()
    return jsonify({'course': c.to_dict()})


@app.route('/api/admin/courses/<int:cid>', methods=['PUT'])
@admin_required
def admin_update_course(cid):
    c    = Course.query.get_or_404(cid)
    data = request.get_json()
    if 'title'       in data: c.title       = data['title'].strip()
    if 'description' in data: c.description = data['description'].strip()
    if 'weeks'       in data: c.weeks       = int(data['weeks'])
    if 'programme'   in data: c.programme   = data['programme'].strip()
    if 'language'    in data: c.language    = data['language']
    if 'seat_cap'    in data:
        c.seat_cap = int(data['seat_cap']) if data['seat_cap'] else None
    if 'start_date'  in data and data['start_date']:
        c.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    elif 'start_date' in data and not data['start_date']:
        c.start_date = None
    db.session.commit()
    d = c.to_dict()
    d['enrolled_count'] = Enrollment.query.filter_by(course_id=c.id).count()
    return jsonify({'course': d})


@app.route('/api/admin/courses/<int:cid>', methods=['DELETE'])
@admin_required
def admin_delete_course(cid):
    c = Course.query.get_or_404(cid)
    Enrollment.query.filter_by(course_id=cid).delete()
    db.session.delete(c)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/courses/<int:cid>/students', methods=['GET'])
@teacher_required
def admin_course_students(cid):
    enrollments = Enrollment.query.filter_by(course_id=cid).all()
    return jsonify([e.to_dict() for e in enrollments])


# ── Materials upload (admin) ───────────────────
@app.route('/api/admin/courses/<int:cid>/materials', methods=['POST'])
@admin_required
def admin_upload_material(cid):
    try:
        stored, original = save_upload(
            request.files.get('file'), 'materials',
            app.config['ALLOWED_MATERIAL'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    ext   = original.rsplit('.', 1)[1].lower() if '.' in original else ''
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'materials', stored)

    mat = Material(
        course_id   = cid,
        week        = int(request.form.get('week', 0)),
        title       = request.form.get('title', original),
        description = request.form.get('description', ''),
        filename    = stored,
        file_type   = ext,
        file_size   = human_size(fpath)
    )
    db.session.add(mat)
    db.session.commit()
    return jsonify({'material': mat.to_dict()}), 201


@app.route('/api/admin/materials/<int:mid>', methods=['PUT'])
@admin_required
def admin_update_material(mid):
    mat  = Material.query.get_or_404(mid)
    data = request.get_json()
    if 'week' in data:
        mat.week = max(0, int(data['week']))
    if data.get('title'):
        mat.title = data['title'].strip()
    db.session.commit()
    return jsonify({'material': mat.to_dict()})


@app.route('/api/admin/materials/<int:mid>', methods=['DELETE'])
@admin_required
def admin_delete_material(mid):
    mat   = Material.query.get_or_404(mid)
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'materials', mat.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(mat)
    db.session.commit()
    return jsonify({'ok': True})


# ── Attendance ────────────────────────────────
@app.route('/api/admin/courses/<int:cid>/attendance', methods=['GET'])
@admin_required
def admin_get_attendance(cid):
    course      = Course.query.get_or_404(cid)
    enrollments = Enrollment.query.filter_by(course_id=cid).all()
    records     = Attendance.query.filter_by(course_id=cid).all()

    # Index by (student_id, week)
    att_map = {(a.student_id, a.week): a for a in records}

    students_data = []
    for e in enrollments:
        s = e.student
        weeks_data = {}
        for w in range(1, course.current_week + 1):
            att = att_map.get((s.id, w))
            weeks_data[str(w)] = att.status if att else 'absent'
        students_data.append({
            'student_id':   s.id,
            'student_name': s.name,
            'weeks':        weeks_data
        })

    return jsonify({
        'course_id':    cid,
        'current_week': course.current_week,
        'students':     students_data
    })


@app.route('/api/admin/courses/<int:cid>/attendance', methods=['POST'])
@admin_required
def admin_set_attendance(cid):
    data       = request.get_json()
    student_id = data.get('student_id')
    week       = data.get('week')
    status     = data.get('status', 'present')
    notes      = data.get('notes', '')

    if not student_id or not week:
        return jsonify({'error': 'student_id and week required'}), 400
    if status not in ('present', 'absent', 'late'):
        return jsonify({'error': 'status must be present/absent/late'}), 400

    att = Attendance.query.filter_by(
        student_id=student_id, course_id=cid, week=week).first()
    if att:
        att.status      = status
        att.notes       = notes
        att.recorded_at = datetime.utcnow()
    else:
        att = Attendance(student_id=student_id, course_id=cid,
                         week=week, status=status, notes=notes)
        db.session.add(att)
    db.session.commit()
    return jsonify({'attendance': att.to_dict()})


# ── Bulk attendance (whole week at once) ──────
@app.route('/api/admin/courses/<int:cid>/attendance/bulk', methods=['POST'])
@admin_required
def admin_bulk_attendance(cid):
    """Expects { week: int, records: [{student_id, status, notes}] }"""
    data    = request.get_json()
    week    = data.get('week')
    records = data.get('records', [])
    if not week:
        return jsonify({'error': 'week required'}), 400

    for r in records:
        sid    = r.get('student_id')
        status = r.get('status', 'absent')
        notes  = r.get('notes', '')
        att    = Attendance.query.filter_by(
            student_id=sid, course_id=cid, week=week).first()
        if att:
            att.status      = status
            att.notes       = notes
            att.recorded_at = datetime.utcnow()
        else:
            att = Attendance(student_id=sid, course_id=cid,
                             week=week, status=status, notes=notes)
            db.session.add(att)
    db.session.commit()
    return jsonify({'ok': True, 'updated': len(records)})


# ── Payment overview ──────────────────────────
@app.route('/api/admin/payments', methods=['GET'])
@admin_required
def admin_payments():
    enrollments = Enrollment.query.all()
    return jsonify([e.to_dict() for e in enrollments])


# ─────────────────────────────────────────────
# Email test route (admin only)
# ─────────────────────────────────────────────
@app.route('/api/admin/test-email')
@login_required
def test_email():
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    ok = send_email(
        current_user.email,
        'codencode.my — Email test',
        _email_wrapper('Email is working!',
            '<p>This is a test email from your codencode.my LMS. SMTP is configured correctly.</p>')
    )
    return jsonify({'sent': ok, 'to': current_user.email})


# ─────────────────────────────────────────────
# RESET ADMIN (one-time recovery route)
# ─────────────────────────────────────────────
@app.route('/api/reset-admin')
def reset_admin():
    secret = request.args.get('secret', '')
    if secret != 'codencode-reset-2026':
        return jsonify({'error': 'forbidden'}), 403
    admin = User.query.filter_by(email='admin@codencode.my').first()
    if not admin:
        admin = User(name='Admin', email='admin@codencode.my', role='admin',
                     phone='010-0000000', ic_number='')
        db.session.add(admin)
    admin.set_password('admin1234')
    db.session.commit()
    return jsonify({'ok': True, 'email': 'admin@codencode.my', 'password': 'admin1234'})


# ─────────────────────────────────────────────
# WELCOME REMINDER  (3 days before class starts)
# ─────────────────────────────────────────────

def _build_welcome_email(student_name: str, course_title: str,
                         class_timing: str, class_format: str,
                         login_email: str = '', login_password: str = '',
                         days_before: int = 3) -> str:
    timing_display   = class_timing or 'as scheduled'
    fmt_display      = class_format  or 'Private'
    password_display = login_password or 'codencode123'
    days_label       = f'{days_before} days' if days_before > 1 else 'tomorrow'
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a1a12;color:#e0ffe8;padding:32px;border-radius:12px">
      <div style="text-align:center;margin-bottom:24px">
        <span style="font-size:28px;font-weight:900;letter-spacing:-1px">code<span style="color:#00e5a0">ncode</span>.my</span>
      </div>
      <h2 style="color:#00e5a0;margin-bottom:8px">Your class starts in {days_label}! 🎉</h2>
      <p style="color:#aaa;margin-bottom:24px">Hi <strong style="color:#fff">{student_name}</strong>, we're excited to have you!</p>

      <div style="background:#0d2a1c;border-radius:8px;padding:20px;margin-bottom:20px">
        <p style="margin:4px 0"><strong>📚 Course:</strong> {course_title}</p>
        <p style="margin:4px 0"><strong>🕐 Schedule:</strong> {timing_display}</p>
        <p style="margin:4px 0"><strong>👥 Format:</strong> {fmt_display}</p>
      </div>

      <div style="background:#0a2a1a;border:1px solid #00e5a033;border-radius:8px;padding:20px;margin-bottom:20px">
        <p style="color:#00e5a0;font-weight:700;margin:0 0 12px 0">🔐 Your Login Details</p>
        <p style="margin:6px 0;font-size:14px"><strong>Portal:</strong>
          <a href="https://learn.codencode.my" style="color:#00e5a0">learn.codencode.my</a>
        </p>
        <p style="margin:6px 0;font-size:14px"><strong>Username:</strong>
          <span style="background:#0d3a20;padding:2px 8px;border-radius:4px;font-family:monospace">{login_email}</span>
        </p>
        <p style="margin:6px 0;font-size:14px"><strong>Password:</strong>
          <span style="background:#0d3a20;padding:2px 8px;border-radius:4px;font-family:monospace">{password_display}</span>
        </p>
        <p style="color:#888;font-size:11px;margin-top:10px">Please change your password after your first login.</p>
      </div>

      <h3 style="color:#00e5a0">What to prepare:</h3>
      <ul style="color:#ccc;line-height:1.8">
        <li>Laptop with Python 3.10+ installed (<a href="https://python.org" style="color:#00e5a0">python.org</a>)</li>
        <li>VS Code installed (<a href="https://code.visualstudio.com" style="color:#00e5a0">code.visualstudio.com</a>)</li>
        <li>Stable internet connection</li>
        <li>Notebook &amp; pen for notes</li>
      </ul>
      <hr style="border-color:#1a3a28;margin:24px 0">
      <p style="font-size:11px;color:#666;text-align:center">
        {_BUSINESS_NAME} · SSM {_BUSINESS_SSM}
      </p>
    </div>"""


def _build_welcome_whatsapp(student_name: str, course_title: str,
                             class_timing: str, class_format: str) -> str:
    timing_display = class_timing or 'as scheduled'
    fmt_display    = class_format  or 'Private'
    return (
        f"Hi {student_name}! 👋\n\n"
        f"Your *{course_title}* class starts in *3 days*!\n\n"
        f"📅 Schedule: {timing_display}\n"
        f"👥 Format: {fmt_display}\n\n"
        f"*What to prepare:*\n"
        f"✅ Laptop with Python 3.10+\n"
        f"✅ VS Code installed\n"
        f"✅ Stable internet\n\n"
        f"Log in anytime: https://learn.codencode.my\n\n"
        f"See you soon! 🚀\n"
        f"— {_BUSINESS_NAME}"
    )


def _send_reminders_for_day(days_before: int):
    """Send welcome reminder emails/WhatsApp for courses starting in exactly `days_before` days."""
    target = (datetime.utcnow() + timedelta(days=days_before)).date()
    days_label = f'{days_before} days' if days_before > 1 else 'tomorrow'
    app.logger.info('[Reminder] Checking %d-day reminders for courses starting on %s', days_before, target)

    courses = Course.query.filter_by(start_date=target).all()
    if not courses:
        app.logger.info('[Reminder] No courses starting on %s', target)
        return

    for course in courses:
        for enrollment in course.enrollments:
            student = enrollment.student
            if not student:
                continue

            timing = enrollment.class_timing or ''
            fmt    = enrollment.class_format  or ''

            # Email
            try:
                send_email(
                    student.email,
                    f'Your {course.title} class starts in {days_label}! 🎉',
                    _build_welcome_email(
                        student.name, course.title, timing, fmt,
                        login_email=student.email,
                        login_password=student.temp_password or 'codencode123',
                        days_before=days_before
                    )
                )
                app.logger.info('[Reminder] %d-day email sent to %s', days_before, student.email)
            except Exception as exc:
                app.logger.error('[Reminder] %d-day email failed for %s: %s', days_before, student.email, exc)

            # WhatsApp
            if student.phone:
                send_whatsapp(
                    student.phone,
                    _build_welcome_whatsapp(student.name, course.title, timing, fmt)
                )


def send_welcome_reminders():
    """Called daily — sends welcome emails 5 days and 1 day before class starts."""
    with app.app_context():
        _send_reminders_for_day(5)
        _send_reminders_for_day(1)


def _start_scheduler():
    """Start APScheduler background job — runs daily at 9:00 AM."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            send_welcome_reminders,
            trigger=CronTrigger(hour=9, minute=0),
            id='welcome_reminder',
            replace_existing=True,
            misfire_grace_time=3600,
        )
        scheduler.start()
        app.logger.info('[Scheduler] Welcome reminder job scheduled — runs daily at 09:00')
    except Exception as exc:
        app.logger.error('[Scheduler] Failed to start: %s', exc)


# ── Manual trigger endpoint (admin only) ──────
@app.route('/api/admin/trigger-welcome-reminders', methods=['POST'])
@admin_required
def trigger_welcome_reminders():
    """Manually fire the welcome reminder — useful for testing."""
    import threading
    threading.Thread(target=send_welcome_reminders, daemon=True).start()
    return jsonify({'ok': True, 'message': 'Welcome reminders triggered in background'})


# ─────────────────────────────────────────────
# SEED
# ─────────────────────────────────────────────
def seed_demo():
    if User.query.first():
        return

    admin = User(name='Admin', email='admin@codencode.my', role='admin',
                 phone='010-0000000', ic_number='')
    admin.set_password('admin1234')

    teacher = User(name='Teacher', email='teacher@codencode.my', role='teacher',
                   phone='011-2345678', ic_number='')
    teacher.set_password('demo1234')

    student = User(name='Student', email='student@codencode.my', role='student',
                   phone='012-3456789', ic_number='')
    student.set_password('demo1234')

    db.session.add_all([admin, teacher, student])
    db.session.commit()
    print('✓ Default accounts seeded')


def _seed_demo_old():
    # ── Courses ────────────────────────────────
    python_course = Course(
        title='Python Programming Bootcamp',
        description='6-week hands-on Python course from beginner to advanced.',
        weeks=6, current_week=3, programme='Python Bootcamp')
    python_course.start_date = datetime(2026, 5, 8).date()
    ml_course = Course(
        title='Machine Learning Fundamentals',
        description='Practical ML: NumPy, Pandas, scikit-learn, and real projects.',
        weeks=6, current_week=2, programme='Machine Learning')
    db.session.add_all([python_course, ml_course])
    db.session.flush()

    # ── Enrollments with payment status ────────
    payment_data = {
        # student_index: (py_status, py_remarks, ml_status, ml_remarks)
        0: ('paid',    'Full payment received',        'paid',    'Full payment received'),
        1: ('paid',    'Paid via bank transfer',        'pending', 'Awaiting payment'),
        2: ('overdue', 'Payment overdue — follow up',  'overdue', 'Reminder sent 3x'),
        3: ('paid',    'Installment plan completed',   'paid',    'Paid in full'),
        4: ('pending', 'Partial payment RM200 received','pending', 'Pending balance RM300'),
        5: ('paid',    'Scholarship — full waiver',    'paid',    'Scholarship student'),
    }
    for si, (py_st, py_rm, ml_st, ml_rm) in payment_data.items():
        db.session.add(Enrollment(
            student_id=students[si].id, course_id=python_course.id,
            payment_status=py_st, payment_remarks=py_rm))
        db.session.add(Enrollment(
            student_id=students[si].id, course_id=ml_course.id,
            payment_status=ml_st, payment_remarks=ml_rm))
    db.session.flush()

    # ── Recordings ─────────────────────────────
    py_sessions = [
        (1,1,'Intro to Python & Environment Setup','45:12'),
        (1,2,'Variables, Data Types & Operators','38:44'),
        (1,3,'Control Flow: If, Loops, Break & Continue','52:01'),
        (1,4,'Lists, Tuples, Dictionaries','41:30'),
        (2,1,'Functions Deep Dive — Args, Kwargs, Scope','58:20'),
        (2,2,'Reading & Writing Files — CSV, JSON, TXT','44:50'),
        (2,3,'Modules & Packages — pip & virtualenv','39:15'),
        (2,4,'Error Handling & Debugging','47:05'),
        (3,1,'OOP Part 1 — Classes & Objects','55:40'),
        (3,2,'OOP Part 2 — Inheritance & Polymorphism','49:30'),
        (4,1,'Pandas: DataFrames, Series, Indexing','62:05'),
        (4,2,'Data Cleaning — Nulls, Duplicates, Dtypes','55:18'),
    ]
    for wk, sn, title, dur in py_sessions:
        db.session.add(Recording(
            course_id=python_course.id, week=wk, session_num=sn,
            title=title, duration=dur, filename='demo_placeholder.mp4'))

    ml_sessions = [
        (1,1,'Introduction to ML & the Data Science Workflow','48:30'),
        (1,2,'NumPy Arrays & Vectorised Operations','42:15'),
        (2,1,'Pandas: DataFrames, Series & Indexing','55:10'),
        (2,2,'Data Cleaning — Nulls, Duplicates & Dtypes','50:05'),
        (3,1,'Your First Model: Linear Regression','60:20'),
        (3,2,'Model Evaluation: MSE, R², Cross-Validation','44:45'),
        (4,1,'Classification: Logistic Regression','53:00'),
        (4,2,'Decision Trees & Overfitting','47:30'),
        (5,1,'Random Forests & Ensemble Methods','58:15'),
        (5,2,'Evaluation Metrics: Precision, Recall, AUC','41:50'),
        (6,1,'Feature Engineering & Selection','56:40'),
        (6,2,'Capstone Project Kickoff & Q&A','38:00'),
    ]
    for wk, sn, title, dur in ml_sessions:
        db.session.add(Recording(
            course_id=ml_course.id, week=wk, session_num=sn,
            title=title, duration=dur, filename='demo_placeholder.mp4'))
    db.session.flush()

    # ── Materials ──────────────────────────────
    py_materials = [
        (0, 'Lecture Slides — All Sessions', 'py_slides.zip',            'zip', '2.9 MB'),
        (0, 'Python Cheat Sheet',            'py_cheat_sheet.py',        'py',  '5.4 KB'),
        (1, 'Week 1 — Variables, Loops & Lists', 'py_week1_exercises.py','py',  '3.0 KB'),
        (2, 'Week 2 — Functions',            'py_week2_exercises.py',    'py',  '3.6 KB'),
        (3, 'Week 3 — OOP: Classes & Objects','py_week3_exercises.py',   'py',  '4.8 KB'),
        (4, 'Week 4 — Files & Error Handling','py_week4_exercises.py',   'py',  '3.9 KB'),
        (5, 'Week 5 — Modules & Pythonic Code','py_week5_exercises.py',  'py',  '5.3 KB'),
        (6, 'Week 6 — Building Real Projects','py_week6_exercises.py',   'py',  '8.8 KB'),
        (6, 'Week 6 — Mini Project Starter', 'py_week6_project_starter.py','py','6.9 KB'),
    ]
    for wk, title, fname, ftype, fsize in py_materials:
        db.session.add(Material(course_id=python_course.id, week=wk,
            title=title, filename=fname, file_type=ftype, file_size=fsize))

    ml_materials = [
        (0, 'Lecture Slides — All Sessions',   'ml_slides.zip',                 'zip', '4.7 MB'),
        (0, 'ML Cheat Sheet',                  'ml_cheat_sheet.py',             'py',  '4.6 KB'),
        (1, 'Week 1 — NumPy Fundamentals',     'ml_week1_exercises.py',         'py',  '4.3 KB'),
        (2, 'Week 2 — Pandas Data Wrangling',  'ml_week2_exercises.py',         'py',  '4.7 KB'),
        (3, 'Week 3 — Your First ML Model',    'ml_week3_exercises.py',         'py',  '4.7 KB'),
        (4, 'Week 4 — Classification',         'ml_week4_exercises.py',         'py',  '4.5 KB'),
        (5, 'Week 5 — Random Forest & Eval',   'ml_week5_exercises.py',         'py',  '4.9 KB'),
        (6, 'Week 6 — Feature Engineering',    'ml_week6_feature_engineering.py','py', '6.3 KB'),
        (6, 'Week 6 — Capstone Starter',       'ml_week6_capstone.py',          'py',  '7.6 KB'),
    ]
    for wk, title, fname, ftype, fsize in ml_materials:
        db.session.add(Material(course_id=ml_course.id, week=wk,
            title=title, filename=fname, file_type=ftype, file_size=fsize))
    db.session.flush()

    # ── Assignments ────────────────────────────
    py_assignments = [
        (2, 'Assignment 1 — My Digital Life in Python',
         'Build a Python script that captures and displays your digital life stats.',
         'py_assignment1.py', now + timedelta(days=-20)),
        (4, 'Assignment 2 — Build a Mini Contact Book',
         'Create a command-line contact book with add, search, update and delete.',
         'py_assignment2.py', now + timedelta(days=10)),
    ]
    asgn_objs = []
    for wk, title, desc, brief, due in py_assignments:
        a = Assignment(course_id=python_course.id, week=wk, title=title,
                       description=desc, brief_file=brief, due_date=due, max_points=100)
        db.session.add(a)
        asgn_objs.append(a)

    ml_assignments = [
        (3, 'Assignment 1 — Predict Who Passes the Course',
         'Use a classification model to predict student pass/fail outcomes.',
         'ml_assignment1.py', now + timedelta(days=-10)),
        (6, 'Assignment 2 — JB House Price Predictor',
         'Build a regression model to predict house prices in Johor Bahru.',
         'ml_assignment2.py', now + timedelta(days=14)),
    ]
    ml_asgn_objs = []
    for wk, title, desc, brief, due in ml_assignments:
        a = Assignment(course_id=ml_course.id, week=wk, title=title,
                       description=desc, brief_file=brief, due_date=due, max_points=100)
        db.session.add(a)
        ml_asgn_objs.append(a)
    db.session.flush()

    # ── Submissions & Grades ───────────────────
    py_a1_grades = {0:80, 1:95, 2:60, 3:75, 4:88, 5:92}
    for si, score in py_a1_grades.items():
        db.session.add(Submission(
            assignment_id=asgn_objs[0].id, student_id=students[si].id,
            filename='assignment1_submission.py', notes='',
            submitted_at=now + timedelta(days=-18+si),
            score=score,
            feedback='Good work!' if score >= 80 else 'Needs improvement.',
            graded_at=now + timedelta(days=-15)))

    for si in range(4):
        db.session.add(Submission(
            assignment_id=asgn_objs[1].id, student_id=students[si].id,
            filename='assignment2_submission.py',
            submitted_at=now + timedelta(days=-3+si)))

    ml_a1_grades = {0:78, 1:90, 2:55, 3:82, 4:91, 5:96}
    for si, score in ml_a1_grades.items():
        db.session.add(Submission(
            assignment_id=ml_asgn_objs[0].id, student_id=students[si].id,
            filename='ml_assignment1_submission.py', notes='',
            submitted_at=now + timedelta(days=-8+si),
            score=score,
            feedback='Good work!' if score >= 80 else 'Needs improvement.',
            graded_at=now + timedelta(days=-6)))

    # ── Watch logs ─────────────────────────────
    recs = Recording.query.filter_by(course_id=python_course.id).all()
    watch_map = {0:8, 1:10, 2:5, 3:7, 4:9, 5:10}
    for si, count in watch_map.items():
        for rec in recs[:min(count, len(recs))]:
            db.session.add(WatchLog(student_id=students[si].id, recording_id=rec.id))

    # ── Attendance ─────────────────────────────
    # Python course: weeks 1–3; ML course: weeks 1–2
    py_att = [
        # (student_index, week, status)
        (0,1,'present'),(0,2,'present'),(0,3,'present'),
        (1,1,'present'),(1,2,'present'),(1,3,'late'),
        (2,1,'absent'), (2,2,'present'),(2,3,'absent'),
        (3,1,'present'),(3,2,'late'),   (3,3,'present'),
        (4,1,'present'),(4,2,'present'),(4,3,'present'),
        (5,1,'present'),(5,2,'present'),(5,3,'present'),
    ]
    for si, wk, status in py_att:
        db.session.add(Attendance(
            student_id=students[si].id, course_id=python_course.id,
            week=wk, status=status))

    ml_att = [
        (0,1,'present'),(0,2,'present'),
        (1,1,'present'),(1,2,'present'),
        (2,1,'late'),   (2,2,'absent'),
        (3,1,'present'),(3,2,'present'),
        (4,1,'present'),(4,2,'late'),
        (5,1,'present'),(5,2,'present'),
    ]
    for si, wk, status in ml_att:
        db.session.add(Attendance(
            student_id=students[si].id, course_id=ml_course.id,
            week=wk, status=status))

    db.session.commit()
    print('✓ Demo data seeded (unused)')


# ─────────────────────────────────────────────
# SESSIONS (live class scheduling)
# ─────────────────────────────────────────────

@app.route('/api/sessions', methods=['GET'])
@login_required
def api_list_sessions():
    """Teacher sees sessions they created; student sees their timetable sessions."""
    if current_user.role in ('teacher', 'admin'):
        sessions = Session.query.filter_by(created_by=current_user.id).order_by(Session.start_datetime).all()
        return jsonify([s.to_dict() for s in sessions])
    # student: cohort sessions for enrolled courses + group/private where participant
    enrolled_course_ids = {e.course_id for e in current_user.enrollments}
    participant_session_ids = {p.session_id for p in SessionParticipant.query.filter_by(student_id=current_user.id).all()}

    sessions = Session.query.all()
    visible = []
    for s in sessions:
        if s.session_type == 'cohort' and s.course_id in enrolled_course_ids:
            visible.append(s)
        elif s.session_type in ('group', 'private') and s.id in participant_session_ids:
            visible.append(s)
    visible.sort(key=lambda x: x.start_datetime)
    return jsonify([s.to_dict() for s in visible])


@app.route('/api/sessions/timetable', methods=['GET'])
@login_required
def api_student_timetable():
    """Student's personal timetable split into upcoming / past."""
    now = datetime.utcnow()
    if current_user.role in ('teacher', 'admin'):
        sessions = Session.query.order_by(Session.start_datetime).all()
    else:
        enrolled_course_ids = {e.course_id for e in current_user.enrollments}
        participant_session_ids = {p.session_id for p in SessionParticipant.query.filter_by(student_id=current_user.id).all()}
        sessions = []
        for s in Session.query.order_by(Session.start_datetime).all():
            if s.session_type == 'cohort' and s.course_id in enrolled_course_ids:
                sessions.append(s)
            elif s.session_type in ('group', 'private') and s.id in participant_session_ids:
                sessions.append(s)

    upcoming = [s.to_dict() for s in sessions if s.start_datetime >= now]
    past     = [s.to_dict() for s in sessions if s.start_datetime < now]
    return jsonify({'upcoming': upcoming, 'past': past})


@app.route('/api/sessions', methods=['POST'])
@teacher_required
def api_create_session():
    data = request.get_json()
    title        = data.get('title', '').strip()
    session_type = data.get('session_type', 'cohort')
    course_id    = data.get('course_id')
    start_str    = data.get('start_datetime', '')
    duration     = int(data.get('duration_minutes', 60))
    zoom_link    = data.get('zoom_link', '').strip()
    participant_ids = data.get('participant_ids', [])

    if not title or not start_str:
        return jsonify({'error': 'title and start_datetime are required'}), 400

    try:
        start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        return jsonify({'error': 'start_datetime must be YYYY-MM-DDTHH:MM'}), 400

    s = Session(
        title=title, session_type=session_type, course_id=course_id or None,
        start_datetime=start_dt, duration_minutes=duration,
        zoom_link=zoom_link, created_by=current_user.id
    )
    db.session.add(s)
    db.session.flush()  # get s.id

    for sid in participant_ids:
        db.session.add(SessionParticipant(session_id=s.id, student_id=int(sid)))

    db.session.commit()
    return jsonify({'session': s.to_dict()}), 201


@app.route('/api/sessions/<int:sid>', methods=['PUT'])
@teacher_required
def api_update_session(sid):
    s    = Session.query.get_or_404(sid)
    data = request.get_json()
    if 'title'            in data: s.title            = data['title'].strip()
    if 'session_type'     in data: s.session_type     = data['session_type']
    if 'course_id'        in data: s.course_id        = data['course_id'] or None
    if 'duration_minutes' in data: s.duration_minutes = int(data['duration_minutes'])
    if 'zoom_link'        in data: s.zoom_link        = data['zoom_link'].strip()
    if 'start_datetime'   in data:
        try:
            s.start_datetime = datetime.strptime(data['start_datetime'], '%Y-%m-%dT%H:%M')
        except ValueError:
            pass
    if 'participant_ids' in data:
        SessionParticipant.query.filter_by(session_id=sid).delete()
        for pid in data['participant_ids']:
            db.session.add(SessionParticipant(session_id=sid, student_id=int(pid)))
    db.session.commit()
    return jsonify({'session': s.to_dict()})


@app.route('/api/sessions/<int:sid>', methods=['DELETE'])
@teacher_required
def api_delete_session(sid):
    s = Session.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/sessions/<int:sid>/recording', methods=['PUT'])
@teacher_required
def api_session_recording(sid):
    s    = Session.query.get_or_404(sid)
    data = request.get_json()
    s.recording_url = data.get('recording_url', '').strip()
    db.session.commit()
    return jsonify({'session': s.to_dict()})


@app.route('/api/admin/sessions', methods=['GET'])
@admin_required
def admin_list_sessions():
    sessions = Session.query.order_by(Session.start_datetime.desc()).all()
    return jsonify([s.to_dict() for s in sessions])


# ─────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────

@app.route('/api/notifications', methods=['GET'])
@login_required
def api_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([n.to_dict() for n in notifs])


@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
@login_required
def api_mark_notification_read(nid):
    n = Notification.query.get_or_404(nid)
    if n.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    n.read_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/notifications/read-all', methods=['PUT'])
@login_required
def api_mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, read_at=None)\
        .update({'read_at': datetime.utcnow()})
    db.session.commit()
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# ANNOUNCEMENTS
# ─────────────────────────────────────────────

@app.route('/api/announcements', methods=['GET'])
@login_required
def api_announcements():
    if current_user.role in ('teacher', 'admin'):
        anns = Announcement.query.order_by(Announcement.created_at.desc()).all()
    else:
        enrolled_course_ids = list({e.course_id for e in current_user.enrollments})
        if enrolled_course_ids:
            anns = Announcement.query.filter(
                (Announcement.course_id == None) |
                (Announcement.course_id.in_(enrolled_course_ids))
            ).order_by(Announcement.created_at.desc()).all()
        else:
            anns = Announcement.query.filter(
                Announcement.course_id == None
            ).order_by(Announcement.created_at.desc()).all()
    return jsonify([a.to_dict() for a in anns])


@app.route('/api/announcements', methods=['POST'])
@teacher_required
def api_create_announcement():
    data      = request.get_json()
    title     = data.get('title', '').strip()
    content   = data.get('content', '').strip()
    course_id = data.get('course_id')  # None = global
    if not title or not content:
        return jsonify({'error': 'title and content required'}), 400
    ann = Announcement(
        title=title, content=content,
        course_id=course_id or None,
        created_by=current_user.id
    )
    db.session.add(ann)
    db.session.commit()
    # email all relevant students
    if course_id:
        students = [e.student for e in Enrollment.query.filter_by(course_id=course_id).all() if e.student]
    else:
        students = User.query.filter_by(role='student', is_active=True).all()
    for s in students:
        if s.email:
            email_announcement(s.name, s.email, title, content)
    return jsonify({'announcement': ann.to_dict()}), 201


@app.route('/api/announcements/<int:aid>', methods=['DELETE'])
@teacher_required
def api_delete_announcement(aid):
    ann = Announcement.query.get_or_404(aid)
    db.session.delete(ann)
    db.session.commit()
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# TIMETABLE
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/timetable')
@login_required
def api_get_timetable(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403
    from datetime import timedelta, date as date_type
    course = Course.query.get_or_404(cid)
    sessions_db = {(s.week, s.session_num): s
                   for s in TimetableSession.query.filter_by(course_id=cid).all()}
    # Fixed weekly schedule
    SCHEDULE = [
        (1, 'Friday',   '8:00 PM',  '10:00 PM', 0),
        (2, 'Saturday', '9:00 AM',  '11:00 AM', 1),
        (3, 'Sunday',   '9:00 AM',  '11:00 AM', 2),
    ]
    today = date_type.today()
    weeks = []
    for w in range(1, course.weeks + 1):
        sessions = []
        for snum, day_name, t_start, t_end, day_offset in SCHEDULE:
            if course.start_date:
                sd = course.start_date + timedelta(weeks=w - 1, days=day_offset)
                date_str  = sd.strftime('%d %b %Y')
                is_past   = sd < today
                is_today  = sd == today
            else:
                date_str  = None
                is_past   = False
                is_today  = False
            db_s = sessions_db.get((w, snum))
            sessions.append({
                'session_num': snum,
                'day':        day_name,
                'date':       date_str,
                'time_start': t_start,
                'time_end':   t_end,
                'topic':      db_s.topic if db_s else None,
                'notes':      db_s.notes if db_s else None,
                'is_past':    is_past,
                'is_today':   is_today,
            })
        weeks.append({'week': w, 'sessions': sessions})
    return jsonify({'weeks': weeks, 'current_week': course.current_week,
                    'start_date': course.start_date.strftime('%Y-%m-%d') if course.start_date else None})


@app.route('/api/courses/<int:cid>/timetable', methods=['PUT'])
@login_required
def api_save_timetable_session(cid):
    if current_user.role not in ('teacher', 'admin'):
        return jsonify({'error': 'Teachers only'}), 403
    data    = request.get_json()
    week    = data.get('week')
    snum    = data.get('session_num')
    topic   = (data.get('topic')   or '').strip()
    notes   = (data.get('notes')   or '').strip()
    s = TimetableSession.query.filter_by(course_id=cid, week=week, session_num=snum).first()
    if s:
        s.topic = topic; s.notes = notes
    else:
        s = TimetableSession(course_id=cid, week=week, session_num=snum, topic=topic, notes=notes)
        db.session.add(s)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/courses/<int:cid>/start_date', methods=['PUT'])
@login_required
def api_set_start_date(cid):
    if current_user.role not in ('teacher', 'admin'):
        return jsonify({'error': 'Teachers only'}), 403
    data     = request.get_json()
    date_str = data.get('start_date', '')
    course   = Course.query.get_or_404(cid)
    if date_str:
        course.start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        db.session.commit()
    return jsonify({'ok': True, 'start_date': date_str})


# ─────────────────────────────────────────────
# A5 — Material publish/schedule/reorder
# ─────────────────────────────────────────────
@app.route('/api/materials/<int:mid>/publish', methods=['PUT'])
@teacher_required
def api_material_publish(mid):
    mat = Material.query.get_or_404(mid)
    mat.is_published = not (mat.is_published if mat.is_published is not None else True)
    db.session.commit()
    return jsonify({'material': mat.to_dict()})


@app.route('/api/materials/<int:mid>/schedule', methods=['PUT'])
@teacher_required
def api_material_schedule(mid):
    mat = Material.query.get_or_404(mid)
    data = request.get_json()
    publish_at_str = data.get('publish_at', '')
    if publish_at_str:
        for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d'):
            try:
                mat.publish_at = datetime.strptime(publish_at_str, fmt)
                break
            except ValueError:
                continue
    else:
        mat.publish_at = None
    db.session.commit()
    return jsonify({'material': mat.to_dict()})


@app.route('/api/materials/<int:mid>/order', methods=['PUT'])
@teacher_required
def api_material_order(mid):
    mat = Material.query.get_or_404(mid)
    data = request.get_json()
    mat.order_index = int(data.get('order_index', 0))
    db.session.commit()
    return jsonify({'material': mat.to_dict()})


# ─────────────────────────────────────────────
# A6 — Analytics CSV export + login activity
# ─────────────────────────────────────────────
@app.route('/api/admin/analytics/export')
@admin_required
def admin_analytics_export():
    course_id = request.args.get('course_id', type=int)
    export_type = request.args.get('type', 'students')

    output = io.StringIO()
    writer = csv.writer(output)

    if export_type == 'students':
        writer.writerow(['Name', 'Email', 'Phone', 'IC Number', 'Enrolled At', 'Payment Status', 'Last Login'])
        q = Enrollment.query
        if course_id:
            q = q.filter_by(course_id=course_id)
        for e in q.all():
            s = e.student
            writer.writerow([
                s.name, s.email, s.phone or '', s.ic_number or '',
                e.enrolled_at.strftime('%Y-%m-%d'),
                e.payment_status or '',
                s.last_login.strftime('%Y-%m-%d %H:%M') if s.last_login else ''
            ])
    elif export_type == 'submissions':
        writer.writerow(['Student', 'Email', 'Assignment', 'Week', 'Submitted At', 'Score', 'Max Points', 'Feedback'])
        q = Submission.query.join(Assignment)
        if course_id:
            q = q.filter(Assignment.course_id == course_id)
        for sub in q.all():
            writer.writerow([
                sub.student.name, sub.student.email,
                sub.assignment.title, sub.assignment.week,
                sub.submitted_at.strftime('%Y-%m-%d %H:%M'),
                sub.score or '', sub.assignment.max_points,
                sub.feedback or ''
            ])
    elif export_type == 'attendance':
        if not course_id:
            return jsonify({'error': 'course_id required for attendance export'}), 400
        course = Course.query.get_or_404(course_id)
        week_headers = [f'Week {w}' for w in range(1, course.current_week + 1)]
        writer.writerow(['Student', 'Email'] + week_headers + ['Present', 'Absent', 'Late'])
        enrollments = Enrollment.query.filter_by(course_id=course_id).all()
        att_records = Attendance.query.filter_by(course_id=course_id).all()
        att_map = {(a.student_id, a.week): a.status for a in att_records}
        for e in enrollments:
            s = e.student
            week_statuses = [att_map.get((s.id, w), 'absent') for w in range(1, course.current_week + 1)]
            present = week_statuses.count('present')
            absent  = week_statuses.count('absent')
            late    = week_statuses.count('late')
            writer.writerow([s.name, s.email] + week_statuses + [present, absent, late])

    output.seek(0)
    from flask import Response
    filename = f'export_{export_type}_{course_id or "all"}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/api/admin/analytics/login_activity')
@admin_required
def admin_login_activity():
    course_id = request.args.get('course_id', type=int)
    if course_id:
        student_ids = [e.student_id for e in Enrollment.query.filter_by(course_id=course_id).all()]
        logs = LoginLog.query.filter(LoginLog.user_id.in_(student_ids))\
            .order_by(LoginLog.login_at.desc()).limit(30).all()
    else:
        logs = LoginLog.query.order_by(LoginLog.login_at.desc()).limit(30).all()
    return jsonify([l.to_dict() for l in logs])


# ─────────────────────────────────────────────
# A8+S10 — Certificates
# ─────────────────────────────────────────────
@app.route('/api/admin/certificates', methods=['GET'])
@admin_required
def admin_list_certificates():
    certs = Certificate.query.order_by(Certificate.issued_at.desc()).all()
    return jsonify([c.to_dict() for c in certs])


@app.route('/api/admin/certificates', methods=['POST'])
@admin_required
def admin_issue_certificate():
    data       = request.get_json()
    student_id = data.get('student_id')
    course_id  = data.get('course_id')
    if not student_id or not course_id:
        return jsonify({'error': 'student_id and course_id required'}), 400

    # Generate cert number CC-YYYY-NNN
    year = datetime.utcnow().year
    count = Certificate.query.filter(
        Certificate.cert_number.like(f'CC-{year}-%')
    ).count()
    cert_number = f'CC-{year}-{count + 1:03d}'

    cert = Certificate(
        student_id  = student_id,
        course_id   = course_id,
        issued_by   = current_user.id,
        cert_number = cert_number
    )
    db.session.add(cert)
    db.session.commit()
    # email student
    student = User.query.get(student_id)
    course  = Course.query.get(course_id)
    if student and student.email and course:
        email_certificate_issued(
            student.name, student.email,
            course.title, cert_number, cert.id
        )
    return jsonify({'certificate': cert.to_dict()}), 201


@app.route('/api/certificates/me')
@login_required
def my_certificates():
    certs = Certificate.query.filter_by(student_id=current_user.id)\
        .order_by(Certificate.issued_at.desc()).all()
    return jsonify([c.to_dict() for c in certs])


@app.route('/api/certificates/<int:cert_id>/download')
@login_required
def download_certificate(cert_id):
    from flask import render_template
    cert = Certificate.query.get_or_404(cert_id)
    if current_user.role == 'student' and cert.student_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403

    verify_url = f'https://learn.codencode.my/verify/{cert.cert_number}'
    qr_b64 = ''
    try:
        import qrcode, base64 as _b64, io as _io
        qr = qrcode.QRCode(version=1,
                           error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=4, border=3)
        qr.add_data(verify_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='#0a3d2a', back_color='white')
        buf = _io.BytesIO()
        img.save(buf, format='PNG')
        qr_b64 = _b64.b64encode(buf.getvalue()).decode()
    except Exception as exc:
        app.logger.warning('QR generation failed for cert %s: %s', cert_id, exc)

    html = render_template('certificate.html', cert=cert,
                           qr_b64=qr_b64, verify_url=verify_url)
    return html, 200, {'Content-Type': 'text/html'}


@app.route('/verify/<cert_number>')
def verify_certificate_public(cert_number):
    """Public certificate verification page — no login required."""
    from flask import render_template
    cert = Certificate.query.filter_by(cert_number=cert_number).first()
    return render_template('verify.html', cert=cert, cert_number=cert_number), \
           (200 if cert else 404)


# ─────────────────────────────────────────────
# S5+T2 — Quizzes
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/quizzes')
@login_required
def api_list_quizzes(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403
    if current_user.role == 'student':
        quizzes = Quiz.query.filter_by(course_id=cid, is_published=True).all()
    else:
        quizzes = Quiz.query.filter_by(course_id=cid).all()
    result = []
    for q in quizzes:
        d = q.to_dict()
        if current_user.role == 'student':
            attempts_used = QuizAttempt.query.filter_by(
                quiz_id=q.id, student_id=current_user.id,
                submitted_at=None
            ).count()
            completed = QuizAttempt.query.filter(
                QuizAttempt.quiz_id == q.id,
                QuizAttempt.student_id == current_user.id,
                QuizAttempt.submitted_at != None
            ).count()
            d['attempts_used'] = completed
            d['attempts_remaining'] = max(0, (q.max_attempts or 2) - completed)
            best = QuizAttempt.query.filter(
                QuizAttempt.quiz_id == q.id,
                QuizAttempt.student_id == current_user.id,
                QuizAttempt.submitted_at != None
            ).order_by(QuizAttempt.score.desc()).first()
            d['best_score'] = best.score if best else None
            d['best_passed'] = best.passed if best else None
        result.append(d)
    return jsonify(result)


@app.route('/api/quizzes/<int:qid>')
@login_required
def api_get_quiz(qid):
    q = Quiz.query.get_or_404(qid)
    if not enrolled_or_staff(q.course_id):
        return jsonify({'error': 'Not enrolled'}), 403
    hide_correct = (current_user.role == 'student')
    return jsonify(q.to_dict(include_questions=True, hide_correct=hide_correct))


@app.route('/api/quizzes', methods=['POST'])
@teacher_required
def api_create_quiz():
    data = request.get_json()
    if not data.get('title') or not data.get('course_id'):
        return jsonify({'error': 'title and course_id required'}), 400
    q = Quiz(
        course_id       = data['course_id'],
        title           = data['title'].strip(),
        description     = data.get('description', ''),
        week            = data.get('week'),
        pass_score      = int(data.get('pass_score', 70)),
        max_attempts    = int(data.get('max_attempts', 2)),
        time_limit_mins = int(data['time_limit_mins']) if data.get('time_limit_mins') else None,
        created_by      = current_user.id
    )
    db.session.add(q)
    db.session.commit()
    return jsonify({'quiz': q.to_dict()}), 201


@app.route('/api/quizzes/<int:qid>', methods=['PUT'])
@teacher_required
def api_update_quiz(qid):
    q = Quiz.query.get_or_404(qid)
    data = request.get_json()
    if 'title'           in data: q.title           = data['title'].strip()
    if 'description'     in data: q.description     = data['description']
    if 'week'            in data: q.week             = data['week']
    if 'pass_score'      in data: q.pass_score       = int(data['pass_score'])
    if 'max_attempts'    in data: q.max_attempts     = int(data['max_attempts'])
    if 'time_limit_mins' in data:
        q.time_limit_mins = int(data['time_limit_mins']) if data['time_limit_mins'] else None
    db.session.commit()
    return jsonify({'quiz': q.to_dict()})


@app.route('/api/quizzes/<int:qid>', methods=['DELETE'])
@teacher_required
def api_delete_quiz(qid):
    q = Quiz.query.get_or_404(qid)
    db.session.delete(q)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/quizzes/<int:qid>/publish', methods=['PUT'])
@teacher_required
def api_quiz_publish(qid):
    q = Quiz.query.get_or_404(qid)
    q.is_published = not q.is_published
    db.session.commit()
    return jsonify({'quiz': q.to_dict()})


@app.route('/api/quizzes/<int:qid>/questions', methods=['POST'])
@teacher_required
def api_add_quiz_question(qid):
    quiz = Quiz.query.get_or_404(qid)
    data = request.get_json()
    if not data.get('question_text'):
        return jsonify({'error': 'question_text required'}), 400

    order = len(quiz.questions)
    qq = QuizQuestion(
        quiz_id       = qid,
        question_text = data['question_text'],
        question_type = data.get('question_type', 'mcq'),
        points        = int(data.get('points', 1)),
        explanation   = data.get('explanation', ''),
        order_index   = order
    )
    db.session.add(qq)
    db.session.flush()

    for c in data.get('choices', []):
        db.session.add(QuizChoice(
            question_id = qq.id,
            choice_text = c.get('choice_text', ''),
            is_correct  = bool(c.get('is_correct', False))
        ))
    db.session.commit()
    return jsonify({'question': qq.to_dict()}), 201


@app.route('/api/quizzes/<int:qid>/questions/<int:qqid>', methods=['PUT'])
@teacher_required
def api_update_quiz_question(qid, qqid):
    qq = QuizQuestion.query.get_or_404(qqid)
    data = request.get_json()
    if 'question_text' in data: qq.question_text = data['question_text']
    if 'question_type' in data: qq.question_type = data['question_type']
    if 'points'        in data: qq.points        = int(data['points'])
    if 'explanation'   in data: qq.explanation   = data['explanation']
    if 'order_index'   in data: qq.order_index   = int(data['order_index'])
    if 'choices' in data:
        QuizChoice.query.filter_by(question_id=qqid).delete()
        for c in data['choices']:
            db.session.add(QuizChoice(
                question_id = qqid,
                choice_text = c.get('choice_text', ''),
                is_correct  = bool(c.get('is_correct', False))
            ))
    db.session.commit()
    return jsonify({'question': qq.to_dict()})


@app.route('/api/quizzes/<int:qid>/questions/<int:qqid>', methods=['DELETE'])
@teacher_required
def api_delete_quiz_question(qid, qqid):
    qq = QuizQuestion.query.get_or_404(qqid)
    db.session.delete(qq)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/quizzes/<int:qid>/attempt', methods=['POST'])
@login_required
def api_quiz_attempt(qid):
    quiz = Quiz.query.get_or_404(qid)
    if not enrolled_or_staff(quiz.course_id):
        return jsonify({'error': 'Not enrolled'}), 403

    data = request.get_json() or {}
    is_submit = data.get('submit', False)

    # Count completed attempts
    completed_count = QuizAttempt.query.filter(
        QuizAttempt.quiz_id == qid,
        QuizAttempt.student_id == current_user.id,
        QuizAttempt.submitted_at != None
    ).count()

    if is_submit:
        if completed_count >= (quiz.max_attempts or 2):
            return jsonify({'error': 'Max attempts reached'}), 400

        # Grade the attempt
        answers_data = data.get('answers', {})  # {question_id: choice_id or text}
        attempt = QuizAttempt(
            quiz_id    = qid,
            student_id = current_user.id,
            started_at = datetime.utcnow(),
            submitted_at = datetime.utcnow()
        )
        db.session.add(attempt)
        db.session.flush()

        total_points = 0
        earned_points = 0
        result_answers = []

        for q in quiz.questions:
            total_points += q.points
            user_answer = answers_data.get(str(q.id))
            is_correct = False
            selected_choice_id = None
            short_text = None

            if q.question_type == 'mcq' and user_answer:
                selected_choice_id = int(user_answer)
                choice = QuizChoice.query.get(selected_choice_id)
                is_correct = choice.is_correct if choice else False
                if is_correct:
                    earned_points += q.points
            elif q.question_type == 'short':
                short_text = str(user_answer) if user_answer else ''

            ans = QuizAnswer(
                attempt_id         = attempt.id,
                question_id        = q.id,
                selected_choice_id = selected_choice_id,
                short_answer_text  = short_text,
                is_correct         = is_correct
            )
            db.session.add(ans)
            result_answers.append({
                'question_id': q.id,
                'question_text': q.question_text,
                'is_correct': is_correct,
                'explanation': q.explanation or '',
                'selected_choice_id': selected_choice_id,
                'correct_choice_id': next((c.id for c in q.choices if c.is_correct), None)
            })

        score = round((earned_points / total_points * 100), 1) if total_points > 0 else 0
        passed = score >= (quiz.pass_score or 70)
        attempt.score = score
        attempt.passed = passed
        db.session.commit()

        return jsonify({
            'attempt': attempt.to_dict(),
            'score': score,
            'passed': passed,
            'answers': result_answers,
            'attempts_used': completed_count + 1,
            'attempts_remaining': max(0, (quiz.max_attempts or 2) - completed_count - 1)
        })
    else:
        # Just return quiz info for starting
        if completed_count >= (quiz.max_attempts or 2):
            return jsonify({'error': 'Max attempts reached'}), 400
        return jsonify({'quiz': quiz.to_dict(include_questions=True, hide_correct=True)})


@app.route('/api/quizzes/<int:qid>/attempts')
@login_required
def api_quiz_attempts(qid):
    attempts = QuizAttempt.query.filter_by(
        quiz_id=qid, student_id=current_user.id
    ).filter(QuizAttempt.submitted_at != None)\
    .order_by(QuizAttempt.submitted_at.desc()).all()
    return jsonify([a.to_dict() for a in attempts])


# ─────────────────────────────────────────────
# S8+T8 — Discussion / Q&A
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/discussions')
@login_required
def api_list_discussions(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403
    week = request.args.get('week', type=int)
    q = DiscussionPost.query.filter_by(course_id=cid)
    if week:
        q = q.filter_by(week=week)
    posts = q.all()
    # Sort: pinned first, then by upvotes desc, then by created_at desc
    posts.sort(key=lambda p: (not p.is_pinned, -len(p.upvotes), -p.created_at.timestamp()))
    return jsonify([p.to_dict(current_user_id=current_user.id) for p in posts])


@app.route('/api/courses/<int:cid>/discussions', methods=['POST'])
@login_required
def api_create_discussion(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403
    data = request.get_json()
    if not data.get('body'):
        return jsonify({'error': 'body required'}), 400
    post = DiscussionPost(
        course_id = cid,
        week      = data.get('week'),
        author_id = current_user.id,
        title     = data.get('title', ''),
        body      = data['body']
    )
    db.session.add(post)
    db.session.commit()
    return jsonify({'post': post.to_dict(current_user_id=current_user.id)}), 201


@app.route('/api/discussions/<int:pid>', methods=['DELETE'])
@login_required
def api_delete_discussion(pid):
    post = DiscussionPost.query.get_or_404(pid)
    if current_user.role not in ('teacher', 'admin') and post.author_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    db.session.delete(post)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/discussions/<int:pid>/pin', methods=['PUT'])
@teacher_required
def api_pin_discussion(pid):
    post = DiscussionPost.query.get_or_404(pid)
    post.is_pinned = not post.is_pinned
    db.session.commit()
    return jsonify({'post': post.to_dict(current_user_id=current_user.id)})


@app.route('/api/discussions/<int:pid>/resolve', methods=['PUT'])
@login_required
def api_resolve_discussion(pid):
    post = DiscussionPost.query.get_or_404(pid)
    if current_user.role not in ('teacher', 'admin') and post.author_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    post.is_resolved = not post.is_resolved
    db.session.commit()
    return jsonify({'post': post.to_dict(current_user_id=current_user.id)})


@app.route('/api/discussions/<int:pid>/replies', methods=['POST'])
@login_required
def api_add_reply(pid):
    post = DiscussionPost.query.get_or_404(pid)
    if not enrolled_or_staff(post.course_id):
        return jsonify({'error': 'Not enrolled'}), 403
    data = request.get_json()
    if not data.get('body'):
        return jsonify({'error': 'body required'}), 400
    reply = DiscussionReply(
        post_id       = pid,
        author_id     = current_user.id,
        body          = data['body'],
        is_instructor = current_user.role in ('teacher', 'admin')
    )
    db.session.add(reply)
    db.session.commit()
    return jsonify({'reply': reply.to_dict()}), 201


@app.route('/api/discussions/replies/<int:rid>', methods=['DELETE'])
@login_required
def api_delete_reply(rid):
    reply = DiscussionReply.query.get_or_404(rid)
    if current_user.role not in ('teacher', 'admin') and reply.author_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    db.session.delete(reply)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/discussions/<int:pid>/upvote', methods=['POST'])
@login_required
def api_upvote_discussion(pid):
    post = DiscussionPost.query.get_or_404(pid)
    existing = PostUpvote.query.filter_by(post_id=pid, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        upvoted = False
    else:
        db.session.add(PostUpvote(post_id=pid, user_id=current_user.id))
        upvoted = True
    db.session.commit()
    return jsonify({'upvoted': upvoted, 'upvote_count': len(post.upvotes)})


@app.route('/api/discussions/<int:pid>')
@login_required
def api_get_discussion(pid):
    post = DiscussionPost.query.get_or_404(pid)
    if not enrolled_or_staff(post.course_id):
        return jsonify({'error': 'Not enrolled'}), 403
    d = post.to_dict(current_user_id=current_user.id)
    d['replies'] = [r.to_dict() for r in post.replies]
    return jsonify(d)


# ─────────────────────────────────────────────
# S11 — Resume Last Lesson
# ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/last_lesson', methods=['PUT'])
@login_required
def api_set_last_lesson(cid):
    if current_user.role != 'student':
        return jsonify({'ok': True})
    data = request.get_json()
    material_id = data.get('material_id')
    if not material_id:
        return jsonify({'error': 'material_id required'}), 400

    ll = LastLesson.query.filter_by(student_id=current_user.id, course_id=cid).first()
    if ll:
        ll.material_id = material_id
        ll.updated_at = datetime.utcnow()
    else:
        ll = LastLesson(student_id=current_user.id, course_id=cid, material_id=material_id)
        db.session.add(ll)
    db.session.commit()
    return jsonify({'ok': True, 'last_lesson': ll.to_dict()})


@app.route('/api/courses/<int:cid>/last_lesson')
@login_required
def api_get_last_lesson(cid):
    ll = LastLesson.query.filter_by(student_id=current_user.id, course_id=cid).first()
    if not ll:
        return jsonify({'last_lesson': None})
    return jsonify({'last_lesson': ll.to_dict()})


# ─────────────────────────────────────────────
# R1/R2/R3 — Recording Access Control
# ─────────────────────────────────────────────
@app.route('/api/sessions/<int:sid>/recording/access')
@login_required
def get_recording_access(sid):
    s = Session.query.get_or_404(sid)

    # Admin and teacher always have access
    if current_user.role in ('admin', 'teacher'):
        return jsonify({'url': s.recording_url or ''})

    if not s.recording_url:
        return jsonify({'error': 'No recording available'}), 404

    if s.session_type == 'cohort':
        enrollment = Enrollment.query.filter_by(
            student_id=current_user.id,
            course_id=s.course_id
        ).first()
        if enrollment:
            return jsonify({'url': s.recording_url})
    elif s.session_type in ('group', 'private'):
        participant = SessionParticipant.query.filter_by(
            session_id=sid,
            student_id=current_user.id
        ).first()
        if participant:
            return jsonify({'url': s.recording_url})

    return jsonify({'error': 'Access denied'}), 403


# ─────────────────────────────────────────────
# SY3 — Language preference
# ─────────────────────────────────────────────
@app.route('/api/settings/language', methods=['PUT'])
@login_required
def api_set_language():
    data = request.get_json()
    lang = data.get('language', 'en')
    if lang not in ('en', 'zh', 'bm'):
        return jsonify({'error': 'Invalid language'}), 400
    current_user.language_pref = lang
    db.session.commit()
    return jsonify({'ok': True, 'language': lang})


# ─────────────────────────────────────────────
# SY6 — Full-text search
# ─────────────────────────────────────────────
@app.route('/api/search')
@login_required
def api_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})

    results = []

    # Get enrolled course IDs
    if current_user.role == 'student':
        enrolled_course_ids = [e.course_id for e in Enrollment.query.filter_by(student_id=current_user.id).all()]
    else:
        enrolled_course_ids = [c.id for c in Course.query.all()]

    # Search materials
    mats = Material.query.filter(
        Material.course_id.in_(enrolled_course_ids),
        Material.title.ilike(f'%{q}%')
    ).limit(10).all()
    for m in mats:
        results.append({'type': 'material', 'id': m.id, 'title': m.title,
                        'course': m.course.title if m.course else '', 'week': m.week})

    # Search assignments
    assignments = Assignment.query.filter(
        Assignment.course_id.in_(enrolled_course_ids),
        Assignment.title.ilike(f'%{q}%')
    ).limit(5).all()
    for a in assignments:
        results.append({'type': 'assignment', 'id': a.id, 'title': a.title,
                        'course': a.course.title if a.course else ''})

    # Search discussion posts
    try:
        posts = DiscussionPost.query.filter(
            DiscussionPost.course_id.in_(enrolled_course_ids),
            db.or_(DiscussionPost.title.ilike(f'%{q}%'), DiscussionPost.body.ilike(f'%{q}%'))
        ).limit(5).all()
        for p in posts:
            course_obj = Course.query.get(p.course_id)
            results.append({'type': 'discussion', 'id': p.id, 'title': p.title or p.body[:50],
                            'course': course_obj.title if course_obj else ''})
    except Exception:
        pass

    return jsonify({'results': results, 'query': q})


# ─────────────────────────────────────────────
# Init DB & run
# ─────────────────────────────────────────────
with app.app_context():
    db.create_all()
    # Safe column migrations (SQLite doesn't support ALTER TABLE ADD IF NOT EXISTS)
    from sqlalchemy import text, inspect as sa_inspect
    try:
        insp = sa_inspect(db.engine)
        existing = {c['name'] for c in insp.get_columns('enrollments')}
        with db.engine.connect() as conn:
            if 'receipt_file' not in existing:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN receipt_file VARCHAR(300)'))
                conn.commit()
            if 'class_timing' not in existing:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN class_timing VARCHAR(100)'))
                conn.commit()
            if 'class_format' not in existing:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN class_format VARCHAR(20)'))
                conn.commit()
            if 'cohort_id' not in existing:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN cohort_id INTEGER'))
                conn.commit()
    except Exception:
        pass
    try:
        insp2 = sa_inspect(db.engine)
        course_cols = {c['name'] for c in insp2.get_columns('courses')}
        with db.engine.connect() as conn:
            if 'start_date' not in course_cols:
                conn.execute(text('ALTER TABLE courses ADD COLUMN start_date DATE'))
                conn.commit()
    except Exception:
        pass
    try:
        insp3 = sa_inspect(db.engine)
        course_cols2 = {c['name'] for c in insp3.get_columns('courses')}
        with db.engine.connect() as conn:
            if 'programme' not in course_cols2:
                conn.execute(text('ALTER TABLE courses ADD COLUMN programme VARCHAR(100)'))
                conn.commit()
    except Exception:
        pass
    # Safe migrations for new user columns
    try:
        insp4 = sa_inspect(db.engine)
        user_cols = {c['name'] for c in insp4.get_columns('users')}
        with db.engine.connect() as conn:
            if 'language_pref' not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN language_pref VARCHAR(5) DEFAULT 'en'"))
                conn.commit()
            if 'is_active' not in user_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1'))
                conn.commit()
            if 'last_login' not in user_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN last_login DATETIME'))
                conn.commit()
            if 'temp_password' not in user_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN temp_password VARCHAR(100)'))
                conn.commit()
    except Exception:
        pass
    # A3 — Course language + seat_cap columns
    try:
        insp_c = sa_inspect(db.engine)
        course_cols3 = {c['name'] for c in insp_c.get_columns('courses')}
        with db.engine.connect() as conn:
            if 'language' not in course_cols3:
                conn.execute(text("ALTER TABLE courses ADD COLUMN language VARCHAR(5) DEFAULT 'en'"))
                conn.commit()
            if 'seat_cap' not in course_cols3:
                conn.execute(text('ALTER TABLE courses ADD COLUMN seat_cap INTEGER'))
                conn.commit()
    except Exception:
        pass

    # A5 — Material is_published, publish_at, order_index
    try:
        insp_m = sa_inspect(db.engine)
        mat_cols = {c['name'] for c in insp_m.get_columns('materials')}
        with db.engine.connect() as conn:
            if 'is_published' not in mat_cols:
                conn.execute(text('ALTER TABLE materials ADD COLUMN is_published BOOLEAN DEFAULT 1'))
                conn.commit()
            if 'publish_at' not in mat_cols:
                conn.execute(text('ALTER TABLE materials ADD COLUMN publish_at DATETIME'))
                conn.commit()
            if 'order_index' not in mat_cols:
                conn.execute(text('ALTER TABLE materials ADD COLUMN order_index INTEGER DEFAULT 0'))
                conn.commit()
    except Exception:
        pass

    # Cohort: schedule, notes, end_date columns
    try:
        insp_coh = sa_inspect(db.engine)
        coh_cols = {c['name'] for c in insp_coh.get_columns('cohorts')}
        with db.engine.connect() as conn:
            if 'schedule' not in coh_cols:
                conn.execute(text('ALTER TABLE cohorts ADD COLUMN schedule TEXT'))
                conn.commit()
            if 'notes' not in coh_cols:
                conn.execute(text('ALTER TABLE cohorts ADD COLUMN notes TEXT'))
                conn.commit()
            if 'end_date' not in coh_cols:
                conn.execute(text('ALTER TABLE cohorts ADD COLUMN end_date DATE'))
                conn.commit()
    except Exception:
        pass

    # Payment amount, method, paid_at columns (receipt + QR feature)
    try:
        insp_pay = sa_inspect(db.engine)
        pay_cols = {c['name'] for c in insp_pay.get_columns('enrollments')}
        with db.engine.connect() as conn:
            if 'payment_amount' not in pay_cols:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN payment_amount REAL'))
                conn.commit()
            if 'payment_method' not in pay_cols:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN payment_method VARCHAR(50)'))
                conn.commit()
            if 'paid_at' not in pay_cols:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN paid_at DATETIME'))
                conn.commit()
    except Exception:
        pass

    seed_demo()
    _start_scheduler()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
