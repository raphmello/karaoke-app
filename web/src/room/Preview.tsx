// Hear a song before adding it. A video not yet downloaded comes from YouTube through the API (/api/preview); a
// library song plays from /media, instrumental and voice together, so it sounds like the original. One preview
// plays at a time.
import { useEffect, useRef, useState } from "react";
import { formatTime } from "../tv/time";

let stopPlaying: (() => void) | null = null; // the preview playing now, wherever it is on the page

type State = "idle" | "loading" | "playing" | "paused" | "error";
export type PreviewControl = ReturnType<typeof usePreview>;

export function usePreview(videoId: string, local: boolean) {
  const [state, setState] = useState<State>("idle");
  const [clock, setClock] = useState({ position: 0, duration: 0 });
  const audios = useRef<HTMLAudioElement[]>([]);

  // Stable across renders, so "the preview playing now" can be compared and stopped from another row.
  const stop = useRef(() => {
    for (const audio of audios.current) audio.pause();
    setState((s) => (s === "idle" ? s : "paused"));
  }).current;

  useEffect(
    () => () => {
      for (const audio of audios.current) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load(); // let go of the connection
      }
      if (stopPlaying === stop) stopPlaying = null;
    },
    [stop],
  );

  const create = () => {
    const sources = local
      ? [`/media/${videoId}/play/instrumental.opus`, `/media/${videoId}/play/vocals.opus`]
      : [`/api/preview/${videoId}`];
    audios.current = sources.map((src) => {
      const audio = new Audio(src);
      audio.preload = "auto";
      return audio;
    });
    const [main, ...others] = audios.current;
    main.addEventListener("timeupdate", () => {
      setClock({ position: main.currentTime, duration: main.duration || 0 });
      // the voice follows the instrumental; two elements drift apart a little over time
      for (const other of others) if (Math.abs(other.currentTime - main.currentTime) > 0.15) other.currentTime = main.currentTime;
    });
    main.addEventListener("ended", () => setState("paused"));
    main.addEventListener("error", () => setState("error"));
  };

  const play = async () => {
    if (stopPlaying && stopPlaying !== stop) stopPlaying();
    stopPlaying = stop;
    if (!audios.current.length) create();
    setState("loading");
    try {
      await Promise.all(audios.current.map((audio) => audio.play()));
      setState("playing");
    } catch {
      setState("error");
    }
  };

  return {
    state,
    clock,
    toggle: () => (state === "playing" ? stop() : void play()),
    seek: (seconds: number) => {
      for (const audio of audios.current) audio.currentTime = seconds;
    },
  };
}

/** A round play/pause button, at the right of a song's row. */
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
      className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-60 ${
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
        <svg viewBox="0 0 24 24" className="ml-0.5 h-6 w-6" fill="currentColor" aria-hidden="true">
          <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" />
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
