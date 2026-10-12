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

const button = "rounded-lg bg-zinc-800 px-4 py-2 font-semibold hover:bg-zinc-700 disabled:opacity-40";

export function CreateRoomButton({
  asHost,
  opensTv = false,
  onCreated,
}: {
  asHost: boolean;
  opensTv?: boolean; // the new room's TV opens in this page
  onCreated?: (room: Room) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950" onClick={() => setOpen(true)}>
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

  const field = "rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-base text-zinc-100 outline-none focus:border-amber-400";
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
        className="flex w-full max-w-md flex-col gap-4 rounded-2xl bg-zinc-900 p-6 text-left ring-1 ring-zinc-700"
      >
        <h2 id="create-room-title" className="text-xl font-bold">
          Criar sala
        </h2>
        <label className="flex flex-col gap-1 text-sm text-zinc-400">
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
        <label className="flex flex-col gap-1 text-sm text-zinc-400">
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
          <span className="text-xs text-zinc-500">
            Com senha, só entra e só abre a TV quem souber. Sem ela, a sala é pública.
          </span>
        </label>
        {!asHost && (
          <label className="flex flex-col gap-1 text-sm text-zinc-400">
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
        <p className="text-sm text-zinc-500">A sala some sozinha 24 h depois de criada.</p>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className={button} onClick={onClose}>
            Cancelar
          </button>
          <button
            className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950 disabled:opacity-50"
            disabled={busy || !name.trim() || (!asHost && !nickname.trim())}
          >
            Criar sala
          </button>
        </div>
      </form>
    </div>
  );
}
