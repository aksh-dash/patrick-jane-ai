// The one place that knows what J.A.N.E. is doing right now.
//
// Everything visual reads from here; nothing visual owns state of its own. The
// interface is adaptive, so a single honest state value — plus the last-known
// data snapshots — is enough for every layer to decide whether it belongs on
// screen this instant.

// The lifecycle Jane moves through. Order matters only as documentation.
export const STATES = Object.freeze({
  IDLE: 'idle',            // calm. almost nothing on screen.
  LISTENING: 'listening',  // microphone live, waveform awake.
  PROCESSING: 'processing',// utterance received, thinking.
  SEARCHING: 'searching',  // an investigation is underway — the core scans.
  TRACKING: 'tracking',    // a subject is locked; the core holds it.
  ALERT: 'alert',          // presence / anomaly — the one time red leads.
});

const state = {
  mode: STATES.IDLE,
  focus: false,            // focus mode: unrelated layers fade fully away.
  context: null,           // which context a request pulled up: 'subject' | 'environment' | 'schedule' | 'intel' | 'ledger' | 'system' | null
  target: null,            // { name, place, lat, lon, confidence, since }
  micLive: false,
  // Last-known data, filled by bootstrap then kept fresh over the stream.
  data: {
    model: '—', version: '—', city: '—', hasKey: false,
    telemetry: {}, weather: null, news: [], ledger: [], netmap: [],
    encryption: null, log: [],
  },
};

const subs = new Set();

/** Subscribe to any change. Returns an unsubscribe fn. */
export function subscribe(fn) {
  subs.add(fn);
  return () => subs.delete(fn);
}

function notify(kind) {
  for (const fn of subs) {
    try { fn(state, kind); } catch (e) { console.error('store subscriber', e); }
  }
}

export function get() { return state; }

/** Move to a new lifecycle state. No-op if already there. */
export function setMode(mode) {
  if (state.mode === mode) return;
  state.mode = mode;
  notify('mode');
}

export function setMic(live) {
  if (state.micLive === live) return;
  state.micLive = live;
  notify('mic');
}

/** Pull a context layer into view (or clear it with null). */
export function setContext(context) {
  if (state.context === context) return;
  state.context = context;
  notify('context');
}

export function setFocus(on) {
  if (state.focus === on) return;
  state.focus = on;
  notify('focus');
}

export function setTarget(target) {
  state.target = target;
  notify('target');
}

/** Merge fresh data in and tell everyone which slice changed. */
export function patch(slice, value) {
  state.data[slice] = value;
  notify(`data:${slice}`);
}

export function seed(bootstrap) {
  const d = state.data;
  d.model = bootstrap.model || '—';
  d.version = bootstrap.version || '—';
  d.city = bootstrap.city || '—';
  d.hasKey = Boolean(bootstrap.has_key);
  d.telemetry = bootstrap.telemetry || {};
  d.weather = bootstrap.weather || null;
  d.news = bootstrap.news || [];
  d.ledger = bootstrap.ledger || [];
  d.netmap = bootstrap.netmap || [];
  d.encryption = bootstrap.encryption || null;
  d.log = bootstrap.log || [];
  notify('seed');
}
