# codencode.my LMS

Simple Flask + PostgreSQL (or SQLite) Learning Management System.

## Files

```
codencode_lms/
├── app_simple.py          ← entire backend (one file)
├── requirements.txt
├── templates/
│   └── lms.html           ← entire frontend (one file)
└── uploads/               ← created automatically
    ├── videos/
    ├── materials/
    ├── submissions/
    └── briefs/
```

---

## Quick Start (SQLite — no Postgres needed)

```bash
pip install -r requirements.txt
python app_simple.py
```

Open http://localhost:5000

Demo logins (password: `demo1234`):
- `student@codencode.my`
- `teacher@codencode.my`

---

## Switch to PostgreSQL

1. Create the database:
```sql
CREATE DATABASE codencode_lms;
```

2. Set environment variable before running:
```bash
export DATABASE_URL="postgresql://postgres:yourpassword@localhost:5432/codencode_lms"
python app_simple.py
```

3. Change `get_db()` in `app_simple.py` (instructions are in the comments at the top of the function).

---

## Production (Ubuntu + Nginx)

```bash
# Install gunicorn
pip install gunicorn

# Run
gunicorn -w 2 -b 0.0.0.0:5000 "app_simple:app"
```

Nginx config snippet:
```nginx
location / {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    client_max_body_size 2G;   # for video uploads
}
location /uploads/ {
    alias /path/to/codencode_lms/uploads/;
    internal;                  # only Flask can serve these
}
```

---

## API Endpoints

| Method | URL | Who | What |
|--------|-----|-----|------|
| POST | `/api/auth/login` | All | Login |
| POST | `/api/auth/logout` | All | Logout |
| GET | `/api/auth/me` | All | Current user |
| GET | `/api/courses` | All | List courses |
| GET | `/api/courses/:id/dashboard` | All | Stats |
| GET | `/api/courses/:id/recordings` | All | List recordings |
| POST | `/api/courses/:id/recordings` | Teacher | Upload recording |
| DELETE | `/api/recordings/:id` | Teacher | Delete recording |
| POST | `/api/recordings/:id/watch` | Student | Mark watched |
| GET | `/api/courses/:id/materials` | All | List materials |
| POST | `/api/courses/:id/materials` | Teacher | Upload material |
| DELETE | `/api/materials/:id` | Teacher | Delete material |
| GET | `/api/courses/:id/assignments` | All | List assignments |
| POST | `/api/courses/:id/assignments` | Teacher | Create assignment |
| DELETE | `/api/assignments/:id` | Teacher | Delete assignment |
| POST | `/api/assignments/:id/submit` | Student | Submit work |
| GET | `/api/assignments/:id/submissions` | Teacher | View submissions |
| POST | `/api/submissions/:id/grade` | Teacher | Save grade |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | SQLite `codencode_lms.db` | Postgres connection string |
| `SECRET_KEY` | random per process (dev only) | Flask session key. **Required in production**: the app refuses to start on Railway without it |
| `DB_PATH` | `codencode_lms.db` | SQLite path (ignored if DATABASE_URL set) |
| `ZOOM_ACCOUNT_ID` | unset | Zoom Server-to-Server OAuth account ID |
| `ZOOM_CLIENT_ID` | unset | Zoom Server-to-Server OAuth client ID |
| `ZOOM_CLIENT_SECRET` | unset | Zoom Server-to-Server OAuth client secret |
| `ZOOM_USER_ID` | `me` | Zoom user ID or email that hosts auto-created LMS meetings |
| `ZOOM_TIMEZONE` | `Asia/Kuala_Lumpur` | Timezone sent when creating scheduled Zoom meetings |

When `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, and `ZOOM_CLIENT_SECRET` are set, teachers can leave the Zoom Link field blank while scheduling a session. The LMS will create the Zoom meeting through Zoom's API and save the returned student join link.

---

## Staff Portal

Staff attendance and payroll, inside this same app: same database, `users` table, sign-in and roles.
It lives at `/staff` and is served on **staff.codencode.my** (where `/` redirects to `/staff`).

- **Teacher**: sees and acts on their own records only (attendance, classes, schedule requests, office clock-in, pay).
- **Admin**: everyone, plus all schedules and approvals, Zoom reports, review, payroll and the team's rates and caps.
- **Student**: 403 on every `/staff` route.

Code: `staff/` (models, `evaluate.py` pay rules, `occurrences.py`, Zoom reports, jobs, routes), `templates/staff/`,
`static/css/staff.css`, `static/js/staff.js`, `static/js/staff-sw.js`. Design reference: `_design/attendance_mockup.html`.

### How it works

- **Zoom classes** reuse `cohorts` (`schedule`, `start_date`/`end_date`, `teacher_id`, `zoom_meeting_id`, plus `every_n_weeks`).
  *Start class* appears from 15 minutes before the start until the scheduled end; it clocks the teacher in and opens Zoom.
- **Verification**: when Zoom sends `meeting.ended`, the participant report is fetched 10 minutes later (retries up to 6 times).
  The teacher is the participant with `ZOOM_HOST_EMAIL`, or else the one whose name contains "teacher".
  Paid hours = the shorter of app time and the teacher's Zoom time. Gap over 10 min, teacher missing, or outside the
  office geofence is flagged for admin review. A nightly job (02:00 MYT) pulls anything from the last 14 days still missing,
  and admin can upload Zoom's participant CSV as a fallback.
- **Office**: clock-in is accepted only within `OFFICE_RADIUS_M` of the office (distance computed on the server; GPS accuracy must be 100 m or better).
- **Records are tamper-resistant**: staff can clock in and out only. Admin adjustments, approvals and overrides need a reason and are written to `audit_log`.
- All times are stored in UTC and shown in Malaysia time. Payroll months are MYT months. Pay by the 7th of the next month.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OFFICE_LAT`, `OFFICE_LNG` | unset | Office coordinates. Office clock-in is disabled until set |
| `OFFICE_RADIUS_M` | `200` | Geofence radius in metres |
| `OFFICE_NAME` | `Mount Austin` | Shown on the clock-in page |
| `ZOOM_HOST_EMAIL` | `codencodemy@gmail.com` | The shared Zoom host account (identifies the teacher row) |
| `ZOOM_WEBHOOK_SECRET_TOKEN` | unset | Zoom app's webhook *Secret Token* (`ZOOM_WEBHOOK_SECRET` also accepted) |
| `ZOOM_MAX_CONCURRENT` | `2` | Zoom classes the shared account can run at the same time |
| `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET` | unset | Existing Server-to-Server OAuth app (reused) |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | unset | Web Push keys. Without them, alerts go in-app and by email |
| `VAPID_SUBJECT` | `mailto:codencodemy@gmail.com` | Contact for push services |
| `STAFF_HOST` | `staff.codencode.my` | Host whose `/` redirects to `/staff` |
| `SESSION_COOKIE_DOMAIN`, `REMEMBER_COOKIE_DOMAIN` | unset | Set both to `.codencode.my` so one sign-in covers learn. and staff. |
| `RATELIMIT_STORAGE_URI` | `memory://` | Rate-limit storage (per worker by default; e.g. a Redis URL to share) |

### Zoom app setup

In the Zoom App Marketplace, open the existing **Server-to-Server OAuth** app:

1. **Scopes**: add `report:read:list_meeting_participants:admin` and `meeting:read:list_past_instances:admin`
   (keep the existing meeting and recording scopes).
2. **Feature → Event subscriptions**: add the event **Meeting → End Meeting** (`meeting.ended`) to the subscription that already
   sends `recording.completed`, or create one with endpoint URL `https://learn.codencode.my/zoom/staff-webhook`
   (the existing `/api/integrations/zoom/webhook` also works). Click *Validate*; the app answers the URL-validation challenge.
3. Copy the app's **Secret Token** into `ZOOM_WEBHOOK_SECRET_TOKEN`.

Zoom reports need a Pro (or higher) account. Teachers on a second concurrent class should rename themselves to
"Name – Teacher" after joining so the report can find them.

### Web Push (VAPID keys)

Run once (pywebpush is already installed) and paste both lines into Railway:

```bash
python -c "from py_vapid import Vapid; from cryptography.hazmat.primitives import serialization as s; import base64; v=Vapid(); v.generate_keys(); b=lambda x: base64.urlsafe_b64encode(x).rstrip(b'=').decode(); print('VAPID_PUBLIC_KEY='+b(v.public_key.public_bytes(s.Encoding.X962, s.PublicFormat.UncompressedPoint))); print('VAPID_PRIVATE_KEY='+b(v.private_key.private_numbers().private_value.to_bytes(32,'big')))"
```

Keep the private key secret; changing the keys means everyone has to turn notifications on again. Staff then tap **Turn on notifications** in the sidebar.
**iPhone users must first open staff.codencode.my in Safari, tap Share → Add to Home Screen, and open it from the
home screen**; iOS only allows push for installed web apps (iOS 16.4+).

### Railway

1. Set `SECRET_KEY` (required now; generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.
   A new key signs everyone out once).
2. Set the variables above (at least `OFFICE_LAT`, `OFFICE_LNG`, `ZOOM_WEBHOOK_SECRET_TOKEN`,
   `SESSION_COOKIE_DOMAIN=.codencode.my`, `REMEMBER_COOKIE_DOMAIN=.codencode.my`).
3. Service → Settings → Networking → **Custom Domain** → add `staff.codencode.my` to the **same service** as learn.codencode.my.
4. At the DNS provider for codencode.my, add a **CNAME** record `staff` → the target Railway shows. Wait for the certificate.
5. Deploy. New tables are created on start-up (`db.create_all()`), and `cohorts.every_n_weeks` is added automatically.
6. In **/staff/admin/team**, set each teacher's rate (RM/hr), monthly cap and type.

The background jobs run on the existing APScheduler in each gunicorn worker; a Postgres advisory lock makes sure only one
worker runs each job. `flask staff-run-jobs` runs the 5-minute job once by hand.

### Development and tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
flask --app app staff-seed-demo   # sample profiles, a demo class and shift, sessions (refuses to run in production)
```

