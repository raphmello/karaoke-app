// /j/<code>: the link in the QR and in the list of rooms. First the choice: a guest picks a nickname (and types the
// room's password, when it has one) and gets an anonymous cookie (no account); the admin types the PIN and goes to
// the management screen (/host).
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";
import { api, type RoomInfo } from "../api";
import { HostLogin } from "../room/HostLogin";
import { loadNickname, saveNickname } from "./identity";

export function JoinPage({ code }: { code: string }) {
  const [as, setAs] = useState<"guest" | "admin" | null>(null);
  const room = useQuery({ queryKey: ["room", code], queryFn: () => api.room(code) });
  if (room.isError) {
    return (
      <main className="flex min-h-full items-center justify-center px-4 py-8">
        <div className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-zinc-900 p-6 text-center">
          <h1 className="text-2xl font-bold">Sala não encontrada</h1>
          <p className="text-zinc-400">A sala {code.toUpperCase()} foi encerrada ou expirou.</p>
          <a className="rounded-lg bg-amber-400 px-4 py-3 font-bold text-zinc-950" href="/">
            Ver as salas abertas
          </a>
        </div>
      </main>
    );
  }
  if (as === "admin") {
    return <HostLogin title="Entrar como admin" onDone={() => location.assign("/host")} onBack={() => setAs(null)} />;
  }
  if (as === "guest" && room.data) return <GuestJoin room={room.data} onBack={() => setAs(null)} />;
  const title = room.data?.name ?? `Sala ${code.toUpperCase()}`;
  return (
    <main className="flex min-h-full items-center justify-center px-4 py-8">
      <div className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-zinc-900 p-6">
        <h1 className="text-2xl font-bold">Entrar no karaokê</h1>
        <p className="text-zinc-400">
          {room.data?.protected ? "🔒 " : ""}
          {title}. Como você quer entrar?
        </p>
        <Choice
          title="Convidado"
          detail="Escolha músicas e entre na fila"
          primary
          disabled={!room.data}
          onClick={() => (room.data?.joined ? location.assign(`/m/${code}`) : setAs("guest"))}
        />
        <Choice title="Admin" detail="Gerencie as salas, a fila e o player (pede o PIN)" onClick={() => setAs("admin")} />
        <a className="text-center text-sm text-zinc-400 underline" href="/">
          Ver as salas abertas
        </a>
      </div>
    </main>
  );
}

function Choice({
  title,
  detail,
  primary,
  disabled,
  onClick,
}: {
  title: ReactNode;
  detail: string;
  primary?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex flex-col items-start rounded-xl px-4 py-3 text-left disabled:opacity-50 ${
        primary ? "bg-amber-400 text-zinc-950" : "bg-zinc-800 text-zinc-100 hover:bg-zinc-700"
      }`}
    >
      <span className="text-lg font-bold">{title}</span>
      <span className={`text-sm ${primary ? "text-zinc-800" : "text-zinc-400"}`}>{detail}</span>
    </button>
  );
}

function GuestJoin({ room, onBack }: { room: RoomInfo; onBack: () => void }) {
  const [nickname, setNickname] = useState(loadNickname);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const guest = await api.join(room.code, nickname.trim(), room.protected ? password : undefined);
      saveNickname(guest.nickname);
      location.assign(`/m/${guest.room_code}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const field = "rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-lg outline-none focus:border-amber-400";
  return (
    <main className="flex min-h-full items-center justify-center px-4 py-8">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-zinc-900 p-6">
        <h1 className="text-2xl font-bold">Entrar no karaokê</h1>
        <p className="text-zinc-400">{room.name ?? `Sala ${room.code}`}. Como você quer aparecer na fila?</p>
        <input
          autoFocus
          maxLength={40}
          className={field}
          placeholder="Seu apelido"
          value={nickname}
          onChange={(event) => setNickname(event.target.value)}
          aria-label="Apelido"
        />
        {room.protected && (
          <input
            type="password"
            maxLength={64}
            className={field}
            placeholder="Senha da sala"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-label="Senha da sala"
          />
        )}
        {error && <p className="text-red-400">{error}</p>}
        <button
          className="rounded-lg bg-amber-400 px-4 py-3 text-lg font-bold text-zinc-950 disabled:opacity-50"
          disabled={busy || !nickname.trim() || (room.protected && !password)}
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
