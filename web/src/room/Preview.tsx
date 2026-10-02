// Hear a song before adding it. A video not yet downloaded comes from YouTube through the API (/api/preview); a
// library song plays from /media, instrumental and voice together, so it sounds like the original. One preview
// plays at a time.
import { useEffect, useRef, useState } from "react";
import { formatTime } from "../tv/time";

let stopPlaying: (() => void) | null = null; // the preview playing now, wherever it is on the page

type State = "idle" | "loading" | "playing" | "paused" | "error";

export function Preview({ videoId, local }: { videoId: string; local: boolean }) {
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
    [],
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

  const seek = (seconds: number) => {
    for (const audio of audios.current) audio.currentTime = seconds;
  };

  const button = "rounded-lg bg-zinc-800 px-3 py-1.5 text-sm font-semibold hover:bg-zinc-700 disabled:opacity-50";
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <button
        type="button"
        className={button}
        disabled={state === "loading"}
        onClick={() => (state === "playing" ? stop() : void play())}
        aria-label={state === "playing" ? "Pausar a prévia" : "Ouvir a prévia"}
      >
        {state === "playing" ? "❚❚ Pausar" : state === "loading" ? "Carregando…" : "▶ Ouvir"}
      </button>
      {state === "error" && <span className="text-xs text-red-400">Prévia indisponível</span>}
      {(state === "playing" || state === "paused") && clock.duration > 0 && (
        <>
          <input
            type="range"
            className="min-w-0 flex-1 accent-amber-400"
            min={0}
            max={clock.duration}
            step={1}
            value={clock.position}
            onChange={(event) => seek(Number(event.target.value))}
            aria-label="Posição da prévia"
          />
          <span className="shrink-0 text-xs tabular-nums text-zinc-400">{formatTime(clock.position)}</span>
        </>
      )}
    </div>
  );
}
