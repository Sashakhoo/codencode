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
| `SECRET_KEY` | `dev-secret-change-me` | Flask session key — **change this in production** |
| `DB_PATH` | `codencode_lms.db` | SQLite path (ignored if DATABASE_URL set) |
