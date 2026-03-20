// popup.js — side panel UI logic for ResumeForge
// NOTE: MV3 extensions block inline scripts, so this file is loaded by popup.html.

const API_BASE = 'https://web-production-356b1.up.railway.app';
const AUTH_STORAGE_KEY = 'resumeforge_auth';

// Must match backend threshold logic (see backend/nodes.py MATCH_THRESHOLD)
const MATCH_THRESHOLD = 0.4; // 40%

// ── STATE ──
let state = {
  jd: '',
  resumeFile: null,
  pdfPath: null,
  generatedPdfUrl: null,
  authMode: 'login',
  authToken: null,
  currentUser: null,
};

// ── AUTH ──
document.getElementById('auth-tab-login').addEventListener('click', () => setAuthMode('login'));
document.getElementById('auth-tab-signup').addEventListener('click', () => setAuthMode('signup'));

document.getElementById('btn-login').addEventListener('click', handleLogin);
document
  .getElementById('login-pass')
  .addEventListener('keydown', e => {
    if (e.key === 'Enter') handleLogin();
  });

document
  .getElementById('signup-email')
  .addEventListener('keydown', e => {
    if (e.key === 'Enter') handleLogin();
  });
document
  .getElementById('signup-name')
  .addEventListener('keydown', e => {
    if (e.key === 'Enter') handleLogin();
  });

function setAuthMode(mode) {
  state.authMode = mode;
  document.getElementById('auth-card').classList.toggle('signup-mode', mode === 'signup');
  document.getElementById('auth-tab-login').classList.toggle('active', mode === 'login');
  document.getElementById('auth-tab-signup').classList.toggle('active', mode === 'signup');
  document.getElementById('signup-name-group').classList.toggle('hidden', mode !== 'signup');
  document.getElementById('signup-email-group').classList.toggle('hidden', mode !== 'signup');
  document.getElementById('btn-login').textContent = mode === 'signup' ? 'Create Account →' : 'Log In →';
  document.getElementById('login-error').textContent = '';
}

async function handleLogin() {
  const name = document.getElementById('signup-name').value.trim();
  const user = document.getElementById('login-user').value.trim();
  const pass = document.getElementById('login-pass').value;
  const email = document.getElementById('signup-email').value.trim();
  const err = document.getElementById('login-error');

  if (!user || !pass) {
    err.textContent = 'Please enter both fields.';
    return;
  }

  if (state.authMode === 'signup') {
    if (!name) {
      err.textContent = 'Please enter your full name.';
      return;
    }
    if (!email) {
      err.textContent = 'Please enter your email address.';
      return;
    }
  }

  try {
    err.textContent = '';
    const endpoint = state.authMode === 'signup' ? '/auth/signup' : '/auth/login';
    const payload = state.authMode === 'signup'
      ? { name, username: user, email, password: pass }
      : { username: user, password: pass };

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || 'Authentication failed');
    }

    setAuthenticatedSession(data.token, data.user);
    showScreen('app-screen');
    pulseScreen();
    tryExtractJD();
  } catch (error) {
    err.textContent = error.message || 'Unable to authenticate.';
    document.getElementById('login-pass').value = '';
  }
}

document.getElementById('btn-logout').addEventListener('click', async () => {
  if (state.authToken) {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
    } catch (_) {
      // Best-effort logout; local cleanup still happens below.
    }
  }
  clearAuthSession();
  document.getElementById('login-user').value = '';
  document.getElementById('login-pass').value = '';
  document.getElementById('signup-name').value = '';
  document.getElementById('signup-email').value = '';
  showScreen('login-screen');
});

function setAuthenticatedSession(token, user) {
  state.authToken = token;
  state.currentUser = user;
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ token, user }));
  const displayName = user.name || user.username;
  document.getElementById('user-display').textContent = displayName;
  document.getElementById('user-avatar').textContent = displayName[0].toUpperCase();
  document.getElementById('user-usage').textContent = `${user.resume_build_count || 0} builds`;
  document.getElementById('usage-count-card').textContent = user.resume_build_count || 0;
  document.getElementById('member-name-card').textContent = displayName;
}

function clearAuthSession() {
  state.authToken = null;
  state.currentUser = null;
  localStorage.removeItem(AUTH_STORAGE_KEY);
  document.getElementById('user-display').textContent = 'Guest';
  document.getElementById('user-avatar').textContent = 'G';
  document.getElementById('user-usage').textContent = '0 builds';
  document.getElementById('usage-count-card').textContent = '0';
  document.getElementById('member-name-card').textContent = '—';
}

function getAuthHeaders(extraHeaders = {}) {
  return {
    ...extraHeaders,
    ...(state.authToken ? { Authorization: `Bearer ${state.authToken}` } : {}),
  };
}

async function restoreAuthSession() {
  const raw = localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return;

  try {
    const parsed = JSON.parse(raw);
    if (!parsed?.token) return;

    state.authToken = parsed.token;
    const response = await fetch(`${API_BASE}/auth/me`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      clearAuthSession();
      return;
    }

    const data = await response.json();
    setAuthenticatedSession(parsed.token, data.user);
    showScreen('app-screen');
    tryExtractJD();
  } catch (_) {
    clearAuthSession();
  }
}

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function pulseScreen() {
  const appScreen = document.getElementById('app-screen');
  appScreen.classList.remove('flash-success');
  void appScreen.offsetWidth;
  appScreen.classList.add('flash-success');
}

// ── TABS ──
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document
      .querySelectorAll('.tab-content')
      .forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    updateReadiness();
  });
});

// ── JD TEXTAREA ──
const jdTextarea = document.getElementById('jd-text');
jdTextarea.addEventListener('input', () => {
  state.jd = jdTextarea.value;
  document.getElementById('char-count').textContent =
    state.jd.length + ' characters';
  updateReadiness();
});

function tryExtractJD() {
  const banner = document.getElementById('jd-banner');

  // Try to get JD from the active tab via content script
  if (typeof chrome !== 'undefined' && chrome.tabs) {
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (!tabs[0]) return;
      chrome.tabs.sendMessage(tabs[0].id, { type: 'GET_JD' }, res => {
        if (chrome.runtime.lastError || !res || !res.jd) {
          banner.style.display = 'none';
          return;
        }
        jdTextarea.value = res.jd;
        state.jd = res.jd;
        document.getElementById('char-count').textContent =
          res.jd.length + ' characters';
        banner.style.display = 'flex';
        updateReadiness();
      });
    });
  } else {
    // Running as standalone HTML — hide banner
    banner.style.display = 'none';
  }
}

// ── FILE UPLOAD ──
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('resume-file-input');
const resumePreviewSection = document.getElementById('resume-preview-section');
const resumeIframe = document.getElementById('resume-iframe');
const resumePlaceholder = document.getElementById('resume-placeholder');

let resumeObjectUrl = null;

uploadZone.addEventListener('click', e => {
  if (e.target.closest('label')) return;
  fileInput.click();
});

fileInput.addEventListener('change', () => handleFile(fileInput.files[0]));

uploadZone.addEventListener('dragover', e => {
  e.preventDefault();
  uploadZone.classList.add('dragover');
});
uploadZone.addEventListener('dragleave', () =>
  uploadZone.classList.remove('dragover')
);
uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  uploadZone.classList.remove('dragover');
  const f = e.dataTransfer.files[0];
  if (f && f.type === 'application/pdf') handleFile(f);
});

document.getElementById('file-remove').addEventListener('click', () => {
  state.resumeFile = null;
  fileInput.value = '';
  document.getElementById('upload-zone').style.display = 'flex';
  document.getElementById('file-attached').style.display = 'none';
  clearResumePreview();
  updateReadiness();
});

function clearResumePreview() {
  if (resumeObjectUrl) {
    URL.revokeObjectURL(resumeObjectUrl);
    resumeObjectUrl = null;
  }
  if (resumeIframe) {
    resumeIframe.src = 'about:blank';
    resumeIframe.style.display = 'none';
  }
  if (resumePlaceholder) resumePlaceholder.style.display = 'flex';
  if (resumePreviewSection) resumePreviewSection.classList.remove('visible');
}

function clearGeneratedPdfPreview() {
  if (state.generatedPdfUrl) {
    URL.revokeObjectURL(state.generatedPdfUrl);
    state.generatedPdfUrl = null;
  }

  const section = document.getElementById('pdf-preview-section');
  const iframe = document.getElementById('pdf-iframe');
  const placeholder = document.getElementById('pdf-placeholder');

  if (iframe) {
    iframe.src = 'about:blank';
    iframe.style.display = 'none';
  }
  if (placeholder) placeholder.style.display = 'flex';
  if (section) section.classList.remove('visible');
}

function showResumePreview(file) {
  if (!file) return;
  // Replace any previous object URL
  if (resumeObjectUrl) URL.revokeObjectURL(resumeObjectUrl);
  resumeObjectUrl = URL.createObjectURL(file);

  if (resumePreviewSection) resumePreviewSection.classList.add('visible');
  if (resumePlaceholder) resumePlaceholder.style.display = 'none';

  if (resumeIframe) {
    resumeIframe.src = resumeObjectUrl;
    resumeIframe.style.display = 'block';
  }
}

function handleFile(file) {
  if (!file) return;
  state.resumeFile = file;
  document.getElementById('upload-zone').style.display = 'none';
  document.getElementById('file-attached').style.display = 'flex';
  document.getElementById('file-name').textContent = file.name;
  document.getElementById('file-size').textContent =
    (file.size / 1024).toFixed(1) + ' KB';
  showResumePreview(file);
  updateReadiness();
}

// ── READINESS ──
function updateReadiness() {
  const hasJD = state.jd.trim().length > 50;
  const hasResume = !!state.resumeFile;

  const jdBadge = document.getElementById('ready-jd');
  const resBadge = document.getElementById('ready-resume');

  jdBadge.textContent = hasJD ? '✓ Ready' : '✕ Missing';
  jdBadge.className =
    'readiness-badge ' + (hasJD ? 'badge-ok' : 'badge-missing');
  resBadge.textContent = hasResume ? '✓ Ready' : '✕ Missing';
  resBadge.className =
    'readiness-badge ' + (hasResume ? 'badge-ok' : 'badge-missing');

  document.getElementById('btn-generate').disabled = !(hasJD && hasResume);
}

// ── GENERATE ──
document.getElementById('btn-generate').addEventListener('click', generateResume);

async function generateResume() {
  if (!state.authToken) {
    showStatus('Please log in to generate a resume.', 'error');
    showScreen('login-screen');
    return;
  }

  const btn = document.getElementById('btn-generate');
  btn.classList.add('loading');
  btn.disabled = true;

  showStatus('', '');
  document.getElementById('match-score-section').classList.remove('visible');
  clearGeneratedPdfPreview();

  const steps = document.getElementById('progress-steps');
  steps.classList.add('visible');
  resetSteps();

  try {
    await setStep(1);
    await setStep(2);

    const formData = new FormData();
    formData.append('resume', state.resumeFile);
    formData.append('jd', state.jd);

    await setStep(3);

    const res = await fetch(`${API_BASE}/generate`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    if (data.user) {
      setAuthenticatedSession(state.authToken, data.user);
    }

    await setStep(4);

    // show score
    showMatchScore(
      data.final_score ?? data.match_score,
      data.final_missing_keywords ?? data.missing_keywords,
      data.total_keywords,
      data.matched_keywords_count,
      data.missing_keywords_count
    );

    // show PDF
    if (data.pdf_path) {
      const filename = data.pdf_path.split('/').pop().replace('.pdf', '');
      await showPDFPreview(filename);
      showStatus('Resume generated successfully!', 'success');
    } else {
      const score = typeof (data.final_score ?? data.match_score) === 'number'
        ? (data.final_score ?? data.match_score)
        : 0;
      if (score < MATCH_THRESHOLD) {
        showStatus(
          `Match score too low (< ${Math.round(MATCH_THRESHOLD * 100)}%) — resume not generated.`,
          'info'
        );
      } else {
        const latexError = formatLatexError(data.latex_error);
        showStatus(
          latexError
            ? `Match score is sufficient, but PDF generation failed: ${latexError}`
            : 'Match score is sufficient, but the PDF was not generated. Check backend logs for LaTeX/tectonic errors.',
          'info'
        );
      }
    }
  } catch (err) {
    showStatus('Error: ' + err.message, 'error');
  } finally {
    btn.classList.remove('loading');
    btn.disabled = false;
  }
}

async function setStep(n) {
  for (let i = 1; i < n; i++) {
    const el = document.getElementById(`step-${i}`);
    el.classList.remove('active');
    el.classList.add('done');
  }
  const cur = document.getElementById(`step-${n}`);
  cur.classList.add('active');
  await sleep(600);
}

function resetSteps() {
  for (let i = 1; i <= 4; i++) {
    const el = document.getElementById(`step-${i}`);
    el.classList.remove('active', 'done');
  }
}

function showMatchScore(score, missing, totalKeywords = 0, matchedCount = 0, missingCount = 0) {
  const section = document.getElementById('match-score-section');
  section.classList.add('visible');

  const pct = Math.round((score || 0) * 100);
  const cls = pct >= 70 ? 'high' : pct >= 40 ? 'mid' : 'low';

  const val = document.getElementById('score-value');
  val.textContent = pct + '%';
  val.className = 'score-value ' + cls;

  const bar = document.getElementById('score-bar');
  bar.className = 'score-bar-fill ' + cls;
  setTimeout(() => {
    bar.style.width = pct + '%';
  }, 100);

  document.getElementById('total-keywords-value').textContent = totalKeywords || 0;
  document.getElementById('matched-keywords-value').textContent = matchedCount || 0;
  document.getElementById('missing-keywords-count').textContent = missingCount || 0;

  const kwContainer = document.getElementById('missing-keywords');
  kwContainer.innerHTML = '';
  if (missing && missing.length) {
    const label = document.createElement('span');
    label.style.cssText = 'font-size:11px;color:var(--muted);width:100%;';
    label.textContent = 'Missing keywords:';
    kwContainer.appendChild(label);
    missing.slice(0, 8).forEach(kw => {
      const chip = document.createElement('span');
      chip.className = 'kw-chip';
      chip.textContent = kw;
      kwContainer.appendChild(chip);
    });
  }
}

async function showPDFPreview(filename) {
  const section = document.getElementById('pdf-preview-section');
  section.classList.add('visible');

  const iframe = document.getElementById('pdf-iframe');
  const placeholder = document.getElementById('pdf-placeholder');

  if (state.generatedPdfUrl) {
    URL.revokeObjectURL(state.generatedPdfUrl);
    state.generatedPdfUrl = null;
  }

  const response = await fetch(`${API_BASE}/download/${filename}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error(`Unable to load generated PDF preview (${response.status})`);
  }

  const blob = await response.blob();
  state.generatedPdfUrl = URL.createObjectURL(blob);

  iframe.src = state.generatedPdfUrl;
  iframe.style.display = 'block';
  placeholder.style.display = 'none';

  document.getElementById('btn-download').onclick = () => {
    const a = document.createElement('a');
    a.href = state.generatedPdfUrl;
    a.download = filename + '.pdf';
    a.click();
  };
}

function showStatus(msg, type) {
  const el = document.getElementById('status-msg');
  el.textContent = msg;
  el.className = 'status-msg' + (msg ? ` visible ${type}` : '');
}

function formatLatexError(errorText) {
  if (!errorText || typeof errorText !== 'string') return '';

  const compact = errorText
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .find(line =>
      !line.startsWith('note:') &&
      !line.startsWith('help:') &&
      !line.startsWith('warning:')
    );

  if (!compact) return '';
  return compact.length > 220 ? compact.slice(0, 217) + '...' : compact;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

updateReadiness();
setAuthMode('login');
restoreAuthSession();
