import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { fetchLyrics, type Song } from "../api";
import { clampSemitones, keyLabel, MAX_SEMITONES, MIN_SEMITONES } from "../lib/keys";
import type { AudioEngine } from "../player/engine";
import { Lyrics } from "./Lyrics";
import { formatTime } from "./time";

const DELAY_KEY = "karaoke.tv.delayMs"; // the manual lyrics delay is saved in this browser
const DELAY_STEP_MS = 50;

function loadDelay(): number {
  try {
    return Number(localStorage.getItem(DELAY_KEY)) || 0;
  } catch {
    return 0;
  }
}

function saveDelay(ms: number): void {
  try {
    localStorage.setItem(DELAY_KEY, String(ms));
  } catch {
    // private window: the delay lasts only this session
  }
}

const button =
  "rounded-lg bg-zinc-800 px-4 py-2 text-lg font-semibold hover:bg-zinc-700 disabled:opacity-40 disabled:hover:bg-zinc-800";

export function PlayerScreen({ song, engine, onExit }: { song: Song; engine: AudioEngine; onExit: () => void }) {
  const media = song.media!;
  const lyrics = useQuery({ queryKey: ["lyrics", song.video_id], queryFn: () => fetchLyrics(media.lyrics) });
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [semitones, setSemitones] = useState(0);
  const [guide, setGuide] = useState(0);
  const [delayMs, setDelayMs] = useState(loadDelay);
  const [clock, setClock] = useState({ position: 0, lyrics: 0 });
  const delayRef = useRef(delayMs);
  delayRef.current = delayMs;

  useEffect(() => {
    let cancelled = false;
    engine.setSemitones(0);
    engine.setGuide(0);
    engine
      .load(media)
      .then(async () => {
        if (cancelled) return;
        setLoaded(true);
        await engine.play();
        setPlaying(true);
      })
      .catch((error: Error) => !cancelled && setLoadError(error.message));
    return () => {
      cancelled = true;
      engine.stop();
    };
  }, [engine, media]);

  // The lyrics follow the audio clock, recomputed every frame.
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      if (engine.playing && engine.position() >= engine.duration) {
        engine.stop();
        setPlaying(false);
        onExit();
        return;
      }
      setClock({ position: engine.position(), lyrics: engine.lyricsTime(delayRef.current / 1000) });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [engine, onExit]);

  const changeKey = (n: number) => {
    const value = clampSemitones(n);
    engine.setSemitones(value);
    setSemitones(value);
  };
  const togglePlay = async () => {
    if (engine.playing) {
      engine.pause();
      setPlaying(false);
    } else {
      await engine.play();
      setPlaying(true);
    }
  };
  const changeDelay = (ms: number) => {
    setDelayMs(ms);
    saveDelay(ms);
  };

  // Keyboard, for a TV with a remote or a keyboard: space plays and pauses, arrows change the key.
  const keys = useRef({ togglePlay, changeKey, semitones });
  keys.current = { togglePlay, changeKey, semitones };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement) return;
      const { togglePlay, changeKey, semitones } = keys.current;
      if (event.code === "Space") void togglePlay();
      else if (event.code === "ArrowUp") changeKey(semitones + 1);
      else if (event.code === "ArrowDown") changeKey(semitones - 1);
      else return;
      event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const label = keyLabel(song.original_key, semitones);
  const title = song.track ?? song.title ?? song.video_id;
  const duration = engine.duration || song.duration_s || 0;

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-4 px-6 py-4">
        <div className="min-w-0">
          <p className="truncate text-2xl font-semibold">{title}</p>
          <p className="truncate text-zinc-400">
            {song.artist ?? song.channel}
            {song.lyrics_source === "transcrita" ? " · letra transcrita automaticamente" : ""}
          </p>
        </div>
        <button className={button} onClick={onExit}>
          Voltar ao acervo
        </button>
      </header>

      <main className="flex flex-1 items-center justify-center overflow-hidden px-6">
        {loadError ? (
          <p className="text-2xl text-red-400">Não foi possível carregar a música: {loadError}</p>
        ) : !loaded || lyrics.isPending ? (
          <p className="text-2xl text-zinc-400">Carregando a música…</p>
        ) : (
          <Lyrics lines={lyrics.data?.lines ?? null} t={clock.lyrics} title={title} />
        )}
      </main>

      <footer className="flex flex-col gap-4 bg-zinc-950/80 px-6 py-4">
        <div className="flex items-center gap-4">
          <button className={`${button} w-28`} onClick={togglePlay} disabled={!loaded}>
            {playing ? "Pausar" : "Tocar"}
          </button>
          <span className="w-14 text-right tabular-nums text-zinc-400">{formatTime(clock.position)}</span>
          <input
            type="range"
            className="flex-1 accent-amber-400"
            min={0}
            max={duration || 1}
            step={0.1}
            value={Math.min(clock.position, duration)}
            onChange={(event) => engine.seek(Number(event.target.value))}
            disabled={!loaded}
            aria-label="Posição na música"
          />
          <span className="w-14 tabular-nums text-zinc-400">{formatTime(duration)}</span>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <button className={button} onClick={() => changeKey(semitones - 1)} disabled={semitones <= MIN_SEMITONES}>
              −½ tom
            </button>
            <div className="min-w-64 text-center" aria-live="polite">
              <p className="text-xl font-bold text-amber-300">{label.current}</p>
              {label.original && <p className="text-sm text-zinc-400">{label.original}</p>}
            </div>
            <button className={button} onClick={() => changeKey(semitones + 1)} disabled={semitones >= MAX_SEMITONES}>
              +½ tom
            </button>
            <button className={button} onClick={() => changeKey(0)} disabled={semitones === 0}>
              Voltar ao tom original
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-6 text-zinc-300">
            <label className="flex items-center gap-3">
              Voz guia
              <input
                type="range"
                className="w-32 accent-amber-400"
                min={0}
                max={100}
                step={5}
                value={guide}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  setGuide(value);
                  engine.setGuide(value / 100);
                }}
              />
              <span className="w-12 tabular-nums">{guide}%</span>
            </label>
            <div className="flex items-center gap-2">
              Atraso da letra
              <button className={button} onClick={() => changeDelay(delayMs - DELAY_STEP_MS)} aria-label="Diminuir atraso">
                −
              </button>
              <span className="w-20 text-center tabular-nums">
                {delayMs > 0 ? "+" : ""}
                {delayMs} ms
              </span>
              <button className={button} onClick={() => changeDelay(delayMs + DELAY_STEP_MS)} aria-label="Aumentar atraso">
                +
              </button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
