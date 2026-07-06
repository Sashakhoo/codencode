(function () {
  const PYTHON_BOOTCAMP = 'python-programming-bootcamp';
  const ML_FUNDAMENTALS = 'ml-fundamentals';
  const AI_WORKPLACE = 'ai-for-workplace';
  const PYTHON_ML = 'python-machine-learning';
  const ACCESS_KEY = 'codencode_slide_access';
  const ACCESS_TTL_MS = 12 * 60 * 60 * 1000;
  const isHosted = location.hostname === 'codencodemy.github.io';

  if (!isHosted) return;

  function normalize(value) {
    const lowered = String(value || '').trim().toLowerCase();
    if (['python', 'python-bootcamp', 'python_programming_bootcamp', 'python-programming-bootcamp'].includes(lowered)) {
      return PYTHON_BOOTCAMP;
    }
    if (['ml', 'machine-learning', 'machine_learning', 'ml-fundamentals', 'machine-learning-fundamentals'].includes(lowered)) {
      return ML_FUNDAMENTALS;
    }
    if (['ai', 'ai-workplace', 'ai_for_workplace', 'ai-for-workplace', 'workplace-ai'].includes(lowered)) {
      return AI_WORKPLACE;
    }
    if (['python-ml', 'python_machine_learning', 'python-machine-learning', 'python+ml', 'full'].includes(lowered)) {
      return PYTHON_ML;
    }
    return lowered;
  }

  function parseList(value) {
    return (value || '').split(',').map(normalize).filter(Boolean);
  }

  function storeAccess(courses) {
    try {
      localStorage.setItem(ACCESS_KEY, JSON.stringify({
        courses,
        expires: Date.now() + ACCESS_TTL_MS
      }));
    } catch (error) {}
  }

  function readStoredAccess() {
    try {
      const stored = JSON.parse(localStorage.getItem(ACCESS_KEY) || '{}');
      if (!stored.expires || Date.now() > stored.expires) return [];
      return Array.isArray(stored.courses) ? stored.courses : [];
    } catch (error) {
      return [];
    }
  }

  const params = new URLSearchParams(location.search);
  const paramAccess = [
    ...parseList(params.get('access')),
    ...parseList(params.get('allowed')),
    ...parseList(params.get('enrolled'))
  ];

  if (paramAccess.includes('all')) {
    storeAccess([PYTHON_BOOTCAMP, ML_FUNDAMENTALS, AI_WORKPLACE, PYTHON_ML]);
  } else if (paramAccess.length) {
    storeAccess(paramAccess);
  }

  const allowed = new Set([...readStoredAccess(), ...paramAccess]);
  const sessionMatch = location.pathname.match(/session-(\d+)\/index\.html$/);
  const sessionNum = sessionMatch ? parseInt(sessionMatch[1], 10) : 0;
  const canAccessSession = allowed.has('all') ||
    allowed.has(PYTHON_ML) ||
    (sessionNum >= 1 && sessionNum <= 7 && allowed.has(PYTHON_BOOTCAMP)) ||
    (sessionNum >= 8 && sessionNum <= 15 && allowed.has(ML_FUNDAMENTALS)) ||
    (sessionNum >= 14 && sessionNum <= 15 && allowed.has(AI_WORKPLACE));
  if (canAccessSession) return;

  document.documentElement.style.background = '#0a0d0c';
  document.body.innerHTML = `
    <main style="min-height:100vh;display:grid;place-items:center;padding:24px;background:#0a0d0c;color:#f4f7f5;font-family:Inter,Arial,Helvetica,sans-serif">
      <section style="width:min(620px,100%);border:1px solid rgba(255,111,145,.32);border-radius:8px;background:rgba(20,26,24,.92);box-shadow:0 18px 60px rgba(0,0,0,.36);padding:28px">
        <div style="color:#ff6f91;font-size:12px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;margin-bottom:14px">Locked Course</div>
        <h1 style="margin:0 0 12px;font-size:clamp(30px,6vw,52px);line-height:1">Python and Machine Learning Slides</h1>
        <p style="margin:0 0 20px;color:#8f9a96;line-height:1.65">This slide session is available only to enrolled students. Please open it from your LMS course page.</p>
        <a href="../" style="display:inline-flex;align-items:center;justify-content:center;min-height:42px;border-radius:8px;border:1px solid rgba(0,229,160,.34);background:rgba(0,229,160,.12);color:#00e5a0;text-decoration:none;padding:0 16px;font-weight:800">Back to Courses</a>
      </section>
    </main>`;
})();
