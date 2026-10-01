// Tiny sparklines for the SYSTEM STATUS panel.

const POINTS = 46;

export class Spark {
  constructor(canvas, { max = 100, color = '#8c8c8c' } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.data = new Array(POINTS).fill(0);
    this.max = max;
    this.color = color;
    this.resize();
    addEventListener('resize', () => this.resize());
  }

  resize() {
    const dpr = devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.w = Math.max(rect.width, 40);
    this.h = Math.max(rect.height, 14);
    this.canvas.width = this.w * dpr;
    this.canvas.height = this.h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.draw();
  }

  push(value) {
    this.data.push(Number.isFinite(value) ? value : 0);
    if (this.data.length > POINTS) this.data.shift();
    // Auto-range for unbounded series (network bytes/s) so the shape stays legible.
    if (this.autoRange) this.max = Math.max(1, ...this.data) * 1.15;
    this.draw();
  }

  draw() {
    const { ctx, w, h } = this;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = this.color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    const step = w / (POINTS - 1);
    const pad = 2;
    for (let i = 0; i < this.data.length; i++) {
      const norm = Math.min(1, this.data[i] / this.max);
      const x = i * step;
      const y = h - pad - norm * (h - pad * 2);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
}
