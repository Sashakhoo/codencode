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
import re
import base64
import time
import urllib.request
import urllib.error
import urllib.parse
import json as _json_mod
from html import escape as html_escape
from datetime import datetime, timedelta
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import (Flask, request, jsonify, send_from_directory,
                   session, g)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from itsdangerous import BadSignature, URLSafeSerializer
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
                    LastLesson, Cohort, Registration,
                    Workshop, WorkshopRun, WorkshopAttendee, WorkshopFeedback)

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
app = Flask(__name__, static_folder='static', template_folder='templates')

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
    ALLOWED_MATERIAL={'pdf', 'py', 'ipynb', 'zip', 'csv', 'txt', 'docx', 'pptx', 'html'},
    ALLOWED_SUBMISSION={'py', 'ipynb', 'zip', 'pdf', 'txt'},
    ALLOWED_RECEIPT={'pdf', 'jpg', 'jpeg', 'png', 'heic'},
)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'serve_frontend'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'receipts'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)

_zoom_token_cache = {'token': None, 'expires_at': 0, 'api_url': 'https://api.zoom.us'}

SLIDE_MATERIALS = [
    (1, 'Session 01: Python Basics and Environment Setup', 'Session_01_Student_Python_Basics_and_Environment_Setup.html'),
    (2, 'Session 02: Control Flow Decisions and Loops', 'Session_02_Student_Control_Flow_Decisions_and_Loops.html'),
    (3, 'Session 03: Functions Modules and Reusable Code', 'Session_03_Student_Functions_Modules_and_Reusable_Code.html'),
    (4, 'Session 04: NumPy and Pandas Data Wrangling', 'Session_04_Student_NumPy_and_Pandas_Data_Wrangling.html'),
    (5, 'Session 05: Data Visualization Matplotlib and Seaborn', 'Session_05_Student_Data_Visualization_Matplotlib_and_Seaborn.html'),
    (6, 'Session 06: APIs and Real Data', 'Session_06_Student_APIs and Real Data.html'),
    (7, 'Session 07: Statistics and Probability', 'Session_07_Student_Statistics and Probability.html'),
    (8, 'Session 08: Feature Engineering', 'Session_08_Student_Feature Engineering.html'),
    (9, 'Session 09: Intro to Machine Learning', 'Session_09_Student_Intro to Machine Learning.html'),
    (10, 'Session 10: Regression Models Predict Any Number', 'Session_10_Student_Regression Models Predict Any Number.html'),
    (11, 'Session 11: Classification Random Forest and Evaluation', 'Session_11_Student_Classification Random Forest and Evaluation.html'),
    (12, 'Session 12: Neural Networks and Deep Learning', 'Session_12_Student_Neural Networks and Deep Learning.html'),
    (13, 'Session 13: LSTM and Time Series Sequential Learning', 'Session_13_Student_LSTM and Time Series Sequential Learning.html'),
    (14, 'Session 14: Vibe Coding - Building with AI', 'Session_14_Student_Vibe Coding — Building with AI.html'),
    (15, 'Session 15: Project Planning and Capstone Execution', 'Session_15_Student_Project Planning and Capstone Execution.html'),
]



@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────
# Email utility
# ─────────────────────────────────────────────
_EMAIL_FROM     = os.environ.get('EMAIL_FROM', 'codencodemy@gmail.com')
_BREVO_API_KEY  = os.environ.get('BREVO_API_KEY', '')
_BUSINESS_NAME  = os.environ.get('BUSINESS_NAME',    'CODE N CODE SOLUTION')
_BUSINESS_SSM   = os.environ.get('BUSINESS_SSM',     '202603072017 (AS0511861-M)')
_BUSINESS_ADDR  = os.environ.get(
    'BUSINESS_ADDRESS',
    "1st Floor - Room 16, 117, Jalan Mutiara Emas 10/19, Taman Mount Austin, "
    "81100 Johor Bahru, Johor Darul Ta'zim, Malaysia"
)
_BUSINESS_PHONE = os.environ.get('BUSINESS_PHONE', '0196811628')
_BUSINESS_EMAIL = os.environ.get('BUSINESS_EMAIL', 'codencodemy@gmail.com')
_BUSINESS_WEBSITE = os.environ.get('BUSINESS_WEBSITE', 'codencode.my')
_INVOICE_DUE_DAYS = int(os.environ.get('INVOICE_DUE_DAYS', '7'))
_BANK_NAME = os.environ.get('BANK_NAME', 'MAYBANK')
_BANK_ACCOUNT_NAME = os.environ.get('BANK_ACCOUNT_NAME', 'CODE N CODE SOLUTION')
_BANK_ACCOUNT_NO = os.environ.get('BANK_ACCOUNT_NO', '5512 7610 6077')
_DUITNOW_QR_PATH = os.environ.get('DUITNOW_QR_PATH', '/static/img/duitnow-qr.jpg')
_DEFAULT_STUDENT_PASSWORD = os.environ.get('DEFAULT_STUDENT_PASSWORD', 'codencode123')

# ─────────────────────────────────────────────
# WhatsApp notifications disabled for now
# ─────────────────────────────────────────────
_WHATSAPP_DISABLED = True


def send_whatsapp(to_phone: str, body: str) -> bool:
    """WhatsApp sending is disabled for now."""
    app.logger.info('WhatsApp disabled; skipping message to %s', to_phone)
    return False


def _brevo_error_detail(exc) -> str:
    """Extract the actual reason Brevo rejected a request (its body has the real cause)."""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            return f'HTTP {exc.code}: {exc.read().decode("utf-8", "replace")}'
        except Exception:
            return f'HTTP {exc.code}'
    return str(exc)


def send_email(to: str, subject: str, html_body: str):
    """Send email via Brevo HTTP API. Returns True on success, False on failure."""
    if not _BREVO_API_KEY:
        app.logger.warning('BREVO_API_KEY not set — skipping email to %s', to)
        return False
    try:
        payload = _json_mod.dumps({
            'sender':     {'name': _BUSINESS_NAME, 'email': _EMAIL_FROM},
            'to':         [{'email': to}],
            'subject':    subject,
            'htmlContent': html_body,
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            data    = payload,
            headers = {
                'api-key':      _BREVO_API_KEY,
                'Content-Type': 'application/json',
                'Accept':       'application/json',
            },
            method = 'POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True
    except Exception as exc:
        app.logger.error('Email send failed to %s: %s', to, _brevo_error_detail(exc))
        return False


def send_email_bulk(recipients: list[str], subject: str, html_body: str):
    """Send the same email to a list of addresses."""
    results = {r: send_email(r, subject, html_body) for r in recipients}
    return results


def _bill_to_section_html(user, heading='Bill To') -> str:
    """Render invoice/receipt billing details, preferring company billing info."""
    if not user:
        return f'''
    <div class="section">
      <div class="section-title">{html_escape(heading)}</div>
      <p><strong>(deleted)</strong></p>
    </div>'''

    company_name = (getattr(user, 'bill_company_name', '') or '').strip()
    business_reg = (getattr(user, 'bill_business_reg_number', '') or '').strip()
    sst_number = (getattr(user, 'bill_sst_number', '') or '').strip()
    company_address = (getattr(user, 'bill_company_address', '') or '').strip()

    if company_name:
        address_html = '<br>'.join(html_escape(line) for line in company_address.splitlines() if line.strip())
        return f'''
    <div class="section">
      <div class="section-title">{html_escape(heading)}</div>
      <p><strong>{html_escape(company_name)}</strong></p>
      {f'<p>Business Reg No: {html_escape(business_reg)}</p>' if business_reg else ''}
      {f'<p>SST Registration No: {html_escape(sst_number)}</p>' if sst_number else ''}
      {f'<p>{address_html}</p>' if address_html else ''}
      <p>Attention: {html_escape(user.name or '')}</p>
      <p>{html_escape(user.email or '')}</p>
      {f'<p>{html_escape(user.phone)}</p>' if user.phone else ''}
    </div>'''

    return f'''
    <div class="section">
      <div class="section-title">{html_escape(heading)}</div>
      <p><strong>{html_escape(user.name or '')}</strong></p>
      <p>{html_escape(user.email or '')}</p>
      {f'<p>{html_escape(user.phone)}</p>' if user.phone else ''}
      {f'<p>IC/Passport: {html_escape(user.ic_number)}</p>' if user.ic_number else ''}
    </div>'''


def _fmt_money(amount) -> str:
    return f'RM {float(amount or 0):,.2f}'


def _invoice_due_date(issue_dt=None):
    return (issue_dt or datetime.utcnow()) + timedelta(days=_INVOICE_DUE_DAYS)


def _invoice_business_html() -> str:
    addr_html = '<br>'.join(html_escape(line.strip()) for line in _BUSINESS_ADDR.split(', ') if line.strip())
    return f'''
    <div class="business">
      <img src="https://learn.codencode.my/static/img/logo.png" alt="{html_escape(_BUSINESS_NAME)}" class="brand-logo">
      <div class="business-name">{html_escape(_BUSINESS_NAME)}</div>
      <p>SSM / Business Registration No.: {html_escape(_BUSINESS_SSM)}</p>
      <p>{addr_html}</p>
      <p>{html_escape(_BUSINESS_PHONE)} &bull; {html_escape(_BUSINESS_EMAIL)}</p>
      <p>{html_escape(_BUSINESS_WEBSITE)}</p>
    </div>'''


def _invoice_meta_html(doc_no, issue_dt, status, title='INVOICE') -> str:
    due_dt = _invoice_due_date(issue_dt)
    return f'''
    <div class="inv-meta">
      <div class="doc-title">{html_escape(title)}</div>
      <div class="inv-num">{html_escape(doc_no)}</div>
      <p>Issued: {issue_dt.strftime('%d %B %Y')}</p>
      <p>Due: {due_dt.strftime('%d %B %Y')}</p>
      <p>Status: <span class="status-badge">{html_escape((status or 'pending').upper())}</span></p>
    </div>'''


def _invoice_line_items_html(description, qty, unit_price, details=None) -> str:
    qty = int(qty or 1)
    unit_price = float(unit_price or 0)
    amount = qty * unit_price
    detail_html = ''.join(f'<p>{html_escape(label)}: {html_escape(value)}</p>' for label, value in (details or []) if value)
    return f'''
  <div class="section">
    <div class="section-title">Course / Service</div>
    <table class="items">
      <thead><tr><th>Description</th><th>Qty</th><th>Unit Price</th><th>Amount</th></tr></thead>
      <tbody>
        <tr>
          <td>{html_escape(description)}</td>
          <td class="num">{qty}</td>
          <td class="num">{_fmt_money(unit_price)}</td>
          <td class="num">{_fmt_money(amount)}</td>
        </tr>
      </tbody>
    </table>
    <div class="item-details">{detail_html}</div>
  </div>'''


def _payment_summary_html(total, status, discount_amount=0, discount_reason=None) -> str:
    total = float(total or 0)
    discount_amount = max(float(discount_amount or 0), 0)
    subtotal = total + discount_amount
    paid = total if (status or '').lower() == 'paid' else 0
    balance = max(total - paid, 0)
    discount_label = 'Discount'
    if discount_reason:
        discount_label += f' ({html_escape(discount_reason)})'
    discount_row = ''
    if discount_amount > 0:
        discount_row = f'<p><span>{discount_label}:</span><strong>-{_fmt_money(discount_amount)}</strong></p>'
    return f'''
  <div class="section totals">
    <div class="section-title">Amount</div>
    <p><span>Subtotal:</span><strong>{_fmt_money(subtotal)}</strong></p>
    {discount_row}
    <p><span>Total:</span><strong>{_fmt_money(total)}</strong></p>
    <p><span>Amount Paid:</span><strong>{_fmt_money(paid)}</strong></p>
    <div class="balance">BALANCE DUE: {_fmt_money(balance)}</div>
  </div>'''


def _payment_instructions_html(doc_no) -> str:
    qr_fs_path = os.path.join(app.static_folder or '', _DUITNOW_QR_PATH.replace('/static/', '').replace('/', os.sep))
    qr_html = ''
    if os.path.exists(qr_fs_path):
        qr_html = f'''
      <div class="qr-box">
        <div class="qr-title">SCAN TO PAY</div>
        <img src="{html_escape(_DUITNOW_QR_PATH)}" alt="DuitNow QR" class="duitnow-qr">
        <p>Account Name: {html_escape(_BANK_ACCOUNT_NAME)}</p>
      </div>'''
    return f'''
  <div class="section payment-grid">
    <div>
      <div class="section-title">Payment</div>
      <p><strong>Bank:</strong> {html_escape(_BANK_NAME)}</p>
      <p><strong>Account Name:</strong> {html_escape(_BANK_ACCOUNT_NAME)}</p>
      <p><strong>Account No.:</strong> {html_escape(_BANK_ACCOUNT_NO)}</p>
      <p><strong>Reference:</strong> {html_escape(doc_no)}</p>
      <p class="terms"><strong>Payment Terms:</strong> Payment is due by the due date stated on this invoice.</p>
      <p class="terms"><strong>Proof of Payment:</strong> Kindly send your payment receipt via WhatsApp or email after payment.</p>
    </div>
    {qr_html}
  </div>'''


def _invoice_footer_html(doc_no, issue_dt) -> str:
    due_dt = _invoice_due_date(issue_dt)
    return f'''
  <div class="footer">
    <p><strong>{html_escape(_BUSINESS_NAME)}</strong> &bull; SSM No.: {html_escape(_BUSINESS_SSM)}</p>
    <p>{html_escape(_BUSINESS_WEBSITE)} &bull; {html_escape(_BUSINESS_EMAIL)} &bull; {html_escape(_BUSINESS_PHONE)}</p>
    <p>Payment due by {due_dt.strftime('%d %B %Y')}.</p>
    <p>Thank you for learning with us!</p>
    <p><em>This is a computer-generated invoice. No signature is required.</em></p>
    <p style="margin-top:8px">{html_escape(doc_no)} &bull; Generated {issue_dt.strftime('%d %B %Y')}</p>
  </div>'''


def _invoice_page_html(doc_no, status, bill_to_user, description, unit_price, details=None, doc_label='INVOICE', discount_amount=0, discount_reason=None) -> str:
    issue_dt = datetime.utcnow()
    status_colour = {'paid': '#28ca41', 'pending': '#e3b341', 'overdue': '#f85149', 'partially paid': '#2f81f7'}.get(
        (status or 'pending').lower(), '#7d8590')
    total = float(unit_price or 0)
    discount_amount = max(float(discount_amount or 0), 0)
    subtotal = total + discount_amount
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{html_escape(doc_no)} - codencode.my</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Mono:wght@400;700&display=swap');
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:'Space Mono',monospace; background:#fff; color:#2d2d2d; font-size:13px; padding:54px 58px; max-width:920px; margin:auto; }}
    .header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:36px; margin-bottom:24px; }}
    .brand-logo {{ height:38px; display:block; margin-bottom:10px; }}
    .business {{ max-width:520px; color:#666; }}
    .business-name {{ font-family:'Syne',sans-serif; font-size:31px; font-weight:800; color:#080c10; line-height:1.05; margin-bottom:7px; }}
    .inv-meta {{ text-align:right; min-width:280px; color:#666; padding-top:2px; }}
    .doc-title {{ font-family:'Syne',sans-serif; font-size:40px; font-weight:800; color:#080c10; line-height:1; margin-bottom:12px; letter-spacing:0; }}
    .inv-num {{ font-size:13px; font-weight:700; color:#2d2d2d; margin-bottom:6px; }}
    .top-rule {{ border-top:7px solid #080c10; border-bottom:2px solid #00dcb4; height:12px; margin-bottom:18px; }}
    .section {{ margin-bottom:28px; }}
    .section-title {{ font-size:12px; text-transform:uppercase; letter-spacing:0; color:#080c10; font-weight:700; margin-bottom:10px; border-bottom:1px solid #00dcb4; padding-bottom:5px; }}
    .bill-section {{ max-width:100%; margin-bottom:34px; }}
    .bill-section p:first-of-type {{ font-size:16px; font-weight:700; color:#2d2d2d; }}
    .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
    p {{ margin:4px 0; line-height:1.45; }}
    strong {{ color:#080c10; }}
    .status-badge {{ display:inline-block; padding:4px 12px; border-radius:999px; font-size:11px; font-weight:700; color:#fff; background:{status_colour}; }}
    .items {{ width:100%; border-collapse:collapse; margin-top:4px; }}
    .items th {{ text-align:left; font-size:13px; color:#080c10; background:#00dcb4; padding:11px 10px; font-weight:700; }}
    .items td {{ border-bottom:1px solid #d6d6d6; padding:13px 10px; vertical-align:top; }}
    .items .num {{ text-align:right; white-space:nowrap; }}
    .item-details {{ margin-top:12px; color:#333; font-size:12px; }}
    .totals {{ max-width:420px; margin:8px 0 26px auto; }}
    .totals p {{ display:flex; justify-content:space-between; gap:24px; padding:5px 18px; font-size:14px; }}
    .balance {{ margin-top:8px; padding:13px 18px; background:#080c10; font-family:'Syne',sans-serif; font-size:21px; font-weight:800; color:#00dcb4; text-align:right; }}
    .payment-grid {{ display:grid; grid-template-columns:1fr 210px; gap:26px; align-items:start; margin-top:2px; }}
    .terms {{ margin-top:10px; color:#666; font-size:11px; }}
    .qr-box {{ text-align:center; padding:4px 0 0; }}
    .qr-title {{ font-family:'Syne',sans-serif; font-weight:800; margin-bottom:8px; }}
    .duitnow-qr {{ width:150px; height:auto; display:block; margin:0 0 8px auto; }}
    .footer {{ margin-top:28px; padding-top:22px; border-top:1px solid #d6d6d6; font-size:11px; color:#999; text-align:center; }}
    @media print {{
      body {{ padding:20px; }}
      .no-print {{ display:none !important; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    {_invoice_business_html()}
    {_invoice_meta_html(doc_no, issue_dt, status, doc_label)}
  </div>
  <div class="top-rule"></div>

  <div class="bill-section">
    {_bill_to_section_html(bill_to_user)}
  </div>

  {_invoice_line_items_html(description, 1, subtotal, details)}
  {_payment_summary_html(total, status, discount_amount, discount_reason)}
  {_payment_instructions_html(doc_no)}
  {_invoice_footer_html(doc_no, issue_dt)}

  <div class="no-print" style="margin-top:32px;text-align:center">
    <button onclick="window.print()" style="background:#00dcb4;color:#080c10;border:none;padding:10px 28px;border-radius:6px;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer;">
      Print / Save as PDF
    </button>
    <button onclick="window.close()" style="background:#eee;color:#333;border:none;padding:10px 24px;border-radius:6px;font-family:inherit;font-size:13px;cursor:pointer;margin-left:8px;">
      Close
    </button>
  </div>
</body>
</html>"""


def generate_receipt_html(enrollment) -> str:
    """Render the official receipt as a printable HTML page — same template as the
    invoice, rendered fresh from the database every time (nothing stored on disk).
    Assigns a permanent sequential receipt number (RCP-<year>-111, 112, …) the
    first time a paid enrollment's receipt is viewed."""
    s      = enrollment.student
    course = enrollment.course
    rcpt_no = f'RCP-{get_or_assign_document_number(enrollment):03d}'
    paid_d  = (enrollment.paid_at or datetime.utcnow()).strftime('%d %B %Y')
    issued  = datetime.utcnow().strftime('%d %B %Y')
    amt_str = f'RM {enrollment.payment_amount:,.2f}' if enrollment.payment_amount else '—'
    discount = float(enrollment.payment_discount_amount or 0)
    subtotal = float(enrollment.payment_amount or 0) + discount
    discount_html = ''
    if discount > 0:
        reason = f' ({html_escape(enrollment.payment_discount_reason)})' if enrollment.payment_discount_reason else ''
        discount_html = f'''
    <p><strong>Original Amount:</strong> {_fmt_money(subtotal)}</p>
    <p><strong>Discount{reason}:</strong> -{_fmt_money(discount)}</p>'''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{rcpt_no} — codencode.my</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Mono:wght@400;700&display=swap');
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:'Space Mono',monospace; background:#fff; color:#111; font-size:13px; padding:40px; max-width:720px; margin:auto; }}
    .header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:40px; border-bottom:3px solid #00dcb4; padding-bottom:24px; }}
    .brand-logo {{ height:28px; display:block; }}
    .inv-meta {{ text-align:right; }}
    .inv-num {{ font-size:18px; font-weight:700; color:#080c10; }}
    .inv-date {{ color:#555; margin-top:4px; }}
    .section {{ margin-bottom:28px; }}
    .section-title {{ font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#888; margin-bottom:10px; border-bottom:1px solid #eee; padding-bottom:6px; }}
    .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
    p {{ margin:5px 0; line-height:1.6; }}
    strong {{ color:#080c10; }}
    .status-badge {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#fff; background:#28ca41; }}
    .amount-paid {{ font-size:26px; font-weight:700; color:#00a382; }}
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
      <img src="https://learn.codencode.my/static/img/logo.png" alt="codencode.my" class="brand-logo">
      <div style="color:#555;margin-top:4px;font-size:12px">Official Receipt · SSM No. {_BUSINESS_SSM}</div>
    </div>
    <div class="inv-meta">
      <div class="inv-num">{rcpt_no}</div>
      <div class="inv-date">Issued: {issued}</div>
    </div>
  </div>

  <div class="grid-2">
    {_bill_to_section_html(s, 'Received From')}
    <div class="section">
      <div class="section-title">Course</div>
      <p><strong>{course.title}</strong></p>
      {'<p>Format: ' + enrollment.class_format.upper() + '</p>' if enrollment.class_format else ''}
      {'<p>Schedule: ' + enrollment.class_timing + '</p>' if enrollment.class_timing else ''}
    </div>
  </div>

  <div class="section">
    <div class="section-title">Payment Details</div>
    <p><strong>Status:</strong> <span class="status-badge">PAID</span></p>
    <p style="margin-top:12px"><strong>Amount Paid:</strong></p>
    <p class="amount-paid">{amt_str}</p>
    {discount_html}
    <p style="margin-top:12px"><strong>Payment Method:</strong> {enrollment.payment_method or '—'}</p>
    <p><strong>Date Paid:</strong> {paid_d}</p>
  </div>

  <div class="footer">
    <p><strong>{_BUSINESS_NAME}</strong> · SSM No. {_BUSINESS_SSM}</p>
    <p style="margin-top:8px">codencode.my · {rcpt_no} · Generated {issued}</p>
    <p style="margin-top:4px">This is an official receipt. Please retain for your records.</p>
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
  <div class="footer">learn.codencode.my &nbsp;·&nbsp; This is an automated message, please do not reply.<br>For any matters, WhatsApp us at +60 19-861 1628.</div>
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


def email_new_material(student_name: str, email: str, course_title: str, material_title: str, session: int):
    body = f"""
    <p>Hi <strong>{student_name}</strong>,</p>
    <p>New content is available in <strong>{course_title}</strong>:</p>
    <p><strong>Session {session} - {material_title}</strong></p>
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
    """Assign/persist the receipt number and email the student a link to view it."""
    s = enrollment.student
    if not s or not s.email:
        return False
    rcpt_no  = f'RCP-{get_or_assign_document_number(enrollment):03d}'
    amt_str  = f'RM {enrollment.payment_amount:,.2f}' if enrollment.payment_amount else '—'
    paid_d   = (enrollment.paid_at or datetime.utcnow()).strftime('%d %B %Y')
    body = f"""
    <p>Hi <strong>{s.name}</strong>,</p>
    <p>Thank you! Your payment for <strong>{enrollment.course.title}</strong> has been received and confirmed.</p>
    <p>
      <span class="badge">{rcpt_no}</span>&nbsp;
      <span class="badge">{amt_str}</span>
    </p>
    <p style="color:#A4B4A4;font-size:13px">Payment date: {paid_d}</p>
    <a class="btn" href="https://learn.codencode.my/api/enrollments/{enrollment.id}/receipt/view">View Your Receipt →</a>
    """
    return send_email(
        s.email,
        f'Payment Confirmed — {enrollment.course.title} | codencode.my',
        _email_wrapper('Payment Received! 🎉', body)
    )


def _workshop_receipt_serializer():
    return URLSafeSerializer(app.config['SECRET_KEY'], salt='workshop-receipt')


def _workshop_receipt_token(attendee) -> str:
    return _workshop_receipt_serializer().dumps({'rid': attendee.run_id, 'aid': attendee.id})


def email_workshop_payment_receipt(attendee) -> bool:
    """Assign/persist the workshop receipt number and email the attendee a receipt link."""
    client = attendee.client
    run = attendee.run
    workshop = run.workshop if run else None
    if not client or not client.email or not workshop:
        return False
    doc_no = f'RCP-{get_or_assign_attendee_document_number(attendee):03d}'
    amount = attendee.payment_amount
    if amount is None and run:
        amount = run.effective_price()
    amt_str = f'RM {amount:,.2f}' if amount is not None else '—'
    paid_d = (attendee.paid_at or datetime.utcnow()).strftime('%d %B %Y')
    receipt_url = f'https://learn.codencode.my/api/workshop-attendees/receipt/{_workshop_receipt_token(attendee)}'
    body = f"""
    <p>Hi <strong>{client.name}</strong>,</p>
    <p>Thank you! Your payment for <strong>{workshop.title}</strong> has been received and confirmed.</p>
    <p>
      <span class="badge">{doc_no}</span>&nbsp;
      <span class="badge">{amt_str}</span>
    </p>
    <p style="color:#A4B4A4;font-size:13px">Payment date: {paid_d}</p>
    <a class="btn" href="{receipt_url}">View Your Receipt →</a>
    """
    return send_email(
        client.email,
        f'Payment Confirmed — {workshop.title} | codencode.my',
        _email_wrapper('Payment Received! 🎉', body)
    )


def email_invoice(enrollment) -> bool:
    """Send invoice to student by email."""
    s = enrollment.student
    if not s or not s.email:
        return False
    inv_num  = f'INV-{get_or_assign_document_number(enrollment):03d}'
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


def recording_visible_to_student_filter(course_id, student_id):
    enrollment = Enrollment.query.filter_by(
        student_id=student_id, course_id=course_id).first()
    if not enrollment:
        return db.false()
    if enrollment.cohort_id:
        return db.or_(
            Recording.cohort_id.is_(None),
            Recording.cohort_id == enrollment.cohort_id
        )
    return Recording.cohort_id.is_(None)


def visible_recordings_query(course_id, student_id=None):
    query = Recording.query.filter_by(course_id=course_id)
    if student_id:
        query = query.filter(recording_visible_to_student_filter(course_id, student_id))
    return query


def teacher_can_manage_course(course_id):
    """Return True when the current teacher/admin may manage this course."""
    if current_user.role == 'admin':
        return True
    if current_user.role != 'teacher':
        return False
    course = Course.query.get(course_id)
    if not course:
        return False
    if course.teacher_id == current_user.id:
        return True
    if Cohort.query.filter_by(course_id=course_id, teacher_id=current_user.id).first():
        return True
    # Backwards-compatible fallback for old installs with one teacher and unassigned courses.
    return course.teacher_id is None and User.query.filter_by(role='teacher').count() == 1


def teacher_manageable_course_ids():
    """Return course ids the current user can manage."""
    if current_user.role == 'admin':
        return [c.id for c in Course.query.all()]
    if current_user.role != 'teacher':
        return []

    ids = {c.id for c in Course.query.filter_by(teacher_id=current_user.id).all()}
    ids.update(
        h.course_id for h in Cohort.query.filter_by(teacher_id=current_user.id).all()
        if h.course_id
    )
    if User.query.filter_by(role='teacher').count() == 1:
        ids.update(c.id for c in Course.query.filter_by(teacher_id=None).all())
    return sorted(ids)


def next_document_number():
    """Next number in the single shared serial used for invoices, receipts, and
    certificates. First number is 111. All three document types for the same
    enrollment share one number (e.g. INV-111 / RCP-111 / CC-111)."""
    last_number = 110
    for (doc_no,) in Enrollment.query.filter(Enrollment.document_number.isnot(None)) \
                                      .with_entities(Enrollment.document_number).all():
        last_number = max(last_number, doc_no)
    for (cert_no,) in Certificate.query.filter(Certificate.cert_number.isnot(None)) \
                                        .with_entities(Certificate.cert_number).all():
        match = re.search(r'(\d+)$', cert_no or '')
        if match:
            last_number = max(last_number, int(match.group(1)))
    for (doc_no,) in WorkshopAttendee.query.filter(WorkshopAttendee.document_number.isnot(None)) \
                                           .with_entities(WorkshopAttendee.document_number).all():
        last_number = max(last_number, doc_no)
    return last_number + 1


def get_or_assign_document_number(enrollment) -> int:
    """Return this enrollment's shared document number, assigning one on first use."""
    if not enrollment.document_number:
        enrollment.document_number = next_document_number()
        db.session.commit()
    return enrollment.document_number


def get_or_assign_attendee_document_number(attendee) -> int:
    """Return this workshop attendee's shared document number, assigning one on first use."""
    if not attendee.document_number:
        attendee.document_number = next_document_number()
        db.session.commit()
    return attendee.document_number


def send_certificate_email(cert):
    """Email a download link for an issued student certificate."""
    if not cert or not cert.student or not cert.student.email or not cert.course:
        return False
    return email_certificate_issued(
        cert.student.name, cert.student.email,
        cert.course.title, cert.cert_number, cert.id
    )


def issue_certificate_for(student_id, course_id, send_email_now=True):
    """Create and email a certificate for an enrolled student/course."""
    student = User.query.get(student_id)
    course = Course.query.get(course_id)
    if not student or student.role != 'student' or not course:
        return None, ('student/course not found', 404)
    enrollment = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
    if not enrollment:
        return None, ('Student is not enrolled in this course', 400)
    existing = Certificate.query.filter_by(student_id=student_id, course_id=course_id).first()
    if existing:
        return existing, None

    cert = None
    for _ in range(5):
        doc_num = get_or_assign_document_number(enrollment)
        cert = Certificate(
            student_id=student_id,
            course_id=course_id,
            issued_by=current_user.id,
            cert_number=f'CC-{doc_num:03d}'
        )
        db.session.add(cert)
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            existing = Certificate.query.filter_by(student_id=student_id, course_id=course_id).first()
            if existing:
                return existing, None
            cert = None
    if cert is None:
        return None, ('Could not generate a unique certificate number. Please try again.', 409)

    if send_email_now:
        send_certificate_email(cert)
    return cert, None


def issue_blank_name_certificate_for(course_id):
    """Create a course certificate without a named student, for workshops."""
    course = Course.query.get(course_id)
    if not course:
        return None, ('course not found', 404)

    cert = None
    for _ in range(5):
        cert = Certificate(
            student_id=None,
            course_id=course_id,
            issued_by=current_user.id,
            cert_number=f'CC-{next_document_number():03d}'
        )
        db.session.add(cert)
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            cert = None
    if cert is None:
        return None, ('Could not generate a unique certificate number. Please try again.', 409)
    return cert, None


def teacher_can_manage_workshop(workshop_id):
    if current_user.role == 'admin':
        return True
    if current_user.role != 'teacher':
        return False
    workshop = Workshop.query.get(workshop_id)
    if not workshop:
        return False
    if WorkshopRun.query.filter_by(workshop_id=workshop_id, teacher_id=current_user.id).first():
        return True
    return not workshop.runs and User.query.filter_by(role='teacher').count() == 1


def certificate_course_for_workshop(workshop):
    course = Course.query.filter_by(title=workshop.title).first()
    if course:
        return course
    course = Course(
        title=workshop.title,
        description=workshop.description or '',
        total_sessions=1,
        programme='Workshop',
        language='en',
        teacher_id=current_user.id if current_user.role == 'teacher' else None,
    )
    db.session.add(course)
    db.session.flush()
    return course


def issue_workshop_certificate_for(student_id, workshop_id, send_email_now=True):
    student = User.query.get(student_id)
    workshop = Workshop.query.get(workshop_id)
    if not student or student.role != 'student' or not workshop:
        return None, ('student/workshop not found', 404)

    course = certificate_course_for_workshop(workshop)
    enrollment = Enrollment.query.filter_by(student_id=student.id, course_id=course.id).first()
    if not enrollment:
        enrollment = Enrollment(
            student_id=student.id,
            course_id=course.id,
            payment_status='paid',
            class_format='workshop',
        )
        attendee = WorkshopAttendee.query.join(WorkshopRun).filter(
            WorkshopRun.workshop_id == workshop.id,
            WorkshopAttendee.client_id == student.id
        ).order_by(WorkshopAttendee.registered_at.desc()).first()
        if attendee and attendee.document_number:
            enrollment.document_number = attendee.document_number
        db.session.add(enrollment)
        db.session.flush()

    existing = Certificate.query.filter_by(student_id=student.id, course_id=course.id).first()
    if existing:
        return existing, None

    cert = None
    for _ in range(5):
        doc_num = get_or_assign_document_number(enrollment)
        cert = Certificate(
            student_id=student.id,
            course_id=course.id,
            issued_by=current_user.id,
            cert_number=f'CC-{doc_num:03d}'
        )
        db.session.add(cert)
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            existing = Certificate.query.filter_by(student_id=student.id, course_id=course.id).first()
            if existing:
                return existing, None
            cert = None
    if cert is None:
        return None, ('Could not generate a unique certificate number. Please try again.', 409)

    if send_email_now:
        send_certificate_email(cert)
    return cert, None


def _certificate_quantity(data):
    try:
        qty = int(data.get('quantity') or 1)
    except (TypeError, ValueError):
        return None, ('quantity must be a number', 400)
    if qty < 1:
        return None, ('quantity must be at least 1', 400)
    if qty > 200:
        return None, ('quantity cannot exceed 200 per batch', 400)
    return qty, None


# ─────────────────────────────────────────────
# Serve frontends
# ─────────────────────────────────────────────
@app.route('/')
@app.route('/lms')
@app.route('/login')
def serve_frontend():
    return send_from_directory('templates', 'lms.html')


@app.route('/admin')
@login_required
def serve_admin():
    if current_user.role not in ('admin', 'teacher'):
        return send_from_directory('templates', 'lms.html')
    return send_from_directory('templates', 'admin.html')


# ─────────────────────────────────────────────
# Public Registration
# ─────────────────────────────────────────────
@app.route('/register', methods=['GET'])
def serve_register():
    return send_from_directory('templates', 'register.html')


@app.route('/register', methods=['POST'])
def public_register():
    data = request.get_json(silent=True) or {}
    required = ('full_name', 'whatsapp', 'email', 'learning_goals')
    missing = [f for f in required if not str(data.get(f, '')).strip()]
    if missing:
        return jsonify({'detail': f'Missing required fields: {", ".join(missing)}'}), 400

    reg = Registration(
        full_name          = data['full_name'].strip(),
        whatsapp           = data['whatsapp'].strip(),
        email              = data['email'].strip().lower(),
        occupation         = data.get('occupation', '').strip(),
        language           = data.get('language', ''),
        experience_level   = data.get('experience_level', ''),
        referral_source    = data.get('referral_source', ''),
        learning_goals     = data.get('learning_goals', '').strip(),
        course             = data.get('course', ''),
        class_format       = data.get('class_format', ''),
        total_fee          = data.get('total_fee', ''),
        payment_preference = data.get('payment_preference', ''),
        instalment_week1   = data.get('instalment_week1', ''),
        instalment_week3   = data.get('instalment_week3', ''),
        timing             = data.get('timing', ''),
    )
    db.session.add(reg)
    db.session.commit()

    try:
        send_email(
            reg.email,
            'Registration Received — codencode.my',
            _email_wrapper('We got your registration! 🎉', f'''
                <p>Hi {reg.full_name},</p>
                <p>Thanks for registering with <strong>codencode.my</strong>! We've received your details and will WhatsApp you at <strong>{reg.whatsapp}</strong> within 24 hours to confirm your slot.</p>
                <p><strong>Course:</strong> {reg.course or 'Python / ML'}<br>
                <strong>Format:</strong> {reg.class_format}<br>
                <strong>Timing:</strong> {reg.timing}</p>
                <p>Questions? Just reply to this email or WhatsApp us at +60196811628.</p>
            ''')
        )
    except Exception as exc:
        app.logger.warning('Registration confirmation email failed: %s', exc)

    return jsonify({'ok': True, 'id': reg.id}), 200


@app.route('/api/admin/registrations', methods=['GET'])
@login_required
def api_admin_registrations():
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    regs = Registration.query.order_by(Registration.submitted_at.desc()).all()
    return jsonify([r.to_dict() for r in regs])


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
@app.route('/health')
def health():
    return jsonify({'ok': True})


@app.route('/api/courses')
@login_required
def api_courses():
    if current_user.role == 'admin':
        courses = Course.query.order_by(Course.title).all()
    elif current_user.role == 'teacher':
        # Teachers see courses assigned directly, plus courses where they own a cohort/intake.
        from sqlalchemy import or_
        courses = Course.query.outerjoin(Cohort).filter(or_(
            Course.teacher_id == current_user.id,
            Cohort.teacher_id == current_user.id,
        )).order_by(Course.title).distinct().all()
        if not courses and User.query.filter_by(role='teacher').count() == 1:
            courses = Course.query.filter(Course.teacher_id.is_(None)).order_by(Course.title).all()
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
    query = visible_recordings_query(
        cid,
        current_user.id if current_user.role == 'student' else None
    )
    if current_user.role in ('teacher', 'admin'):
        cohort_id = request.args.get('cohort_id')
        if cohort_id:
            Cohort.query.filter_by(id=int(cohort_id), course_id=cid).first_or_404()
            query = query.filter(Recording.cohort_id == int(cohort_id))
    recs = query.order_by(Recording.week, Recording.session_num).all()

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
    current_week = _student_week(cid) if current_user.role == 'student' else course.current_session
    return jsonify({'weeks': weeks, 'current_week': current_week})


@app.route('/api/courses/<int:cid>/recordings', methods=['POST'])
@teacher_required
def api_upload_recording(cid):
    Course.query.get_or_404(cid)
    recording_url = (request.form.get('recording_url') or '').strip()
    cohort_id = request.form.get('cohort_id') or None
    if cohort_id:
        Cohort.query.filter_by(id=int(cohort_id), course_id=cid).first_or_404()
    stored = None
    original = ''
    source_type = 'upload'

    if recording_url:
        if not recording_url.startswith(('https://drive.google.com/', 'https://docs.google.com/')):
            return jsonify({'error': 'Please use a Google Drive folder or file link'}), 400
        original = recording_url
        source_type = 'link'
    else:
        try:
            stored, original = save_upload(
                request.files.get('file'), 'videos',
                app.config['ALLOWED_VIDEO'])
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    rec = Recording(
        course_id   = cid,
        cohort_id   = int(cohort_id) if cohort_id else None,
        week        = int(request.form.get('week', 1)),
        session_num = int(request.form.get('session_num', 1)),
        title       = request.form.get('title') or ('Google Drive Recording' if recording_url else original),
        description = request.form.get('description', ''),
        filename    = stored,
        recording_url = recording_url or None,
        source_type = source_type,
        duration    = request.form.get('duration', '')
    )
    db.session.add(rec)
    db.session.commit()
    return jsonify({'recording': rec.to_dict()}), 201


@app.route('/api/recordings/<int:rid>', methods=['DELETE'])
@teacher_required
def api_delete_recording(rid):
    rec = Recording.query.get_or_404(rid)
    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', rec.filename or '')
    if rec.filename and os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(rec)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/recordings/<int:rid>/watch', methods=['POST'])
@student_required
def api_mark_watched(rid):
    rec = Recording.query.get_or_404(rid)
    if not visible_recordings_query(rec.course_id, current_user.id).filter(
        Recording.id == rid).first():
        return jsonify({'error': 'Recording not available for your class'}), 403
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

def _slide_materials_for_course(course):
    title = f'{course.title or ""} {course.programme or ""}'.lower()
    has_python = 'python' in title
    has_ml = 'machine learning' in title or 'ml' in title
    has_ai_workplace = 'ai' in title and 'workplace' in title

    if has_ai_workplace:
        return [item for item in SLIDE_MATERIALS if item[0] in (14, 15)]
    if has_python and has_ml:
        return SLIDE_MATERIALS
    if has_python:
        return [item for item in SLIDE_MATERIALS if item[0] <= 7]
    if has_ml:
        return [item for item in SLIDE_MATERIALS if item[0] >= 8]
    return []


def _ensure_slide_materials(course):
    expected = _slide_materials_for_course(course)
    if not course or not expected:
        return

    expected_by_filename = {filename: (session_num, title)
                            for session_num, title, filename in expected}
    session_file_pattern = re.compile(r'^Session_(\d+)_Student_.*\.html$')
    existing_materials = Material.query.filter_by(course_id=course.id).all()
    changed = False

    for material in existing_materials:
        if session_file_pattern.match(material.filename or '') and material.filename not in expected_by_filename:
            db.session.delete(material)
            changed = True

    existing = {
        m.filename for m in existing_materials
        if m.filename in expected_by_filename and m not in db.session.deleted
    }
    from sqlalchemy import inspect as sa_inspect
    material_cols = {c['name'] for c in sa_inspect(db.engine).get_columns('materials')}
    materials_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'materials')

    for session_num, title, filename in expected:
        if filename in existing:
            continue
        fpath = os.path.join(materials_dir, filename)
        if not os.path.exists(fpath):
            continue
        values = {
            'course_id': course.id,
            'session': 0,
            'title': title,
            'description': 'Student HTML slides',
            'filename': filename,
            'file_type': 'html',
            'file_size': human_size(fpath),
        }
        if 'is_published' in material_cols:
            values['is_published'] = True
        if 'order_index' in material_cols:
            values['order_index'] = session_num
        db.session.add(Material(**values))
        changed = True
    if changed:
        db.session.commit()


@app.route('/api/courses/<int:cid>/materials')
@login_required
def api_materials(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403

    course = Course.query.get_or_404(cid)
    _ensure_slide_materials(course)
    now = datetime.utcnow()
    mats = Material.query.filter_by(course_id=cid).order_by(
        Material.session, Material.order_index, Material.uploaded_at).all()

    if current_user.role == 'student':
        # Gate by cohort session progress (or course session as fallback) and publish state
        visible_week = _student_week(cid)
        mats = [m for m in mats
                if (m.session == 0 or m.session <= visible_week)
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
        session     = int(request.form.get('session', 0)),
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
    mats = Material.query.filter_by(filename=filename).all()
    if not mats and filename in {item[2] for item in SLIDE_MATERIALS}:
        for course in Course.query.all():
            _ensure_slide_materials(course)
        mats = Material.query.filter_by(filename=filename).all()
    if not mats:
        return jsonify({'error': 'Material not found'}), 404
    if current_user.role == 'student':
        if not any(enrolled_or_staff(m.course_id) for m in mats):
            return jsonify({'error': 'Not enrolled'}), 403
    as_att = request.args.get('download') == '1' or not filename.lower().endswith('.html')
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'materials'),
        filename, as_attachment=as_att)


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
        Assignment.session).all()

    # Gate by cohort session progress (or course session as fallback) for students
    if current_user.role == 'student':
        visible_week = _student_week(cid)
        assignments = [a for a in assignments if a.session <= visible_week]
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
            stored, _ = save_upload(request.files['file'], 'materials',
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
        session     = int(request.form.get('session', 1)),
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
        file = request.files.get('file')
        if not file or file.filename == '':
            return jsonify({'error': 'No file provided'}), 400
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if ext not in app.config['ALLOWED_SUBMISSION']:
            return jsonify({'error': f'File type not allowed'}), 400
        assignment = Assignment.query.get_or_404(aid)
        safe_title  = re.sub(r'[^a-z0-9]+', '', assignment.title.lower())
        safe_name   = re.sub(r'[^a-z0-9]+', '', current_user.name.lower())
        stored = f"{safe_title}_{safe_name}.{ext}"
        dest = os.path.join(app.config['UPLOAD_FOLDER'], 'submissions')
        os.makedirs(dest, exist_ok=True)
        file.save(os.path.join(dest, stored))
        original = file.filename
    except Exception as e:
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
        total_recordings = visible_recordings_query(cid, current_user.id).count()
        watched = WatchLog.query.join(Recording).filter(
            Recording.course_id == cid,
            recording_visible_to_student_filter(cid, current_user.id),
            WatchLog.student_id == current_user.id).count()
        subs = Submission.query.join(Assignment).filter(
            Assignment.course_id == cid,
            Submission.student_id == current_user.id).all()
        graded  = [s for s in subs if s.score is not None]
        avg     = round(sum(s.score for s in graded) / len(graded), 1) if graded else None
        pending = total_assignments - len(subs)

        # Build recent activity feed
        activity = []
        recent_recordings = (visible_recordings_query(cid, current_user.id)
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

        course = Course.query.get(cid)
        return jsonify({
            'videos_watched': watched,
            'total_recordings': total_recordings,
            'assignments_pending': max(pending, 0),
            'total_assignments': total_assignments,
            'assignments_submitted': len(subs),
            'avg_grade': avg,
            'submissions_graded': len(graded),
            'recent_activity': activity[:5],
            'programme': course.programme or course.title or '',
            'current_week': _student_week(cid),
            'weeks': course.total_sessions,
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
            visible_total_recordings = visible_recordings_query(cid, s.id).count()
            watched = WatchLog.query.join(Recording).filter(
                Recording.course_id == cid,
                recording_visible_to_student_filter(cid, s.id),
                WatchLog.student_id == s.id).count()
            subs   = Submission.query.join(Assignment).filter(
                Assignment.course_id == cid,
                Submission.student_id == s.id).all()
            graded = [x for x in subs if x.score is not None]
            avg    = round(sum(x.score for x in graded) / len(graded), 1) if graded else None
            pct    = round((watched / visible_total_recordings * 100)) if visible_total_recordings else 0
            student_progress.append({
                'id': s.id, 'name': s.name, 'email': s.email,
                'initials': s.initials(),
                'videos_watched': watched, 'total_recordings': visible_total_recordings,
                'submissions': len(subs), 'total_assignments': total_assignments,
                'avg_grade': avg, 'progress_pct': pct
            })

        recent_subs = (Submission.query
            .join(Assignment).filter(Assignment.course_id == cid)
            .filter(Submission.score == None)
            .order_by(Submission.submitted_at.desc())
            .limit(5).all())

        course = Course.query.get(cid)
        return jsonify({
            'enrolled_students': enrolled_count,
            'ungraded_submissions': ungraded,
            'total_recordings': total_recordings,
            'total_materials': total_materials,
            'student_progress': student_progress,
            'recent_ungraded': [s.to_dict() for s in recent_subs],
            'programme': course.programme or course.title or '',
            'start_date': course.start_date.strftime('%b %d, %Y') if course.start_date else '',
        })


# ═════════════════════════════════════════════
# ADMIN API
# ═════════════════════════════════════════════

# ── Students ──────────────────────────────────
def _admin_student_payload(student):
    d = student.to_dict()
    d['enrollments'] = [e.to_dict() for e in student.enrollments]
    workshop_attendances = WorkshopAttendee.query.filter_by(client_id=student.id) \
        .join(WorkshopRun, WorkshopAttendee.run_id == WorkshopRun.id) \
        .order_by(WorkshopRun.start_datetime.desc()) \
        .all()
    d['workshop_attendances'] = []
    for att in workshop_attendances:
        run = att.run
        workshop = run.workshop if run else None
        d['workshop_attendances'].append({
            'id': att.id,
            'run_id': att.run_id,
            'workshop_title': workshop.title if workshop else '',
            'start_display': run.start_datetime.strftime('%a, %d %b %Y · %I:%M %p') if run and run.start_datetime else '',
            'venue': (run.venue or '') if run else '',
            'attended': bool(att.attended),
            'payment_status': att.payment_status or 'pending',
            'payment_amount': att.payment_amount,
            'payment_method': att.payment_method or '',
            'paid_at': att.paid_at.strftime('%b %d, %Y') if att.paid_at else None,
            'document_number': att.document_number,
        })
    return d


@app.route('/api/admin/students', methods=['GET', 'POST'])
@admin_required
def admin_students():
    if request.method == 'GET':
        student_ids = {uid for (uid,) in User.query.filter_by(role='student').with_entities(User.id).all()}
        student_ids.update(
            uid for (uid,) in WorkshopAttendee.query.with_entities(WorkshopAttendee.client_id).distinct().all()
        )
        students = User.query.filter(User.id.in_(student_ids)).order_by(User.name).all() if student_ids else []
        return jsonify([_admin_student_payload(s) for s in students])
    # POST
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
        bill_company_name = data.get('bill_company_name', '').strip(),
        bill_business_reg_number = data.get('bill_business_reg_number', '').strip(),
        bill_sst_number = data.get('bill_sst_number', '').strip(),
        bill_company_address = data.get('bill_company_address', '').strip(),
    )
    plain_pw = data.get('password') or 'codencode123'
    u.set_password(plain_pw)
    u.temp_password = plain_pw
    db.session.add(u)
    db.session.commit()
    return jsonify({'student': _admin_student_payload(u)}), 201


@app.route('/api/admin/students/<int:uid>', methods=['GET', 'PUT', 'DELETE'])
@admin_required
def admin_student_detail(uid):
    s = User.query.get_or_404(uid)

    if request.method == 'GET':
        return jsonify(_admin_student_payload(s))

    if request.method == 'DELETE':
        if s.role == 'admin':
            return jsonify({'error': 'Cannot delete admin accounts'}), 403
        Enrollment.query.filter_by(student_id=uid).delete()
        db.session.delete(s)
        db.session.commit()
        return jsonify({'ok': True})

    # PUT
    data = request.get_json()
    if 'name'          in data: s.name          = data['name'].strip()
    if 'phone'         in data: s.phone         = data['phone'].strip()
    if 'ic_number'     in data: s.ic_number     = data['ic_number'].strip()
    if 'language_pref' in data: s.language_pref = data['language_pref']
    if 'bill_company_name' in data: s.bill_company_name = data['bill_company_name'].strip()
    if 'bill_business_reg_number' in data: s.bill_business_reg_number = data['bill_business_reg_number'].strip()
    if 'bill_sst_number' in data: s.bill_sst_number = data['bill_sst_number'].strip()
    if 'bill_company_address' in data: s.bill_company_address = data['bill_company_address'].strip()
    if 'email'         in data:
        new_email = data['email'].strip().lower()
        existing  = User.query.filter_by(email=new_email).first()
        if existing and existing.id != uid:
            return jsonify({'error': 'Email already in use'}), 409
        s.email = new_email
    if 'password' in data and data['password']:
        s.set_password(data['password'])
        s.temp_password = data['password']
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
    if 'payment_discount_reason' in data: e.payment_discount_reason = data['payment_discount_reason'] or None
    if 'payment_discount_amount' in data:
        try:
            e.payment_discount_amount = float(data['payment_discount_amount'] or 0) or None
        except (ValueError, TypeError):
            pass
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
    email_status = None
    if just_paid:
        email_status = {}
        try:
            email_status['receipt_sent'] = email_payment_receipt(e)
        except Exception as exc:
            app.logger.error('Receipt email failed for enrollment %s: %s', eid, exc)
            email_status['receipt_sent'] = False
            email_status['receipt_error'] = str(exc)
        try:
            email_status['confirmation_sent'] = email_enrollment_confirmation(e)
        except Exception as exc:
            app.logger.error('Enrolment confirmation email failed for enrollment %s: %s', eid, exc)
            email_status['confirmation_sent'] = False
            email_status['confirmation_error'] = str(exc)

    return jsonify({'enrollment': e.to_dict(), 'just_paid': just_paid, 'email_status': email_status})


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


@app.route('/api/admin/enrollments/<int:eid>/receipt/view')
@admin_required
def admin_receipt_view(eid):
    """Render the official receipt as printable HTML, generated fresh from the
    database every time — same template as the invoice, no file on disk involved."""
    e = Enrollment.query.get_or_404(eid)
    if e.payment_status != 'paid':
        return jsonify({'error': 'Enrollment is not marked as paid'}), 400
    from flask import Response
    try:
        html = generate_receipt_html(e)
    except Exception as exc:
        app.logger.error('Receipt HTML generation failed for enrollment %s: %s', eid, exc)
        return jsonify({'error': f'Could not generate receipt: {exc}'}), 500
    return Response(html, mimetype='text/html')


@app.route('/api/enrollments/<int:eid>/receipt/view')
@login_required
def student_receipt_view(eid):
    """Student-facing version of the same receipt page — own enrollment only."""
    e = Enrollment.query.get_or_404(eid)
    if current_user.role == 'student' and e.student_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    if e.payment_status != 'paid':
        return jsonify({'error': 'Enrollment is not marked as paid'}), 400
    from flask import Response
    try:
        html = generate_receipt_html(e)
    except Exception as exc:
        app.logger.error('Receipt HTML generation failed for enrollment %s: %s', eid, exc)
        return jsonify({'error': f'Could not generate receipt: {exc}'}), 500
    return Response(html, mimetype='text/html')


@app.route('/api/admin/email-diagnostics')
@admin_required
def admin_email_diagnostics():
    """Report exactly why an email send is failing, without needing server log access."""
    to = request.args.get('to')
    info = {
        'brevo_api_key_present': bool(_BREVO_API_KEY),
        'brevo_api_key_length':  len(_BREVO_API_KEY) if _BREVO_API_KEY else 0,
        'email_from':            _EMAIL_FROM,
    }
    if not to:
        info['note'] = 'Pass ?to=someone@example.com to send a real test email and see the result.'
        return jsonify(info)
    if not _BREVO_API_KEY:
        info['sent'] = False
        info['error'] = 'BREVO_API_KEY is not set in this environment.'
        return jsonify(info)
    try:
        payload = _json_mod.dumps({
            'sender':      {'name': _BUSINESS_NAME, 'email': _EMAIL_FROM},
            'to':          [{'email': to}],
            'subject':     'codencode.my — test email',
            'htmlContent': '<p>This is a diagnostic test email from the LMS.</p>',
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            data    = payload,
            headers = {
                'api-key':      _BREVO_API_KEY,
                'Content-Type': 'application/json',
                'Accept':       'application/json',
            },
            method = 'POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8', 'replace')
        info['sent'] = True
        info['brevo_response'] = body
    except Exception as exc:
        info['sent'] = False
        info['error'] = _brevo_error_detail(exc)
    return jsonify(info)


@app.route('/api/admin/enrollments/<int:eid>/invoice')
@admin_required
def admin_invoice(eid):
    """Return a printable HTML invoice page."""
    e = Enrollment.query.get_or_404(eid)
    s = e.student
    c = e.course
    inv_num  = f'INV-{get_or_assign_document_number(e):03d}'
    issued   = datetime.utcnow().strftime('%d %B %Y')
    enr_date = e.enrolled_at.strftime('%d %B %Y') if e.enrolled_at else issued
    pay_status = (e.payment_status or 'pending').lower()

    status_colour = {'paid': '#28ca41', 'pending': '#e3b341', 'overdue': '#f85149'}.get(
        pay_status, '#7d8590')

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
    .brand-logo {{ height:28px; display:block; }}
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
      <img src="https://learn.codencode.my/static/img/logo.png" alt="codencode.my" class="brand-logo">
      <div style="color:#555;margin-top:4px;font-size:12px">Learning Management System</div>
    </div>
    <div class="inv-meta">
      <div class="inv-num">{inv_num}</div>
      <div class="inv-date">Issued: {issued}</div>
    </div>
  </div>

  <div class="grid-2">
    {_bill_to_section_html(s)}
    <div class="section">
      <div class="section-title">Course</div>
      <p><strong>{c.title}</strong></p>
      <p>Duration: {c.total_sessions} sessions</p>
      <p>Enrolled: {enr_date}</p>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Payment Details</div>
    <p><strong>Status:</strong> <span class="status-badge">{pay_status.upper()}</span></p>
    {'<p><strong>Amount:</strong> RM ' + (str(e.payment_amount) if e.payment_amount else '—') + '</p>'}
    {'<p><strong>Method:</strong> ' + (e.payment_method or '—') + '</p>'}
    {'<p><strong>Remarks:</strong> ' + (e.payment_remarks or '—') + '</p>'}
    {receipt_html}
  </div>

  <div class="footer">
    <p><strong>{_BUSINESS_NAME}</strong> · SSM No. {_BUSINESS_SSM}</p>
    <p style="margin-top:8px">codencode.my · {inv_num} · Generated {issued}</p>
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
    service_details = [
        ('Duration', f'{c.total_sessions} sessions'),
        ('Enrolled', enr_date),
        ('Schedule', e.class_timing or ''),
    ]
    html = _invoice_page_html(
        inv_num,
        pay_status,
        s,
        f'{c.title} - {c.total_sessions} Sessions',
        e.payment_amount or 0,
        service_details,
        discount_amount=e.payment_discount_amount or 0,
        discount_reason=e.payment_discount_reason
    )
    # Send invoice email to student
    try:
        email_invoice(e)
    except Exception as exc:
        app.logger.error('[Invoice] Email failed for enrollment %s: %s', eid, exc)

    from flask import Response
    return Response(html, mimetype='text/html')


# ── Teachers ──────────────────────────────────
@app.route('/api/admin/teachers', methods=['GET', 'POST'])
@admin_required
def admin_teachers():
    if request.method == 'GET':
        teachers = User.query.filter_by(role='teacher').order_by(User.name).all()
        return jsonify([t.to_dict() for t in teachers])
    # POST
    data  = request.get_json()
    email = data.get('email', '').strip().lower()
    if not email or not data.get('name'):
        return jsonify({'error': 'name and email are required'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 409
    t = User(
        name          = data['name'].strip(),
        email         = email,
        role          = 'teacher',
        phone         = data.get('phone', '').strip(),
        ic_number     = data.get('ic_number', '').strip(),
        language_pref = data.get('language_pref', 'en'),
    )
    plain_pw = data.get('password') or 'codencode123'
    t.set_password(plain_pw)
    t.temp_password = plain_pw
    for field in ('title', 'bio', 'education', 'experience',
                  'specializations', 'website', 'linkedin'):
        if field in data:
            setattr(t, field, (data[field] or '').strip())
    db.session.add(t)
    db.session.commit()
    return jsonify({'teacher': t.to_dict()}), 201


@app.route('/api/admin/teachers/<int:uid>', methods=['PUT', 'DELETE'])
@admin_required
def admin_teacher_detail(uid):
    t = User.query.get_or_404(uid)
    if request.method == 'DELETE':
        db.session.delete(t)
        db.session.commit()
        return jsonify({'ok': True})
    # PUT
    data = request.get_json()
    if 'name'          in data: t.name          = data['name'].strip()
    if 'phone'         in data: t.phone         = data['phone'].strip()
    if 'ic_number'     in data: t.ic_number     = data['ic_number'].strip()
    if 'language_pref' in data: t.language_pref = data['language_pref']
    if 'email'         in data:
        new_email = data['email'].strip().lower()
        existing  = User.query.filter_by(email=new_email).first()
        if existing and existing.id != uid:
            return jsonify({'error': 'Email already in use'}), 409
        t.email = new_email
    if 'password' in data and data['password']:
        t.set_password(data['password'])
        t.temp_password = data['password']
    for field in ('title', 'bio', 'education', 'experience',
                  'specializations', 'website', 'linkedin'):
        if field in data:
            setattr(t, field, (data[field] or '').strip())
    db.session.commit()
    return jsonify({'teacher': t.to_dict()})


# ── Teacher self-service profile ───────────────────────────────
@app.route('/api/teacher/profile', methods=['GET', 'PUT'])
@teacher_required
def teacher_profile():
    if request.method == 'GET':
        return jsonify({'profile': current_user.to_dict()})
    # PUT
    data = request.get_json()
    u = current_user
    for field in ('title', 'bio', 'education', 'experience',
                  'specializations', 'website', 'linkedin'):
        if field in data:
            setattr(u, field, (data[field] or '').strip())
    db.session.commit()
    return jsonify({'profile': u.to_dict()})


@app.route('/api/teacher/profile/avatar', methods=['POST'])
@teacher_required
def teacher_upload_avatar():
    """Upload a profile photo for the logged-in teacher."""
    f = request.files.get('file')
    if not f or f.filename == '':
        return jsonify({'error': 'No file'}), 400
    allowed_img = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
    if not allowed(f.filename, allowed_img):
        return jsonify({'error': 'Image files only (jpg, png, webp, gif)'}), 400
    stored, _ = save_upload(f, 'avatars', allowed_img)
    current_user.avatar_filename = stored
    db.session.commit()
    return jsonify({'avatar_filename': stored})


@app.route('/api/courses/<int:cid>/teacher-profile', methods=['GET'])
@login_required
def course_teacher_profile(cid):
    """Return the assigned teacher's profile for a course.
    Accessible by enrolled students and staff."""
    c = Course.query.get_or_404(cid)
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403
    if not c.teacher:
        return jsonify({'teacher': None})
    return jsonify({'teacher': c.teacher.to_dict()})


# ── Courses ───────────────────────────────────
@app.route('/api/admin/courses', methods=['GET', 'POST'])
@admin_required
def admin_courses():
    if request.method == 'GET':
        courses = Course.query.order_by(Course.title).all()
        result  = []
        for c in courses:
            d = c.to_dict()
            d['enrolled_count'] = Enrollment.query.filter_by(course_id=c.id).count()
            result.append(d)
        return jsonify(result)
    # POST
    data = request.get_json()
    if not data.get('title'):
        return jsonify({'error': 'title is required'}), 400
    seat_cap_val = data.get('seat_cap')
    tid = data.get('teacher_id')
    c = Course(
        title           = data['title'].strip(),
        description     = data.get('description', ''),
        total_sessions  = int(data.get('total_sessions', 6)),
        current_session = 1,
        start_date   = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None,
        programme    = data.get('programme', '').strip(),
        language     = data.get('language', 'en'),
        seat_cap     = int(seat_cap_val) if seat_cap_val else None,
        teacher_id   = int(tid) if tid else None,
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({'course': c.to_dict()}), 201


# ── Cohort routes ─────────────────────────────────────────────
@app.route('/api/courses/<int:cid>/cohorts', methods=['GET', 'POST'])
@login_required
def api_cohorts(cid):
    if request.method == 'GET':
        cohorts = Cohort.query.filter_by(course_id=cid).order_by(Cohort.start_date).all()
        return jsonify([c.to_dict() for c in cohorts])
    # POST — admin only
    if current_user.role != 'admin':
        return jsonify({'error': 'Admins only'}), 403
    Course.query.get_or_404(cid)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    sd = None
    if data.get('start_date'):
        sd = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    ed = None
    if data.get('end_date'):
        ed = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    tid = data.get('teacher_id')
    c = Cohort(course_id=cid, name=name, start_date=sd, end_date=ed, current_session=1,
               teacher_id=int(tid) if tid else None)
    db.session.add(c)
    db.session.commit()
    return jsonify({'cohort': c.to_dict()}), 201

@app.route('/api/admin/cohorts/<int:cohort_id>/session', methods=['PUT'])
@admin_required
def admin_set_cohort_session(cohort_id):
    cohort  = Cohort.query.get_or_404(cohort_id)
    course  = cohort.course
    data    = request.get_json()
    session_num = int(data.get('current_session', cohort.current_session))
    session_num = max(1, min(session_num, course.total_sessions))
    cohort.current_session = session_num
    db.session.commit()
    return jsonify({'cohort': cohort.to_dict()})

@app.route('/api/admin/cohorts/<int:cohort_id>', methods=['PUT', 'DELETE'])
@teacher_required
def admin_cohort_detail(cohort_id):
    cohort = Cohort.query.get_or_404(cohort_id)
    if request.method == 'DELETE':
        if current_user.role != 'admin':
            return jsonify({'error': 'Admins only'}), 403
        db.session.delete(cohort)
        db.session.commit()
        return jsonify({'ok': True})
    # PUT
    import json as _json
    data   = request.get_json()
    if data.get('name'):
        cohort.name = data['name'].strip()
    if 'start_date' in data:
        cohort.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data['start_date'] else None
    if 'end_date' in data:
        cohort.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data['end_date'] else None
    if 'current_session' in data:
        cohort.current_session = max(1, min(cohort.course.total_sessions, int(data['current_session'])))
    if 'schedule' in data:
        cohort.schedule = _json.dumps(data['schedule']) if data['schedule'] else None
    if 'notes' in data:
        cohort.notes = data['notes']
    if 'teacher_id' in data:
        tid = data['teacher_id']
        cohort.teacher_id = int(tid) if tid else None
    db.session.commit()
    return jsonify({'cohort': cohort.to_dict()})


def _student_week(course_id):
    """Return the current_session applicable to the logged-in student for this course.
    Uses the student's cohort progress if assigned, otherwise falls back to the course."""
    enrollment = Enrollment.query.filter_by(
        course_id=course_id, student_id=current_user.id).first()
    if enrollment and enrollment.cohort:
        return enrollment.cohort.current_session
    return Course.query.get(course_id).current_session


@app.route('/api/admin/courses/<int:cid>/session', methods=['PUT'])
@admin_required
def admin_set_session(cid):
    c    = Course.query.get_or_404(cid)
    data = request.get_json()
    session_num = int(data.get('current_session', c.current_session))
    session_num = max(1, min(session_num, c.total_sessions))
    c.current_session = session_num
    db.session.commit()
    return jsonify({'course': c.to_dict()})


@app.route('/api/admin/courses/<int:cid>', methods=['PUT', 'DELETE'])
@admin_required
def admin_course_detail(cid):
    c = Course.query.get_or_404(cid)
    if request.method == 'DELETE':
        Enrollment.query.filter_by(course_id=cid).delete()
        db.session.delete(c)
        db.session.commit()
        return jsonify({'ok': True})
    # PUT
    data = request.get_json()
    if 'title'       in data: c.title       = data['title'].strip()
    if 'description' in data: c.description = data['description'].strip()
    if 'total_sessions' in data: c.total_sessions = int(data['total_sessions'])
    if 'programme'   in data: c.programme   = data['programme'].strip()
    if 'language'    in data: c.language    = data['language']
    if 'seat_cap'    in data:
        c.seat_cap = int(data['seat_cap']) if data['seat_cap'] else None
    if 'start_date'  in data and data['start_date']:
        c.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    elif 'start_date' in data and not data['start_date']:
        c.start_date = None
    if 'teacher_id' in data:
        tid = data['teacher_id']
        c.teacher_id = int(tid) if tid else None
    db.session.commit()
    d = c.to_dict()
    d['enrolled_count'] = Enrollment.query.filter_by(course_id=c.id).count()
    return jsonify({'course': d})


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
        session     = int(request.form.get('session', 0)),
        title       = request.form.get('title', original),
        description = request.form.get('description', ''),
        filename    = stored,
        file_type   = ext,
        file_size   = human_size(fpath)
    )
    db.session.add(mat)
    db.session.commit()
    return jsonify({'material': mat.to_dict()}), 201


@app.route('/api/admin/materials/<int:mid>', methods=['PUT', 'DELETE'])
@admin_required
def admin_material_detail(mid):
    mat = Material.query.get_or_404(mid)
    if request.method == 'DELETE':
        fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'materials', mat.filename)
        if os.path.exists(fpath):
            os.remove(fpath)
        db.session.delete(mat)
        db.session.commit()
        return jsonify({'ok': True})
    # PUT
    data = request.get_json()
    if 'session' in data:
        mat.session = max(0, int(data['session']))
    if data.get('title'):
        mat.title = data['title'].strip()
    db.session.commit()
    return jsonify({'material': mat.to_dict()})


# ── Attendance ────────────────────────────────
@app.route('/api/admin/courses/<int:cid>/attendance', methods=['GET', 'POST'])
@admin_required
def admin_attendance(cid):
    if request.method == 'GET':
        course      = Course.query.get_or_404(cid)
        enrollments = Enrollment.query.filter_by(course_id=cid).all()
        records     = Attendance.query.filter_by(course_id=cid).all()
        att_map = {(a.student_id, a.session): a for a in records}
        students_data = []
        for e in enrollments:
            s = e.student
            weeks_data = {}
            for w in range(1, course.current_session + 1):
                att = att_map.get((s.id, w))
                weeks_data[str(w)] = att.status if att else 'absent'
            students_data.append({
                'student_id':   s.id,
                'student_name': s.name,
                'weeks':        weeks_data
            })
        return jsonify({
            'course_id':    cid,
            'current_week': course.current_session,
            'students':     students_data
        })
    # POST
    data       = request.get_json()
    student_id = data.get('student_id')
    session_num = data.get('session')
    status     = data.get('status', 'present')
    notes      = data.get('notes', '')
    if not student_id or not session_num:
        return jsonify({'error': 'student_id and session required'}), 400
    if status not in ('present', 'absent', 'late'):
        return jsonify({'error': 'status must be present/absent/late'}), 400
    att = Attendance.query.filter_by(
        student_id=student_id, course_id=cid, session=session_num).first()
    if att:
        att.status      = status
        att.notes       = notes
        att.recorded_at = datetime.utcnow()
    else:
        att = Attendance(student_id=student_id, course_id=cid,
                         session=session_num, status=status, notes=notes)
        db.session.add(att)
    db.session.commit()
    return jsonify({'attendance': att.to_dict()})


# ── Bulk attendance (whole session at once) ──────
@app.route('/api/admin/courses/<int:cid>/attendance/bulk', methods=['POST'])
@admin_required
def admin_bulk_attendance(cid):
    """Expects { session: int, records: [{student_id, status, notes}] }"""
    data    = request.get_json()
    session_num = data.get('session')
    records = data.get('records', [])
    if not session_num:
        return jsonify({'error': 'session required'}), 400

    for r in records:
        sid    = r.get('student_id')
        status = r.get('status', 'absent')
        notes  = r.get('notes', '')
        att    = Attendance.query.filter_by(
            student_id=sid, course_id=cid, session=session_num).first()
        if att:
            att.status      = status
            att.notes       = notes
            att.recorded_at = datetime.utcnow()
        else:
            att = Attendance(student_id=sid, course_id=cid,
                             session=session_num, status=status, notes=notes)
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
    to = request.args.get('to', current_user.email)
    ok = send_email(
        to,
        'codencode.my — Email test',
        _email_wrapper('Email is working!',
            '<p>This is a test email from your codencode.my LMS. SMTP is configured correctly.</p>')
    )
    return jsonify({'sent': ok, 'to': to})


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
    created = []

    admin = User.query.filter_by(email='admin@codencode.my').first()
    if not admin:
        admin = User(name='Admin', email='admin@codencode.my', role='admin',
                     phone='010-0000000', ic_number='')
        admin.set_password('admin1234')
        db.session.add(admin)
        created.append('admin')

    teacher = User.query.filter_by(email='teacher@codencode.my').first()
    if not teacher:
        teacher = User(name='Teacher', email='teacher@codencode.my', role='teacher',
                       phone='011-2345678', ic_number='')
        teacher.set_password('demo1234')
        db.session.add(teacher)
        created.append('teacher')

    if not User.query.filter_by(email='student@codencode.my').first():
        student = User(name='Student', email='student@codencode.my', role='student',
                       phone='012-3456789', ic_number='')
        student.set_password('demo1234')
        db.session.add(student)
        created.append('student')

    if created:
        db.session.commit()
        print(f'Default accounts seeded: {", ".join(created)}')

@app.cli.command('reset-certificates')
def reset_certificates_command():
    """Delete all certificate records. Next issued cert starts at CC-111."""
    deleted = Certificate.query.delete()
    db.session.commit()
    print(f'Deleted {deleted} certificate record(s). Next document number is {next_document_number()}.')

def _seed_demo_old():
    # ── Courses ────────────────────────────────
    python_course = Course(
        title='Python Programming Bootcamp',
        description='6-session hands-on Python course from beginner to advanced.',
        total_sessions=6, current_session=3, programme='Python Bootcamp')
    python_course.start_date = datetime(2026, 5, 8).date()
    ml_course = Course(
        title='Machine Learning Fundamentals',
        description='Practical ML: NumPy, Pandas, scikit-learn, and real projects.',
        total_sessions=6, current_session=2, programme='Machine Learning')
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
        (1, 'Session 1 — Variables, Loops & Lists', 'py_week1_exercises.py','py',  '3.0 KB'),
        (2, 'Session 2 — Functions',            'py_week2_exercises.py',    'py',  '3.6 KB'),
        (3, 'Session 3 — OOP: Classes & Objects','py_week3_exercises.py',   'py',  '4.8 KB'),
        (4, 'Session 4 — Files & Error Handling','py_week4_exercises.py',   'py',  '3.9 KB'),
        (5, 'Session 5 — Modules & Pythonic Code','py_week5_exercises.py',  'py',  '5.3 KB'),
        (6, 'Session 6 — Building Real Projects','py_week6_exercises.py',   'py',  '8.8 KB'),
        (6, 'Session 6 — Mini Project Starter', 'py_week6_project_starter.py','py','6.9 KB'),
    ]
    for wk, title, fname, ftype, fsize in py_materials:
        db.session.add(Material(course_id=python_course.id, session=wk,
            title=title, filename=fname, file_type=ftype, file_size=fsize))

    ml_materials = [
        (0, 'Lecture Slides — All Sessions',   'ml_slides.zip',                 'zip', '4.7 MB'),
        (0, 'ML Cheat Sheet',                  'ml_cheat_sheet.py',             'py',  '4.6 KB'),
        (1, 'Session 1 — NumPy Fundamentals',     'ml_week1_exercises.py',         'py',  '4.3 KB'),
        (2, 'Session 2 — Pandas Data Wrangling',  'ml_week2_exercises.py',         'py',  '4.7 KB'),
        (3, 'Session 3 — Your First ML Model',    'ml_week3_exercises.py',         'py',  '4.7 KB'),
        (4, 'Session 4 — Classification',         'ml_week4_exercises.py',         'py',  '4.5 KB'),
        (5, 'Session 5 — Random Forest & Eval',   'ml_week5_exercises.py',         'py',  '4.9 KB'),
        (6, 'Session 6 — Feature Engineering',    'ml_week6_feature_engineering.py','py', '6.3 KB'),
        (6, 'Session 6 — Capstone Starter',       'ml_week6_capstone.py',          'py',  '7.6 KB'),
    ]
    for wk, title, fname, ftype, fsize in ml_materials:
        db.session.add(Material(course_id=ml_course.id, session=wk,
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
        a = Assignment(course_id=python_course.id, session=wk, title=title,
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
        a = Assignment(course_id=ml_course.id, session=wk, title=title,
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
            session=wk, status=status))

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
            session=wk, status=status))

    db.session.commit()
    print('✓ Demo data seeded (unused)')


# ─────────────────────────────────────────────
# SESSIONS (live class scheduling)
# ─────────────────────────────────────────────

def _zoom_configured():
    return all(os.environ.get(k) for k in ('ZOOM_ACCOUNT_ID', 'ZOOM_CLIENT_ID', 'ZOOM_CLIENT_SECRET'))


def _zoom_access_token():
    if not _zoom_configured():
        return None
    now = time.time()
    if _zoom_token_cache['token'] and _zoom_token_cache['expires_at'] > now + 60:
        return _zoom_token_cache['token']

    client_id = os.environ['ZOOM_CLIENT_ID']
    client_secret = os.environ['ZOOM_CLIENT_SECRET']
    account_id = os.environ['ZOOM_ACCOUNT_ID']
    basic = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    payload = urllib.parse.urlencode({
        'grant_type': 'account_credentials',
        'account_id': account_id,
    }).encode()
    req = urllib.request.Request(
        'https://zoom.us/oauth/token',
        data=payload,
        headers={
            'Authorization': f'Basic {basic}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        body = _json_mod.loads(res.read().decode())
    _zoom_token_cache.update({
        'token': body['access_token'],
        'expires_at': now + int(body.get('expires_in', 3600)),
        'api_url': body.get('api_url') or 'https://api.zoom.us',
    })
    return _zoom_token_cache['token']


def _create_zoom_meeting(title, start_dt, duration_minutes):
    token = _zoom_access_token()
    if not token:
        return None
    zoom_user = os.environ.get('ZOOM_USER_ID', 'me')
    timezone = os.environ.get('ZOOM_TIMEZONE', 'Asia/Kuala_Lumpur')
    api_url = _zoom_token_cache.get('api_url') or 'https://api.zoom.us'
    url = f"{api_url}/v2/users/{urllib.parse.quote(zoom_user, safe='')}/meetings"
    payload = _json_mod.dumps({
        'topic': title,
        'type': 2,
        'start_time': start_dt.strftime('%Y-%m-%dT%H:%M:%S'),
        'timezone': timezone,
        'duration': int(duration_minutes or 60),
        'settings': {
            'join_before_host': True,
            'waiting_room': False,
            'mute_upon_entry': True,
            'approval_type': 2,
            'audio': 'both',
        }
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return _json_mod.loads(res.read().decode())

@app.route('/api/sessions', methods=['GET', 'POST'])
@login_required
def api_sessions():
    if request.method == 'GET':
        if current_user.role in ('teacher', 'admin'):
            sessions = Session.query.filter_by(created_by=current_user.id).order_by(Session.start_datetime).all()
            return jsonify([s.to_dict() for s in sessions])
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
    # POST — teacher/admin only
    if current_user.role not in ('teacher', 'admin'):
        return jsonify({'error': 'Teachers only'}), 403
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
    if not zoom_link and _zoom_configured():
        try:
            meeting = _create_zoom_meeting(title, start_dt, duration)
            zoom_link = (meeting or {}).get('join_url', '')
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors='ignore')
            return jsonify({'error': f'Zoom meeting could not be created: {msg or e.reason}'}), 502
        except Exception as e:
            return jsonify({'error': f'Zoom meeting could not be created: {e}'}), 502
    s = Session(
        title=title, session_type=session_type, course_id=course_id or None,
        start_datetime=start_dt, duration_minutes=duration,
        zoom_link=zoom_link, created_by=current_user.id
    )
    db.session.add(s)
    db.session.flush()
    for sid in participant_ids:
        db.session.add(SessionParticipant(session_id=s.id, student_id=int(sid)))
    db.session.commit()
    return jsonify({'session': s.to_dict()}), 201


@app.route('/api/sessions/timetable', methods=['GET'])
@login_required
def api_sessions_timetable():
    now = datetime.utcnow()
    timetable_items = []
    if current_user.role in ('teacher', 'admin'):
        if current_user.role == 'admin':
            sessions = Session.query.order_by(Session.start_datetime).all()
            courses = Course.query.order_by(Course.title).all()
        else:
            sessions = [
                s for s in Session.query.order_by(Session.start_datetime).all()
                if s.created_by == current_user.id or (s.course and s.course.teacher_id == current_user.id)
            ]
            courses = [
                c for c in Course.query.order_by(Course.title).all()
                if c.teacher_id == current_user.id or any(h.teacher_id == current_user.id for h in c.cohorts)
            ]
        for course in courses:
            if current_user.role == 'admin' or course.teacher_id == current_user.id:
                scopes = [(None, '')] + [(h.id, h.name) for h in course.cohorts]
            else:
                scopes = [(h.id, h.name) for h in course.cohorts if h.teacher_id == current_user.id]
            for cohort_id, cohort_name in scopes:
                data = _build_timetable(course, cohort_id=cohort_id, include_blank=False)
                teacher = data.get('cohort_id') and Cohort.query.get(data['cohort_id'])
                teacher_user = teacher.teacher if teacher and teacher.teacher else course.teacher
                student_names = []
                if cohort_id:
                    student_names = [e.student.name for e in Enrollment.query.filter_by(cohort_id=cohort_id).all() if e.student]
                else:
                    student_names = [e.student.name for e in course.enrollments if e.student and not e.cohort_id]
                for week in data['weeks']:
                    for row in week['sessions']:
                        if not row.get('date_iso') or not row.get('time_start'):
                            continue
                        start_dt = datetime.strptime(
                            f"{row['date_iso']}T{row['time_start']}", '%Y-%m-%dT%H:%M'
                        )
                        timetable_items.append({
                            'id': f"tt-{course.id}-{cohort_id or 'course'}-{week['week']}-{row['session_num']}",
                            'title': row.get('topic') or f"Session {week['week']}",
                            'session_type': 'cohort' if cohort_id else 'class',
                            'course_id': course.id,
                            'course_title': course.title,
                            'cohort_id': cohort_id,
                            'cohort_name': cohort_name,
                            'teacher_id': teacher_user.id if teacher_user else None,
                            'teacher_name': teacher_user.name if teacher_user else '',
                            'student_names': student_names,
                            'start_datetime': start_dt.strftime('%Y-%m-%dT%H:%M'),
                            'start_display': start_dt.strftime('%a, %d %b %Y · %I:%M %p'),
                            'duration_minutes': row.get('duration_minutes') or 60,
                            'zoom_link': '',
                            'recording_url': '',
                            'has_recording': False,
                            'source': 'planned',
                        })
    else:
        enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
        enrolled_course_ids = {e.course_id for e in enrollments}
        participant_session_ids = {p.session_id for p in SessionParticipant.query.filter_by(student_id=current_user.id).all()}
        sessions = []
        for s in Session.query.order_by(Session.start_datetime).all():
            if s.session_type == 'cohort' and s.course_id in enrolled_course_ids:
                sessions.append(s)
            elif s.session_type in ('group', 'private') and s.id in participant_session_ids:
                sessions.append(s)
        timetable_items = []
        for e in enrollments:
            if not e.course:
                continue
            current_week = e.cohort.current_session if e.cohort else e.course.current_session
            data = _build_timetable(
                e.course,
                cohort_id=e.cohort_id,
                weeks=4,
                start_week=current_week,
                include_blank=False
            )
            for week in data['weeks']:
                for row in week['sessions']:
                    if not row.get('date_iso') or not row.get('time_start'):
                        continue
                    start_dt = datetime.strptime(
                        f"{row['date_iso']}T{row['time_start']}", '%Y-%m-%dT%H:%M'
                    )
                    timetable_items.append({
                        'id': f"tt-{e.course_id}-{e.cohort_id or 'course'}-{week['week']}-{row['session_num']}",
                        'title': row.get('topic') or f"Session {week['week']} Class",
                        'session_type': 'cohort' if e.cohort_id else 'class',
                        'course_id': e.course_id,
                        'course_title': e.course.title,
                        'cohort_id': e.cohort_id,
                        'cohort_name': e.cohort.name if e.cohort else '',
                        'teacher_id': e.cohort.teacher_id if e.cohort and e.cohort.teacher_id else e.course.teacher_id,
                        'teacher_name': e.cohort.teacher.name if e.cohort and e.cohort.teacher else (e.course.teacher.name if e.course.teacher else ''),
                        'student_names': [current_user.name],
                        'start_datetime': start_dt.strftime('%Y-%m-%dT%H:%M'),
                        'start_display': start_dt.strftime('%a, %d %b %Y · %I:%M %p'),
                        'duration_minutes': row.get('duration_minutes') or 60,
                        'zoom_link': '',
                        'recording_url': '',
                        'has_recording': False,
                        'source': 'planned',
                    })
    session_items = []
    for s in sessions:
        item = s.to_dict()
        end_dt = s.start_datetime + timedelta(minutes=s.duration_minutes or 60)
        if s.session_type == 'cohort' and s.course:
            student_names = [e.student.name for e in s.course.enrollments if e.student]
        else:
            student_names = [p.student.name for p in s.participants if p.student]
        item.update({
            'time_end': end_dt.strftime('%H:%M'),
            'date': s.start_datetime.strftime('%Y-%m-%d'),
            'student_names': student_names,
            'source': 'session',
        })
        session_items.append(item)
    all_items = session_items + timetable_items
    for item in all_items:
        start_dt = datetime.strptime(item['start_datetime'], '%Y-%m-%dT%H:%M')
        end_dt = start_dt + timedelta(minutes=item.get('duration_minutes') or 60)
        item['date'] = item.get('date') or start_dt.strftime('%Y-%m-%d')
        item['time_start'] = start_dt.strftime('%H:%M')
        item['time_end'] = item.get('time_end') or end_dt.strftime('%H:%M')
        item['month_key'] = start_dt.strftime('%Y-%m')
    upcoming = [s for s in all_items if datetime.strptime(s['start_datetime'], '%Y-%m-%dT%H:%M') >= now]
    past     = [s for s in all_items if datetime.strptime(s['start_datetime'], '%Y-%m-%dT%H:%M') < now]
    upcoming.sort(key=lambda s: s['start_datetime'])
    past.sort(key=lambda s: s['start_datetime'], reverse=True)
    all_items.sort(key=lambda s: s['start_datetime'])
    return jsonify({'upcoming': upcoming, 'past': past, 'events': all_items})


@app.route('/api/sessions/<int:sid>', methods=['PUT', 'DELETE'])
@teacher_required
def api_session_detail(sid):
    s = Session.query.get_or_404(sid)
    if request.method == 'DELETE':
        db.session.delete(s)
        db.session.commit()
        return jsonify({'ok': True})
    # PUT
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


@app.route('/api/admin/calendar', methods=['GET'])
@admin_required
def admin_calendar():
    """Session calendar data for admin scheduling and availability checks."""
    start_str = request.args.get('start')
    teacher_id = request.args.get('teacher_id')
    try:
        start_day = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else datetime.utcnow().date()
    except ValueError:
        start_day = datetime.utcnow().date()
    start_day = start_day - timedelta(days=start_day.weekday())
    end_day = start_day + timedelta(days=7)

    events = []
    query = Session.query.filter(
        Session.start_datetime >= datetime.combine(start_day, datetime.min.time()),
        Session.start_datetime < datetime.combine(end_day, datetime.min.time())
    ).order_by(Session.start_datetime)
    for s in query.all():
        item = s.to_dict()
        if teacher_id and str(item.get('teacher_id') or item.get('created_by')) != str(teacher_id):
            continue
        end_dt = s.start_datetime + timedelta(minutes=s.duration_minutes or 60)
        item.update({
            'source': 'session',
            'date': s.start_datetime.strftime('%Y-%m-%d'),
            'time_start': s.start_datetime.strftime('%H:%M'),
            'time_end': end_dt.strftime('%H:%M'),
            'end_datetime': end_dt.strftime('%Y-%m-%dT%H:%M'),
        })
        events.append(item)

    courses = Course.query.all()
    for course in courses:
        scopes = [None] + list(course.cohorts)
        for cohort in scopes:
            current_week = cohort.current_session if cohort else course.current_session
            data = _build_timetable(
                course,
                cohort_id=cohort.id if cohort else None,
                weeks=8,
                start_week=current_week or 1,
                include_blank=False
            )
            event_teacher = cohort.teacher if cohort and cohort.teacher else course.teacher
            if teacher_id and str(event_teacher.id if event_teacher else '') != str(teacher_id):
                continue
            for week in data['weeks']:
                for row in week['sessions']:
                    if not row.get('date_iso') or not row.get('time_start'):
                        continue
                    if not (start_day <= datetime.strptime(row['date_iso'], '%Y-%m-%d').date() < end_day):
                        continue
                    title = row.get('topic') or f"Session {week['week']} Class"
                    start_dt = datetime.strptime(f"{row['date_iso']}T{row['time_start']}", '%Y-%m-%dT%H:%M')
                    end_dt = start_dt + timedelta(minutes=row.get('duration_minutes') or 60)
                    events.append({
                        'id': f"tt-{course.id}-{cohort.id if cohort else 'course'}-{week['week']}-{row['session_num']}",
                        'source': 'timetable',
                        'title': title,
                        'session_type': 'cohort' if cohort else 'class',
                        'course_id': course.id,
                        'course_title': course.title,
                        'cohort_id': cohort.id if cohort else None,
                        'cohort_name': cohort.name if cohort else '',
                        'teacher_id': event_teacher.id if event_teacher else None,
                        'teacher_name': event_teacher.name if event_teacher else '',
                        'date': row['date_iso'],
                        'time_start': row.get('time_start'),
                        'time_end': row.get('time_end'),
                        'start_datetime': start_dt.strftime('%Y-%m-%dT%H:%M'),
                        'end_datetime': end_dt.strftime('%Y-%m-%dT%H:%M'),
                        'start_display': start_dt.strftime('%a, %d %b %Y · %I:%M %p'),
                        'duration_minutes': row.get('duration_minutes') or 60,
                    })

    teachers = User.query.filter_by(role='teacher').order_by(User.name).all()
    return jsonify({
        'start': start_day.strftime('%Y-%m-%d'),
        'end': (end_day - timedelta(days=1)).strftime('%Y-%m-%d'),
        'teachers': [{'id': t.id, 'name': t.name} for t in teachers],
        'events': sorted(events, key=lambda e: e['start_datetime']),
    })


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

@app.route('/api/announcements', methods=['GET', 'POST'])
@login_required
def api_announcements():
    if request.method == 'GET':
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
    # POST — teacher/admin only
    if current_user.role not in ('teacher', 'admin'):
        return jsonify({'error': 'Teachers only'}), 403
    data      = request.get_json()
    title     = data.get('title', '').strip()
    content   = data.get('content', '').strip()
    course_id = data.get('course_id')
    if not title or not content:
        return jsonify({'error': 'title and content required'}), 400
    ann = Announcement(
        title=title, content=content,
        course_id=course_id or None,
        created_by=current_user.id
    )
    db.session.add(ann)
    db.session.commit()
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
_DEFAULT_TIMETABLE_SLOTS = [
    {'session_num': 1, 'day': 'Friday',   'time_start': '20:00', 'time_end': '22:00', 'day_offset': 0},
    {'session_num': 2, 'day': 'Saturday', 'time_start': '09:00', 'time_end': '11:00', 'day_offset': 1},
    {'session_num': 3, 'day': 'Sunday',   'time_start': '09:00', 'time_end': '11:00', 'day_offset': 2},
]

_DAY_INDEX = {
    'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3,
    'Friday': 4, 'Saturday': 5, 'Sunday': 6,
}


def _time_label(value):
    if not value:
        return ''
    try:
        return datetime.strptime(value, '%H:%M').strftime('%-I:%M %p')
    except ValueError:
        return value


def _time_duration_minutes(start, end):
    try:
        s = datetime.strptime(start, '%H:%M')
        e = datetime.strptime(end, '%H:%M')
        minutes = int((e - s).total_seconds() // 60)
        return minutes if minutes > 0 else 60
    except Exception:
        return 60


def _day_offset(day_name, start_date=None):
    if not start_date:
        return {'Friday': 0, 'Saturday': 1, 'Sunday': 2}.get(day_name, _DAY_INDEX.get(day_name, 0))
    return (_DAY_INDEX.get(day_name, start_date.weekday()) - start_date.weekday()) % 7


def _scope_for_timetable(course, cohort_id=None):
    cohort = None
    if cohort_id:
        cohort = Cohort.query.filter_by(id=int(cohort_id), course_id=course.id).first_or_404()
    return {
        'cohort': cohort,
        'start_date': cohort.start_date if cohort and cohort.start_date else course.start_date,
        'current_week': cohort.current_session if cohort else course.current_session,
    }


def _cohort_schedule_slots(cohort):
    if not cohort or not cohort.schedule:
        return []
    try:
        raw_slots = _json_mod.loads(cohort.schedule)
    except Exception:
        return []
    slots = []
    for i, slot in enumerate(raw_slots, start=1):
        day = slot.get('day') or 'Friday'
        slots.append({
            'session_num': i,
            'day': day,
            'time_start': slot.get('start') or '20:00',
            'time_end': slot.get('end') or '22:00',
            'day_offset': None,
        })
    return slots


def _build_timetable(course, cohort_id=None, weeks=None, start_week=1, include_blank=True):
    from datetime import timedelta, date as date_type
    scope = _scope_for_timetable(course, cohort_id)
    cohort = scope['cohort']
    start_date = scope['start_date']
    current_week = scope['current_week']
    max_week = course.total_sessions
    end_week = min(max_week, start_week + weeks - 1) if weeks else max_week
    start_week = max(1, min(start_week, max_week))
    slots = _cohort_schedule_slots(cohort) or _DEFAULT_TIMETABLE_SLOTS
    shared_rows = TimetableSession.query.filter_by(course_id=course.id, cohort_id=None).all()
    scoped_rows = []
    if cohort:
        scoped_rows = TimetableSession.query.filter_by(course_id=course.id, cohort_id=cohort.id).all()
    shared = {(s.week, s.session_num): s for s in shared_rows}
    scoped = {(s.week, s.session_num): s for s in scoped_rows}
    query = shared_rows + scoped_rows
    today = date_type.today()
    weeks_out = []
    for w in range(start_week, end_week + 1):
        nums = sorted({slot['session_num'] for slot in slots} |
                      {s.session_num for s in query if s.week == w})
        sessions = []
        for snum in nums:
            base = next((slot for slot in slots if slot['session_num'] == snum), None) or {
                'session_num': snum, 'day': 'Friday', 'time_start': '20:00', 'time_end': '22:00', 'day_offset': 0
            }
            shared_s = shared.get((w, snum))
            scoped_s = scoped.get((w, snum))
            db_s = scoped_s or shared_s
            timing_s = scoped_s or shared_s
            day_name = timing_s.day_name if timing_s and timing_s.day_name else base['day']
            time_start = timing_s.time_start if timing_s and timing_s.time_start else base['time_start']
            time_end = timing_s.time_end if timing_s and timing_s.time_end else base['time_end']
            day_offset = _day_offset(day_name, start_date)
            if start_date:
                sd = start_date + timedelta(weeks=w - 1, days=day_offset)
                date_str = sd.strftime('%d %b %Y')
                date_iso = sd.strftime('%Y-%m-%d')
                is_past = sd < today
                is_today = sd == today
            else:
                date_str = date_iso = None
                is_past = is_today = False
            topic = shared_s.topic if shared_s else None
            notes = shared_s.notes if shared_s else None
            if not include_blank and not topic:
                continue
            sessions.append({
                'id': db_s.id if db_s else None,
                'session_num': snum,
                'day': day_name,
                'date': date_str,
                'date_iso': date_iso,
                'time_start': time_start,
                'time_start_display': _time_label(time_start),
                'time_end': time_end,
                'time_end_display': _time_label(time_end),
                'topic': topic,
                'notes': notes,
                'is_past': is_past,
                'is_today': is_today,
                'duration_minutes': _time_duration_minutes(time_start, time_end),
            })
        weeks_out.append({'week': w, 'sessions': sessions})
    return {
        'weeks': weeks_out,
        'current_week': current_week,
        'start_date': start_date.strftime('%Y-%m-%d') if start_date else None,
        'cohort_id': cohort.id if cohort else None,
        'cohort_name': cohort.name if cohort else '',
    }


@app.route('/api/courses/<int:cid>/timetable')
@login_required
def api_get_timetable(cid):
    if not enrolled_or_staff(cid):
        return jsonify({'error': 'Not enrolled'}), 403
    course = Course.query.get_or_404(cid)
    cohort_id = request.args.get('cohort_id') or None
    return jsonify(_build_timetable(course, cohort_id=cohort_id))


@app.route('/api/courses/<int:cid>/timetable', methods=['PUT'])
@login_required
def api_save_timetable_session(cid):
    if current_user.role not in ('teacher', 'admin'):
        return jsonify({'error': 'Teachers only'}), 403
    data    = request.get_json()
    week    = int(data.get('week'))
    cohort_id = data.get('cohort_id') or None
    snum    = data.get('session_num')
    topic   = (data.get('topic')   or '').strip()
    notes   = (data.get('notes')   or '').strip()
    day_name = data.get('day') or data.get('day_name') or 'Friday'
    time_start = data.get('time_start') or '20:00'
    time_end = data.get('time_end') or '22:00'
    day_offset = data.get('day_offset')
    if day_offset is None:
        course = Course.query.get_or_404(cid)
        cohort = Cohort.query.filter_by(id=int(cohort_id), course_id=cid).first() if cohort_id else None
        base_date = cohort.start_date if cohort and cohort.start_date else course.start_date
        day_offset = _day_offset(day_name, base_date)
    if cohort_id:
        Cohort.query.filter_by(id=int(cohort_id), course_id=cid).first_or_404()
    if not snum:
        max_num = db.session.query(db.func.max(TimetableSession.session_num)).filter_by(
            course_id=cid, cohort_id=int(cohort_id) if cohort_id else None, week=week
        ).scalar() or 0
        snum = max(max_num + 1, 4)
    snum = int(snum)
    shared_s = TimetableSession.query.filter_by(
        course_id=cid, cohort_id=None, week=week, session_num=snum
    ).first()
    if shared_s:
        shared_s.topic = topic
        shared_s.notes = notes
    else:
        shared_s = TimetableSession(
            course_id=cid, cohort_id=None, week=week, session_num=snum,
            day_name=day_name if not cohort_id else None,
            time_start=time_start if not cohort_id else None,
            time_end=time_end if not cohort_id else None,
            day_offset=int(day_offset) if not cohort_id else 0,
            topic=topic, notes=notes
        )
        db.session.add(shared_s)
    if not cohort_id:
        db.session.commit()
        return jsonify({'ok': True})
    s = TimetableSession.query.filter_by(
        course_id=cid, cohort_id=int(cohort_id), week=week, session_num=snum
    ).first()
    if s:
        s.day_name = day_name; s.time_start = time_start; s.time_end = time_end; s.day_offset = int(day_offset)
    else:
        s = TimetableSession(
            course_id=cid, cohort_id=int(cohort_id),
            week=week, session_num=snum, day_name=day_name,
            time_start=time_start, time_end=time_end, day_offset=int(day_offset),
            topic=None, notes=None
        )
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
        writer.writerow(['Student', 'Email', 'Assignment', 'Session', 'Submitted At', 'Score', 'Max Points', 'Feedback'])
        q = Submission.query.join(Assignment)
        if course_id:
            q = q.filter(Assignment.course_id == course_id)
        for sub in q.all():
            writer.writerow([
                sub.student.name, sub.student.email,
                sub.assignment.title, sub.assignment.session,
                sub.submitted_at.strftime('%Y-%m-%d %H:%M'),
                sub.score or '', sub.assignment.max_points,
                sub.feedback or ''
            ])
    elif export_type == 'attendance':
        if not course_id:
            return jsonify({'error': 'course_id required for attendance export'}), 400
        course = Course.query.get_or_404(course_id)
        week_headers = [f'Session {w}' for w in range(1, course.current_session + 1)]
        writer.writerow(['Student', 'Email'] + week_headers + ['Present', 'Absent', 'Late'])
        enrollments = Enrollment.query.filter_by(course_id=course_id).all()
        att_records = Attendance.query.filter_by(course_id=course_id).all()
        att_map = {(a.student_id, a.session): a.status for a in att_records}
        for e in enrollments:
            s = e.student
            week_statuses = [att_map.get((s.id, w), 'absent') for w in range(1, course.current_session + 1)]
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
@app.route('/api/admin/certificates', methods=['GET', 'POST'])
@teacher_required
def admin_certificates():
    if request.method == 'GET':
        query = Certificate.query
        if current_user.role == 'teacher':
            course_ids = teacher_manageable_course_ids()
            if not course_ids:
                return jsonify([])
            query = query.filter(Certificate.course_id.in_(course_ids))
        certs = query.order_by(Certificate.issued_at.desc()).all()
        return jsonify([c.to_dict() for c in certs])
    # POST
    data       = request.get_json()
    student_id = data.get('student_id')
    course_id  = data.get('course_id')
    workshop_id = data.get('workshop_id')
    target_type = data.get('target_type') or ('workshop' if workshop_id else 'course')
    blank_name = bool(data.get('blank_name'))
    send_email_now = bool(data.get('send_email', True))
    if target_type == 'workshop':
        if not workshop_id or (not blank_name and not student_id):
            return jsonify({'error': 'workshop_id required; student_id required unless blank_name is true'}), 400
        if not teacher_can_manage_workshop(workshop_id):
            return jsonify({'error': 'Forbidden'}), 403
        workshop = Workshop.query.get_or_404(workshop_id)
        course_id = certificate_course_for_workshop(workshop).id
    else:
        if not course_id or (not blank_name and not student_id):
            return jsonify({'error': 'course_id required; student_id required unless blank_name is true'}), 400
        if not teacher_can_manage_course(course_id):
            return jsonify({'error': 'Forbidden'}), 403
    if blank_name:
        qty, qty_err = _certificate_quantity(data)
        if qty_err:
            msg, status = qty_err
            return jsonify({'error': msg}), status
        certs = []
        for _ in range(qty):
            cert, err = issue_blank_name_certificate_for(course_id)
            if err:
                msg, status = err
                return jsonify({'error': msg, 'certificates': [c.to_dict() for c in certs]}), status
            certs.append(cert)
        return jsonify({
            'certificate': certs[0].to_dict(),
            'certificates': [c.to_dict() for c in certs],
            'count': len(certs)
        }), 201

    if target_type == 'workshop':
        cert, err = issue_workshop_certificate_for(student_id, workshop_id, send_email_now=send_email_now)
    else:
        cert, err = issue_certificate_for(student_id, course_id, send_email_now=send_email_now)
    if err:
        msg, status = err
        return jsonify({'error': msg}), status
    return jsonify({'certificate': cert.to_dict()}), 201


@app.route('/api/admin/certificates/<int:cert_id>', methods=['DELETE'])
@teacher_required
def admin_delete_certificate(cert_id):
    cert = Certificate.query.get_or_404(cert_id)
    if not teacher_can_manage_course(cert.course_id):
        return jsonify({'error': 'Forbidden'}), 403
    db.session.delete(cert)
    db.session.commit()
    return jsonify({'ok': True, 'deleted': cert_id})


@app.route('/api/admin/certificates/<int:cert_id>/send', methods=['POST'])
@teacher_required
def admin_send_certificate_email(cert_id):
    cert = Certificate.query.get_or_404(cert_id)
    if not teacher_can_manage_course(cert.course_id):
        return jsonify({'error': 'Forbidden'}), 403
    if not cert.student:
        return jsonify({'error': 'Blank-name certificates are not linked to a student'}), 400
    if not cert.student.email:
        return jsonify({'error': 'Student has no email address'}), 400
    if not send_certificate_email(cert):
        return jsonify({'error': 'Email could not be sent. Check email configuration.'}), 500
    return jsonify({'ok': True, 'certificate': cert.to_dict()})


@app.route('/api/admin/certificates/reset', methods=['POST'])
@admin_required
def admin_reset_certificates():
    deleted = Certificate.query.delete()
    db.session.commit()
    return jsonify({
        'deleted': deleted,
        'next_document_number': next_document_number()
    })


@app.route('/api/teacher/certificate-options')
@teacher_required
def teacher_certificate_options():
    course_ids = teacher_manageable_course_ids()
    courses = Course.query.filter(Course.id.in_(course_ids)).order_by(Course.title).all() if course_ids else []
    enrollments = Enrollment.query.filter(Enrollment.course_id.in_(course_ids)).all() if course_ids else []
    workshops = Workshop.query.order_by(Workshop.title).all()

    student_map = {}
    option_rows = []
    for enrollment in enrollments:
        if not enrollment.student or enrollment.student.role != 'student':
            continue
        student_map[enrollment.student.id] = enrollment.student
        option_rows.append({
            'student_id': enrollment.student.id,
            'student_name': enrollment.student.name,
            'course_id': enrollment.course_id,
            'course_title': enrollment.course.title if enrollment.course else ''
        })

    for attendee in WorkshopAttendee.query.join(WorkshopRun).all():
        if not attendee.client or attendee.client.role != 'student':
            continue
        student_map[attendee.client.id] = attendee.client
        if attendee.run and attendee.run.workshop:
            option_rows.append({
                'student_id': attendee.client.id,
                'student_name': attendee.client.name,
                'course_id': f'workshop:{attendee.run.workshop.id}',
                'course_title': attendee.run.workshop.title
            })

    course_options = []
    for c in courses:
        row = c.to_dict()
        row.update({'target_type': 'course', 'target_id': c.id, 'option_value': f'course:{c.id}'})
        course_options.append(row)
    for w in workshops:
        course_options.append({
            'id': f'workshop:{w.id}',
            'title': w.title,
            'description': w.description or '',
            'target_type': 'workshop',
            'target_id': w.id,
            'option_value': f'workshop:{w.id}',
        })

    return jsonify({
        'courses': sorted(course_options, key=lambda row: row['title'].lower()),
        'students': [s.to_dict() for s in sorted(student_map.values(), key=lambda u: u.name.lower())],
        'enrollments': sorted(option_rows, key=lambda row: (row['course_title'].lower(), row['student_name'].lower()))
    })


@app.route('/api/teacher/students', methods=['POST'])
@teacher_required
def teacher_add_student():
    data = request.get_json() or {}
    course_id = data.get('course_id')
    if not course_id:
        return jsonify({'error': 'course_id required'}), 400
    course = Course.query.get_or_404(course_id)
    if not teacher_can_manage_course(course.id):
        return jsonify({'error': 'Forbidden'}), 403

    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    if not name or not email:
        return jsonify({'error': 'name and email are required'}), 400

    student = User.query.filter_by(email=email).first()
    created = False
    if student:
        if student.role != 'student':
            return jsonify({'error': 'Email belongs to a non-student account'}), 409
    else:
        plain_pw = data.get('password') or 'codencode123'
        student = User(
            name=name,
            email=email,
            role='student',
            phone=(data.get('phone') or '').strip(),
            ic_number=(data.get('ic_number') or '').strip(),
            language_pref=data.get('language_pref', 'en'),
        )
        student.set_password(plain_pw)
        student.temp_password = plain_pw
        db.session.add(student)
        db.session.flush()
        created = True

    if course.teacher_id is None and current_user.role == 'teacher':
        course.teacher_id = current_user.id

    enrollment = Enrollment.query.filter_by(
        student_id=student.id, course_id=course.id
    ).first()
    if not enrollment:
        enrollment = Enrollment(
            student_id=student.id,
            course_id=course.id,
            payment_status=data.get('payment_status', 'pending'),
            payment_remarks=data.get('payment_remarks', ''),
            class_timing=data.get('class_timing', ''),
            class_format=data.get('class_format', ''),
            cohort_id=data.get('cohort_id') or None,
        )
        db.session.add(enrollment)

    db.session.commit()
    return jsonify({
        'student': student.to_dict(),
        'enrollment': enrollment.to_dict(),
        'created': created
    }), 201


@app.route('/api/teacher/certificates', methods=['POST'])
@teacher_required
def teacher_issue_certificate():
    data = request.get_json() or {}
    student_id = data.get('student_id')
    course_id = data.get('course_id')
    blank_name = bool(data.get('blank_name'))
    send_email_now = bool(data.get('send_email', True))
    if not course_id or (not blank_name and not student_id):
        return jsonify({'error': 'course_id required; student_id required unless blank_name is true'}), 400
    if not teacher_can_manage_course(course_id):
        return jsonify({'error': 'Forbidden'}), 403
    if blank_name:
        qty, qty_err = _certificate_quantity(data)
        if qty_err:
            msg, status = qty_err
            return jsonify({'error': msg}), status
        certs = []
        for _ in range(qty):
            cert, err = issue_blank_name_certificate_for(course_id)
            if err:
                msg, status = err
                return jsonify({'error': msg, 'certificates': [c.to_dict() for c in certs]}), status
            certs.append(cert)
        return jsonify({
            'certificate': certs[0].to_dict(),
            'certificates': [c.to_dict() for c in certs],
            'count': len(certs)
        }), 201

    cert, err = issue_certificate_for(student_id, course_id, send_email_now=send_email_now)
    if err:
        msg, status = err
        return jsonify({'error': msg}), status
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
    if current_user.role == 'teacher' and not teacher_can_manage_course(cert.course_id):
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
# WORKSHOPS — one-off in-person events (Mount Austin etc.)
# ─────────────────────────────────────────────
_GOOGLE_REVIEW_URL = os.environ.get('GOOGLE_REVIEW_URL', '')


def _qr_png_base64(data: str, fill='#0a3d2a') -> str:
    """Generate a QR code PNG as a base64 data string. Same helper used for
    certificate verification QR codes."""
    import qrcode, base64 as _b64, io as _io
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=6, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill, back_color='white')
    buf = _io.BytesIO()
    img.save(buf, format='PNG')
    return _b64.b64encode(buf.getvalue()).decode()


def _find_or_create_client(name, email, phone=None):
    """Find an existing User by email, or create a minimal student-role User
    for a workshop attendee who has never touched the LMS before."""
    email = (email or '').strip().lower()
    if not email:
        return None, 'email is required', None
    user = User.query.filter_by(email=email).first()
    if user:
        repaired = False
        if user.role == 'student' and not user.temp_password and not user.last_login:
            user.set_password(_DEFAULT_STUDENT_PASSWORD)
            user.temp_password = _DEFAULT_STUDENT_PASSWORD
            repaired = True
        if phone and not user.phone:
            user.phone = phone.strip()
        return user, None, {
            'created': False,
            'repaired_login': repaired,
            'login_email': user.email,
            'login_password': user.temp_password if repaired else None,
        }
    user = User(
        name=(name or email).strip(),
        email=email,
        role='student',
        phone=(phone or '').strip(),
        language_pref='en',
    )
    user.set_password(_DEFAULT_STUDENT_PASSWORD)
    user.temp_password = _DEFAULT_STUDENT_PASSWORD
    db.session.add(user)
    db.session.flush()
    return user, None, {
        'created': True,
        'repaired_login': False,
        'login_email': user.email,
        'login_password': _DEFAULT_STUDENT_PASSWORD,
    }


def _ensure_workshop_client_login(user):
    """Give older never-logged-in workshop student accounts a known LMS password."""
    if not user or user.role != 'student':
        return {
            'created': False,
            'repaired_login': False,
            'login_email': user.email if user else '',
            'login_password': None,
        }
    repaired = False
    if not user.temp_password and not user.last_login:
        user.set_password(_DEFAULT_STUDENT_PASSWORD)
        user.temp_password = _DEFAULT_STUDENT_PASSWORD
        repaired = True
    return {
        'created': False,
        'repaired_login': repaired,
        'login_email': user.email,
        'login_password': user.temp_password if repaired else None,
    }


def repair_workshop_attendee_logins():
    """Repair legacy workshop attendees created before workshop logins were enabled."""
    repaired = 0
    attendee_user_ids = [
        uid for (uid,) in WorkshopAttendee.query.with_entities(WorkshopAttendee.client_id).distinct().all()
    ]
    if not attendee_user_ids:
        return 0
    users = User.query.filter(User.id.in_(attendee_user_ids), User.role == 'student').all()
    for user in users:
        if not user.temp_password and not user.last_login:
            user.set_password(_DEFAULT_STUDENT_PASSWORD)
            user.temp_password = _DEFAULT_STUDENT_PASSWORD
            repaired += 1
    if repaired:
        db.session.commit()
        app.logger.info('Repaired LMS login for %d legacy workshop attendee account(s)', repaired)
    return repaired


def mark_foon_yew_evening_workshop_paid():
    """Mark Foon Yew AI for Workplace workshop/enrollment payments as paid."""
    runs = WorkshopRun.query.filter(WorkshopRun.venue.ilike('%Foon%Yew%')).all()
    ai_workplace_enrollments = Enrollment.query.join(Course).filter(
        Course.title == 'AI for Workplace',
        Enrollment.payment_status != 'paid',
    ).all()
    if not runs and not ai_workplace_enrollments:
        return 0
    paid_at = datetime.utcnow()
    updated = 0
    next_doc_no = next_document_number()
    for run in runs:
        for attendee in run.attendees:
            if attendee.payment_status != 'paid':
                attendee.payment_status = 'paid'
                attendee.paid_at = attendee.paid_at or paid_at
                if not attendee.document_number:
                    attendee.document_number = next_doc_no
                    next_doc_no += 1
                updated += 1
    for enrollment in ai_workplace_enrollments:
        enrollment.payment_status = 'paid'
        enrollment.paid_at = enrollment.paid_at or paid_at
        if not enrollment.document_number:
            enrollment.document_number = next_doc_no
            next_doc_no += 1
        updated += 1
    if updated:
        db.session.commit()
        app.logger.info('Marked %d Foon Yew AI for Workplace payment record(s) as paid', updated)
    return updated


def _create_workshop(data):
    title = data['title'].strip()
    description = data.get('description', '')
    duration_hours = float(data.get('duration_hours', 4))
    price_per_pax = float(data['price_per_pax']) if data.get('price_per_pax') not in (None, '') else None

    from sqlalchemy import inspect as _sa_inspect
    insp = _sa_inspect(db.engine)
    workshop_cols = {c['name'] for c in insp.get_columns('workshops')}

    # Production may still have the first workshop schema. It has required
    # columns such as workshop_date that are not part of the current catalogue
    # model, so ORM inserts cannot satisfy its NOT NULL constraints.
    if 'workshop_date' in workshop_cols:
        legacy_defaults = {
            'title': title,
            'description': description,
            'workshop_date': None,
            'start_time': None,
            'end_time': None,
            'format': 'physical',
            'language': 'English',
            'category': 'python',
            'is_active': False,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'duration_hours': duration_hours,
            'price_per_pax': price_per_pax,
        }
        insert_values = {k: v for k, v in legacy_defaults.items() if k in workshop_cols}
        col_sql = ', '.join(insert_values.keys())
        val_sql = ', '.join(f':{k}' for k in insert_values)
        result = db.session.execute(
            text(f'INSERT INTO workshops ({col_sql}) VALUES ({val_sql}) RETURNING id'),
            insert_values
        )
        db.session.commit()
        return Workshop.query.get(result.scalar_one())

    w = Workshop(
        title=title,
        description=description,
        duration_hours=duration_hours,
        price_per_pax=price_per_pax,
    )
    db.session.add(w)
    db.session.commit()
    return w


PREDEFINED_WORKSHOPS = [
    'AI for Automation',
    'AI for HR',
    'AI for Event Management',
    'AI for Workplace',
    'AI for Marketing',
]


def seed_predefined_workshops():
    created, updated = [], []
    for title in PREDEFINED_WORKSHOPS:
        workshop = Workshop.query.filter_by(title=title).first()
        if workshop:
            if workshop.duration_hours != 4:
                workshop.duration_hours = 4
                updated.append(title)
            continue
        _create_workshop({
            'title': title,
            'description': '',
            'duration_hours': 4,
            'price_per_pax': None,
        })
        created.append(title)
    if created or updated:
        db.session.commit()
    if created:
        print(f'Predefined workshops seeded: {", ".join(created)}')
    if updated:
        print(f'Predefined workshops updated to 4 hours: {", ".join(updated)}')


@app.route('/api/admin/workshops', methods=['GET', 'POST'])
@admin_required
def admin_workshops():
    if request.method == 'GET':
        workshops = Workshop.query.order_by(Workshop.title).all()
        return jsonify([w.to_dict() for w in workshops])
    data = request.get_json()
    if not data.get('title'):
        return jsonify({'error': 'title is required'}), 400
    try:
        w = _create_workshop(data)
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('Create workshop failed')
        return jsonify({'error': f'Could not save workshop: {exc}'}), 500
    return jsonify({'workshop': w.to_dict()}), 201


@app.route('/api/admin/workshops/<int:wid>', methods=['PUT', 'DELETE'])
@admin_required
def admin_workshop_detail(wid):
    w = Workshop.query.get_or_404(wid)
    if request.method == 'DELETE':
        db.session.delete(w)
        db.session.commit()
        return jsonify({'ok': True})
    data = request.get_json()
    if data.get('title'): w.title = data['title'].strip()
    if 'description' in data: w.description = data['description']
    if 'duration_hours' in data: w.duration_hours = float(data['duration_hours'])
    if 'price_per_pax' in data:
        w.price_per_pax = float(data['price_per_pax']) if data['price_per_pax'] not in (None, '') else None
    db.session.commit()
    return jsonify({'workshop': w.to_dict()})


@app.route('/api/admin/workshop-runs', methods=['GET'])
@admin_required
def admin_list_workshop_runs():
    """All runs, most recent first — used for the Upcoming Runs view."""
    upcoming_only = request.args.get('upcoming') == '1'
    q = WorkshopRun.query
    if upcoming_only:
        now = datetime.utcnow()
        q = q.filter(db.or_(
            WorkshopRun.start_datetime >= now,
            WorkshopRun.end_datetime >= now
        ))
    runs = q.order_by(WorkshopRun.start_datetime).all()
    return jsonify([r.to_dict() for r in runs])


@app.route('/api/admin/workshops/<int:wid>/runs', methods=['POST'])
@admin_required
def admin_create_workshop_run(wid):
    Workshop.query.get_or_404(wid)
    data = request.get_json()
    if not data.get('start_datetime'):
        return jsonify({'error': 'start_datetime is required'}), 400
    run = WorkshopRun(
        workshop_id=wid,
        start_datetime=datetime.strptime(data['start_datetime'], '%Y-%m-%dT%H:%M'),
        end_datetime=datetime.strptime(data['end_datetime'], '%Y-%m-%dT%H:%M') if data.get('end_datetime') else None,
        venue=data.get('venue', '').strip(),
        capacity=int(data['capacity']) if data.get('capacity') else None,
        price_per_pax=float(data['price_per_pax']) if data.get('price_per_pax') not in (None, '') else None,
        teacher_id=int(data['teacher_id']) if data.get('teacher_id') else None,
        google_review_url=data.get('google_review_url', '').strip(),
        feedback_token=uuid.uuid4().hex[:20],
    )
    db.session.add(run)
    db.session.commit()
    return jsonify({'run': run.to_dict()}), 201


@app.route('/api/admin/workshop-runs/<int:rid>', methods=['GET', 'PUT', 'DELETE'])
@admin_required
def admin_workshop_run_detail(rid):
    run = WorkshopRun.query.get_or_404(rid)
    if request.method == 'DELETE':
        db.session.delete(run)
        db.session.commit()
        return jsonify({'ok': True})
    if request.method == 'GET':
        d = run.to_dict()
        d['attendees'] = [a.to_dict() for a in run.attendees]
        d['feedback'] = [f.to_dict() for f in run.feedback]
        return jsonify(d)
    # PUT
    data = request.get_json()
    if data.get('start_datetime'):
        run.start_datetime = datetime.strptime(data['start_datetime'], '%Y-%m-%dT%H:%M')
    if 'end_datetime' in data:
        run.end_datetime = datetime.strptime(data['end_datetime'], '%Y-%m-%dT%H:%M') if data['end_datetime'] else None
    if 'venue' in data: run.venue = data['venue'].strip()
    if 'capacity' in data: run.capacity = int(data['capacity']) if data['capacity'] else None
    if 'price_per_pax' in data:
        run.price_per_pax = float(data['price_per_pax']) if data['price_per_pax'] not in (None, '') else None
    if 'teacher_id' in data: run.teacher_id = int(data['teacher_id']) if data['teacher_id'] else None
    if 'google_review_url' in data: run.google_review_url = data['google_review_url'].strip()
    db.session.commit()
    return jsonify({'run': run.to_dict()})


@app.route('/api/admin/workshop-runs/<int:rid>/attendees', methods=['POST'])
@admin_required
def admin_add_workshop_attendee(rid):
    run = WorkshopRun.query.get_or_404(rid)
    data = request.get_json()
    client_id = data.get('client_id')
    account = None
    if client_id:
        client = User.query.get_or_404(int(client_id))
        account = _ensure_workshop_client_login(client)
    else:
        client, err, account = _find_or_create_client(data.get('name'), data.get('email'), data.get('phone'))
        if err:
            return jsonify({'error': err}), 400
    existing = WorkshopAttendee.query.filter_by(run_id=rid, client_id=client.id).first()
    if existing:
        return jsonify({'error': f'{client.name} is already registered for this run'}), 409
    price = run.effective_price()
    att = WorkshopAttendee(
        run_id=rid, client_id=client.id,
        payment_amount=price,
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({'attendee': att.to_dict(), 'account': account}), 201


@app.route('/api/admin/workshop-runs/<int:rid>/attendees/<int:aid>', methods=['PUT', 'DELETE'])
@admin_required
def admin_workshop_attendee_detail(rid, aid):
    att = WorkshopAttendee.query.filter_by(id=aid, run_id=rid).first_or_404()
    if request.method == 'DELETE':
        db.session.delete(att)
        db.session.commit()
        return jsonify({'ok': True})
    data = request.get_json()
    if 'attended' in data: att.attended = bool(data['attended'])
    old_status = att.payment_status
    if 'payment_status' in data: att.payment_status = data['payment_status']
    if 'payment_amount' in data and data['payment_amount'] not in (None, ''):
        att.payment_amount = float(data['payment_amount'])
    if 'payment_method' in data: att.payment_method = data['payment_method'] or None
    just_paid = old_status != 'paid' and att.payment_status == 'paid'
    if just_paid:
        att.paid_at = att.paid_at or datetime.utcnow()
        if not att.document_number:
            att.document_number = next_document_number()
    db.session.commit()

    email_status = None
    if just_paid:
        email_status = {}
        try:
            email_status['receipt_sent'] = email_workshop_payment_receipt(att)
        except Exception as exc:
            app.logger.error('Workshop receipt email failed for attendee %s: %s', aid, exc)
            email_status['receipt_sent'] = False
            email_status['receipt_error'] = str(exc)

    return jsonify({'attendee': att.to_dict(), 'just_paid': just_paid, 'email_status': email_status})


def render_workshop_attendee_invoice_html(attendee):
    """Render the printable workshop receipt/invoice HTML for admin and emailed links."""
    att = attendee
    run = att.run
    workshop = run.workshop if run else None
    client = att.client
    inv_num = f'RCP-{get_or_assign_attendee_document_number(att):03d}' if (att.payment_status or '').lower() == 'paid' else f'INV-{get_or_assign_attendee_document_number(att):03d}'
    issued = datetime.utcnow().strftime('%d %B %Y')
    pay_status = (att.payment_status or 'pending').lower()
    status_colour = {'paid': '#28ca41', 'pending': '#e3b341', 'overdue': '#f85149'}.get(
        pay_status, '#7d8590')
    amount = att.payment_amount
    if amount is None and run:
        amount = run.effective_price()
    amount_str = f'RM {amount:,.2f}' if amount is not None else '—'
    date_str = run.start_datetime.strftime('%d %B %Y') if run and run.start_datetime else 'TBC'
    time_str = ''
    if run and run.start_datetime:
        time_str = run.start_datetime.strftime('%I:%M %p')
        if run.end_datetime:
            time_str += ' - ' + run.end_datetime.strftime('%I:%M %p')
    duration_hours = workshop.duration_hours if workshop and workshop.duration_hours else 4

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{inv_num} - codencode.my</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Mono:wght@400;700&display=swap');
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:'Space Mono',monospace; background:#fff; color:#111; font-size:13px; padding:40px; max-width:720px; margin:auto; }}
    .header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:40px; border-bottom:3px solid #00dcb4; padding-bottom:24px; }}
    .brand-logo {{ height:28px; display:block; }}
    .inv-meta {{ text-align:right; }}
    .inv-num {{ font-size:18px; font-weight:700; color:#080c10; }}
    .inv-date {{ color:#555; margin-top:4px; }}
    .section {{ margin-bottom:28px; }}
    .section-title {{ font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#888; margin-bottom:10px; border-bottom:1px solid #eee; padding-bottom:6px; }}
    .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
    p {{ margin:5px 0; line-height:1.6; }}
    strong {{ color:#080c10; }}
    .status-badge {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#fff; background:{status_colour}; }}
    .amount {{ font-size:24px; font-weight:700; color:#00a382; margin-top:8px; }}
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
      <img src="https://learn.codencode.my/static/img/logo.png" alt="codencode.my" class="brand-logo">
      <div style="color:#555;margin-top:4px;font-size:12px">Workshop {'Receipt' if pay_status == 'paid' else 'Invoice'}</div>
    </div>
    <div class="inv-meta">
      <div class="inv-num">{inv_num}</div>
      <div class="inv-date">Issued: {issued}</div>
    </div>
  </div>

  <div class="grid-2">
    {_bill_to_section_html(client)}
    <div class="section">
      <div class="section-title">Workshop</div>
      <p><strong>{workshop.title if workshop else ''}</strong></p>
      <p>Duration: {duration_hours:g} hours</p>
      <p>Date: {date_str}</p>
      {'<p>Time: ' + time_str + '</p>' if time_str else ''}
      {'<p>Venue: ' + run.venue + '</p>' if run and run.venue else ''}
    </div>
  </div>

  <div class="section">
    <div class="section-title">Payment Details</div>
    <p><strong>Status:</strong> <span class="status-badge">{pay_status.upper()}</span></p>
    <p><strong>Amount:</strong></p>
    <p class="amount">{amount_str}</p>
    <p><strong>Method:</strong> {att.payment_method or '—'}</p>
  </div>

  <div class="footer">
    <p><strong>{_BUSINESS_NAME}</strong> · SSM No. {_BUSINESS_SSM}</p>
    <p style="margin-top:8px">codencode.my · {inv_num} · Generated {issued}</p>
    <p style="margin-top:4px">Thank you for learning with us!</p>
  </div>

  <div class="no-print" style="margin-top:32px;text-align:center">
    <button onclick="window.print()" style="background:#00dcb4;color:#080c10;border:none;padding:10px 28px;border-radius:6px;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer;">
      Print / Save as PDF
    </button>
    <button onclick="window.close()" style="background:#eee;color:#333;border:none;padding:10px 24px;border-radius:6px;font-family:inherit;font-size:13px;cursor:pointer;margin-left:8px;">
      Close
    </button>
  </div>
</body>
</html>"""
    service_details = [
        ('Duration', f'{duration_hours:g} hours'),
        ('Date', date_str),
        ('Time', time_str),
        ('Venue', run.venue if run and run.venue else ''),
    ]
    html = _invoice_page_html(
        inv_num,
        pay_status,
        client,
        f'{workshop.title if workshop else "Workshop"} - {duration_hours:g} Hours',
        amount or 0,
        service_details,
        'RECEIPT' if pay_status == 'paid' else 'INVOICE'
    )
    return html


@app.route('/api/admin/workshop-runs/<int:rid>/attendees/<int:aid>/invoice')
@admin_required
def admin_workshop_attendee_invoice(rid, aid):
    """Return a printable HTML invoice page for a workshop attendee."""
    att = WorkshopAttendee.query.filter_by(id=aid, run_id=rid).first_or_404()
    html = render_workshop_attendee_invoice_html(att)
    from flask import Response
    return Response(html, mimetype='text/html')


@app.route('/api/workshop-attendees/receipt/<token>')
def public_workshop_attendee_receipt(token):
    """Signed public workshop receipt link for attendees who do not use LMS login."""
    try:
        data = _workshop_receipt_serializer().loads(token)
    except BadSignature:
        return 'Invalid receipt link', 404
    att = WorkshopAttendee.query.filter_by(id=data.get('aid'), run_id=data.get('rid')).first_or_404()
    html = render_workshop_attendee_invoice_html(att)
    from flask import Response
    return Response(html, mimetype='text/html')


@app.route('/api/admin/workshop-runs/<int:rid>/qr')
@admin_required
def admin_workshop_run_qr(rid):
    """Two QR codes for a run: one to the public feedback form, one to the
    Google Business review link (per-run override, else the business default)."""
    run = WorkshopRun.query.get_or_404(rid)
    feedback_url = f'https://learn.codencode.my/feedback/{run.feedback_token}'
    review_url = run.google_review_url or _GOOGLE_REVIEW_URL
    return jsonify({
        'feedback_url': feedback_url,
        'feedback_qr_png_base64': _qr_png_base64(feedback_url),
        'review_url': review_url or None,
        'review_qr_png_base64': _qr_png_base64(review_url) if review_url else None,
    })


@app.route('/api/admin/workshop-runs/classify-existing-students', methods=['POST'])
@admin_required
def admin_classify_existing_students_workshop():
    """One-time utility: create the 'AI for Workplace' workshop + its run
    (16 Jun - 7 Aug 2026, Foon Yew School), then register every current
    student as an attendee EXCEPT the named Core Subjects students, who
    keep their existing course enrollments untouched. Safe to run more than
    once — skips students already registered and reuses the existing
    workshop/run if already created."""
    core_subject_names = {'ban soon', 'vanessa', 'henry', 'sya sya', 'buan jeng', 'jaylene'}

    try:
        workshop = Workshop.query.filter_by(title='AI for Workplace').first()
        if not workshop:
            workshop = Workshop(title='AI for Workplace', duration_hours=2)
            db.session.add(workshop)
            db.session.flush()
        elif not workshop.duration_hours:
            workshop.duration_hours = 2

        run = WorkshopRun.query.filter_by(workshop_id=workshop.id, venue='Foon Yew School').first()
        if not run:
            run = WorkshopRun(
                workshop_id=workshop.id,
                start_datetime=datetime(2026, 6, 16, 19, 30),
                end_datetime=datetime(2026, 8, 7, 21, 30),
                venue='Foon Yew School',
                feedback_token=uuid.uuid4().hex[:20],
            )
            db.session.add(run)
            db.session.flush()
        else:
            if not run.start_datetime:
                run.start_datetime = datetime(2026, 6, 16, 19, 30)
            if not run.end_datetime:
                run.end_datetime = datetime(2026, 8, 7, 21, 30)
            if not run.feedback_token:
                run.feedback_token = uuid.uuid4().hex[:20]

        added, already_registered, skipped_core = [], [], []
        for s in User.query.filter_by(role='student').all():
            name_lower = (s.name or '').strip().lower()
            if any(core in name_lower for core in core_subject_names):
                skipped_core.append(s.name)
                continue
            if WorkshopAttendee.query.filter_by(run_id=run.id, client_id=s.id).first():
                already_registered.append(s.name)
                continue
            db.session.add(WorkshopAttendee(run_id=run.id, client_id=s.id))
            added.append(s.name)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('Classify existing students for workshop failed')
        return jsonify({'error': f'Could not classify existing students: {exc}'}), 500

    return jsonify({
        'workshop_id': workshop.id,
        'run_id': run.id,
        'added': added,
        'already_registered': already_registered,
        'skipped_as_core_subjects': skipped_core,
    })


@app.route('/feedback/<token>')
def public_workshop_feedback_page(token):
    """Public, no-login feedback form for a workshop run — reached via QR code."""
    from flask import render_template
    run = WorkshopRun.query.filter_by(feedback_token=token).first()
    if not run:
        return render_template('workshop_feedback.html', run=None), 404
    review_url = run.google_review_url or _GOOGLE_REVIEW_URL
    return render_template('workshop_feedback.html', run=run, review_url=review_url)


@app.route('/api/public/workshop-feedback/<token>', methods=['POST'])
def submit_workshop_feedback(token):
    run = WorkshopRun.query.filter_by(feedback_token=token).first()
    if not run:
        return jsonify({'error': 'Invalid feedback link'}), 404
    data = request.get_json()
    event_rating = data.get('event_rating')
    teacher_rating = data.get('teacher_rating')
    if not event_rating:
        return jsonify({'error': 'An event rating is required'}), 400
    attendee_id = None
    email = (data.get('email') or '').strip().lower()
    if email:
        client = User.query.filter_by(email=email).first()
        if client:
            att = WorkshopAttendee.query.filter_by(run_id=run.id, client_id=client.id).first()
            if att:
                attendee_id = att.id
    fb = WorkshopFeedback(
        run_id=run.id,
        attendee_id=attendee_id,
        event_rating=int(event_rating),
        teacher_rating=int(teacher_rating) if teacher_rating else None,
        comment=(data.get('comment') or '').strip(),
    )
    db.session.add(fb)
    db.session.commit()
    return jsonify({'ok': True})


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
        session         = data.get('session'),
        pass_score      = int(data.get('pass_score', 70)),
        max_attempts    = int(data.get('max_attempts', 2)),
        time_limit_mins = int(data['time_limit_mins']) if data.get('time_limit_mins') else None,
        created_by      = current_user.id
    )
    db.session.add(q)
    db.session.commit()
    return jsonify({'quiz': q.to_dict()}), 201


@app.route('/api/quizzes/<int:qid>', methods=['PUT', 'DELETE'])
@teacher_required
def api_quiz_detail(qid):
    q = Quiz.query.get_or_404(qid)
    if request.method == 'DELETE':
        db.session.delete(q)
        db.session.commit()
        return jsonify({'ok': True})
    # PUT
    data = request.get_json()
    if 'title'           in data: q.title           = data['title'].strip()
    if 'description'     in data: q.description     = data['description']
    if 'session'         in data: q.session          = data['session']
    if 'pass_score'      in data: q.pass_score       = int(data['pass_score'])
    if 'max_attempts'    in data: q.max_attempts     = int(data['max_attempts'])
    if 'time_limit_mins' in data:
        q.time_limit_mins = int(data['time_limit_mins']) if data['time_limit_mins'] else None
    db.session.commit()
    return jsonify({'quiz': q.to_dict()})


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


@app.route('/api/quizzes/<int:qid>/questions/<int:qqid>', methods=['PUT', 'DELETE'])
@teacher_required
def api_quiz_question_detail(qid, qqid):
    qq = QuizQuestion.query.get_or_404(qqid)
    if request.method == 'DELETE':
        db.session.delete(qq)
        db.session.commit()
        return jsonify({'ok': True})
    # PUT
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
    session_num = request.args.get('session', type=int)
    q = DiscussionPost.query.filter_by(course_id=cid)
    if session_num:
        q = q.filter_by(session=session_num)
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
        session   = data.get('session'),
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
                        'course': m.course.title if m.course else '', 'session': m.session})

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
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN class_timing VARCHAR(300)'))
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
            if 'bill_company_name' not in user_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN bill_company_name VARCHAR(200)'))
                conn.commit()
            if 'bill_business_reg_number' not in user_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN bill_business_reg_number VARCHAR(100)'))
                conn.commit()
            if 'bill_sst_number' not in user_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN bill_sst_number VARCHAR(100)'))
                conn.commit()
            if 'bill_company_address' not in user_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN bill_company_address TEXT'))
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

    try:
        insp_rec = sa_inspect(db.engine)
        rec_cols = {c['name'] for c in insp_rec.get_columns('recordings')}
        with db.engine.connect() as conn:
            if 'recording_url' not in rec_cols:
                conn.execute(text('ALTER TABLE recordings ADD COLUMN recording_url VARCHAR(1000)'))
                conn.commit()
            if 'source_type' not in rec_cols:
                conn.execute(text("ALTER TABLE recordings ADD COLUMN source_type VARCHAR(20) DEFAULT 'upload'"))
                conn.commit()
            if 'cohort_id' not in rec_cols:
                conn.execute(text('ALTER TABLE recordings ADD COLUMN cohort_id INTEGER'))
                conn.commit()
    except Exception:
        pass

    # Cohort: schedule, notes, end_date, teacher assignment columns
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
            if 'teacher_id' not in coh_cols:
                conn.execute(text('ALTER TABLE cohorts ADD COLUMN teacher_id INTEGER'))
                conn.commit()
    except Exception:
        pass

    # Timetable: cohort scoping and editable timing columns
    try:
        insp_tt = sa_inspect(db.engine)
        tt_cols = {c['name'] for c in insp_tt.get_columns('timetable_sessions')}
        with db.engine.connect() as conn:
            for col, ddl in [
                ('cohort_id',  'INTEGER'),
                ('day_name',   'VARCHAR(20)'),
                ('time_start', 'VARCHAR(5)'),
                ('time_end',   'VARCHAR(5)'),
                ('day_offset', 'INTEGER'),
            ]:
                if col not in tt_cols:
                    conn.execute(text(f'ALTER TABLE timetable_sessions ADD COLUMN {col} {ddl}'))
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
            if 'payment_discount_amount' not in pay_cols:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN payment_discount_amount REAL'))
                conn.commit()
            if 'payment_discount_reason' not in pay_cols:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN payment_discount_reason VARCHAR(200)'))
                conn.commit()
            if 'payment_method' not in pay_cols:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN payment_method VARCHAR(50)'))
                conn.commit()
            if 'paid_at' not in pay_cols:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN paid_at DATETIME'))
                conn.commit()
            if 'document_number' not in pay_cols:
                conn.execute(text('ALTER TABLE enrollments ADD COLUMN document_number INTEGER'))
                conn.commit()
    except Exception:
        pass

    # ── "week" → "session" terminology rename ──────────────────────────────────
    # Renames columns in place (data preserved) rather than add+backfill+drop,
    # since this is a straight 1:1 rename with no data reshaping needed.
    # RENAME COLUMN is supported by both Postgres and modern SQLite (3.25+).
    _week_to_session_renames = [
        ('courses',           'weeks',        'total_sessions'),
        ('courses',           'current_week', 'current_session'),
        ('cohorts',           'current_week', 'current_session'),
        ('materials',         'week',         'session'),
        ('assignments',       'week',         'session'),
        ('attendance',        'week',         'session'),
        ('quizzes',           'week',         'session'),
        ('discussion_posts',  'week',         'session'),
    ]
    for table, old_col, new_col in _week_to_session_renames:
        try:
            insp_r = sa_inspect(db.engine)
            cols = {c['name'] for c in insp_r.get_columns(table)}
            if old_col in cols and new_col not in cols:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE {table} RENAME COLUMN {old_col} TO {new_col}'))
                    conn.commit()
        except Exception:
            pass

    # ── Teacher profile columns migration ────────────────────────────────────────
    try:
        insp_tp = sa_inspect(db.engine)
        u_cols  = {c['name'] for c in insp_tp.get_columns('users')}
        with db.engine.connect() as conn:
            for col, ddl in [
                ('title',           'VARCHAR(120)'),
                ('bio',             'TEXT'),
                ('education',       'TEXT'),
                ('experience',      'TEXT'),
                ('specializations', 'VARCHAR(300)'),
                ('website',         'VARCHAR(300)'),
                ('linkedin',        'VARCHAR(300)'),
                ('avatar_filename',  'VARCHAR(300)'),
            ]:
                if col not in u_cols:
                    conn.execute(text(f'ALTER TABLE users ADD COLUMN {col} {ddl}'))
                    conn.commit()
    except Exception:
        pass

    # ── teacher_id on courses ─────────────────────────────────────────────────
    try:
        insp_tc = sa_inspect(db.engine)
        c_cols  = {c['name'] for c in insp_tc.get_columns('courses')}
        if 'teacher_id' not in c_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE courses ADD COLUMN teacher_id INTEGER'))
                conn.commit()
    except Exception:
        pass

    # Workshop feature columns. Existing deployed databases may already have
    # early workshop tables, and create_all() will not add missing columns.
    try:
        insp_ws = sa_inspect(db.engine)
        timestamp_ddl = 'TIMESTAMP' if db.engine.dialect.name == 'postgresql' else 'DATETIME'
        bool_default_ddl = 'BOOLEAN DEFAULT FALSE' if db.engine.dialect.name == 'postgresql' else 'BOOLEAN DEFAULT 0'
        with db.engine.connect() as conn:
            if insp_ws.has_table('workshops'):
                workshop_cols = {c['name'] for c in insp_ws.get_columns('workshops')}
                for col, ddl in [
                    ('description',    'TEXT'),
                    ('duration_hours', 'FLOAT DEFAULT 4'),
                    ('price_per_pax',  'FLOAT'),
                    ('created_at',     timestamp_ddl),
                ]:
                    if col not in workshop_cols:
                        conn.execute(text(f'ALTER TABLE workshops ADD COLUMN {col} {ddl}'))
                        conn.commit()
                if db.engine.dialect.name == 'postgresql':
                    for col in ['workshop_date', 'start_time', 'end_time']:
                        if col in workshop_cols:
                            conn.execute(text(f'ALTER TABLE workshops ALTER COLUMN {col} DROP NOT NULL'))
                            conn.commit()

            if insp_ws.has_table('workshop_runs'):
                run_cols = {c['name'] for c in insp_ws.get_columns('workshop_runs')}
                for col, ddl in [
                    ('end_datetime',      timestamp_ddl),
                    ('venue',             'VARCHAR(300)'),
                    ('capacity',          'INTEGER'),
                    ('price_per_pax',     'FLOAT'),
                    ('teacher_id',        'INTEGER'),
                    ('google_review_url', 'VARCHAR(500)'),
                    ('feedback_token',    'VARCHAR(32)'),
                    ('created_at',        timestamp_ddl),
                ]:
                    if col not in run_cols:
                        conn.execute(text(f'ALTER TABLE workshop_runs ADD COLUMN {col} {ddl}'))
                        conn.commit()

            if insp_ws.has_table('workshop_attendees'):
                attendee_cols = {c['name'] for c in insp_ws.get_columns('workshop_attendees')}
                for col, ddl in [
                    ('attended',        bool_default_ddl),
                    ('payment_status',  "VARCHAR(20) DEFAULT 'pending'"),
                    ('payment_amount',  'FLOAT'),
                    ('payment_method',  'VARCHAR(50)'),
                    ('paid_at',         timestamp_ddl),
                    ('document_number', 'INTEGER'),
                    ('registered_at',   timestamp_ddl),
                ]:
                    if col not in attendee_cols:
                        conn.execute(text(f'ALTER TABLE workshop_attendees ADD COLUMN {col} {ddl}'))
                        conn.commit()

            if insp_ws.has_table('workshop_feedback'):
                feedback_cols = {c['name'] for c in insp_ws.get_columns('workshop_feedback')}
                for col, ddl in [
                    ('attendee_id',     'INTEGER'),
                    ('event_rating',    'INTEGER'),
                    ('teacher_rating',  'INTEGER'),
                    ('comment',         'TEXT'),
                    ('submitted_at',    timestamp_ddl),
                ]:
                    if col not in feedback_cols:
                        conn.execute(text(f'ALTER TABLE workshop_feedback ADD COLUMN {col} {ddl}'))
                        conn.commit()
    except Exception:
        app.logger.exception('Workshop schema migration failed')

    try:
        repair_workshop_attendee_logins()
    except Exception:
        db.session.rollback()
        app.logger.exception('Workshop attendee login repair failed')

    # Existing installs may have courses from before teacher assignment existed.
    # When there is only one teacher, make that teacher the owner so their portal
    # does not come up empty after the migration.
    try:
        teachers = User.query.filter_by(role='teacher').all()
        if len(teachers) == 1:
            Course.query.filter(Course.teacher_id.is_(None)).update(
                {Course.teacher_id: teachers[0].id},
                synchronize_session=False
            )
            db.session.commit()
    except Exception:
        db.session.rollback()

    seed_demo()
    seed_predefined_workshops()
    try:
        mark_foon_yew_evening_workshop_paid()
    except Exception:
        db.session.rollback()
        app.logger.exception('Foon Yew evening workshop payment update failed')
    _start_scheduler()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
