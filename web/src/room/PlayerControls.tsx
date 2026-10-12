// The room's player, from a screen other than its TV: what plays now, Tocar/Pausar/Pular, the guide voice and the
// TV's delay. The host has it for every room; the room's owner has it on their phone (docs/ARCHITECTURE.md, "Salas").
import { useState } from "react";
import { api, type QueueEntry } from "../api";
import { songTitle } from "../lib/queue";
import { formatTime } from "../tv/time";
import type { PlayerState } from "./useRoom";

const button = "rounded-lg bg-zinc-800 px-4 py-2 font-semibold hover:bg-zinc-700 disabled:opacity-40";

export function PlayerControls({
  code,
  entries,
  playerState,
}: {
  code: string;
  entries: QueueEntry[] | null;
  playerState: PlayerState | null;
}) {
  const [error, setError] = useState<string | null>(null);
  const playing = entries?.find((entry) => entry.id === playerState?.entry_id);
  const control = async (action: "play" | "pause" | "skip") => {
    setError(null);
    try {
      await api.player(code, action);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section className="flex flex-col gap-3 rounded-xl bg-zinc-900 p-4">
      <p className="text-sm text-zinc-400">Tocando agora</p>
      <p className="text-lg font-semibold">
        {playing ? `${songTitle(playing.song)} · ${playing.singer_name ?? playing.added_by}` : "Nada"}
        {playerState?.entry_id ? (
          <span className="ml-2 text-sm text-zinc-400">
            {formatTime(playerState.position)}
            {playerState.paused ? " · pausada" : ""}
          </span>
        ) : null}
      </p>
      <div className="flex flex-wrap gap-2">
        <button className={button} onClick={() => control("play")}>
          Tocar
        </button>
        <button className={button} onClick={() => control("pause")}>
          Pausar
        </button>
        <button className={button} onClick={() => control("skip")}>
          Pular
        </button>
      </div>
      <TvSettings code={code} onError={setError} />
      {error && <p className="text-sm text-red-400">{error}</p>}
    </section>
  );
}

/** Guide voice and the TV's delay, sent to the TV as player.command. */
function TvSettings({ code, onError }: { code: string; onError: (message: string | null) => void }) {
  const [guide, setGuide] = useState(0);
  const [delay, setDelay] = useState(0);
  const send = async (action: "guide" | "delay", value: number) => {
    onError(null);
    try {
      await api.playerValue(code, action, value);
    } catch (e) {
      onError((e as Error).message);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-6 text-sm text-zinc-300">
      <label className="flex items-center gap-3">
        Voz guia
        <input
          type="range"
          className="w-32 accent-amber-400"
          min={0}
          max={100}
          step={5}
          value={guide}
          onChange={(event) => setGuide(Number(event.target.value))}
          onPointerUp={() => send("guide", guide)}
          onKeyUp={() => send("guide", guide)}
        />
        <span className="w-10 tabular-nums">{guide}%</span>
      </label>
      <div className="flex items-center gap-2">
        Atraso da letra na TV
        {[-50, 50].map((step) => (
          <button
            key={step}
            className={button}
            onClick={() => {
              const value = delay + step;
              setDelay(value);
              void send("delay", value);
            }}
          >
            {step < 0 ? "−" : "+"}
          </button>
        ))}
        <span className="w-16 tabular-nums">
          {delay > 0 ? "+" : ""}
          {delay} ms
        </span>
      </div>
    </div>
  );
}
