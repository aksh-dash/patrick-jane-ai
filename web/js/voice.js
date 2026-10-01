// Ears and mouth. Web Speech API — works in Chrome and Edge; elsewhere the
// typed input in the footer is the fallback (see app.js).

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
export const canListen = Boolean(SR);
export const canSpeak = 'speechSynthesis' in window;

// Preference order for Jane's voice: a relaxed male English voice.
const VOICE_HINTS = [
  'Google UK English Male', 'Microsoft Ryan', 'Microsoft Guy', 'Microsoft George',
  'Microsoft David', 'Microsoft Mark', 'Daniel', 'Alex', 'Google US English',
];

export class Voice {
  constructor({ onFinal, onInterim, onStateChange, onError, onSpeaking }) {
    this.onFinal = onFinal;
    this.onInterim = onInterim;
    this.onStateChange = onStateChange || (() => {});
    this.onError = onError || (() => {});
    this.onSpeaking = onSpeaking || (() => {});
    this.listening = false;
    this.wantListening = false;
    this.muted = false;          // true while Jane is talking
    this.speakingNow = false;
    this.queue = [];
    this.voice = null;
    this.rec = null;
    this.spoken = [];            // {text, at} of what Jane recently said aloud
    this.audioQueue = [];        // URLs of server-synthesised speech, played in order
    this.audioEl = null;         // the single <audio> element that plays them
    this.audioPlaying = false;
    if (canSpeak) this.pickVoice();
  }

  // --- voice selection --------------------------------------------------
  pickVoice() {
    const choose = () => {
      const voices = speechSynthesis.getVoices();
      if (!voices.length) return;
      for (const hint of VOICE_HINTS) {
        const hit = voices.find((v) => v.name.includes(hint));
        if (hit) { this.voice = hit; return; }
      }
      this.voice = voices.find((v) => v.lang.startsWith('en')) || voices[0];
    };
    choose();
    speechSynthesis.addEventListener('voiceschanged', choose);
  }

  // --- listening --------------------------------------------------------
  start() {
    if (!canListen) { this.onError('This browser has no speech recognition. Use Chrome or Edge, or type instead.'); return; }
    this.wantListening = true;
    this.spin();
  }

  stop() {
    this.wantListening = false;
    if (this.rec) { try { this.rec.stop(); } catch { /* already stopped */ } }
    this.listening = false;
    this.onStateChange(false);
  }

  toggle() { this.wantListening ? this.stop() : this.start(); }

  /** Create a recognizer and keep it alive for as long as we want to listen. */
  spin() {
    if (!this.wantListening || this.listening) return;
    const rec = new SR();
    this.rec = rec;
    rec.lang = 'en-IN';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => { this.listening = true; this.onStateChange(true); };

    rec.onresult = (e) => {
      // Anything heard while Jane is talking is Jane, not the user.
      if (this.muted) return;
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i];
        const text = result[0].transcript.trim();
        if (!text) continue;
        if (result.isFinal) {
          const clean = strip(text);
          // Drop it if it's an echo of something Jane just said aloud.
          if (this.echoedByJane(clean)) continue;
          this.onFinal(clean);
        } else {
          interim += `${text} `;
        }
      }
      if (interim) this.onInterim(interim.trim());
    };

    rec.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return;   // routine
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        this.wantListening = false;
        this.onError('Microphone blocked. Allow it in the address bar, then try again.');
      } else {
        this.onError(`Microphone: ${e.error}`);
      }
    };

    // Chrome ends the session on its own every so often; restart if still wanted.
    rec.onend = () => {
      this.listening = false;
      this.onStateChange(false);
      if (this.wantListening) setTimeout(() => this.spin(), 260);
    };

    try { rec.start(); } catch { /* a stale instance is still winding down */ }
  }

  // --- speaking ---------------------------------------------------------
  /** True if heard text matches a sentence Jane spoke in the last few seconds. */
  echoedByJane(heard) {
    const now = Date.now();
    this.spoken = this.spoken.filter((s) => now - s.at < 6000);
    const h = norm(heard);
    if (!h) return false;
    return this.spoken.some((s) => s.text.includes(h) || h.includes(s.text));
  }

  /** Queue one sentence. Sentences arrive from the server as Jane writes them. */
  say(text) {
    const clean = speakable(text);
    if (!clean || !canSpeak) return;
    const n = norm(clean);
    if (n) this.spoken.push({ text: n, at: Date.now() });
    this.queue.push(clean);
    this.drain();
  }

  drain() {
    if (!this.queue.length || this.speakingNow) return;
    const text = this.queue.shift();
    const u = new SpeechSynthesisUtterance(text);
    if (this.voice) { u.voice = this.voice; u.lang = this.voice.lang; }
    u.rate = 0.99;      // unhurried — he is never in a rush
    u.pitch = 0.92;
    u.volume = 1;

    this.speakingNow = true;
    this.muted = true;
    this.onSpeaking(true);

    // Chrome silently pauses long utterances after ~15s; a gentle nudge keeps
    // it talking. Cleared the moment this utterance ends.
    const keepAlive = setInterval(() => {
      if (this.speakingNow) speechSynthesis.resume();
    }, 8000);

    const done = () => {
      clearInterval(keepAlive);
      this.speakingNow = false;
      if (this.queue.length) { this.drain(); return; }
      this.onSpeaking(false);
      // Let the room go quiet before trusting the microphone again — long
      // enough that the tail of Jane's own voice doesn't get re-heard.
      setTimeout(() => { if (!this.speakingNow) this.muted = false; }, 500);
    };
    u.onend = done;
    u.onerror = done;
    speechSynthesis.speak(u);
  }

  /** Cut Jane off mid-sentence. */
  hush() {
    this.queue.length = 0;
    this.audioQueue.length = 0;
    if (this.audioEl) { try { this.audioEl.pause(); } catch { /* nothing playing */ } }
    this.audioPlaying = false;
    if (canSpeak) speechSynthesis.cancel();
    this.speakingNow = false;
    this.muted = false;
    this.onSpeaking(false);
  }

  // --- neural voice (server-synthesised audio) --------------------------
  /** Play one server-generated speech clip. Queued so clips never overlap. */
  playAudio(url) {
    if (!url) return;
    this.audioQueue.push(url);
    this.drainAudio();
  }

  drainAudio() {
    if (this.audioPlaying || !this.audioQueue.length) return;
    const url = this.audioQueue.shift();
    if (!this.audioEl) this.audioEl = new Audio();
    const el = this.audioEl;

    this.audioPlaying = true;
    this.muted = true;              // anything the mic hears now is Jane
    this.onSpeaking(true);

    const done = () => {
      this.audioPlaying = false;
      if (this.audioQueue.length) { this.drainAudio(); return; }
      this.onSpeaking(false);
      // Let the tail of Jane's own voice die before trusting the mic again.
      setTimeout(() => { if (!this.audioPlaying) this.muted = false; }, 450);
    };
    el.onended = done;
    el.onerror = done;
    el.src = url;
    const p = el.play();
    if (p && p.catch) p.catch(() => done());   // autoplay blocked → don't hang
  }
}

// Drop the wake word if the user used one — "Jane, what's the weather" works too.
function strip(text) {
  return text.replace(/^(hey\s+|ok\s+)?jane[,.\s]+/i, '').trim() || text;
}

// Normalise for echo comparison: lowercase, strip punctuation, collapse spaces.
function norm(text) {
  return String(text || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
}

// Screen readers of the world: the model is told not to emit markdown, but if a
// stray asterisk or bullet slips through, don't read it aloud.
function speakable(text) {
  return String(text || '')
    .replace(/[*_`#>]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

