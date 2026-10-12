// "Abrir como TV" (docs/ARCHITECTURE.md, "Como alguém entra"): only the room's owner and the admin see it. The tap
// is what the browser needs before it plays sound, so the audio starts right here, and the TV opens in this same
// page, without a reload, with that audio already on: no "Iniciar" screen.
import { useState } from "react";
import { api } from "../api";
import { navigate } from "../lib/navigate";
import { AudioEngine } from "../player/engine";

// The engine the tap started, for the room it was opened for, until the TV's screen picks it up
let handed: { code: string; engine: Promise<AudioEngine> } | null = null;

/** The audio the tap on "Abrir como TV" started for this room; null when the TV was opened some other way. Reading
 *  it twice gives the same engine. */
export function handedEngine(code: string): Promise<AudioEngine> | null {
  return handed?.code === code ? handed.engine : null;
}

/** The TV's screen has the engine: a later visit to the same room starts its own. */
export function engineTaken(engine: Promise<AudioEngine>): void {
  if (handed?.engine === engine) handed = null;
}

export function OpenTvButton({ code, className }: { code: string; className: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = async () => {
    setBusy(true);
    setError(null);
    const ctx = AudioEngine.context(); // before the first await, while it still counts as the tap
    try {
      await api.roomTv(code);
    } catch (e) {
      void ctx.close().catch(() => undefined);
      setError((e as Error).message);
      setBusy(false);
      return;
    }
    handed = { code, engine: AudioEngine.create(ctx) };
    navigate(`/tv/${code}`);
  };
  return (
    <span className="inline-flex flex-col gap-1">
      <button type="button" className={className} onClick={() => void open()} disabled={busy}>
        Abrir como TV
      </button>
      {error && <span className="text-sm text-red-400">{error}</span>}
    </span>
  );
}
