// Reads a single utterance and decides what J.A.N.E. should bring forward.
//
// This is deliberately shallow — a keyword read, not language understanding.
// The real answer still comes from the model over the stream; this only decides
// which context layer to materialise while she thinks, so the interface feels
// like it is responding to *this* request rather than showing everything.

const SUBJECT = /\b(red\s*john|track|tracking|subject|target|suspect|locate|find him|where is)\b/i;
const ENVIRONMENT = /\b(weather|temperature|temp|forecast|humidity|wind|rain|environment|climate|hot|cold outside)\b/i;
const SCHEDULE = /\b(schedule|calendar|date|today|appointment|timeline|deadline|meeting|what day|case timeline)\b/i;
const INTEL = /\b(news|headline|headlines|intelligence|happening|reports?|press|wire|story|stories)\b/i;
const LEDGER = /\b(ledger|task|tasks|to-?do|to do|checklist|board|open items?|what.s left)\b/i;
const SYSTEM = /\b(system|status|cpu|memory|ram|gpu|disk|network|load|diagnostics?|health|performance)\b/i;

// A known subject the demo can lock onto. Real coordinates for Pune so the
// numbers on screen aren't invented.
const SUBJECTS = {
  'red john': {
    name: 'RED JOHN',
    place: 'PUNE · INDIA',
    lat: '18.5204° N',
    lon: '73.8567° E',
    confidence: 87.4,
  },
};

/**
 * @returns {{ context: string|null, investigation: boolean, subject: object|null }}
 */
export function classify(text) {
  const t = String(text || '').toLowerCase();

  if (SUBJECT.test(t)) {
    let subject = null;
    for (const [key, value] of Object.entries(SUBJECTS)) {
      if (t.includes(key)) { subject = value; break; }
    }
    return { context: 'subject', investigation: true, subject };
  }
  if (SCHEDULE.test(t)) return { context: 'schedule', investigation: false, subject: null };
  if (ENVIRONMENT.test(t)) return { context: 'environment', investigation: false, subject: null };
  if (INTEL.test(t)) return { context: 'intel', investigation: false, subject: null };
  if (LEDGER.test(t)) return { context: 'ledger', investigation: false, subject: null };
  if (SYSTEM.test(t)) return { context: 'system', investigation: false, subject: null };

  // No strong signal — Jane simply answers, no layer materialises.
  return { context: null, investigation: false, subject: null };
}
