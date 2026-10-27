/* Codencode Staff Portal. Pages are server-rendered; this file only wires
   up the actions. Every POST carries the CSRF token from the page. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const csrf = $('meta[name="csrf-token"]')?.content || '';

  async function api(url, body, opts = {}) {
    const init = {method: 'POST', credentials: 'same-origin', headers: {'X-CSRFToken': csrf}};
    if (body instanceof FormData) init.body = body;
    else { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body || {}); }
    const res = await fetch(url, init);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || (res.status === 429 ? 'Too many requests. Wait a minute.' : `Request failed (${res.status})`));
    return data;
  }

  let toastTimer;
  function toast(text, kind = 'ok') {
    const t = $('#toast');
    if (!t) return alert(text);
    t.textContent = text; t.className = `toast status ${kind}`; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 4500);
  }
  const reloadSoon = () => setTimeout(() => location.reload(), 700);

  // Month / staff pickers submit on change.
  $$('form[data-autosubmit] select').forEach(s => s.addEventListener('change', () => s.form.submit()));

  // Clock out (live banner).
  $$('[data-clock-out]').forEach(b => b.addEventListener('click', async () => {
    b.disabled = true;
    try { await api('/staff/api/clock-out'); toast('Clocked out.'); reloadSoon(); }
    catch (e) { toast(e.message, 'bad'); b.disabled = false; }
  }));

  // Start class: clock in on the server, then open Zoom in a new tab.
  $$('[data-start-class]').forEach(b => b.addEventListener('click', async () => {
    const win = window.open('', '_blank');        // open now so pop-up blockers allow it
    b.disabled = true;
    try {
      const r = await api('/staff/api/clock-in', {mode: 'zoom', cohort_id: Number(b.dataset.startClass)});
      if (r.zoom_link && win) win.location = r.zoom_link; else if (r.zoom_link) location.href = r.zoom_link;
      toast('Clocked in. Rename yourself to "Name – Teacher" in Zoom.'); reloadSoon();
    } catch (e) { if (win) win.close(); toast(e.message, 'bad'); b.disabled = false; }
  }));

  // Office clock-in with the geofence check.
  const locBtn = $('#locBtn');
  if (locBtn) {
    let fix = null;
    const stat = $('#stat'), inBtn = $('#inBtn');
    const set = (t, c = '') => { stat.textContent = t; stat.className = `status ${c}`; };
    locBtn.addEventListener('click', () => {
      if (!navigator.geolocation) return set('Location is not available on this device.', 'warn');
      set('Locating…');
      navigator.geolocation.getCurrentPosition(p => {
        fix = {lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy};
        if (p.coords.accuracy > 100) { inBtn.disabled = true; return set(`GPS accuracy is ${Math.round(p.coords.accuracy)} m. Move near a window and check again.`, 'warn'); }
        inBtn.disabled = false; set(`Location found (±${Math.round(p.coords.accuracy)} m). Clock in to confirm with the office geofence.`, 'ok');
      }, err => set(err.code === 1 ? 'Location permission is blocked. Allow location for this site and try again.' : 'Could not get your location. Try again.', 'warn'),
      {enableHighAccuracy: true, timeout: 15000, maximumAge: 0});
    });
    inBtn.addEventListener('click', async () => {
      if (!fix) return;
      inBtn.disabled = true;
      try {
        const r = await api('/staff/api/clock-in', {mode: 'office', task: $('#task').value, ...fix});
        set(`✓ Clocked in, ${r.distance_m} m from the office.`, 'ok'); reloadSoon();
      } catch (e) { set(`✗ ${e.message}`, 'bad'); inBtn.disabled = false; }
    });
  }

  // History: timeline / timecard toggle and day filter from the calendar dots.
  const vTime = $('#vTime'), vCard = $('#vCard');
  if (vTime && $('#hTime')) {
    const show = card => {
      vTime.setAttribute('aria-pressed', !card); vCard.setAttribute('aria-pressed', card);
      $('#hTime').hidden = card; $('#hCard').hidden = !card;
    };
    vTime.addEventListener('click', () => show(false));
    vCard.addEventListener('click', () => show(true));
  }
  let selDay = null;
  const filterDay = d => {
    selDay = selDay === d ? null : d;
    $$('.day').forEach(b => b.classList.toggle('sel', b.dataset.d === selDay));
    $$('[data-date]').forEach(r => (r.hidden = !!selDay && r.dataset.date !== selDay));
    const c = $('#clearDay'); if (c) c.hidden = !selDay;
  };
  $$('.day.has').forEach(b => b.addEventListener('click', () => filterDay(b.dataset.d)));
  $('#clearDay')?.addEventListener('click', () => filterDay(selDay));

  // Generic POST buttons (approve / reject / withdraw / remove / create Zoom).
  $$('[data-post]').forEach(b => b.addEventListener('click', async () => {
    let body = {};
    if (b.hasAttribute('data-note')) {
      const note = prompt('Reason (shown to the teacher):', '');
      if (note === null) return;
      body.note = note;
    }
    b.disabled = true;
    try {
      const r = await api(b.dataset.post, body);
      if (b.hasAttribute('data-report')) {
        toast(`Pulled ${r.pulled} report(s) for ${r.meetings_checked} meeting(s).` + (r.errors?.length ? ` Errors: ${r.errors.join('; ')}` : ''), r.errors?.length ? 'warn' : 'ok');
      } else toast('Done.');
      reloadSoon();
    } catch (e) { toast(e.message, 'bad'); b.disabled = false; }
  }));

  // Skip a date on an active schedule.
  $$('[data-skip]').forEach(b => b.addEventListener('click', async () => {
    const input = $(`[data-skip-for="${b.dataset.skipInput}"]`);
    if (!input.value) return input.focus();
    try { await api(b.dataset.skip, {date: input.value}); toast(`Skipped ${input.value}.`); reloadSoon(); }
    catch (e) { toast(e.message, 'bad'); }
  }));

  // Schedule form.
  const sf = $('#schedForm');
  if (sf) {
    const type = $('#fType'), cohortSel = $('#fCohort');
    const sync = () => {
      const zoom = type.value === 'zoom';
      $$('[data-zoom]', sf).forEach(el => (el.hidden = !zoom));
      $$('[data-new]', sf).forEach(el => (el.hidden = !zoom || !!cohortSel.value));
    };
    type.addEventListener('change', sync);
    cohortSel.addEventListener('change', () => {
      const o = cohortSel.selectedOptions[0];
      if (cohortSel.value) { $('#fTitle').value = o.dataset.name || ''; sf.zoom_meeting_id.value = o.dataset.mid || ''; }
      sync();
    });
    sync();
    sf.addEventListener('submit', async e => {
      e.preventDefault();
      const fd = new FormData(sf), st = $('#fStat');
      const body = Object.fromEntries([...fd.entries()].filter(([k]) => k !== 'days'));
      body.days = fd.getAll('days').map(Number);
      const zoom = body.type === 'zoom';
      if (!zoom || body.cohort_id) delete body.course_id;
      if (!zoom) { delete body.cohort_id; delete body.zoom_meeting_id; }
      st.hidden = false;
      try {
        const r = await api(zoom ? '/staff/api/cohort-requests' : '/staff/api/shifts', body);
        st.className = 'status ok';
        st.textContent = r.status === 'pending' ? `Sent "${body.title}" to admin for approval.` : `Added "${body.title}". It is live now.`;
        sf.reset(); sync(); reloadSoon();
      } catch (x) { st.className = 'status bad'; st.textContent = x.message; }
    });
  }

  // Zoom CSV upload.
  const cf = $('#csvForm');
  cf?.addEventListener('submit', async e => {
    e.preventDefault();
    const st = $('#zStat');
    st.className = 'status'; st.textContent = 'Uploading…';
    try {
      const r = await api('/staff/api/admin/reports/upload', new FormData(cf));
      const bad = r.failed.map(f => `${f.file} (${f.error})`);
      st.className = `status ${bad.length ? 'warn' : 'ok'}`;
      st.textContent = `${r.ok.length} report(s) loaded.` + (bad.length ? ` Could not read: ${bad.join(', ')}` : '');
      if (r.ok.length) setTimeout(() => location.reload(), 1800);
    } catch (x) { st.className = 'status bad'; st.textContent = x.message; }
  });

  // Review: quick approve from the list.
  $$('[data-review]').forEach(b => b.addEventListener('click', async () => {
    const reason = prompt('Reason for approving (written to the audit log):', '');
    if (!reason) return;
    try { await api(`/staff/api/admin/sessions/${b.dataset.review}/review`, {action: b.dataset.action, reason}); toast('Approved.'); reloadSoon(); }
    catch (e) { toast(e.message, 'bad'); }
  }));
  const rf = $('#reviewForm');
  if (rf) {
    const sync = () => $$('[data-for]', rf).forEach(el => (el.hidden = el.dataset.for !== $('#rvAction').value));
    $('#rvAction').addEventListener('change', sync); sync();
    rf.addEventListener('submit', async e => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(rf).entries());
      try { await api(`/staff/api/admin/sessions/${rf.dataset.session}/review`, body); toast('Saved.'); reloadSoon(); }
      catch (x) { toast(x.message, 'bad'); }
    });
  }

  // Team profiles.
  $$('[data-save-team]').forEach(b => b.addEventListener('click', async () => {
    const tr = b.closest('tr');
    const val = n => tr.querySelector(`[name="${n}"]`);
    try {
      await api(`/staff/api/admin/team/${tr.dataset.team}`, {
        employment_type: val('employment_type').value, hourly_rate: val('hourly_rate').value,
        monthly_cap_hours: val('monthly_cap_hours').value, active: val('active').checked});
      toast('Saved.');
    } catch (e) { toast(e.message, 'bad'); }
  }));

  // Install guide: device detection, home-screen prompt, setup checklist.
  const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const ua = navigator.userAgent;
  const os = /iPhone|iPad|iPod/.test(ua) || (ua.includes('Mac') && navigator.maxTouchPoints > 1) ? 'ios'
    : /Android/.test(ua) ? 'android' : 'desktop';
  const store = {get: k => { try { return localStorage.getItem(k); } catch (_) { return null; } },
                 set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} }};

  // "Add to home screen" prompt on phones, until installed or dismissed.
  const tip = $('#installTip');
  if (tip && !standalone && os !== 'desktop' && !store.get('staffTipDismissed')) tip.hidden = false;
  $('[data-dismiss-tip]')?.addEventListener('click', () => { tip.hidden = true; store.set('staffTipDismissed', '1'); });

  // Guide page: open the tab for this device.
  let deferred = null;     // Chrome's install prompt, when it offers one
  const tabs = $$('[data-os]');
  const showOs = v => {
    tabs.forEach(t => t.setAttribute('aria-pressed', t.dataset.os === v));
    $$('[data-panel]').forEach(p => (p.hidden = p.dataset.panel !== v));
    const q = $('#androidQuick'); if (q) q.hidden = !(deferred && v !== 'ios');
  };
  if (tabs.length) { showOs(os); tabs.forEach(t => t.addEventListener('click', () => showOs(t.dataset.os))); }

  const setCheck = (id, state, msg) => {
    const el = $(id); if (!el) return;
    el.className = `check ${state}`; $('[data-msg]', el).textContent = msg;
  };
  setCheck('#chkInstalled', standalone ? 'ok' : 'no', standalone ? 'Yes, you opened it from the home screen.'
    : 'Not yet. Follow step 1 below, then open it from the new icon.');

  // Android and desktop Chrome: one-tap install.
  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault(); deferred = e;
    const q = $('#androidQuick'), cur = $('[data-os][aria-pressed="true"]');
    if (q && cur && cur.dataset.os !== 'ios') q.hidden = false;
  });
  $('#installNow')?.addEventListener('click', async () => {
    if (!deferred) return;
    deferred.prompt(); await deferred.userChoice.catch(() => null); deferred = null;
    $('#androidQuick').hidden = true;
  });

  // Web Push: register the service worker and offer to subscribe.
  const vapid = $('meta[name="vapid-key"]')?.content;
  const pushBtn = $('#pushBtn'), pushNow = $('#pushNow');
  const pushStat = (t, k) => { const s = $('#pushStat'); if (s) { s.hidden = false; s.className = `status ${k}`; s.textContent = t; } };
  const pushOn = () => {
    setCheck('#chkPush', 'ok', 'Yes, reminders will arrive on this device.');
    if (pushBtn) pushBtn.hidden = true;
    if (pushNow) { pushNow.disabled = true; pushNow.textContent = 'Notifications are on'; }
  };
  const pushSupported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  if (!vapid) {
    setCheck('#chkPush', 'no', 'Not switched on by admin yet. You will get reminders by email meanwhile.');
    if (pushNow) pushNow.disabled = true;
  } else if (!pushSupported) {
    setCheck('#chkPush', 'no', os === 'ios' ? 'Add it to your home screen and open it from the icon first (iOS 16.4 or later).'
      : 'This browser cannot show notifications.');
    if (pushNow) pushNow.disabled = true;
  } else if (Notification.permission === 'denied') {
    setCheck('#chkPush', 'no', 'Blocked. See “I tapped Don’t Allow by mistake” below.');
  }
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/staff/sw.js', {scope: '/staff/'}).then(async reg => {
      if (!vapid || !pushSupported) return;
      const existing = await reg.pushManager.getSubscription();
      if (existing) { pushOn(); return api('/staff/api/push/subscribe', existing.toJSON()).catch(() => {}); }
      if (Notification.permission !== 'denied') {
        setCheck('#chkPush', 'no', 'Not yet. Follow step 2 below.');
        if (pushBtn) pushBtn.hidden = false;
      }
      const turnOn = async () => {
        try {
          const key = Uint8Array.from(atob(vapid.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - vapid.length % 4) % 4)), c => c.charCodeAt(0));
          const sub = await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: key});
          await api('/staff/api/push/subscribe', sub.toJSON());
          pushOn(); pushStat('Done. You will get a notification 15 minutes before each class.', 'ok');
          toast('Notifications are on.');
        } catch (e) {
          const msg = Notification.permission === 'denied' ? 'Notifications are blocked. See the help below to allow them.'
            : os === 'ios' && !standalone ? 'On iPhone, add the Staff Portal to your Home Screen first, then open it from the icon.'
            : 'Could not turn on notifications. Try again.';
          pushStat(msg, 'warn'); toast(msg, 'warn');
        }
      };
      pushBtn?.addEventListener('click', turnOn);
      pushNow?.addEventListener('click', turnOn);
    }).catch(() => {});
  }
})();
