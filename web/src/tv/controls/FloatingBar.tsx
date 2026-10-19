// The TV's controls as a floating bar (docs/ARCHITECTURE.md, "Barra de controles"): over the video, never taking its
// room, at most 860 px wide. The pill keeps what is used all the time (play, skip, where the song is, the key); a
// tray, folded away, keeps what is set now and then (guide voice, lyrics delay, background, outline). After a few
// seconds without anyone touching it the bar goes, leaving a thin progress line; it never goes while paused, with the
// tray open, with a control in keyboard focus (a click leaves its button focused, which does not hold the bar) or
// with the mouse over it. The player, the key, the guide voice and the lyrics work as before: this is only their
// controls.
import { type ReactNode, useEffect, useRef, useState } from "react";
import type { Song } from "../../api";
import { keyName, MAX_SEMITONES, MIN_SEMITONES, parseKey, signed } from "../../lib/keys";
import type { Look } from "../look";
import { Icon, type IconName } from "../menu/icons";
import { formatTime } from "../time";

export const HIDE_AFTER_MS = 3000; // without anyone touching the bar
const TRAY_KEY = "karaoke.tv.tray"; // the tray open or folded, kept in this window
export const DELAY_STEP_MS = 50;
export const DELAY_LIMIT_MS = 10_000; // −10,00 to +10,00 s: a mirror through Edge lags about 2 s

function loadTray(): boolean {
  try {
    return localStorage.getItem(TRAY_KEY) === "1";
  } catch {
    return false;
  }
}

function saveTray(open: boolean): void {
  try {
    localStorage.setItem(TRAY_KEY, open ? "1" : "0");
  } catch {
    // a private window: it lasts until the page closes
  }
}

export function FloatingBar({
  song,
  loaded,
  playing,
  position,
  duration,
  onToggle,
  onSkip,
  onSeek,
  semitones,
  onKey,
  guide,
  onGuide,
  delayMs,
  onDelay,
  look,
  onLook,
  region,
}: {
  song: Song;
  loaded: boolean;
  playing: boolean;
  position: number;
  duration: number;
  onToggle: () => void;
  onSkip: () => void;
  onSeek: (seconds: number) => void;
  semitones: number;
  onKey: (semitones: number) => void;
  guide: number;
  onGuide: (percent: number) => void;
  delayMs: number;
  onDelay: (ms: number) => void;
  look: Look;
  onLook: (change: Partial<Look>) => void;
  region: { current: HTMLElement | null }; // where the mouse moving shows the bar: the video
}) {
  const [tray, setTray] = useState(loadTray);
  const [awake, setAwake] = useState(true);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [tip, setTip] = useState(false); // the progress's time tip is open
  const timer = useRef(0);
  const held = !playing || tray || hovered || focused || tip;

  // Moving the mouse over the video, or a control key, shows the bar for a while
  useEffect(() => {
    const wake = () => {
      setAwake(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setAwake(false), HIDE_AFTER_MS);
    };
    const onKey = (event: KeyboardEvent) => {
      if (["Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Tab"].includes(event.code)) wake();
    };
    const element = region.current;
    element?.addEventListener("pointermove", wake);
    window.addEventListener("keydown", onKey);
    wake();
    return () => {
      element?.removeEventListener("pointermove", wake);
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(timer.current);
    };
  }, [region]);
  const shown = awake || held;
  // With the bar gone, the mouse's pointer goes too, over the video (full screen)
  useEffect(() => {
    const element = region.current;
    if (!element) return;
    element.style.cursor = shown ? "" : "none";
    return () => void (element.style.cursor = "");
  }, [shown, region]);

  const toggleTray = () => {
    setTray(!tray);
    saveTray(!tray);
  };
  const percent = duration ? Math.min(100, (100 * position) / duration) : 0;

  return (
    <>
      {/* Gone: only a thin progress line at the bottom of the video */}
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute right-0 bottom-0 left-0 z-20 h-[3px] bg-(--menu-thumb) transition-opacity duration-300 ${
          shown ? "opacity-0" : "opacity-100"
        }`}
      >
        <div className="h-full bg-(--menu-accent)" style={{ width: `${percent}%` }} />
      </div>
      <div
        data-floating-bar
        className={`@container absolute bottom-[18px] left-1/2 z-30 flex w-[min(860px,calc(100%-32px))] -translate-x-1/2 flex-col gap-2 text-[13px] text-(--menu-text) transition-opacity duration-300 ${
          shown ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
        onFocus={(event) => setFocused(event.target.matches(":focus-visible"))}
        onBlur={(event) => !event.currentTarget.contains(event.relatedTarget as Node) && setFocused(false)}
      >
        {tray && (
          <Tray guide={guide} onGuide={onGuide} delayMs={delayMs} onDelay={onDelay} look={look} onLook={onLook} />
        )}
        <div className="flex items-center gap-2.5 rounded-[30px] bg-(--menu-rail) px-[14px] py-2 shadow-[0_8px_30px_rgba(0,0,0,.45)]">
          <button
            type="button"
            onClick={onToggle}
            disabled={!loaded}
            aria-label={playing ? "Pausar" : "Retomar"}
            title={playing ? "Pausar" : "Retomar"}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-(--menu-accent) text-(--menu-on-accent) disabled:opacity-50"
          >
            <Icon name={playing ? "pause" : "play"} className="h-[18px] w-[18px]" />
          </button>
          <Round icon="skip" label="Pular" onClick={onSkip} />
          <span className="shrink-0 text-[12px] whitespace-nowrap text-(--menu-text-3) tabular-nums">
            {formatTime(position)} / {formatTime(duration)}
          </span>
          <Progress position={position} duration={duration} onSeek={onSeek} disabled={!loaded} onTip={setTip} />
          <Divider />
          <KeySelector originalKey={song.original_key} semitones={semitones} onKey={onKey} />
          <Divider />
          <Round
            icon={tray ? "down" : "up"}
            label={tray ? "Recolher os ajustes" : "Mostrar os ajustes"}
            onClick={toggleTray}
            active={tray}
            expanded={tray}
          />
        </div>
      </div>
    </>
  );
}

function Divider() {
  return <span aria-hidden="true" className="h-[22px] w-px shrink-0 bg-[#2a2a30]" />;
}

/** A round button of the pill (32 px). */
function Round({
  icon,
  label,
  onClick,
  active,
  disabled,
  expanded,
}: {
  icon: IconName;
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  expanded?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      aria-expanded={expanded}
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
        active ? "bg-[rgba(255,193,7,.18)] text-(--menu-accent)" : "bg-(--menu-btn) text-[#e4e4e8] hover:bg-(--menu-btn-hover)"
      } disabled:cursor-default disabled:text-(--menu-text-off) disabled:hover:bg-(--menu-btn)`}
    >
      <Icon name={icon} className="h-4 w-4" />
    </button>
  );
}

/** Where the song is: click or drag to go there; the line thickens under the mouse and a tip says the time there. */
function Progress({
  position,
  duration,
  onSeek,
  disabled,
  onTip,
}: {
  position: number;
  duration: number;
  onSeek: (seconds: number) => void;
  disabled: boolean;
  onTip: (open: boolean) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null); // the fraction under the mouse
  const [dragging, setDragging] = useState(false);
  const fraction = (clientX: number) => {
    const rect = track.current!.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  };
  const done = duration ? Math.min(1, position / duration) : 0;
  useEffect(() => onTip(hover !== null || dragging), [hover, dragging, onTip]);
  return (
    <div
      ref={track}
      role="slider"
      tabIndex={disabled ? -1 : 0}
      aria-label="Posição na música"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(position)}
      aria-valuetext={`${formatTime(position)} de ${formatTime(duration)}`}
      className="group relative flex h-6 min-w-[60px] flex-1 cursor-pointer touch-none items-center focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--menu-accent)"
      onPointerDown={(event) => {
        if (disabled || !duration) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragging(true);
        onSeek(fraction(event.clientX) * duration);
      }}
      onPointerMove={(event) => {
        if (!duration) return;
        setHover(fraction(event.clientX));
        if (dragging) onSeek(fraction(event.clientX) * duration);
      }}
      onPointerUp={() => setDragging(false)}
      onPointerCancel={() => setDragging(false)}
      onPointerLeave={() => setHover(null)}
      onKeyDown={(event) => {
        if (disabled) return;
        if (event.key === "ArrowLeft") onSeek(Math.max(0, position - 5));
        else if (event.key === "ArrowRight") onSeek(Math.min(duration, position + 5));
        else return;
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <div className={`w-full rounded-full bg-(--menu-thumb) transition-[height] ${hover !== null || dragging ? "h-1.5" : "h-1"}`}>
        <div className="h-full rounded-full bg-(--menu-accent)" style={{ width: `${done * 100}%` }} />
      </div>
      <div
        aria-hidden="true"
        className="absolute h-3 w-3 -translate-x-1/2 rounded-full bg-(--menu-accent)"
        style={{ left: `${done * 100}%` }}
      />
      {hover !== null && (
        <span
          aria-hidden="true"
          className="absolute bottom-full mb-1.5 -translate-x-1/2 rounded-md bg-(--menu-panel) px-1.5 py-0.5 text-[11px] text-(--menu-text) tabular-nums shadow"
          style={{ left: `${hover * 100}%` }}
        >
          {formatTime(hover * duration)}
        </span>
      )}
    </div>
  );
}

/** The key: −½, its name and +½, then "voltar ao original". Changed, the name turns yellow with the semitones. */
function KeySelector({
  originalKey,
  semitones,
  onKey,
}: {
  originalKey: string | null;
  semitones: number;
  onKey: (semitones: number) => void;
}) {
  const key = parseKey(originalKey);
  const long = key ? keyName(key, semitones) : semitones ? "Tom" : "Tom original";
  const short = key ? shortKey(keyName(key, semitones)) : "Tom";
  const shift = semitones ? ` · ${signed(semitones)}` : "";
  const step = "flex h-[30px] w-8 items-center justify-center rounded-[15px] text-[13px] text-[#e4e4e8] hover:bg-(--menu-btn-hover) disabled:opacity-40";
  return (
    <>
      <div className="flex shrink-0 items-center rounded-[17px] bg-(--menu-btn) p-0.5">
        <button type="button" className={step} aria-label="Meio tom abaixo" disabled={semitones <= MIN_SEMITONES} onClick={() => onKey(semitones - 1)}>
          −½
        </button>
        <span
          aria-live="polite"
          className={`px-2.5 text-center font-medium whitespace-nowrap @[640px]:min-w-[84px] ${semitones ? "text-(--menu-accent)" : ""}`}
        >
          <span className="hidden @[640px]:inline">{long}</span>
          <span className="@[640px]:hidden">{short}</span>
          {shift}
        </span>
        <button type="button" className={step} aria-label="Meio tom acima" disabled={semitones >= MAX_SEMITONES} onClick={() => onKey(semitones + 1)}>
          +½
        </button>
      </div>
      <Round
        icon="reset"
        label={semitones && key ? `Voltar ao original: ${keyName(key)}` : "Voltar ao tom original"}
        onClick={() => onKey(0)}
        disabled={semitones === 0}
      />
    </>
  );
}

/** "Dó♯ menor" → "Dó♯m", "Ré maior" → "Ré": for a narrow bar. */
function shortKey(name: string): string {
  return name.replace(" menor", "m").replace(" maior", "");
}

// --- the tray ----------------------------------------------------------------------------------------------------

function Tray({
  guide,
  onGuide,
  delayMs,
  onDelay,
  look,
  onLook,
}: {
  guide: number;
  onGuide: (percent: number) => void;
  delayMs: number;
  onDelay: (ms: number) => void;
  look: Look;
  onLook: (change: Partial<Look>) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl bg-(--menu-rail) p-2 shadow-[0_8px_30px_rgba(0,0,0,.45)]">
      <Chip className="flex-[1_1_170px] @max-[640px]:basis-full">
        <span className="text-[12px] text-(--menu-text-2)">Voz guia</span>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={guide}
          onChange={(event) => onGuide(Number(event.target.value))}
          aria-label="Voz guia"
          className="menu-range min-w-12 flex-1"
          style={{ ["--v" as string]: `${guide}%` }}
        />
        <span className="min-w-[30px] text-right text-[12px] tabular-nums">{guide}%</span>
      </Chip>
      <Chip className="@max-[640px]:basis-full">
        <span className="text-[12px] text-(--menu-text-2)">Atraso da letra</span>
        <DelayField ms={delayMs} onChange={onDelay} />
      </Chip>
      <Switch label="Imagem de fundo" on={look.background} onChange={(background) => onLook({ background })} />
      <Switch label="Borda na letra" on={look.outline} onChange={(outline) => onLook({ outline })} />
    </div>
  );
}

function Chip({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`relative flex h-10 min-w-0 items-center gap-2.5 rounded-xl bg-(--menu-field) px-3 whitespace-nowrap ${className}`}>
      {children}
    </div>
  );
}

/** A setting turned on or off by the whole chip: the knob's side and color say which. */
function Switch({ label, on, onChange }: { label: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className="flex h-10 shrink-0 items-center gap-2.5 rounded-xl bg-(--menu-field) px-3 whitespace-nowrap hover:bg-[#292930]"
    >
      <span className="text-[12px] text-(--menu-text-2)">{label}</span>
      <span className={`relative h-[18px] w-8 shrink-0 rounded-[9px] transition-colors ${on ? "bg-(--menu-accent)" : "bg-[#3a3a42]"}`}>
        <span
          className={`absolute top-[3px] left-[3px] h-3 w-3 rounded-full transition-transform ${
            on ? "translate-x-[14px] bg-(--menu-on-accent)" : "bg-[#d8d8de]"
          }`}
        />
      </span>
    </button>
  );
}

/** "0,25": the lyrics' delay in seconds, two decimals and a comma. */
export function seconds(ms: number): string {
  return (ms / 1000).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** The lyrics' delay (docs/ARCHITECTURE.md, "Barra de controles"): − , a field to type it in seconds, s, +. A comma or a point; Enter or leaving the
 *  field applies it, Esc goes back, the arrows step it. Something that is not a number, or out of the limits, says so
 *  in a small tag over the chip. Positive delays the lyrics, negative brings them forward. */
function DelayField({ ms, onChange }: { ms: number; onChange: (ms: number) => void }) {
  const [text, setText] = useState<string | null>(null); // null: not being edited, the value shows
  const [focused, setFocused] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const field = useRef<HTMLInputElement>(null);
  const discard = useRef(false); // Esc: leaving the field must not apply what was typed
  const limit = `O valor vai de ${seconds(-DELAY_LIMIT_MS)} a ${seconds(DELAY_LIMIT_MS)} s`;
  const set = (value: number) => {
    const clamped = Math.max(-DELAY_LIMIT_MS, Math.min(DELAY_LIMIT_MS, Math.round(value)));
    setProblem(clamped !== Math.round(value) ? limit : null);
    onChange(clamped);
  };
  const apply = () => {
    if (discard.current) {
      discard.current = false;
      setText(null);
      return;
    }
    if (text === null) return;
    const typed = text.trim().replace(/\s*s$/i, "").replace(",", ".");
    const value = typed === "" ? NaN : Number(typed);
    if (Number.isFinite(value)) set(value * 1000);
    else setProblem("Digite um número, como 0,25");
    setText(null);
  };
  const step = "flex h-[26px] w-[26px] items-center justify-center rounded-full text-[#e4e4e8] hover:bg-(--menu-btn-hover)";
  return (
    <>
      <div
        className={`inline-flex shrink-0 items-center rounded-[17px] bg-(--menu-btn) p-0.5 ${
          problem ? "shadow-[0_0_0_1px_var(--menu-err)]" : focused ? "shadow-[0_0_0_1px_var(--menu-accent)]" : ""
        }`}
      >
        <button type="button" className={step} aria-label="Diminuir atraso" onClick={() => set(ms - DELAY_STEP_MS)}>
          <Icon name="minus" className="h-[13px] w-[13px]" />
        </button>
        <input
          ref={field}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          aria-label="Atraso da letra em segundos"
          title="Em segundos: positivo atrasa a letra, negativo adianta"
          aria-invalid={!!problem}
          className="h-[26px] w-[52px] bg-transparent p-0 text-center text-[13px] font-medium text-(--menu-text) tabular-nums outline-none"
          value={text ?? seconds(ms)}
          onFocus={(event) => {
            setFocused(true);
            setText(event.target.value);
            event.target.select();
          }}
          onChange={(event) => {
            setProblem(null);
            setText(event.target.value);
          }}
          onBlur={() => {
            setFocused(false);
            apply();
          }}
          onKeyDown={(event) => {
            event.stopPropagation(); // no TV shortcut while typing here
            if (event.key === "Enter") event.currentTarget.blur();
            else if (event.key === "Escape") {
              discard.current = true;
              setText(null);
              setProblem(null);
              event.currentTarget.blur();
            } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
              event.preventDefault();
              const next = ms + (event.key === "ArrowUp" ? DELAY_STEP_MS : -DELAY_STEP_MS);
              set(next);
              setText(seconds(Math.max(-DELAY_LIMIT_MS, Math.min(DELAY_LIMIT_MS, next))));
              window.setTimeout(() => field.current?.select());
            }
          }}
        />
        <span className="pr-1 text-[12px] text-(--menu-text-3)">s</span>
        <button type="button" className={step} aria-label="Aumentar atraso" onClick={() => set(ms + DELAY_STEP_MS)}>
          <Icon name="plus" className="h-[13px] w-[13px]" />
        </button>
      </div>
      {problem && (
        <p
          role="alert"
          className="absolute right-0 bottom-[calc(100%+6px)] z-10 m-0 rounded-lg bg-(--menu-rail) px-2.5 py-[5px] text-[11px] text-(--menu-err) shadow-[0_0_0_1px_var(--menu-err)]"
        >
          {problem}
        </p>
      )}
    </>
  );
}
