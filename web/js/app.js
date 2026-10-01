// Orchestrator. Nothing here draws or decides on its own — it moves the single
// store forward as events arrive (voice, stream, camera, keyboard), and every
// layer reflects that store. The interface constructs itself out of state.

import { on, connect, api } from './bus.js';
import * as store from './store.js';
import { STATES } from './store.js';
import { Core } from './core.js';
import { Wave } from './waveform.js';
import { Voice, canListen, canSpeak } from './voice.js';
import { classify } from './intent.js';
import * as layers from './layers.js';
import { Companion } from './companion.js';
import { mountRedJohn, startVision, stopVision } from './vision.js';

const $ = (sel) => document.querySelector(sel);
const app = $('#app');
const nowStamp = () => new Date().toLocaleTimeString('en-GB', { hour12: false });

const core = new Core($('#core'));
const wave = new Wave($('#wave'));
let companion = null;     // the on-screen pixel Jane — mirrors state, toggles mic
let uptime = 0;
let micStream = null;
let trackTimer = null;
let opened = null;        // the single widget zoomed to centre, or null at home

// A spoken intent maps to the widget it should bring forward.
const CONTEXT_WIDGET = {
  subject: 'subject', environment: 'environment', schedule: 'calendar',
  intel: 'intel', ledger: 'ledger', system: 'system',
};

// ===== store → DOM ==========================================================
// One subscriber turns state into attributes; CSS does the rest.
store.subscribe((s) => {
  app.dataset.state = s.mode;
  if (s.context) app.dataset.context = s.context; else app.removeAttribute('data-context');
  const focused = s.focus || s.mode === STATES.TRACKING;
  if (focused) app.dataset.focus = 'true'; else app.removeAttribute('data-focus');
  core.setState(s.mode);
  companion?.setState(s.mode);
  layers.stateLabel(s.mode.toUpperCase());
});

/** Settle back to a resting state once an interaction ends. */
function settle() {
  const s = store.get();
  if (s.target) { store.setMode(STATES.TRACKING); return; }
  store.setMode(s.micLive ? STATES.LISTENING : STATES.IDLE);
}

// ===== boot =================================================================
layers.mountSystem();
layers.mountNetmap();
mountRedJohn();
layers.calendar();

const voice = new Voice({
  onFinal: (text) => {
    layers.ambient(text, 'YOU');
    handleUtterance(text);
    api.say(text).catch(() => layers.notice('Jane is not answering the door.'));
  },
  onInterim: (text) => layers.ambient(text, 'YOU'),
  onStateChange: (live) => {
    store.setMic(live);
    companion?.setMic(live);
    const btn = $('#mic-toggle');
    btn.classList.toggle('live', live);
    btn.textContent = live ? 'MIC LIVE' : 'SPACE / MIC';
    if (live && store.get().mode === STATES.IDLE) store.setMode(STATES.LISTENING);
    if (!live) settle();
  },
  onError: (message) => layers.notice(message),
  onSpeaking: (speaking) => { wave.setSpeaking(speaking); companion?.setSpeaking(speaking); },
});

// The pixel companion: at rest on his sofa, a click enables the mic and he listens.
companion = new Companion({
  onToggleMic: () => (voice.wantListening ? micOff() : micOn()),
});

async function bootstrap() {
  let data;
  try {
    data = await api.bootstrap();
  } catch {
    layers.notice('The server went quiet. Restart python -m jane.');
    return;
  }
  store.seed(data);
  document.title = `J.A.N.E. v${data.version}`;
  uptime = data.uptime || 0;

  layers.logAll(data.log);
  layers.system(data.telemetry);
  layers.encryption(data.encryption);
  layers.netmap(data.netmap);
  layers.headlines(data.news);
  layers.ledger(data.ledger);
  layers.environment(data.weather);
  layers.turn({ who: 'JANE', text: data.greeting });
  layers.ambient(canListen ? 'Press space, or hit MIC.' : 'Type below — this browser has no ears.',
                 'J.A.N.E.');
  if (!canListen) $('#type-row').classList.add('on');
  if (!data.has_key) layers.notice('No ANTHROPIC_API_KEY in .env — Jane can hear, but not think.');
}

// ===== intent → adaptive surface ===========================================
// A shallow keyword read decides what materialises while the model thinks.
function handleUtterance(text) {
  const { context, investigation, subject } = classify(text);

  if (investigation) {
    store.setContext('subject');
    if (subject) { store.setTarget({ ...subject, since: nowStamp() }); layers.target(store.get().target); }
    const st = $('#tgt-status'); if (st) st.textContent = 'TRACKING';
    store.setMode(STATES.SEARCHING);
    core.ping();
    openWidget('subject');
    clearTimeout(trackTimer);
    trackTimer = setTimeout(() => store.setMode(STATES.TRACKING), 1500);
    return;
  }

  // Not an investigation — clear any held subject, bring the right facet forward.
  store.setTarget(null);
  store.setContext(context);
  store.setMode(STATES.PROCESSING);
  const widget = CONTEXT_WIDGET[context];
  if (widget) {
    if (widget === 'calendar') layers.calendar(new Date());
    openWidget(widget);
  }
}

// ===== live stream ==========================================================
on('log', layers.logLine);
// When Jane reaches for a filesystem tool, the companion gets up and runs.
const RUN_TOOLS = /Tool:\s*(list_dir|read_file|write_file|append_file|run_command)/i;
on('log', (line) => { if (line && RUN_TOOLS.test(line.msg || '')) companion?.run(); });
on('telemetry', (t) => { store.patch('telemetry', t); layers.system(t); });
on('weather', (w) => { store.patch('weather', w); layers.environment(w); });
on('news', (n) => { store.patch('news', n); layers.headlines(n); });
on('ledger', (l) => { store.patch('ledger', l); layers.ledger(l); });
on('netmap', (n) => { store.patch('netmap', n); layers.netmap(n); });
on('transcript', (t) => {
  layers.turn(t);
  // Echo a trimmed version of Jane's line into the companion's bubble.
  if (t && t.who === 'JANE' && t.text) {
    const line = t.text.length > 90 ? `${t.text.slice(0, 88)}…` : t.text;
    companion?.say(line, 4200);
  }
});
on('transcript_open', () => { layers.transcriptOpen(); if (store.get().mode === STATES.IDLE || store.get().mode === STATES.LISTENING) store.setMode(STATES.PROCESSING); });
on('transcript_delta', layers.transcriptDelta);
on('transcript_close', (p) => { layers.transcriptClose(p); settle(); });

on('speak', ({ text }) => voice.say(text));
on('voice', ({ url }) => voice.playAudio(url));
on('state', ({ thinking }) => {
  const m = store.get().mode;
  if (thinking && (m === STATES.IDLE || m === STATES.LISTENING)) store.setMode(STATES.PROCESSING);
});
on('vision', (v) => visionState(Boolean(v && v.present)));

on('__closed', () => layers.ambient('Connection dropped. Reconnecting…', 'J.A.N.E.'));
on('__open', () => { if (uptime !== 0) layers.ambient('Back on the line.', 'J.A.N.E.'); });

connect();
bootstrap();

// ===== microphone ===========================================================
async function micOn() {
  if (!canListen) { $('#type-row').classList.add('on'); $('#type-input').focus(); return; }
  voice.start();
  if (!micStream) {
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      wave.attach(micStream);
    } catch {
      layers.notice('No microphone access, so the waveform stays asleep.');
    }
  }
}

function micOff() {
  voice.stop();
  wave.detach();
  if (micStream) {
    for (const track of micStream.getTracks()) track.stop();
    micStream = null;
  }
}

$('#mic-toggle').addEventListener('click', () => (voice.wantListening ? micOff() : micOn()));

// ===== the deck: open one widget, send it to centre; the rest recede =======
const deck = $('#deck');

// FLIP — note where the tile sits now, move it to its new place, then animate
// the difference away. The phone-like "zoom to centre" without any library.
function flip(tile, mutate) {
  const first = tile.getBoundingClientRect();
  tile.style.transition = 'none';
  tile.style.transform = '';
  mutate();
  const last = tile.getBoundingClientRect();
  const dx = first.left - last.left, dy = first.top - last.top;
  const sx = (first.width / last.width) || 1, sy = (first.height / last.height) || 1;
  tile.style.transformOrigin = 'top left';
  tile.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
  requestAnimationFrame(() => {
    tile.style.transition = 'transform var(--med) var(--ease)';
    tile.style.transform = '';
  });
}

function openWidget(name) {
  const tile = deck?.querySelector(`.tile[data-widget="${name}"]`);
  if (!tile || opened === name) return;
  if (opened) {                       // swapping widgets — drop the old one flat
    const prev = deck.querySelector('.tile.is-open');
    if (prev) { prev.classList.remove('is-open'); prev.style.transition = ''; prev.style.transform = ''; }
  }
  opened = name;
  app.dataset.open = name;
  flip(tile, () => tile.classList.add('is-open'));
}

function closeWidget() {
  if (!opened) return;
  const tile = deck.querySelector('.tile.is-open');
  opened = null;
  app.removeAttribute('data-open');
  if (tile) flip(tile, () => tile.classList.remove('is-open'));
}

// Tap a resting tile to open it; tap the open tile's header (or the dimmed
// backdrop) to send it home. Clicks on links/inputs inside a tile pass through.
deck?.addEventListener('click', (e) => {
  const tile = e.target.closest('.tile');
  if (!tile) return;
  if (tile.classList.contains('is-open')) {
    if (e.target.closest('.tile-head')) closeWidget();
    return;
  }
  if (e.target.closest('a, input, button')) return;
  openWidget(tile.dataset.widget);
});
deck?.addEventListener('keydown', (e) => {
  const tile = e.target.closest?.('.tile');
  if (tile && !tile.classList.contains('is-open') && e.key === 'Enter') {
    e.preventDefault();
    openWidget(tile.dataset.widget);
  }
});
$('#scrim')?.addEventListener('click', closeWidget);
$('#sys')?.addEventListener('click', () => openWidget('system'));

// ===== keyboard =============================================================
const typing = (e) => e.target instanceof HTMLInputElement;

addEventListener('keydown', (e) => {
  if (e.code === 'Space' && !typing(e)) {
    e.preventDefault();
    voice.wantListening ? micOff() : micOn();
  } else if (/^[1-8]$/.test(e.key) && !typing(e)) {
    e.preventDefault();
    const tiles = deck?.querySelectorAll('.tile');
    const t = tiles?.[Number(e.key) - 1];
    if (t) (opened === t.dataset.widget ? closeWidget() : openWidget(t.dataset.widget));
  } else if (e.key === '/' && !typing(e)) {
    e.preventDefault();
    $('#type-row').classList.add('on');
    $('#type-input').focus();
  } else if (e.key === 'Escape') {
    if ($('#type-row').classList.contains('on') && canListen) {
      $('#type-row').classList.remove('on');
      $('#type-input').blur();
    } else if (opened) {
      closeWidget();
    } else {
      voice.hush();
      clearTimeout(trackTimer);
      store.setTarget(null);
      store.setContext(null);
      store.setFocus(false);
      const st = $('#tgt-status'); if (st) st.textContent = 'STANDBY';
      settle();
    }
  }
});

// ===== typed input ==========================================================
$('#type-input').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  const text = e.target.value.trim();
  if (!text) return;
  e.target.value = '';
  layers.ambient(text, 'YOU');
  handleUtterance(text);
  api.say(text).catch(() => layers.notice('Jane is not answering the door.'));
});

$('#ledger-add').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  const text = e.target.value.trim();
  if (!text) return;
  e.target.value = '';
  api.ledger('add', { text }).catch(() => layers.notice('Could not write to the ledger.'));
});

// ===== camera (optical presence) ============================================
function visionState(present) {
  if (present) {
    store.setMode(STATES.ALERT);
    core.ping();
  } else if (store.get().mode === STATES.ALERT) {
    settle();
  }
}

let cameraOn = false;
$('#rj-frame').addEventListener('click', async () => {
  if (cameraOn) {
    stopVision((present) => visionState(present));
    cameraOn = false;
    return;
  }
  cameraOn = await startVision((present) => {
    visionState(present);
    api.vision({ present }).catch(() => {});
  });
});

// ===== clock ================================================================
let day = new Date().getDate();
setInterval(() => {
  const now = new Date();
  $('#clock').textContent = now.toLocaleTimeString('en-GB', { hour12: false });
  uptime++;
  if (now.getDate() !== day) { day = now.getDate(); layers.calendar(now); }
}, 1000);

if (!canSpeak) layers.notice('This browser has no speech synthesis — Jane will type, not talk.');
