// The voice waveform — a thin, centred trace under Jane's line.
//
// Quiet to the point of near-stillness when idle; alive when the microphone is
// live or Jane is speaking. Greyscale only: red is reserved for the core's
// target, never spent on decoration down here.

export class Wave {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.analyser = null;
    this.bins = null;
    this.speaking = false;
    this.active = false;      // microphone live
    this.energy = 0;          // eased 0..1, drives amplitude
    this.t = 0;
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.resize();
    addEventListener('resize', () => this.resize());
    requestAnimationFrame(() => this.frame());
  }

  resize() {
    const dpr = devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.w = Math.max(rect.width, 200);
    this.h = Math.max(rect.height, 24);
    this.canvas.width = this.w * dpr;
    this.canvas.height = this.h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  attach(stream) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    this.audio = this.audio || new AudioCtx();
    const src = this.audio.createMediaStreamSource(stream);
    this.analyser = this.audio.createAnalyser();
    this.analyser.fftSize = 512;
    this.analyser.smoothingTimeConstant = 0.78;
    src.connect(this.analyser);
    this.bins = new Uint8Array(this.analyser.frequencyBinCount);
    this.active = true;
  }

  detach() {
    this.analyser = null;
    this.bins = null;
    this.active = false;
  }

  setSpeaking(on) { this.speaking = on; }

  frame() {
    if (!document.hidden) this.draw();
    requestAnimationFrame(() => this.frame());
  }

  draw() {
    const { ctx, w, h } = this;
    this.t += 0.016;
    ctx.clearRect(0, 0, w, h);

    let level = 0;
    if (this.analyser && this.bins) {
      this.analyser.getByteFrequencyData(this.bins);
      let sum = 0;
      for (let i = 0; i < this.bins.length; i++) sum += this.bins[i];
      level = Math.min(1, (sum / this.bins.length / 255) * 2.2);
    } else if (this.speaking) {
      level = 0.5;
    }
    // A resting shimmer so the line is never quite dead.
    const floor = this.active || this.speaking ? 0.12 : 0.05;
    const goal = Math.max(floor, level);
    this.energy += (goal - this.energy) * 0.15;

    const mid = h / 2;
    const n = Math.floor(w / 3);
    const bright = this.active || this.speaking;
    ctx.strokeStyle = `rgba(190,190,190,${bright ? 0.5 : 0.22})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i <= n; i++) {
      const x = (i / n) * w;
      const p = i / n;
      // Envelope tapers to nothing at both ends — a centred trace, not a fill.
      const env = Math.sin(p * Math.PI);
      const wobble = this.reduced ? 0
        : Math.sin(p * 22 + this.t * 6) * Math.sin(p * 7 - this.t * 3.2);
      const amp = env * this.energy * wobble * (h * 0.42);
      const y = mid + amp;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
}
