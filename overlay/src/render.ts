import { type BotState, type Params, type Theme, clamp, geometry as G } from "./character";

export interface Frame {
  params: Params;
  /** Vertical offset in design units, positive is down. */
  bob: number;
  /** 0 hides the mouth; above 0 opens it, driven by speech audio level. */
  mouth: number;
  state: BotState;
  /** Seconds since start, for looping accents (ring pulse, thinking dots, z's). */
  time: number;
  /** Microphone level 0 to 1 for the listening ring. */
  micLevel: number;
}

/** Room around the 240-unit body for the listening ring, thinking dots and sleep z's. */
export const PADDING = 40;
export const CANVAS_UNITS = G.diameter + PADDING * 2;

const eyeLayer = document.createElement("canvas");

/**
 * Draws the bot into a square canvas. Everything is in design units (body diameter 240), scaled to
 * the canvas, so the numbers match design/character.json and the Figma file one to one.
 */
export function drawBot(canvas: HTMLCanvasElement, frame: Frame, theme: Theme): void {
  const ctx = canvas.getContext("2d")!;
  const scale = canvas.width / CANVAS_UNITS;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.setTransform(scale, 0, 0, scale, PADDING * scale, (PADDING + frame.bob) * scale);
  ctx.globalAlpha = frame.state === "sleeping" ? 0.85 : 1;

  drawAccentsBehind(ctx, frame, theme);
  drawShell(ctx, theme);
  drawBlush(ctx, frame.params.blush, theme);
  drawEyes(ctx, canvas, scale, frame, theme);
  if (frame.mouth > 0) drawMouth(ctx, frame.mouth, theme);
  drawAccentsFront(ctx, frame, theme);
  ctx.globalAlpha = 1;
}

function drawShell(ctx: CanvasRenderingContext2D, theme: Theme): void {
  const r = G.diameter / 2;
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.3)";
  ctx.shadowBlur = 24;
  ctx.shadowOffsetY = 10;
  ctx.fillStyle = theme.shell;
  ctx.beginPath();
  ctx.arc(r, r, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  const shine = ctx.createRadialGradient(94, 43, 0, 94, 43, 70);
  shine.addColorStop(0, "rgba(255,255,255,0.14)");
  shine.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = shine;
  ctx.beginPath();
  ctx.ellipse(94, 43, 66, 35, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = withAlpha(theme.shellHighlight, 0.7);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(r, r, r - 0.75, 0, Math.PI * 2);
  ctx.stroke();
}

function drawBlush(ctx: CanvasRenderingContext2D, blush: number, theme: Theme): void {
  if (blush <= 0.01) return;
  for (const side of [1, -1]) {
    const cx = G.diameter / 2 - side * (G.eye.spacing / 2 + G.blush.offsetX);
    const g = ctx.createRadialGradient(cx, G.blush.y, 0, cx, G.blush.y, G.blush.width / 2 + 4);
    g.addColorStop(0, withAlpha(theme.blush, 0.6 * blush));
    g.addColorStop(1, withAlpha(theme.blush, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(cx, G.blush.y, G.blush.width / 2 + 4, G.blush.height / 2 + 3, 0, 0, Math.PI * 2);
    ctx.fill();
  }
}

/**
 * Each eye is a pill with two shapes cut out of it: a top lid (a half-plane whose edge drops and
 * tilts) and a bottom smile (an ellipse rising from below). Cutting on a separate layer keeps the
 * shell underneath intact, so the eyes work on any shell color.
 */
function drawEyes(ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement, scale: number, frame: Frame, theme: Theme): void {
  if (eyeLayer.width !== canvas.width || eyeLayer.height !== canvas.height) {
    eyeLayer.width = canvas.width;
    eyeLayer.height = canvas.height;
  }
  const e = eyeLayer.getContext("2d")!;
  e.setTransform(1, 0, 0, 1, 0, 0);
  e.clearRect(0, 0, eyeLayer.width, eyeLayer.height);
  e.setTransform(ctx.getTransform());

  const p = frame.params;
  for (const side of [1, -1]) {
    const cx = G.diameter / 2 - side * (G.eye.spacing / 2);
    eyeShape(e, cx, p, side, theme.eye);
  }

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.shadowColor = theme.eyeGlow;
  ctx.shadowBlur = 10 * scale;
  ctx.drawImage(eyeLayer, 0, 0);
  ctx.restore();
}

function eyeShape(e: CanvasRenderingContext2D, cx: number, p: Params, side: number, color: string): void {
  const w = G.eye.width * p.w;
  const h = G.eye.height * p.h;
  const ex = cx + clamp(p.lookX, -1, 1) * G.look.maxX;
  const ey = G.eye.centerY + clamp(p.lookY, -1, 1) * G.look.maxY;
  const left = ex - w / 2;
  const top = ey - h / 2;

  e.globalCompositeOperation = "source-over";
  e.fillStyle = color;
  e.beginPath();
  e.roundRect(left, top, w, h, w / 2);
  e.fill();

  e.globalCompositeOperation = "destination-out";
  e.fillStyle = "#000";
  if (p.lid > 0.001) {
    const tilt = Math.tan((p.angle * Math.PI) / 180) * side;
    const edge = (x: number) => top + clamp(p.lid, 0, 1) * h + tilt * (x - ex);
    const x0 = left - 12;
    const x1 = left + w + 12;
    e.beginPath();
    e.moveTo(x0, top - 60);
    e.lineTo(x1, top - 60);
    e.lineTo(x1, edge(x1));
    e.lineTo(x0, edge(x0));
    e.closePath();
    e.fill();
  }
  if (p.smile > 0.001) {
    const ew = w * 1.7;
    const eh = h * 0.9;
    e.beginPath();
    e.ellipse(ex, top + h - p.smile * h + eh / 2, ew / 2, eh / 2, 0, 0, Math.PI * 2);
    e.fill();
  }
  e.globalCompositeOperation = "source-over";
}

function drawMouth(ctx: CanvasRenderingContext2D, open: number, theme: Theme): void {
  const m = G.mouth;
  const h = m.minHeight + clamp(open, 0, 1) * (m.maxHeight - m.minHeight);
  ctx.fillStyle = theme.eye;
  ctx.beginPath();
  ctx.roundRect(G.diameter / 2 - m.width / 2, m.y - h / 2, m.width, h, Math.min(7, h / 2));
  ctx.fill();
}

function drawAccentsBehind(ctx: CanvasRenderingContext2D, frame: Frame, theme: Theme): void {
  if (frame.state !== "listening") return;
  const c = G.diameter / 2;
  const pulse = 0.5 + 0.5 * Math.sin(frame.time * 4);
  const grow = 2 + frame.micLevel * 10;
  ctx.save();
  ctx.shadowColor = withAlpha(theme.listening, 0.5);
  ctx.shadowBlur = 12;
  ctx.lineWidth = 3;
  ctx.strokeStyle = withAlpha(theme.listening, 0.9);
  ctx.beginPath();
  ctx.arc(c, c, c + 11 + grow * 0.3, 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = 2;
  ctx.strokeStyle = withAlpha(theme.listening, 0.2 + 0.25 * pulse);
  ctx.beginPath();
  ctx.arc(c, c, c + 22 + grow, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

function drawAccentsFront(ctx: CanvasRenderingContext2D, frame: Frame, theme: Theme): void {
  if (frame.state === "thinking") {
    for (let i = 0; i < 3; i++) {
      const phase = (frame.time * 1.6 - i * 0.35) % 3;
      const alpha = 0.35 + 0.65 * Math.max(0, Math.sin(Math.PI * clamp(phase, 0, 1)));
      ctx.fillStyle = withAlpha(theme.thinking, alpha);
      ctx.beginPath();
      ctx.arc(213 + i * 20, 22 - i * 20, 5 + i * 1.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (frame.state === "sleeping") {
    ctx.fillStyle = theme.textSecondary;
    ctx.font = "600 22px ui-rounded, 'SF Pro Rounded', system-ui";
    for (let i = 0; i < 2; i++) {
      const t = (frame.time * 0.5 + i * 0.5) % 1;
      ctx.globalAlpha = 0.85 * Math.sin(Math.PI * t);
      ctx.fillText("z", 214 + i * 16 + t * 10, 30 - i * 18 - t * 16);
    }
    ctx.globalAlpha = 0.85;
  }
}

/** Accepts #rrggbb or #rrggbbaa and returns rgba() with the alpha multiplied in. */
export function withAlpha(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const a = hex.length === 9 ? parseInt(hex.slice(7, 9), 16) / 255 : 1;
  return `rgba(${r},${g},${b},${(a * alpha).toFixed(3)})`;
}
