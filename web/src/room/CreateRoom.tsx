// "Criar sala" (docs/ARCHITECTURE.md, "Salas"): anyone makes a room with a name, an optional password (none: a public
// room) and, except the admin, the nickname the room shows as its owner, who goes straight into it. From the list,
// the tap on "Criar sala" also opens the new room's TV, ready, as "Abrir como TV" does (a phone joins by the QR). The
// other rooms stay open.
import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { api, type Room } from "../api";
import { loadNickname, saveNickname } from "../phone/identity";
import { navigate } from "../lib/navigate";
import { AudioEngine } from "../player/engine";
import { becomeTv } from "../tv/OpenTv";

const button = "rounded-[9px] bg-(--menu-btn) px-[14px] py-2 text-[13px] font-medium text-(--menu-text) hover:bg-(--menu-btn-hover) disabled:opacity-40";

export function CreateRoomButton({
  asHost,
  opensTv = false,
  onCreated,
  className = "rounded-[10px] bg-(--menu-accent) px-[14px] py-[9px] text-[13px] font-medium text-(--menu-on-accent) hover:brightness-105 disabled:opacity-60",
}: {
  asHost: boolean;
  className?: string;
  opensTv?: boolean; // the new room's TV opens in this page
  onCreated?: (room: Room) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className={className} onClick={() => setOpen(true)}>
        Criar sala
      </button>
      {open && (
        <CreateRoomDialog asHost={asHost} opensTv={opensTv} onClose={() => setOpen(false)} onCreated={onCreated} />
      )}
    </>
  );
}

function CreateRoomDialog({
  asHost,
  opensTv,
  onClose,
  onCreated,
}: {
  asHost: boolean;
  opensTv: boolean;
  onClose: () => void;
  onCreated?: (room: Room) => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState(loadNickname);
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
    const ctx = opensTv ? AudioEngine.context() : null; // before the first await, while it still counts as the tap
    let room: Room;
    try {
      room = await api.createRoom({
        name: name.trim(),
        password: password || undefined,
        nickname: asHost ? undefined : nickname.trim() || undefined,
      });
    } catch (e) {
      void ctx?.close().catch(() => undefined);
      setError((e as Error).message);
      setBusy(false);
      return;
    }
    if (!asHost) saveNickname(nickname.trim());
    await queryClient.invalidateQueries({ queryKey: ["rooms"] });
    if (ctx) {
      // Its owner (or the admin) needs no password: the TV opens ready. Should that fail, its screen asks for a tap
      await becomeTv(room.code, ctx).catch(() => navigate(`/tv/${room.code}`));
      return;
    }
    onClose();
    onCreated?.(room);
  };

  const field = "rounded-[9px] border border-(--menu-input-line) bg-(--menu-input) px-3 py-2 text-[13px] text-(--menu-text) outline-none placeholder:text-(--menu-text-off) focus:border-(--menu-accent)";
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <form
        onSubmit={submit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-room-title"
        className="flex w-full max-w-md flex-col gap-3.5 rounded-2xl bg-(--menu-field) p-6 text-left text-[13px] text-(--menu-text) shadow-[0_8px_30px_rgba(0,0,0,.5)]"
      >
        <h2 id="create-room-title" className="text-[17px] font-medium">
          Criar sala
        </h2>
        <label className="flex flex-col gap-1 text-[12px] text-(--menu-text-2)">
          Nome da sala
          <input
            autoFocus
            maxLength={80}
            className={field}
            placeholder="Ex.: Aniversário da Ana"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-(--menu-text-2)">
          Senha (opcional)
          <input
            type="password"
            maxLength={64}
            className={field}
            placeholder="Sem senha, qualquer um pode entrar"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
          />
          <span className="text-[11px] text-(--menu-text-3)">
            Com senha, só entra e só abre a TV quem souber. Sem ela, a sala é pública.
          </span>
        </label>
        {!asHost && (
          <label className="flex flex-col gap-1 text-[12px] text-(--menu-text-2)">
            Seu apelido
            <input
              maxLength={40}
              className={field}
              placeholder="Como você aparece na fila"
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
            />
          </label>
        )}
        <p className="text-[12px] text-(--menu-text-3)">A sala some sozinha 24 h depois de criada.</p>
        {error && <p className="text-[12px] text-(--menu-err)">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className={button} onClick={onClose}>
            Cancelar
          </button>
          <button className="rounded-[10px] bg-(--menu-accent) px-[14px] py-[9px] text-[13px] font-medium text-(--menu-on-accent) hover:brightness-105 disabled:opacity-60" disabled={busy || !name.trim() || (!asHost && !nickname.trim())}>
            Criar sala
          </button>
        </div>
      </form>
    </div>
  );
}
