// "Abrir como TV" (docs/ARCHITECTURE.md, "Como alguém entra"): for everyone. In a room with a password, whoever is
// not its owner nor the admin types the password in a small dialog first. The tap that opens the TV (the button's, or
// the dialog's "Abrir") is what the browser needs before it plays sound, so the audio starts right there, and the TV
// opens in this same page, without a reload, with that audio already on: no "Iniciar" screen.
import { type FormEvent, useEffect, useState } from "react";
import { api, type RoomInfo } from "../api";
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

/** Becomes the room's TV and moves to it, from inside a tap. Throws what the API said, with the audio dropped. */
async function openTv(code: string, password?: string): Promise<void> {
  await becomeTv(code, AudioEngine.context(), password); // the context before the first await, while it is the tap
}

/** Becomes the room's TV, with audio a tap already started (`AudioEngine.context()`), and moves to it without a
 *  reload. Throws what the API said, with the audio dropped. */
export async function becomeTv(code: string, ctx: AudioContext, password?: string): Promise<void> {
  try {
    await api.roomTv(code, password);
  } catch (e) {
    void ctx.close().catch(() => undefined);
    throw e;
  }
  handed = { code, engine: AudioEngine.create(ctx) };
  navigate(`/tv/${code}`);
}

export function OpenTvButton({ room, className }: { room: RoomInfo; className: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  // The owner, the admin, a TV of this room already, or a room without a password: nothing to ask
  const needsPassword = room.protected && !room.manage && !room.tv;

  const open = async () => {
    if (needsPassword) {
      setAsking(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await openTv(room.code);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex flex-col gap-1">
      <button type="button" className={className} onClick={() => void open()} disabled={busy}>
        Abrir como TV
      </button>
      {error && <span className="text-sm text-red-400">{error}</span>}
      {asking && <PasswordDialog room={room} onClose={() => setAsking(false)} />}
    </span>
  );
}

function PasswordDialog({ room, onClose }: { room: RoomInfo; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await openTv(room.code, password);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <form
        onSubmit={submit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="open-tv-title"
        className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-zinc-900 p-6 text-left ring-1 ring-zinc-700"
      >
        <h2 id="open-tv-title" className="text-xl font-bold">
          Abrir {room.name ?? `a sala ${room.code}`} como TV
        </h2>
        <p className="text-sm text-zinc-400">Digite a senha da sala.</p>
        <input
          type="password"
          autoFocus
          maxLength={64}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-base text-zinc-100 outline-none focus:border-amber-400"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-label="Senha da sala"
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="rounded-lg bg-zinc-800 px-4 py-2 font-semibold hover:bg-zinc-700" onClick={onClose}>
            Cancelar
          </button>
          <button
            className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950 disabled:opacity-50"
            disabled={busy || !password}
          >
            Abrir
          </button>
        </div>
      </form>
    </div>
  );
}
