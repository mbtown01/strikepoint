/* ── StrikePoint client-side logic ────────────────────────── */

// State seeded from template (set via window._ vars in each page's <script>)
let _isDetecting = window._isDetecting ?? false;
let _isRecording = window._isRecording ?? false;

// ── SSE connection ─────────────────────────────────────────
const _sse = new EventSource('/events');

_sse.addEventListener('cal_phase', e => {
  const d = JSON.parse(e.data);
  setCalInstruction(d.instruction);
  setCalPhase(d.phase, d.accept_enabled);
});

_sse.addEventListener('calibration_status', e => {
  const d = JSON.parse(e.data);
  updateCalibrationStatus(d.is_calibrated);
});

_sse.addEventListener('strike_detected', e => {
  const d = JSON.parse(e.data);
  renderStrikeResult(d);
  prependHistoryCard(d);
});

_sse.addEventListener('detection_status', e => {
  const d = JSON.parse(e.data);
  _isDetecting = d.is_detecting;
  updateDetectButton();
});

_sse.addEventListener('recording_status', e => {
  const d = JSON.parse(e.data);
  _isRecording = d.is_recording;
  updateRecordButton();
});

_sse.addEventListener('log_entry', e => {
  const d = JSON.parse(e.data);
  appendLogEntry(d);
});

_sse.onerror = () => {
  // SSE will auto-reconnect; nothing to do here
};

// ── Button actions ─────────────────────────────────────────
async function toggleDetection() {
  const r = await fetch('/strike/toggle', { method: 'POST' });
  const d = await r.json();
  _isDetecting = d.is_detecting;
  updateDetectButton();

  const result = document.getElementById('strike-result');
  if (result && !_isDetecting) {
    // Keep last result visible; don't reset
  } else if (result && _isDetecting) {
    result.innerHTML = `
      <div class="strike-placeholder">
        <div class="placeholder-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
            <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/>
          </svg>
        </div>
        <div class="placeholder-text">Waiting for strike...</div>
      </div>`;
  }
}

let _calPollTimer = null;

async function startCalibration() {
  const r = await fetch('/calibrate/start', { method: 'POST' });
  const d = await r.json();
  setCalInstruction(d.instruction);
  resetCalPhase();
  document.getElementById('cal-accept-btn').disabled = true;

  const visImg   = document.getElementById('cal-visual-img');
  const thermImg = document.getElementById('cal-thermal-img');
  let n = 0;
  _calPollTimer = setInterval(() => {
    if (visImg   && window._calVisSrc)   visImg.src   = window._calVisSrc   + '?t=' + n;
    if (thermImg && window._calThermSrc) thermImg.src = window._calThermSrc + '?t=' + n;
    n++;
  }, 100);

  document.getElementById('cal-modal').showModal();
}

async function cancelCalibration() {
  await fetch('/calibrate/cancel', { method: 'POST' });
  document.getElementById('cal-modal').close();
  resetCalPhase();
  _clearCalFeeds();
}

async function acceptCalibration() {
  await fetch('/calibrate/accept', { method: 'POST' });
  document.getElementById('cal-modal').close();
  resetCalPhase();
  _clearCalFeeds();
}

function _clearCalFeeds() {
  if (_calPollTimer) { clearInterval(_calPollTimer); _calPollTimer = null; }
  const vis   = document.getElementById('cal-visual-img');
  const therm = document.getElementById('cal-thermal-img');
  if (vis)   vis.removeAttribute('src');
  if (therm) therm.removeAttribute('src');
}

async function toggleRecording() {
  const r = await fetch('/recording/toggle', { method: 'POST' });
  const d = await r.json();
  _isRecording = d.is_recording;
  updateRecordButton();
}

// ── UI state helpers ───────────────────────────────────────
function updateDetectButton() {
  const btn = document.getElementById('detect-btn');
  if (!btn) return;
  btn.textContent = _isDetecting ? 'Stop Detection' : 'Start Detection';
  btn.className   = `btn ${_isDetecting ? 'btn-danger' : 'btn-success'}`;
}

function updateRecordButton() {
  const btn = document.getElementById('record-btn');
  if (!btn) return;
  btn.textContent = _isRecording ? 'Stop Recording' : 'Start Recording';
  btn.className   = `btn ${_isRecording ? 'btn-danger' : 'btn-outline'}`;
}

function updateCalibrationStatus(isCalibrated) {
  const dot   = document.querySelector('#sidebar-cal-status .status-dot');
  const label = document.querySelector('#sidebar-cal-status .status-label');
  const calBtn = document.querySelector('.header-actions .btn-outline');

  if (dot) {
    dot.className = `status-dot ${isCalibrated ? 'green' : 'yellow'}`;
  }
  if (label) {
    label.textContent = isCalibrated ? 'Calibrated' : 'Not calibrated';
  }
  if (calBtn) {
    calBtn.textContent = isCalibrated ? 'Re-calibrate' : 'Calibrate';
  }
}

function setCalInstruction(text) {
  const el = document.getElementById('cal-instruction');
  if (el) el.textContent = text;
}

function setCalPhase(phase, acceptEnabled) {
  for (let i = 1; i <= 3; i++) {
    const dot = document.getElementById(`phase-dot-${i}`);
    if (!dot) continue;
    if (i < phase)       dot.className = 'phase-dot complete';
    else if (i === phase) dot.className = 'phase-dot active';
    else                  dot.className = 'phase-dot';
  }
  const acceptBtn = document.getElementById('cal-accept-btn');
  if (acceptBtn) acceptBtn.disabled = !acceptEnabled;
}

function resetCalPhase() {
  for (let i = 1; i <= 3; i++) {
    const dot = document.getElementById(`phase-dot-${i}`);
    if (dot) dot.className = 'phase-dot';
  }
}

// ── Strike result rendering ────────────────────────────────
function renderStrikeResult(d) {
  const el = document.getElementById('strike-result');
  if (!el) return;
  el.className = 'card strike-result-card';
  el.innerHTML = buildStrikeHTML(d);
}

function prependHistoryCard(d) {
  const list = document.getElementById('history-list');
  if (!list) return;
  const empty = list.querySelector('.empty-state');
  if (empty) empty.remove();
  const card = document.createElement('div');
  card.className = 'card history-card';
  card.innerHTML = buildHistoryCardHTML(d);
  list.prepend(card);
}

function buildStrikeHTML(d) {
  const leftClass  = d.left_score  >= 0.4 ? 'score-ok' : 'score-warn';
  const rightClass = d.right_score >= 0.4 ? 'score-ok' : 'score-warn';
  const leftPct    = Math.round(d.left_score  * 100);
  const rightPct   = Math.round(d.right_score * 100);
  return `
    <div class="strike-images">
      <img src="${d.visual_url}"  alt="Visual">
      <img src="${d.thermal_url}" alt="Thermal">
    </div>
    <div class="strike-scores">
      <div class="score-block ${leftClass}">
        <div class="score-label">Left</div>
        <div class="score-value">${leftPct}%</div>
      </div>
      <div class="score-block ${rightClass}">
        <div class="score-label">Right</div>
        <div class="score-value">${rightPct}%</div>
      </div>
    </div>
    <div class="strike-timestamp">${d.timestamp}</div>`;
}

function buildHistoryCardHTML(d) {
  const leftClass  = d.left_score  >= 0.4 ? 'score-ok' : 'score-warn';
  const rightClass = d.right_score >= 0.4 ? 'score-ok' : 'score-warn';
  const leftPct    = Math.round(d.left_score  * 100);
  const rightPct   = Math.round(d.right_score * 100);
  return `
    <div class="history-images">
      <img src="${d.visual_url}"  alt="Visual">
      <img src="${d.thermal_url}" alt="Thermal">
    </div>
    <div class="history-meta">
      <div class="score-row">
        <div class="score-block ${leftClass}">
          <div class="score-label">Left</div>
          <div class="score-value">${leftPct}%</div>
        </div>
        <div class="score-block ${rightClass}">
          <div class="score-label">Right</div>
          <div class="score-value">${rightPct}%</div>
        </div>
      </div>
      <div class="history-timestamp">${d.timestamp}</div>
    </div>`;
}

// ── Log pane ───────────────────────────────────────────────
const LOG_LEVEL_CLASS = {
  DEBUG:    'log-debug',
  INFO:     'log-info',
  WARNING:  'log-warning',
  ERROR:    'log-error',
  CRITICAL: 'log-critical',
};
const LOG_MAX_LINES = 500;

function appendLogEntry(d) {
  const pane = document.getElementById('log-pane');
  if (!pane) return;

  const line = document.createElement('div');
  line.className = `log-line ${LOG_LEVEL_CLASS[d.level] ?? 'log-info'}`;
  line.textContent = d.message;
  pane.appendChild(line);

  // Trim old lines to keep DOM lean
  while (pane.children.length > LOG_MAX_LINES) {
    pane.removeChild(pane.firstChild);
  }

  // Auto-scroll only if already near the bottom
  const threshold = 60;
  if (pane.scrollHeight - pane.scrollTop - pane.clientHeight < threshold) {
    pane.scrollTop = pane.scrollHeight;
  }
}
