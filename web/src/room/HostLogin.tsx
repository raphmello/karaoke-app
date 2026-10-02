// The host's PIN, set in .env. The TV and the /host screen both log in with it.
import { type FormEvent, useState } from "react";
import { api } from "../api";

export function HostLogin({ title, onDone }: { title: string; onDone: () => void }) {
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
        <h1 className="text-2xl font-bold">{title}</h1>
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
