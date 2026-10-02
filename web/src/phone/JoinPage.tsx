// /j/<code>: the link in the QR. The phone picks a nickname and gets an anonymous cookie; no account.
import { type FormEvent, useState } from "react";
import { api } from "../api";
import { loadNickname, saveNickname } from "./identity";

export function JoinPage({ code }: { code: string }) {
  const [nickname, setNickname] = useState(loadNickname);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const guest = await api.join(code, nickname.trim());
      saveNickname(guest.nickname);
      location.assign(`/m/${guest.room_code}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-full items-center justify-center px-4 py-8">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-zinc-900 p-6">
        <h1 className="text-2xl font-bold">Entrar no karaokê</h1>
        <p className="text-zinc-400">Sala {code.toUpperCase()}. Como você quer aparecer na fila?</p>
        <input
          autoFocus
          maxLength={40}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-lg outline-none focus:border-amber-400"
          placeholder="Seu apelido"
          value={nickname}
          onChange={(event) => setNickname(event.target.value)}
          aria-label="Apelido"
        />
        {error && <p className="text-red-400">{error}</p>}
        <button
          className="rounded-lg bg-amber-400 px-4 py-3 text-lg font-bold text-zinc-950 disabled:opacity-50"
          disabled={busy || !nickname.trim()}
        >
          Entrar
        </button>
      </form>
    </main>
  );
}
