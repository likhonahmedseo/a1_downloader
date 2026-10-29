const $ = (selector) => document.querySelector(selector);
const input = $('#urlInput');
const analyze = $('#analyzeButton');
const status = $('#status');
const resultSection = $('#resultSection');
const resultName = $('#resultName');
const resultMeta = $('#resultMeta');
const downloadButton = $('#downloadButton');
const mediaNote = $('#mediaNote');
const historyList = $('#historyList');
const clearButton = $('#clearButton');

const state = { history: JSON.parse(localStorage.getItem('nexadrop-history') || '[]'), lastUrl: '' };
const humanSize = (bytes) => {
  if (!bytes) return 'Size unavailable';
  const units = ['B', 'KB', 'MB', 'GB', 'TB']; let n = bytes; let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${units[i]}`;
};
const setStatus = (message = '', error = false) => { status.textContent = message; status.style.color = error ? '#b34e46' : '#7d9c38'; };
const escapeHtml = (text) => String(text).replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

function renderHistory() {
  if (!state.history.length) {
    historyList.innerHTML = '<div class="empty-state"><span class="empty-icon">＋</span><p>Your download history will appear here.</p><small>Files stay on your device. Nothing is uploaded to an account.</small></div>';
    return;
  }
  historyList.innerHTML = state.history.slice(0, 6).map((item) => `<div class="history-item"><span class="file-icon">↓</span><div class="result-main"><div class="result-title">${escapeHtml(item.name)}</div><div class="result-meta">${escapeHtml(item.meta)} · ${escapeHtml(item.when)}</div></div><a href="${escapeHtml(item.url)}" download aria-label="Download ${escapeHtml(item.name)}">↓</a></div>`).join('');
}

function addHistory(item) {
  state.history = [item, ...state.history.filter((entry) => entry.url !== item.url)].slice(0, 10);
  localStorage.setItem('nexadrop-history', JSON.stringify(state.history)); renderHistory();
}

async function inspect() {
  const url = input.value.trim();
  if (!url) { setStatus('Paste a link first.', true); input.focus(); return; }
  try { new URL(url); } catch { setStatus('That does not look like a valid URL.', true); return; }
  analyze.disabled = true; analyze.querySelector('span').textContent = 'Checking…'; setStatus(''); resultSection.hidden = true;
  try {
    const response = await fetch('/api/inspect', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ url }) });
    const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Could not inspect this link.');
    state.lastUrl = data.url; resultName.textContent = data.filename; resultMeta.textContent = data.kind === 'media_page' ? (data.downloadable ? 'media page  ·  extractor ready  ·  best available quality' : 'media page  ·  install the optional extractor to enable downloads') : `${data.content_type}  ·  ${data.size_label || 'size unknown'}  ·  ${data.supports_resume ? 'resume supported' : 'one-shot transfer'}`;
    const target = data.kind === 'media_page' ? `/api/media/download?url=${encodeURIComponent(data.url)}&format=best` : `/api/download?url=${encodeURIComponent(data.url)}`;
    downloadButton.href = data.downloadable ? target : '#'; downloadButton.classList.toggle('disabled', !data.downloadable); mediaNote.hidden = data.kind !== 'media_page';
    if (data.kind === 'media_page') mediaNote.querySelector('p').textContent = data.downloadable ? 'The extractor is ready. Downloading will fetch the best available video and audio for this link.' : 'Install dependencies with start_app.bat, then analyze this link again. The extractor lane supports permitted media downloads.';
    resultSection.hidden = false;
    if (data.downloadable) addHistory({ name: data.filename, meta: data.size_label || data.content_type, url: downloadButton.href, when: 'Just now' }); setStatus(data.downloadable ? 'Link checked. Ready when you are.' : 'Media page recognized. Install the extractor to enable downloads.');
  } catch (error) { setStatus(error.message, true); }
  finally { analyze.disabled = false; analyze.querySelector('span').textContent = 'Analyze link'; }
}

analyze.addEventListener('click', inspect); input.addEventListener('keydown', (event) => { if (event.key === 'Enter') inspect(); }); input.addEventListener('input', () => { clearButton.hidden = !input.value; });
clearButton.addEventListener('click', () => { input.value = ''; clearButton.hidden = true; input.focus(); });
document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => { input.value = button.dataset.example; clearButton.hidden = false; inspect(); }));
$('#copyButton').addEventListener('click', async () => { if (!state.lastUrl) return; await navigator.clipboard.writeText(state.lastUrl); $('#copyButton').textContent = 'Copied'; setTimeout(() => $('#copyButton').textContent = 'Copy link', 1300); });
$('#clearHistory').addEventListener('click', () => { state.history = []; localStorage.removeItem('nexadrop-history'); renderHistory(); });
$('#themeButton').addEventListener('click', () => document.body.classList.toggle('dim'));
setInterval(async () => {
  if (mediaNote.hidden || !input.value.trim() || !downloadButton.classList.contains('disabled')) return;
  try {
    const response = await fetch('/api/health', { cache: 'no-store' });
    const health = await response.json();
    if (health.extractor_available) inspect();
  } catch { /* The next interval will retry without interrupting the page. */ }
}, 3000);
renderHistory();
