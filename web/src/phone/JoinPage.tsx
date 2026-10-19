// /j/<code>: the link in the QR and in the list of rooms. First the choice: a guest picks a nickname (and types the
// room's password, when it has one) and gets an anonymous cookie (no account); the admin types the PIN and goes to
// the management screen (/host). The look is the TV menu's (docs/ARCHITECTURE.md, "Telas do celular").
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, type RoomInfo } from "../api";
import { HostLogin } from "../room/HostLogin";
import { Icon, type IconName } from "../tv/menu/icons";
import { EntryCard, entryInput, entryLink, entryPrimary } from "./EntryCard";
import { loadNickname, saveNickname } from "./identity";

export function JoinPage({ code }: { code: string }) {
  const [as, setAs] = useState<"guest" | "admin" | null>(null);
  const room = useQuery({ queryKey: ["room", code], queryFn: () => api.room(code) });
  if (room.isError) {
    return (
      <EntryCard title="Sala não encontrada" prompt={`A sala ${code.toUpperCase()} foi encerrada ou expirou.`}>
        <a className={`${entryPrimary} text-center`} href="/">
          Ver as salas abertas
        </a>
      </EntryCard>
    );
  }
  if (as === "admin") {
    return <HostLogin title="Entrar como admin" onDone={() => location.assign("/host")} onBack={() => setAs(null)} />;
  }
  if (as === "guest" && room.data) return <GuestJoin room={room.data} onBack={() => setAs(null)} />;
  const title = room.data?.name ?? `Sala ${code.toUpperCase()}`;
  return (
    <EntryCard title="Entrar no karaokê" prompt={`${room.data?.protected ? "🔒 " : ""}${title}. Como você quer entrar?`}>
      <Choice
        icon="mic"
        title="Convidado"
        detail="Escolha músicas e entre na fila"
        primary
        disabled={!room.data}
        onClick={() => (room.data?.joined ? location.assign(`/m/${code}`) : setAs("guest"))}
      />
      <Choice icon="settings" title="Admin" detail="Gerencie as salas, a fila e o player (pede o PIN)" onClick={() => setAs("admin")} />
      <a className={entryLink} href="/">
        Ver as salas abertas
      </a>
    </EntryCard>
  );
}

function Choice({
  icon,
  title,
  detail,
  primary,
  disabled,
  onClick,
}: {
  icon: IconName;
  title: string;
  detail: string;
  primary?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-3 rounded-xl px-4 py-3 text-left disabled:opacity-50 ${
        primary ? "bg-(--menu-accent) text-(--menu-on-accent)" : "bg-(--menu-btn) text-(--menu-text) hover:bg-(--menu-btn-hover)"
      }`}
    >
      <Icon name={icon} className="h-[22px] w-[22px]" />
      <span className="flex flex-col">
        <span className="text-[15px] font-medium">{title}</span>
        <span className={`text-[12px] ${primary ? "text-[#3a3a3a]" : "text-(--menu-text-3)"}`}>{detail}</span>
      </span>
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

  return (
    <EntryCard
      title="Entrar no karaokê"
      prompt={`${room.name ?? `Sala ${room.code}`}. Como você quer aparecer na fila?`}
      onSubmit={submit}
    >
      <input
        autoFocus
        maxLength={40}
        className={entryInput}
        placeholder="Seu apelido"
        value={nickname}
        onChange={(event) => setNickname(event.target.value)}
        aria-label="Apelido"
      />
      {room.protected && (
        <input
          type="password"
          maxLength={64}
          className={entryInput}
          placeholder="Senha da sala"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-label="Senha da sala"
        />
      )}
      {error && <p className="text-[13px] text-(--menu-err)">{error}</p>}
      <button className={entryPrimary} disabled={busy || !nickname.trim() || (room.protected && !password)}>
        Entrar
      </button>
      <button type="button" className={entryLink} onClick={onBack}>
        Voltar
      </button>
    </EntryCard>
  );
}
