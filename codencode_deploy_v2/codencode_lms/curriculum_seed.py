"""Real per-course curriculum decks (self-contained HTML slide apps, each with
its own Prev/Next/Fullscreen nav) - one Material per session, matched to the
course by title. Files live in uploads/materials/ and ship in the repo."""

CURRICULUM = [
    {
        'course_match': 'python fundamentals',
        'sessions': [
            (1, 'Session 01: Python Basics', 'pf-session-01.html'),
            (2, 'Session 02: Conditionals & Logic', 'pf-session-02.html'),
            (3, 'Session 03: Loops & Data Structures', 'pf-session-03.html'),
            (4, 'Session 04: Functions & Modules', 'pf-session-04.html'),
            (5, 'Session 05: Object-Oriented Programming', 'pf-session-05.html'),
            (6, 'Session 06: Files, APIs & Project Ideation', 'pf-session-06.html'),
            (7, 'Session 07: Vibe Coding & Capstone', 'pf-session-07.html'),
        ],
    },
    {
        'course_match': 'machine learning',
        'sessions': [
            (1, 'ML Session 01: Feature Engineering', 'ml-session-01.html'),
            (2, 'ML Session 02: Intro to Machine Learning', 'ml-session-02.html'),
            (3, 'ML Session 03: Regression Models', 'ml-session-03.html'),
            (4, 'ML Session 04: Classification & Random Forest', 'ml-session-04.html'),
            (5, 'ML Session 05: Neural Networks & Deep Learning', 'ml-session-05.html'),
            (6, 'ML Session 06: LSTM & Time Series', 'ml-session-06.html'),
            (7, 'ML Session 07: Capstone - Project Planning & Execution', 'ml-session-07.html'),
        ],
    },
]
