// "Criar sala" (docs/ARCHITECTURE.md, "Salas"): anyone makes a room with a name, an optional password (none: a public
// room) and, except the admin, the nickname the room shows as its owner, who goes straight into it. The other rooms
// stay open.
import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { api, type Room } from "../api";
import { loadNickname, saveNickname } from "../phone/identity";

const button = "rounded-lg bg-zinc-800 px-4 py-2 font-semibold hover:bg-zinc-700 disabled:opacity-40";

export function CreateRoomButton({ asHost, onCreated }: { asHost: boolean; onCreated?: (room: Room) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950" onClick={() => setOpen(true)}>
        Criar sala
      </button>
      {open && <CreateRoomDialog asHost={asHost} onClose={() => setOpen(false)} onCreated={onCreated} />}
    </>
  );
}

function CreateRoomDialog({
  asHost,
  onClose,
  onCreated,
}: {
  asHost: boolean;
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
    try {
      const room = await api.createRoom({
        name: name.trim(),
        password: password || undefined,
        nickname: asHost ? undefined : nickname.trim() || undefined,
      });
      if (!asHost) saveNickname(nickname.trim());
      await queryClient.invalidateQueries({ queryKey: ["rooms"] });
      onClose();
      onCreated?.(room);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
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
            Com senha, só entra quem souber. Sem ela, a sala é pública. A TV, só você e o admin abrem.
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
