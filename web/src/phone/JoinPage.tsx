// /j/<code>: the link in the QR. First the choice: a guest picks a nickname and gets an anonymous cookie (no
// account); the admin types the PIN and goes to the room's management screen (/host).
import { type FormEvent, type ReactNode, useState } from "react";
import { api } from "../api";
import { HostLogin } from "../room/HostLogin";
import { loadNickname, saveNickname } from "./identity";

export function JoinPage({ code }: { code: string }) {
  const [as, setAs] = useState<"guest" | "admin" | null>(null);
  if (as === "admin") {
    return <HostLogin title="Entrar como admin" onDone={() => location.assign("/host")} onBack={() => setAs(null)} />;
  }
  if (as === "guest") return <GuestJoin code={code} onBack={() => setAs(null)} />;
  return (
    <main className="flex min-h-full items-center justify-center px-4 py-8">
      <div className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-zinc-900 p-6">
        <h1 className="text-2xl font-bold">Entrar no karaokê</h1>
        <p className="text-zinc-400">Sala {code.toUpperCase()}. Como você quer entrar?</p>
        <Choice title="Convidado" detail="Escolha músicas e entre na fila" primary onClick={() => setAs("guest")} />
        <Choice title="Admin" detail="Gerencie a sala, a fila e o player (pede o PIN)" onClick={() => setAs("admin")} />
      </div>
    </main>
  );
}

function Choice({
  title,
  detail,
  primary,
  onClick,
}: {
  title: ReactNode;
  detail: string;
  primary?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-start rounded-xl px-4 py-3 text-left ${
        primary ? "bg-amber-400 text-zinc-950" : "bg-zinc-800 text-zinc-100 hover:bg-zinc-700"
      }`}
    >
      <span className="text-lg font-bold">{title}</span>
      <span className={`text-sm ${primary ? "text-zinc-800" : "text-zinc-400"}`}>{detail}</span>
    </button>
  );
}

function GuestJoin({ code, onBack }: { code: string; onBack: () => void }) {
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
        <button type="button" className="text-sm text-zinc-400 underline" onClick={onBack}>
          Voltar
        </button>
      </form>
    </main>
  );
}
