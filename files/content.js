// content.js — extracts job description from the current page

function extractJD() {
  const host = window.location.hostname;

  // ── LinkedIn ──
  if (host.includes('linkedin.com')) {
    const el = document.querySelector('.jobs-description__content .jobs-box__html-content')
            || document.querySelector('.job-view-layout .jobs-description');
    return el ? el.innerText.trim() : null;
  }

  // ── Greenhouse ──
  if (host.includes('greenhouse.io')) {
    const el = document.querySelector('#content .job-post');
    return el ? el.innerText.trim() : null;
  }

  // ── Lever ──
  if (host.includes('lever.co')) {
    const el = document.querySelector('.content[data-qa="job-description"]')
            || document.querySelector('.section-wrapper');
    return el ? el.innerText.trim() : null;
  }

  // ── Workday ──
  if (host.includes('myworkdayjobs.com') || host.includes('workday.com')) {
    const el = document.querySelector('[data-automation-id="jobPostingDescription"]');
    return el ? el.innerText.trim() : null;
  }

  // ── Indeed ──
  if (host.includes('indeed.com')) {
    const el = document.querySelector('#jobDescriptionText')
            || document.querySelector('.jobsearch-jobDescriptionText');
    return el ? el.innerText.trim() : null;
  }

  // ── Generic fallback — find the largest text block on the page ──
  const candidates = Array.from(document.querySelectorAll(
    'div, section, article, main'
  )).filter(el => {
    const text = el.innerText || '';
    return text.length > 300 && text.length < 15000;
  });

  if (!candidates.length) return null;

  // Pick the element with the most text that isn't the whole body
  const best = candidates.reduce((a, b) =>
    (b.innerText.length > a.innerText.length ? b : a)
  );

  return best ? best.innerText.trim() : null;
}

// Listen for popup asking for JD
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'GET_JD') {
    const jd = extractJD();
    sendResponse({ jd: jd || '' });
  }
  return true;
});
