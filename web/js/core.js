// The intelligence core — the one thing at the centre of the stage.
//
// It is almost invisible when Jane is idle: a few concentric rings breathing
// slowly in near-black. As she moves through listening → processing → searching
// it wakes: rings brighten, a restrained scan line rotates, a pulse expands.
// When a subject locks it holds a single red point with a quiet reticle. Red is
// used once, and only here, and only when it means something.

const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

// Per-mode targets the core eases toward. `intensity` drives ring opacity and
// whether the scan is drawn; `spin` is radians/second.
const MODES = {
  idle:       { intensity: 0.12, spin: 0.05, scan: false, pulse: false },
  listening:  { intensity: 0.28, spin: 0.10, scan: false, pulse: false },
  processing: { intensity: 0.55, spin: 0.55, scan: true,  pulse: true },
  searching:  { intensity: 0.80, spin: 0.95, scan: true,  pulse: true },
  tracking:   { intensity: 0.62, spin: 0.16, scan: false, pulse: false },
  alert:      { intensity: 0.72, spin: 0.30, scan: true,  pulse: true },
};

const RINGS = [0.20, 0.34, 0.50, 0.68, 0.88];

export class Core {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.mode = 'idle';
    this.angle = 0;
    this.intensity = MODES.idle.intensity;
    this.spin = MODES.idle.spin;
    this.pulses = [];        // expanding rings, spawned on demand
    this.target = null;      // { locked:0..1 } once a subject is held
    this.lastPulse = 0;
    this.resize();
    addEventListener('resize', () => this.resize());
    this.last = performance.now();
    requestAnimationFrame((t) => this.frame(t));
  }

  setState(mode) {
    if (!MODES[mode]) return;
    this.mode = mode;
    if (mode === 'tracking' && !this.target) this.target = { locked: 0 };
    if (mode !== 'tracking' && mode !== 'alert') this.target = null;
  }

  /** Fire a single expanding pulse — used at the moment a target is found. */
  ping() { this.pulses.push({ r: 0.12, a: 0.5 }); }

  resize() {
    const dpr = devicePixelRatio || 1;
    const parent = this.canvas.parentElement.getBoundingClientRect();
    const size = Math.max(240, Math.min(parent.width, parent.height));
    this.canvas.style.width = `${size}px`;
    this.canvas.style.height = `${size}px`;
    this.canvas.width = size * dpr;
    this.canvas.height = size * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.size = size;
    this.R = size / 2 - 6;
  }

  frame(now) {
    const dt = Math.min((now - this.last) / 1000, 0.05);
    this.last = now;
    if (document.hidden) { requestAnimationFrame((t) => this.frame(t)); return; }

    const m = MODES[this.mode];
    // Ease intensity and spin toward the mode's target — nothing snaps.
    this.intensity += (m.intensity - this.intensity) * Math.min(1, dt * 2.4);
    this.spin += (m.spin - this.spin) * Math.min(1, dt * 3);
    if (!REDUCED) this.angle = (this.angle + this.spin * dt) % (Math.PI * 2);

    // Occasional pulse while active.
    if (m.pulse && !REDUCED && now - this.lastPulse > 2600) {
      this.ping();
      this.lastPulse = now;
    }
    for (const p of this.pulses) { p.r += dt * 0.5; p.a -= dt * 0.32; }
    this.pulses = this.pulses.filter((p) => p.a > 0.01);

    if (this.target && this.target.locked < 1) {
      this.target.locked = Math.min(1, this.target.locked + dt * 1.6);
    }

    this.draw(m);
    requestAnimationFrame((t) => this.frame(t));
  }

  ring(r, alpha, { dash = null, width = 1 } = {}) {
    const { ctx } = this;
    ctx.save();
    ctx.strokeStyle = `rgba(150,150,150,${alpha})`;
    ctx.lineWidth = width;
    ctx.setLineDash(dash || []);
    ctx.beginPath();
    ctx.arc(0, 0, this.R * r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  draw(m) {
    const { ctx, size, R } = this;
    ctx.clearRect(0, 0, size, size);
    ctx.save();
    ctx.translate(size / 2, size / 2);

    const k = this.intensity;

    // Concentric rings — the resting structure. Faint, a couple dashed.
    RINGS.forEach((r, i) => {
      const base = i === RINGS.length - 1 ? 0.5 : 0.28;
      this.ring(r, base * k, { dash: i % 2 ? [2, 8] : null });
    });

    // Fine outer graduations, only once the core is meaningfully awake.
    if (k > 0.4) {
      ctx.save();
      ctx.strokeStyle = `rgba(150,150,150,${0.4 * k})`;
      ctx.lineWidth = 1;
      const count = 72;
      for (let i = 0; i < count; i++) {
        const a = (i / count) * Math.PI * 2;
        const long = i % 6 === 0;
        const r1 = R * 0.88;
        const r2 = R * (0.88 + (long ? 0.03 : 0.015));
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
        ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
        ctx.stroke();
      }
      ctx.restore();
    }

    // Expanding pulses.
    for (const p of this.pulses) {
      ctx.strokeStyle = `rgba(180,180,180,${p.a * k})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(0, 0, R * p.r, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Scan wedge — greyscale, not red. Red is reserved for the target.
    if (m.scan) {
      ctx.save();
      ctx.rotate(this.angle);
      const grad = ctx.createLinearGradient(0, 0, R * 0.88, 0);
      grad.addColorStop(0, `rgba(190,190,190,${0.16 * k})`);
      grad.addColorStop(1, 'rgba(190,190,190,0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, R * 0.88, -0.34, 0);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = `rgba(210,210,210,${0.5 * k})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(R * 0.88, 0);
      ctx.stroke();
      ctx.restore();
    }

    if (this.target) this.drawTarget();

    ctx.restore();
  }

  drawTarget() {
    const { ctx, R } = this;
    const lock = this.target.locked;
    // Held a little off-centre, upper-right, so it reads as a position not a hub.
    const tx = R * 0.30, ty = -R * 0.22;
    const reach = 1 - lock;

    // Reticle closing in as the lock completes.
    ctx.strokeStyle = `rgba(216,26,26,${0.5 + 0.3 * lock})`;
    ctx.lineWidth = 1;
    const gap = 6 + reach * 26;
    const len = 5;
    for (const [dx, dy] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
      ctx.beginPath();
      ctx.moveTo(tx + dx * gap, ty + dy * gap);
      ctx.lineTo(tx + dx * (gap + len), ty + dy * (gap + len));
      ctx.stroke();
    }

    // Soft red core.
    const glow = ctx.createRadialGradient(tx, ty, 0, tx, ty, 14);
    glow.addColorStop(0, `rgba(216,26,26,${0.4 * lock})`);
    glow.addColorStop(1, 'rgba(216,26,26,0)');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(tx, ty, 14, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = `rgba(216,26,26,${0.7 + 0.3 * lock})`;
    ctx.beginPath();
    ctx.arc(tx, ty, 2.6, 0, Math.PI * 2);
    ctx.fill();
  }
}
