// Hear a song before adding it, from one audio file, so voice and instrumental can't drift apart: a library song plays
// its original download from /media; a video not yet downloaded comes from YouTube through the API (/api/preview).
// When the browser can't play a source (older iPhones don't play .webm), the next one is tried. One preview plays at
// a time.
import { useEffect, useRef, useState } from "react";
import { formatTime } from "../tv/time";

let stopPlaying: (() => void) | null = null; // the preview playing now, wherever it is on the page

type State = "idle" | "loading" | "playing" | "paused" | "error";
export type PreviewControl = ReturnType<typeof usePreview>;

/** Where a song's preview comes from, best first. */
export function previewSources(videoId: string, original?: string | null): string[] {
  return [...(original ? [original] : []), `/api/preview/${videoId}`];
}

export function usePreview(sources: string[]) {
  const [state, setState] = useState<State>("idle");
  const [clock, setClock] = useState({ position: 0, duration: 0 });
  const audio = useRef<HTMLAudioElement | null>(null);

  // Stable across renders, so "the preview playing now" can be compared and stopped from another row.
  const stop = useRef(() => {
    audio.current?.pause();
    setState((s) => (s === "idle" ? s : "paused"));
  }).current;

  useEffect(
    () => () => {
      if (audio.current) {
        audio.current.pause();
        audio.current.removeAttribute("src");
        audio.current.load(); // let go of the connection
      }
      if (stopPlaying === stop) stopPlaying = null;
    },
    [stop],
  );

  /** Plays the sources in order until one works. */
  const start = async (from: number): Promise<void> => {
    if (from >= sources.length) {
      setState("error");
      return;
    }
    const element = new Audio(sources[from]);
    element.preload = "auto";
    element.addEventListener("timeupdate", () =>
      setClock({ position: element.currentTime, duration: element.duration || 0 }),
    );
    element.addEventListener("ended", () => setState("paused"));
    audio.current = element;
    try {
      await element.play();
      element.addEventListener("error", () => setState("error"));
      setState("playing");
    } catch (e) {
      if ((e as Error).name === "NotAllowedError") {
        setState("error"); // the browser wants a tap: nothing else to try
        return;
      }
      await start(from + 1); // this format or source failed: the next one
    }
  };

  const play = async () => {
    if (stopPlaying && stopPlaying !== stop) stopPlaying();
    stopPlaying = stop;
    setState("loading");
    if (audio.current) {
      try {
        await audio.current.play();
        setState("playing");
        return;
      } catch {
        // fall through and start over
      }
    }
    await start(0);
  };

  return {
    state,
    clock,
    toggle: () => (state === "playing" ? stop() : void play()),
    seek: (seconds: number) => {
      if (audio.current) audio.current.currentTime = seconds;
    },
  };
}

/** A round button with an ear: hear a preview. While it plays, a pause button. */
export function PreviewButton({ preview }: { preview: PreviewControl }) {
  const { state } = preview;
  const label = state === "playing" ? "Pausar a prévia" : state === "error" ? "Prévia indisponível" : "Ouvir a prévia";
  return (
    <button
      type="button"
      onClick={preview.toggle}
      disabled={state === "loading" || state === "error"}
      aria-label={label}
      title={label}
      className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-60 ${
        state === "playing" ? "bg-amber-400 text-zinc-950" : "bg-zinc-800 text-amber-300 hover:bg-zinc-700"
      }`}
    >
      {state === "loading" ? (
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : state === "playing" ? (
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="currentColor" aria-hidden="true">
          <rect x="6" y="5" width="4" height="14" rx="1" />
          <rect x="14" y="5" width="4" height="14" rx="1" />
        </svg>
      ) : state === "error" ? (
        <span className="text-xl font-bold" aria-hidden="true">
          !
        </span>
      ) : (
        <svg
          viewBox="0 0 24 24"
          className="h-6 w-6"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          {/* an ear */}
          <path d="M6.5 9a5.5 5.5 0 0 1 11 0c0 2.6-1.4 3.8-2.6 4.9-1 .9-1.9 1.7-1.9 3.1a3 3 0 0 1-5.7 1.3" />
          <path d="M9.5 9.2a2.5 2.5 0 0 1 5 0c0 1.1-.7 1.6-1.3 2.1" />
        </svg>
      )}
    </button>
  );
}

/** Under the row while the preview plays (or is paused): where it is, and a way to jump. */
export function PreviewBar({ preview }: { preview: PreviewControl }) {
  const { state, clock } = preview;
  if (state === "error") return <p className="mt-2 text-xs text-red-400">Não foi possível tocar a prévia.</p>;
  if ((state !== "playing" && state !== "paused") || clock.duration <= 0) return null;
  return (
    <div className="mt-2 flex items-center gap-2">
      <input
        type="range"
        className="min-w-0 flex-1 accent-amber-400"
        min={0}
        max={clock.duration}
        step={1}
        value={clock.position}
        onChange={(event) => preview.seek(Number(event.target.value))}
        aria-label="Posição da prévia"
      />
      <span className="shrink-0 text-xs tabular-nums text-zinc-400">
        {formatTime(clock.position)} / {formatTime(clock.duration)}
      </span>
    </div>
  );
}
