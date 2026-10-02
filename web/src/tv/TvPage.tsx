import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useRef, useState } from "react";
import { api, type Song } from "../api";
import { AudioEngine } from "../player/engine";
import { Library } from "./Library";
import { PlayerScreen } from "./PlayerScreen";

/** /tv: the TV logs in with the host's PIN (the TV is on the host's PC), then picks and plays songs. */
export function TvPage() {
  const queryClient = useQueryClient();
  const [needsLogin, setNeedsLogin] = useState(false);
  const [song, setSong] = useState<Song | null>(null);
  const [engine, setEngine] = useState<AudioEngine | null>(null);
  const [error, setError] = useState<string | null>(null);
  const creating = useRef<Promise<AudioEngine> | null>(null);

  // The audio starts from this click: browsers allow sound only after the user interacts with the page.
  const pick = async (picked: Song) => {
    setError(null);
    try {
      creating.current ??= AudioEngine.create();
      setEngine(await creating.current);
      setSong(picked);
    } catch (e) {
      creating.current = null;
      setError(`O áudio não pôde ser iniciado: ${(e as Error).message}`);
    }
  };
  const exit = useCallback(() => setSong(null), []);

  if (needsLogin) {
    return (
      <Login
        onDone={() => {
          setNeedsLogin(false);
          void queryClient.invalidateQueries();
        }}
      />
    );
  }
  if (song && engine) return <PlayerScreen key={song.video_id} song={song} engine={engine} onExit={exit} />;
  return (
    <>
      {error && <p className="bg-red-950 px-6 py-3 text-red-200">{error}</p>}
      <Library onPick={pick} onUnauthorized={() => setNeedsLogin(true)} />
    </>
  );
}

function Login({ onDone }: { onDone: () => void }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.hostLogin(pin);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex h-full items-center justify-center px-4">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-zinc-900 p-8">
        <h1 className="text-2xl font-bold">Karaokê na TV</h1>
        <p className="text-zinc-400">Digite o PIN do host, definido no arquivo .env.</p>
        <input
          type="password"
          inputMode="numeric"
          autoFocus
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-xl outline-none focus:border-amber-400"
          value={pin}
          onChange={(event) => setPin(event.target.value)}
          aria-label="PIN do host"
        />
        {error && <p className="text-red-400">{error}</p>}
        <button
          className="rounded-lg bg-amber-400 px-4 py-3 text-lg font-bold text-zinc-950 disabled:opacity-50"
          disabled={busy || !pin}
        >
          Entrar
        </button>
      </form>
    </main>
  );
}
