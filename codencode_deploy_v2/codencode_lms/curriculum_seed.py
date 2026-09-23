"""Real per-course curriculum decks (self-contained HTML slide apps, each with
its own Prev/Next/Fullscreen nav) - one Material per session, matched to the
course by title. Source files ship in ../bundled_materials/ (not uploads/ -
that's on Railway's persistent volume, which shadows anything git puts
there) and are synced onto the live uploads/materials/ at startup by
_sync_bundled_materials() in app.py.

Course matching uses AND-of-substrings 'include' plus optional 'exclude',
so a course whose title contains BOTH "python" and "machine learning" (the
bundled course) is matched by its own spec instead of colliding with either
standalone course."""

PYTHON_SESSIONS = [
    (1, 'Session 01: Python Basics', 'pf-session-01.html'),
    (2, 'Session 02: Conditionals & Logic', 'pf-session-02.html'),
    (3, 'Session 03: Loops & Data Structures', 'pf-session-03.html'),
    (4, 'Session 04: Functions & Modules', 'pf-session-04.html'),
    (5, 'Session 05: Object-Oriented Programming', 'pf-session-05.html'),
    (6, 'Session 06: Files, APIs & Project Ideation', 'pf-session-06.html'),
    (7, 'Session 07: Vibe Coding & Capstone', 'pf-session-07.html'),
]

ML_SESSIONS = [
    (1, 'ML Session 01: Feature Engineering', 'ml-session-01.html'),
    (2, 'ML Session 02: Intro to Machine Learning', 'ml-session-02.html'),
    (3, 'ML Session 03: Regression Models', 'ml-session-03.html'),
    (4, 'ML Session 04: Classification & Random Forest', 'ml-session-04.html'),
    (5, 'ML Session 05: Neural Networks & Deep Learning', 'ml-session-05.html'),
    (6, 'ML Session 06: LSTM & Time Series', 'ml-session-06.html'),
    (7, 'ML Session 07: Ensembles & Model Tuning', 'ml-session-07.html'),
    (8, 'ML Session 08: Capstone - Project Planning & Execution', 'ml-session-08.html'),
]


def _offset(sessions, by):
    return [(n + by, title, filename) for n, title, filename in sessions]


CURRICULUM = [
    {
        'include': ['python fundamentals'],
        'exclude': [],
        'sessions': PYTHON_SESSIONS,
    },
    {
        'include': ['machine learning'],
        'exclude': ['python'],
        'sessions': ML_SESSIONS,
    },
    {
        # The bundled course: Python 1-7, then Machine Learning continuing at 8-15.
        # 'fixup_ml_cutoff' corrects an earlier bug where a looser match wrote
        # the ML sessions here at 1-8 (colliding with the Python sessions)
        # instead of offset - see seed_course_curriculum_materials().
        'include': ['python', 'machine learning'],
        'exclude': [],
        'sessions': PYTHON_SESSIONS + _offset(ML_SESSIONS, len(PYTHON_SESSIONS)),
        'fixup_ml_cutoff': len(PYTHON_SESSIONS),
    },
]
