// Every contextual layer's renderer. Given data, paint DOM — no layer decides
// on its own whether it is visible; app.js reveals and retracts them by state.
// This keeps all the original functionality (telemetry, encryption, network,
// weather, headlines, ledger, calendar, transcript, log) alive while letting
// the interface show only what the moment calls for.

import { Spark } from './spark.js';
import { api } from './bus.js';

const $ = (sel) => document.querySelector(sel);

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

const stamp = () => new Date().toLocaleTimeString('en-GB', { hour12: false });

// ===== SYSTEM (top-right indicator + hover detail) =========================
const ROWS = [
  { key: 'cpu',  label: 'CPU',  max: 100 },
  { key: 'mem',  label: 'MEM',  max: 100 },
  { key: 'gpu',  label: 'GPU',  max: 100 },
  { key: 'net',  label: 'NET',  auto: true },
  { key: 'disk', label: 'DISK', max: 100 },
];
const sparks = new Map();

export function mountSystem() {
  const host = $('#sys-detail-rows');
  host.textContent = '';
  for (const row of ROWS) {
    const line = el('div', 'metric');
    line.append(el('span', 'metric-k', row.label), el('span', 'metric-v', '—'));
    const canvas = el('canvas', 'metric-spark');
    line.append(canvas);
    host.append(line);
    const spark = new Spark(canvas, { max: row.max || 100, color: '#6a6a6a' });
    if (row.auto) spark.autoRange = true;
    sparks.set(row.key, { spark, value: line.children[1] });
  }
}

export function system(telemetry) {
  let worst = 0;
  for (const row of ROWS) {
    const slot = sparks.get(row.key);
    if (!slot) continue;
    const raw = telemetry[row.key];
    if (raw === null || raw === undefined) { slot.value.textContent = 'N/A'; continue; }
    slot.value.textContent = row.key === 'net' ? telemetry.net_label : `${Math.round(raw)}%`;
    slot.spark.push(raw);
    if (row.key !== 'net' && raw > worst) worst = raw;
  }
  // Drive the persistent health dot from the worst core metric.
  const dot = $('#sys-dot');
  const label = $('#sys-word');
  if (!dot) return;
  let word = 'NOMINAL', cls = '';
  if (worst >= 92) { word = 'CRITICAL'; cls = 'crit'; }
  else if (worst >= 75) { word = 'ELEVATED'; cls = 'warn'; }
  dot.className = `dot ${cls}`;
  label.textContent = word;
}

export function encryption(state) {
  if (!state) return;
  $('#sys-enc').textContent = state.signal === 'SECURE'
    ? `LINK SECURE · ${state.level}` : 'LINK OFFLINE · LOCAL ONLY';
  $('#sys-enc').classList.toggle('secure', state.signal === 'SECURE');
}

// ===== NETWORK (folded into the system detail layer) =======================
const net = { rounds: [], ctx: null, w: 0, h: 0 };
const NET_ROUNDS = 4;
const DOT_PITCH = 13;

export function mountNetmap() {
  const canvas = $('#sys-netmap');
  if (!canvas) return;
  net.ctx = canvas.getContext('2d');
  const size = () => {
    const dpr = devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    net.w = Math.max(rect.width, 160);
    net.h = Math.max(rect.height, 40);
    canvas.width = net.w * dpr;
    canvas.height = net.h * dpr;
    net.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawNet();
  };
  addEventListener('resize', size);
  size();
}

export function netmap(nodes) {
  if (!nodes || !nodes.length) return;
  net.rounds.push(nodes);
  if (net.rounds.length > NET_ROUNDS) net.rounds.shift();
  drawNet();
  const host = $('#sys-net-labels');
  if (!host) return;
  host.textContent = '';
  for (const node of nodes) {
    const cell = el('span', null, node.name);
    cell.append(el('b', null, node.ms === null ? 'NO LINK' : `${Math.round(node.ms)}`));
    cell.title = node.host || '';
    host.append(cell);
  }
}

function drawNet() {
  const { ctx, w, h, rounds } = net;
  if (!ctx) return;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#1c1c1c';
  for (let y = DOT_PITCH / 2; y < h; y += DOT_PITCH)
    for (let x = DOT_PITCH / 2; x < w; x += DOT_PITCH)
      ctx.fillRect(Math.round(x), Math.round(y), 1, 1);
  if (!rounds.length) return;
  const worst = Math.max(400, ...rounds.flat().map((n) => n.ms || 0));
  const pad = 11;
  const count = rounds[0].length;
  const step = count > 1 ? (w - pad * 2) / (count - 1) : 0;
  rounds.forEach((round, r) => {
    const age = rounds.length - 1 - r;
    const shade = [0.6, 0.3, 0.18, 0.1][age] ?? 0.08;
    const pts = round.map((n, i) => {
      const norm = n.ms === null ? 1 : Math.min(1, n.ms / worst);
      return { x: pad + i * step, y: pad + norm * (h - pad * 2), live: n.ms !== null };
    });
    ctx.strokeStyle = `rgba(185,185,185,${shade})`;
    ctx.lineWidth = age === 0 ? 1 : 0.9;
    ctx.beginPath();
    pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.stroke();
    for (const p of pts) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, age === 0 ? 2.3 : 1.7, 0, Math.PI * 2);
      if (p.live) { ctx.fillStyle = `rgba(200,200,200,${shade + 0.16})`; ctx.fill(); }
      else { ctx.strokeStyle = `rgba(216,26,26,${shade + 0.25})`; ctx.lineWidth = 1; ctx.stroke(); }
    }
  });
}

// ===== ENVIRONMENT (contextual) ============================================
export function environment(w) {
  if (!w) return;
  $('#ctx-env-city').textContent = w.city || '—';
  if (!w.ok) {
    $('#ctx-env-temp').textContent = '—';
    $('#ctx-env-cond').textContent = 'NO READING';
    $('#ctx-env-detail').textContent = '';
    return;
  }
  $('#ctx-env-temp').textContent = `${w.temp}°`;
  $('#ctx-env-cond').textContent = w.condition;
  const bits = [
    `${w.humidity}% HUMIDITY`,
    `${w.wind} KM/H WIND`,
    w.visibility == null ? null : `${w.visibility} KM VIS`,
    `${w.pressure} HPA`,
  ].filter(Boolean);
  $('#ctx-env-detail').textContent = bits.join('   ');
}

// ===== RELATED INTELLIGENCE (headlines, contextual) ========================
export function headlines(items) {
  const host = $('#ctx-intel-list');
  if (!host) return;
  host.textContent = '';
  if (!items || !items.length) {
    host.append(el('div', 'muted', 'The wire is quiet.'));
    return;
  }
  items.slice(0, 5).forEach((item, i) => {
    const row = el('div', 'intel-item');
    row.append(el('span', 'intel-n', String(i + 1).padStart(2, '0')));
    const body = el('div', 'intel-body');
    const link = el('a', null, item.title);
    link.href = item.link || '#';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    body.append(link);
    if (item.source) body.append(el('span', 'intel-src', item.source));
    row.append(body);
    host.append(row);
  });
}

// ===== LEDGER (minimal task layer) =========================================
export function ledger(items) {
  const host = $('#ledger-list');
  if (!host) return;
  host.textContent = '';
  if (!items || !items.length) {
    host.append(el('div', 'muted', 'Nothing on the board.'));
    return;
  }
  items.forEach((item, i) => {
    const row = el('div', 'ledger-item');
    if (item.done) row.classList.add('done');
    row.append(el('span', 'ledger-n', String(i + 1).padStart(2, '0')));
    row.append(el('span', 'ledger-txt', item.text));
    row.title = item.done ? 'Reopen' : 'Close out';
    row.addEventListener('click', () => {
      api.ledger('toggle', { item: item.id, done: !item.done }).catch(() => {});
    });
    host.append(row);
  });
}

// ===== CASE CALENDAR (contextual) ==========================================
const DOW = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY',
                'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];

export function calendar(now = new Date()) {
  const title = $('#cal-title');
  const host = $('#cal-grid');
  if (!host) return;
  title.textContent = `${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
  host.textContent = '';
  for (const d of DOW) host.append(el('span', 'cal-dow', d));
  const first = new Date(now.getFullYear(), now.getMonth(), 1).getDay();
  const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const prevDays = new Date(now.getFullYear(), now.getMonth(), 0).getDate();
  for (let i = first - 1; i >= 0; i--) host.append(el('span', 'cal-day out', prevDays - i));
  for (let d = 1; d <= days; d++) {
    const cell = el('span', 'cal-day', d);
    if (d === now.getDate()) cell.classList.add('today');
    host.append(cell);
  }
  const tail = (7 - ((first + days) % 7)) % 7;
  for (let d = 1; d <= tail; d++) host.append(el('span', 'cal-day out', d));
}

// ===== TARGET METADATA (investigation mode) ================================
export function target(t) {
  if (!t) return;
  $('#tgt-name').textContent = t.name;
  $('#tgt-place').textContent = t.place;
  $('#tgt-coords').textContent = `${t.lat}   ${t.lon}`;
  $('#tgt-confidence').textContent = `${t.confidence.toFixed(1)}%`;
  $('#tgt-since').textContent = t.since || stamp();
}

// ===== TRANSCRIPT ==========================================================
// Jane's latest line lives at centre-stage (ambient communication). The full
// exchange is kept in a secondary layer that only opens when asked for.
const TURN_MAX = 60;
let open = null;          // the turn Jane is streaming into (full layer)
let liveJane = null;      // the ambient line node being streamed

function fullTurn(who, text) {
  const host = $('#transcript-log');
  if (!host) return null;
  const turn = el('div', 'tr-turn');
  turn.dataset.who = who;
  turn.append(el('span', 'tr-who', who), el('span', 'tr-txt', text || ''));
  host.append(turn);
  while (host.children.length > TURN_MAX) host.firstChild.remove();
  host.scrollTop = host.scrollHeight;
  return turn;
}

/** Set the ambient centre-stage line beneath the core. */
export function ambient(text, who = 'JANE') {
  const line = $('#jane-line');
  const label = $('#jane-line-who');
  if (!line) return;
  label.textContent = who;
  line.textContent = text;
  line.classList.remove('streaming');
}

export function turn({ who, text }) {
  if (who === 'JANE' && open) return;   // Jane's turn is streamed, not dropped whole
  fullTurn(who, text);
  if (who === 'USER') ambient(text, 'YOU');
}

export function transcriptOpen() {
  open = fullTurn('JANE', '');
  if (open) open.classList.add('pending');
  const line = $('#jane-line');
  const label = $('#jane-line-who');
  if (line) { label.textContent = 'J.A.N.E.'; line.textContent = ''; line.classList.add('streaming'); }
  liveJane = line;
}

export function transcriptDelta({ text }) {
  if (open) {
    open.lastChild.textContent += text;
    const host = $('#transcript-log');
    if (host) host.scrollTop = host.scrollHeight;
  }
  if (liveJane) liveJane.textContent += text;
}

export function transcriptClose({ text }) {
  if (open) {
    if (text) open.lastChild.textContent = text;
    open.classList.remove('pending');
    open = null;
  }
  if (liveJane) { if (text) liveJane.textContent = text; liveJane.classList.remove('streaming'); }
  liveJane = null;
}

// ===== SYSTEM LOG (secondary layer) ========================================
const LOG_MAX = 160;

export function logLine(line) {
  const host = $('#log-list');
  if (!host) return;
  const node = el('div', 'log-line');
  node.dataset.level = line.level || 'info';
  node.append(el('span', 'log-t', line.t), el('span', 'log-m', line.msg));
  host.append(node);
  while (host.children.length > LOG_MAX) host.firstChild.remove();
  host.scrollTop = host.scrollHeight;
}

export function logAll(lines) {
  const host = $('#log-list');
  if (!host) return;
  host.textContent = '';
  for (const line of lines || []) logLine(line);
}

// ===== small shared bits ===================================================
export function stateLabel(text) {
  const node = $('#state-word');
  if (node) node.textContent = text;
}

export function notice(message, ms = 4200) {
  const box = $('#notice');
  if (!box) return;
  box.textContent = message;
  box.classList.add('on');
  clearTimeout(notice._t);
  notice._t = setTimeout(() => box.classList.remove('on'), ms);
}
