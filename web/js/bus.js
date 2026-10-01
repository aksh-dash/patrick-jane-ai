// SSE channel + the small REST surface. Auto-reconnects if the server restarts.

const handlers = new Map();
let source = null;
let retry = 0;

export function on(event, fn) {
  if (!handlers.has(event)) handlers.set(event, new Set());
  handlers.get(event).add(fn);
  if (source) attach(event);
}

function emit(event, data) {
  const set = handlers.get(event);
  if (set) for (const fn of set) { try { fn(data); } catch (e) { console.error(event, e); } }
}

const attached = new Set();
function attach(event) {
  if (attached.has(event) || !source) return;
  attached.add(event);
  source.addEventListener(event, (e) => {
    let data = null;
    try { data = JSON.parse(e.data); } catch { data = e.data; }
    emit(event, data);
  });
}

export function connect() {
  source = new EventSource('/api/stream');
  attached.clear();
  for (const event of handlers.keys()) attach(event);

  source.onopen = () => { retry = 0; emit('__open', true); };
  source.onerror = () => {
    emit('__closed', true);
    source.close();
    retry = Math.min(retry + 1, 6);
    setTimeout(connect, 500 * retry);   // back off, then try again
  };
}

async function post(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export const api = {
  bootstrap: () => fetch('/api/bootstrap').then((r) => r.json()),
  say: (text) => post('/api/say', { text }),
  reset: () => post('/api/reset'),
  vision: (state) => post('/api/vision', state),
  ledger: (action, payload) => post('/api/ledger', { action, ...payload }),
};
