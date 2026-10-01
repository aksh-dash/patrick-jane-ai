// The on-screen Patrick Jane — a small pixel companion that lives at the edge of
// the screen and mirrors what J.A.N.E. is doing. It owns no truth: app.js pushes
// state in (setState/setMic/setSpeaking/run/say) and this only decides which pose
// to show and where he stands. Nothing critical is conveyed by motion alone — the
// same information rides the speech bubble and a visually-hidden live region — and
// all movement is dropped under prefers-reduced-motion.

// One shared sprite sheet, sliced into poses. Rects were measured off the sheet
// (1536×1024, 6×2 grid) as tight bounding boxes, so each pose can be bottom-anchored
// to a common floor line regardless of its own height.
const SHEET = 'img/jane-sheet.png';
const FRAMES = {
  idle:    { x: 40,   y: 25,  w: 182, h: 487 },
  left:    { x: 318,  y: 25,  w: 104, h: 487 },
  right:   { x: 551,  y: 25,  w: 217, h: 487 },
  run:     { x: 768,  y: 66,  w: 241, h: 418 },
  think:   { x: 1072, y: 28,  w: 208, h: 484 },
  present: { x: 1280, y: 33,  w: 233, h: 479 },
  smile:   { x: 45,   y: 512, w: 178, h: 495 },
  write:   { x: 288,  y: 512, w: 161, h: 494 },
  point:   { x: 523,  y: 512, w: 244, h: 495 },
  turn:    { x: 808,  y: 552, w: 177, h: 455 },
  back:    { x: 1068, y: 512, w: 166, h: 495 },
  walk:    { x: 1309, y: 512, w: 176, h: 485 },
};

const REF_H = 495;   // tallest pose; every pose scales against this so feet align.
const CH = 150;      // displayed character height in CSS px for a full-height pose.
const SCALE = CH / REF_H;
const PX = 3;        // pixel-block size — the illustration is down- then up-sampled.
const FLOOR = 46;    // px of the character the sofa/floor overlaps (reads as "on it").

// A little in-character line for the right-click delight and the doze.
const QUIPS = [
  "There's no such thing as psychic. I just pay attention.",
  'Tell me what you see, and I will tell you what happened.',
  'A guilty conscience is a loud one.',
  'People are predictable. That is the whole trick.',
  'I already know. I am just waiting for you to catch up.',
];

const rand = (a, b) => a + Math.random() * (b - a);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

export class Companion {
  constructor(opts = {}) {
    this.onToggleMic = opts.onToggleMic || (() => {});
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

    this.mode = 'idle';
    this.mic = false;
    this.speaking = false;
    this.pose = 'smile';
    this.transient = null;        // { pose, until } — a short-lived override (e.g. run)
    this.facing = 1;              // 1 = shown right-facing, -1 = left-facing
    this.idleMs = 0;
    this.bubbleUntil = 0;
    this.dragging = false;

    // World position (CSS px from the left edge). Home is the sofa.
    this.home = 24;
    this.x = this.home;
    this.targetX = this.home;
    this.roam = null;             // 'pace' | 'home' | null
    this.seated = true;
    this.bob = 0;

    this._build();
    this._loadSheet();
    this._bind();
    this.last = performance.now();
    requestAnimationFrame((t) => this._loop(t));
  }

  _build() {
    const root = document.createElement('div');
    root.id = 'jane-pet';
    root.setAttribute('role', 'button');
    root.setAttribute('tabindex', '0');
    root.setAttribute('aria-pressed', 'false');
    root.setAttribute('aria-label', 'Patrick Jane — activate to toggle the microphone');

    const sofa = document.createElement('div');
    sofa.id = 'jane-sofa';
    sofa.setAttribute('aria-hidden', 'true');
    const sofaBack = document.createElement('div');
    sofaBack.id = 'jane-sofa-back';
    sofaBack.setAttribute('aria-hidden', 'true');

    const bubble = document.createElement('div');
    bubble.id = 'jane-bubble';
    bubble.setAttribute('aria-hidden', 'true');

    const canvas = document.createElement('canvas');
    canvas.id = 'jane-canvas';
    canvas.setAttribute('aria-hidden', 'true');

    const live = document.createElement('div');
    live.id = 'jane-live';
    live.className = 'sr-only';
    live.setAttribute('aria-live', 'polite');

    root.append(canvas, bubble);
    document.body.append(sofaBack, sofa, root, live);

    this.root = root;
    this.sofa = sofa;
    this.bubble = bubble;
    this.canvas = canvas;
    this.live = live;

    // Backing store sized for the widest/tallest pose, DPR-aware.
    this.dpr = Math.min(devicePixelRatio || 1, 2);
    this.cw = 100;
    this.chpx = CH + 8;
    canvas.style.width = `${this.cw}px`;
    canvas.style.height = `${this.chpx}px`;
    canvas.width = Math.round(this.cw * this.dpr);
    canvas.height = Math.round(this.chpx * this.dpr);
    this.ctx = canvas.getContext('2d');

    // Offscreen buffer for the down-then-up pixelation pass.
    this.buf = document.createElement('canvas');
    this.bctx = this.buf.getContext('2d');
  }
  // PLACEHOLDER_SHEET
  _loadSheet() {
    this.sheet = new Image();
    this.sheet.onload = () => { this.ready = true; };
    this.sheet.onerror = () => { this.ready = false; };
    this.sheet.src = SHEET;
  }

  _bind() {
    const toggle = (e) => { e.preventDefault(); this.wake(); this.onToggleMic(); };
    this.root.addEventListener('click', toggle);
    this.root.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.code === 'Space') toggle(e);
    });
    // Right-click / long-press → a quip, no menu.
    this.root.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      this.say(QUIPS[Math.floor(Math.random() * QUIPS.length)], 4200);
    });
    this._bindDrag();
    addEventListener('mousemove', (e) => { this._pointer = e.clientX; }, { passive: true });
  }

  // Drag him anywhere along the floor; double-click sends him home to the sofa.
  _bindDrag() {
    let sx = 0, ox = 0, moved = false;
    const down = (e) => {
      const p = e.touches ? e.touches[0] : e;
      this.dragging = true; moved = false; sx = p.clientX; ox = this.x;
      this.root.classList.add('grab');
    };
    const move = (e) => {
      if (!this.dragging) return;
      const p = e.touches ? e.touches[0] : e;
      const nx = ox + (p.clientX - sx);
      if (Math.abs(p.clientX - sx) > 3) moved = true;
      this.x = clamp(nx, 0, innerWidth - this.cw);
      this.targetX = this.x; this.roam = null;
    };
    const up = () => {
      if (!this.dragging) return;
      this.dragging = false; this.root.classList.remove('grab');
      if (moved) { this.idleMs = 0; }        // a drag counts as attention
    };
    this.root.addEventListener('mousedown', down);
    addEventListener('mousemove', move);
    addEventListener('mouseup', up);
    this.root.addEventListener('touchstart', down, { passive: true });
    addEventListener('touchmove', move, { passive: true });
    addEventListener('touchend', up);
    this.root.addEventListener('dblclick', () => this.goHome());
  }
  // PLACEHOLDER_API
  // ===== public API (app.js drives these) ==================================
  setState(mode) {
    if (mode === this.mode) return;
    this.mode = mode;
    if (mode !== 'idle') { this.idleMs = 0; this.roam = null; }
    this._announce(this._statusLine());
    const hint = this._hint();
    if (hint) this.say(hint, 2600);
  }

  setMic(live) {
    this.mic = live;
    this.root.setAttribute('aria-pressed', String(live));
    this.root.classList.toggle('live', live);
    if (live) { this.wake(); this.say('Listening.', 2000); }
  }

  setSpeaking(on) { this.speaking = on; if (on) this.wake(); }

  // A short dash across the floor — used when Jane walks the filesystem.
  run() {
    this.wake();
    this.say('On it — running.', 2200);
    if (this.reduced) return;
    const far = this.x < innerWidth * 0.5;
    this.targetX = far ? innerWidth - this.cw - 20 : 20;
    this.transient = { pose: 'run', until: performance.now() + 2600 };
    this.roam = null;
  }

  goHome() { this.roam = 'home'; this.targetX = this.home; }
  wake() { this.idleMs = 0; this.root.classList.remove('doze'); }

  say(text, ms = 3000) {
    if (!text) return;
    this.bubble.textContent = text;
    this.bubble.classList.add('show');
    this.bubbleUntil = performance.now() + ms;
    this._announce(text);
  }

  _announce(text) { if (text) this.live.textContent = text; }

  _statusLine() {
    return { idle: 'Patrick Jane is resting on the sofa.',
      listening: 'Patrick Jane is listening.',
      processing: 'Patrick Jane is taking notes.',
      searching: 'Patrick Jane is thinking it through.',
      tracking: 'Patrick Jane has locked onto the subject.',
      alert: 'Patrick Jane has spotted something.' }[this.mode] || '';
  }

  _hint() {
    return { processing: 'Taking notes…', searching: 'Let me think…',
      tracking: 'There you are.', alert: 'Someone is here.' }[this.mode] || '';
  }
  // PLACEHOLDER_POSE
  // ===== pose selection =====================================================
  _choosePose(now) {
    if (this.transient && now < this.transient.until) return this.transient.pose;
    this.transient = null;
    if (this.dragging) return 'present';
    if (this.roam && Math.abs(this.targetX - this.x) > 2) {
      return this.targetX > this.x ? 'right' : 'left';
    }
    if (this.speaking) return 'present';               // gesturing while she talks
    switch (this.mode) {
      case 'listening': return 'turn';                 // head cocked, attentive
      case 'processing': return 'write';               // writing notes
      case 'searching': return 'think';                // hand on chin
      case 'tracking': return 'point';
      case 'alert': return 'point';
      default: return 'smile';                          // idle: seated, at ease
    }
  }

  // ===== per-frame update ===================================================
  _loop(now) {
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    this._update(dt, now);
    this._draw(now);
    requestAnimationFrame((t) => this._loop(t));
  }

  _update(dt, now) {
    const busy = this.mode !== 'idle' || this.speaking || this.mic;
    const running = this.transient && this.transient.pose === 'run';

    if (busy && !running) { this.idleMs = 0; }
    else if (!this.dragging) { this.idleMs += dt * 1000; }

    const atHome = Math.abs(this.x - this.home) < 6;
    // He rests seated on the sofa whenever nothing is going on and he's home.
    this.seated = !busy && !running && !this.dragging && this.roam !== 'pace' && atHome;

    // Idle life: an occasional short stroll, then back to the sofa; a doze if left alone.
    if (!this.reduced && !busy && !this.dragging && !running) {
      if (this.idleMs > 75000) {
        this.roam = 'home'; this.targetX = this.home;
        if (atHome) this.root.classList.add('doze');
      } else if (this.idleMs > 22000 && !this.roam) {
        this.roam = 'pace';
        this.paceLeft = 3;                 // a few short legs, then home
        this.targetX = clamp(rand(90, innerWidth * 0.42), 0, innerWidth - this.cw);
      }
    }

    // Move toward target.
    const speed = running ? 620 : 68;                  // px/s
    if (!this.dragging && Math.abs(this.targetX - this.x) > 1) {
      const dir = Math.sign(this.targetX - this.x);
      this.x = clamp(this.x + dir * speed * dt, 0, innerWidth - this.cw);
    } else if (this.roam === 'pace' && !this.reduced && !busy) {
      // reached a waypoint — stroll on a couple more times, then settle home
      if (Math.random() < 0.02) {
        if ((this.paceLeft = (this.paceLeft || 0) - 1) <= 0) { this.roam = null; this.targetX = this.home; }
        else this.targetX = clamp(rand(60, innerWidth * 0.42), 0, innerWidth - this.cw);
      }
    } else if (this.roam === 'home' && Math.abs(this.x - this.home) < 2) {
      this.roam = null;
    }

    // Vertical bob: breathing when still, a bounce when running, scribble when writing.
    if (this.reduced) { this.bob = 0; }
    else if (running) this.bob = Math.abs(Math.sin(now / 90)) * 7;
    else if (this.pose === 'write') this.bob = Math.sin(now / 140) * 1.4;
    else this.bob = Math.sin(now / 620) * 1.6;

    // Watch the cursor: when he's at ease (not busy, not travelling), turn to
    // face where the pointer is — the "looks at what I do" glance. Motion off
    // under reduced-motion, and a small dead-zone stops him flip-flopping.
    const moving = Math.abs(this.targetX - this.x) > 2;
    if (!this.reduced && this._pointer != null && !running && !this.dragging && !moving) {
      const mid = this.x + this.cw / 2;
      if (this._pointer > mid + 24) this.facing = 1;
      else if (this._pointer < mid - 24) this.facing = -1;
    }

    this.pose = this._choosePose(now);

    // Hide the bubble when its time is up.
    if (this.bubbleUntil && now > this.bubbleUntil) {
      this.bubble.classList.remove('show');
      this.bubbleUntil = 0;
    }
    // Doze quip, once.
    if (this.root.classList.contains('doze') && !this.bubbleUntil && Math.random() < 0.004) {
      this.say('z z z…', 2600);
    }
  }
  // PLACEHOLDER_DRAW
  // ===== render =============================================================
  _draw(now) {
    this.root.style.transform = `translateX(${Math.round(this.x)}px)`;
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.cw, this.chpx);
    if (!this.ready) return;

    const f = FRAMES[this.pose] || FRAMES.smile;
    const dispW = f.w * SCALE;
    const dispH = f.h * SCALE;

    // Down-sample the illustration, then blit it back up with smoothing off — the
    // detailed art turns into honest chunky pixels, matching the retro companion.
    const lw = Math.max(1, Math.round(dispW / PX));
    const lh = Math.max(1, Math.round(dispH / PX));
    this.buf.width = lw; this.buf.height = lh;
    this.bctx.imageSmoothingEnabled = true;
    this.bctx.clearRect(0, 0, lw, lh);
    this.bctx.drawImage(this.sheet, f.x, f.y, f.w, f.h, 0, 0, lw, lh);

    const dx = (this.cw - dispW) / 2;
    // When seated, sink him into the sofa so the seat/arms hide him waist-down.
    const sit = this.seated ? 34 : 0;
    const dy = this.chpx - dispH - this.bob + sit;
    // Run frame faces right → mirror it when dashing left. The walk poses carry
    // their own direction; every other pose turns to face the cursor (facing).
    const directional = this.pose === 'left' || this.pose === 'right';
    let flip = 1;
    if (this.pose === 'run') flip = this.targetX < this.x ? -1 : 1;
    else if (!directional && this.facing === -1) flip = -1;

    ctx.imageSmoothingEnabled = false;
    ctx.save();
    if (flip === -1) { ctx.translate(this.cw, 0); ctx.scale(-1, 1); }
    ctx.drawImage(this.buf, 0, 0, lw, lh, dx, dy, dispW, dispH);
    ctx.restore();
  }
}
