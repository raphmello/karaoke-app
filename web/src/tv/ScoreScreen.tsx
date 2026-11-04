// The score at the end of a song, on the TV only: a gauge whose needle climbs trembling while drums roll, passes
// the score, hesitates, slips back and
// locks; then a phrase for the score, confetti from 90 and a fanfare from 95. The score is random (lib/score.ts);
// the sound is made here with Web Audio, so there is no recording to license. "Pular", or Esc, closes it.
import { useEffect, useRef, useState } from "react";
import { HOLD_MS, needle, phrase, SUSPENSE_MS } from "../lib/score";

const R = 120;
const CX = 150;
const CY = 150;
const TICKS = [0, 25, 50, 70, 80, 90, 100];

const angle = (v: number) => Math.PI * (1 - v / 100); // 0 on the left, 100 on the right
const at = (v: number, r: number): [number, number] => [CX + r * Math.cos(angle(v)), CY - r * Math.sin(angle(v))];
function arc(a: number, b: number): string {
  const [x1, y1] = at(a, R);
  const [x2, y2] = at(b, R);
  return `M${x1} ${y1} A${R} ${R} 0 0 1 ${x2} ${y2}`;
}

export function ScoreScreen({
  score,
  title,
  singer,
  thumbnail,
  onDone,
}: {
  score: number;
  title: string;
  singer: string;
  thumbnail: string | null;
  onDone: () => void;
}) {
  const reduce = useRef(matchMedia("(prefers-reduced-motion: reduce)").matches).current;
  const [value, setValue] = useState(reduce ? score : 0);
  const [locked, setLocked] = useState(reduce);
  const [words] = useState(() => phrase(score));
  const done = useRef(onDone);
  done.current = onDone;
  const confetti = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const sound = startSound(score);
    const peak = Math.min(100, score + 3 + Math.random() * 4);
    const t0 = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - t0) / SUSPENSE_MS);
      const tremble = t < 1 ? (1 - t) * (Math.random() - 0.5) * 3 : 0;
      setValue(Math.max(0, Math.min(100, needle(t, score, peak) + tremble)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    if (!reduce) frame = requestAnimationFrame(tick);
    const lock = window.setTimeout(() => {
      setValue(score);
      setLocked(true);
      sound?.reveal();
      if (score >= 90 && !reduce && confetti.current) throwConfetti(confetti.current, score >= 95 ? 220 : 120);
    }, SUSPENSE_MS);
    const close = window.setTimeout(() => done.current(), SUSPENSE_MS + HOLD_MS);
    const esc = (event: KeyboardEvent) => event.key === "Escape" && done.current();
    window.addEventListener("keydown", esc);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(lock);
      window.clearTimeout(close);
      window.removeEventListener("keydown", esc);
      sound?.stop();
    };
  }, [score, reduce]);

  const [nx, ny] = at(value, R - 20);
  return (
    <main className="relative flex h-full items-center justify-center overflow-hidden bg-(--menu-panel) px-4">
      {thumbnail && (
        <img src={thumbnail} alt="" className="absolute inset-0 h-full w-full scale-110 object-cover opacity-35 blur-2xl" />
      )}
      <div
        className="relative flex w-full max-w-[640px] flex-col items-center gap-3 rounded-3xl bg-[rgb(18_18_22/0.85)] px-8 pt-7 pb-8 text-center shadow-[0_20px_60px_rgba(0,0,0,.55)]"
        aria-live="polite"
      >
        <div className="flex min-w-0 max-w-full items-center gap-3">
          {thumbnail ? (
            <img src={thumbnail} alt="" className="h-12 w-12 shrink-0 rounded-lg object-cover" />
          ) : (
            <div className="h-12 w-12 shrink-0 rounded-lg bg-(--menu-thumb)" />
          )}
          <div className="min-w-0 text-left">
            <div className="truncate text-lg font-semibold text-(--menu-text)">{title}</div>
            <div className="truncate text-sm text-(--menu-text-3)">cantou: {singer}</div>
          </div>
        </div>
        <div className="text-xs tracking-[3px] text-(--menu-text-3) uppercase">Sua nota</div>
        <svg viewBox="0 0 300 200" className="w-full max-w-[420px]" role="img" aria-label={locked ? `Nota ${score}` : "Sorteando a nota"}>
          <path d={arc(0, 100)} fill="none" stroke="var(--menu-btn)" strokeWidth={14} strokeLinecap="round" />
          <path d={arc(0, Math.max(0.01, value))} fill="none" stroke="var(--menu-accent)" strokeWidth={14} strokeLinecap="round" />
          {TICKS.map((v) => {
            const [x1, y1] = at(v, R - 18);
            const [x2, y2] = at(v, R - 28);
            const [lx, ly] = at(v, R - 42);
            return (
              <g key={v}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#4f4f58" strokeWidth={2} />
                <text x={lx} y={ly + 4} textAnchor="middle" fontSize={11} fill="var(--menu-text-3)">
                  {v}
                </text>
              </g>
            );
          })}
          <line x1={CX} y1={CY} x2={nx} y2={ny} stroke="var(--menu-text)" strokeWidth={4} strokeLinecap="round" />
          <circle cx={CX} cy={CY} r={7} fill="var(--menu-text)" />
          <text
            x={CX}
            y={CY + 46}
            textAnchor="middle"
            fontSize={46}
            fontWeight={800}
            fill={locked ? "var(--menu-accent)" : "var(--menu-text)"}
            className="tabular-nums"
          >
            {Math.round(value)}
          </text>
        </svg>
        <p className={`min-h-8 text-2xl font-medium text-(--menu-text) transition-all duration-500 ${locked ? "opacity-100" : "translate-y-2 opacity-0"}`}>
          {locked ? words : ""}
        </p>
      </div>
      <button
        type="button"
        onClick={() => done.current()}
        className="absolute right-5 bottom-5 rounded-full bg-[rgb(42_42_49/0.85)] px-4 py-2 text-sm font-medium text-(--menu-text-2) hover:bg-(--menu-btn-hover)"
      >
        Pular
      </button>
      <canvas ref={confetti} className="pointer-events-none absolute inset-0 h-full w-full" />
    </main>
  );
}

// --- the sound: drums that speed up over a rising low tone; a crash and a chord at the score; a fanfare from 95 -----

function startSound(score: number): { reveal: () => void; stop: () => void } | null {
  const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Context) return null;
  const ctx = new Context();
  void ctx.resume().catch(() => undefined);
  const master = ctx.createGain();
  master.gain.value = 0.5;
  master.connect(ctx.destination);

  const noise = (seconds: number) => {
    const buffer = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * seconds), ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    return buffer;
  };
  const hit = (when: number, gain: number, freq = 1800, decay = 0.07) => {
    const source = ctx.createBufferSource();
    source.buffer = noise(decay + 0.02);
    const filter = ctx.createBiquadFilter();
    filter.type = "highpass";
    filter.frequency.value = freq;
    const g = ctx.createGain();
    g.gain.setValueAtTime(gain, when);
    g.gain.exponentialRampToValueAtTime(0.001, when + decay);
    source.connect(filter).connect(g).connect(master);
    source.start(when);
  };
  const tone = (type: OscillatorType, freq: number, when: number, duration: number, gain: number, glideTo?: number) => {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, when);
    if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, when + duration);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(gain, when + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, when + duration);
    osc.connect(g).connect(master);
    osc.start(when);
    osc.stop(when + duration + 0.05);
  };

  // the roll: from a hit every 140 ms down to one every 28 ms, louder as it goes
  const t0 = ctx.currentTime + 0.05;
  const length = SUSPENSE_MS / 1000;
  for (let t = 0; t < length; ) {
    const p = t / length;
    hit(t0 + t, 0.18 + 0.4 * p);
    t += 0.14 - 0.112 * p ** 1.4;
  }
  tone("triangle", 55, t0, length, 0.22, 110);

  return {
    reveal() {
      const t = ctx.currentTime;
      hit(t, 0.8, 4500, 1.6); // crash
      hit(t, 0.9, 120, 0.25); // kick
      const chord = score >= 80 ? [261.6, 329.6, 392, 523.3] : [261.6, 311.1, 392]; // major, or a softer minor
      for (const f of chord) tone("sawtooth", f, t, 1.4, 0.07);
      if (score >= 95) [392, 523.3, 659.3, 784].forEach((f, i) => tone("square", f, t + 0.25 + i * 0.14, i === 3 ? 0.7 : 0.16, 0.06));
    },
    stop() {
      void ctx.close().catch(() => undefined);
    },
  };
}

function throwConfetti(canvas: HTMLCanvasElement, count: number) {
  const g = canvas.getContext("2d");
  if (!g) return;
  const scale = window.devicePixelRatio || 1;
  const box = canvas.getBoundingClientRect();
  canvas.width = box.width * scale;
  canvas.height = box.height * scale;
  const colors = ["#ffc107", "#ffe082", "#f2f2f2", "#ff6f91", "#7ad7f0"];
  let parts = Array.from({ length: count }, (_, i) => ({
    x: canvas.width / 2 + (Math.random() - 0.5) * canvas.width * 0.3,
    y: canvas.height * 0.45,
    vx: (Math.random() - 0.5) * 14 * scale,
    vy: (-6 - Math.random() * 12) * scale,
    size: (4 + Math.random() * 5) * scale,
    a: Math.random() * Math.PI,
    va: (Math.random() - 0.5) * 0.3,
    color: colors[i % colors.length],
  }));
  const step = () => {
    if (!canvas.isConnected) return;
    g.clearRect(0, 0, canvas.width, canvas.height);
    parts = parts.filter((p) => p.y < canvas.height + 20);
    for (const p of parts) {
      p.vy += 0.35 * scale;
      p.vx *= 0.99;
      p.x += p.vx;
      p.y += p.vy;
      p.a += p.va;
      g.save();
      g.translate(p.x, p.y);
      g.rotate(p.a);
      g.fillStyle = p.color;
      g.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
      g.restore();
    }
    if (parts.length) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
