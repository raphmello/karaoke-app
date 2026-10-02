// /host: the host opens tonight's room and runs the queue and the player. The panel of jobs, disk and library comes
// in phase 5.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { ApiError, type ActiveRoom, api } from "../api";
import { songTitle } from "../lib/queue";
import { HostLogin } from "../room/HostLogin";
import { QueueList } from "../room/QueueList";
import { useRoom } from "../room/useRoom";
import { formatTime } from "../tv/time";

const button = "rounded-lg bg-zinc-800 px-4 py-2 font-semibold hover:bg-zinc-700 disabled:opacity-40";

export function HostPage() {
  const queryClient = useQueryClient();
  const active = useQuery({ queryKey: ["active-room"], queryFn: api.activeRoom });
  const status = active.error instanceof ApiError ? active.error.status : null;

  if (status === 401) {
    return <HostLogin title="Host do karaokê" onDone={() => void queryClient.invalidateQueries({ queryKey: ["active-room"] })} />;
  }
  if (active.isPending) return <p className="p-8 text-zinc-400">Carregando…</p>;
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
      <h1 className="text-2xl font-bold">Host do karaokê</h1>
      {active.data ? (
        <Room room={active.data} />
      ) : status === 404 ? (
        <p className="text-zinc-400">Nenhuma sala aberta.</p>
      ) : (
        <p className="text-red-400">{active.error?.message}</p>
      )}
      <OpenRoom replacing={Boolean(active.data)} onOpened={() => void queryClient.invalidateQueries({ queryKey: ["active-room"] })} />
    </main>
  );
}

function OpenRoom({ replacing, onOpened }: { replacing: boolean; onOpened: () => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (replacing && !confirm("Abrir uma sala nova encerra a atual: o QR antigo para de funcionar. Continuar?")) return;
    try {
      await api.openRoom(name.trim());
      setName("");
      onOpened();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2 rounded-xl bg-zinc-900 p-4">
      <input
        className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 outline-none focus:border-amber-400"
        placeholder="Nome da noite (opcional)"
        maxLength={80}
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <button className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950">{replacing ? "Abrir sala nova" : "Abrir sala"}</button>
      {error && <p className="w-full text-sm text-red-400">{error}</p>}
    </form>
  );
}

function Room({ room }: { room: ActiveRoom }) {
  const live = useRoom(room.code);
  const [error, setError] = useState<string | null>(null);
  const playing = live.entries?.find((entry) => entry.id === live.playerState?.entry_id);
  const control = async (action: "play" | "pause" | "skip") => {
    setError(null);
    try {
      await api.player(room.code, action);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <section className="rounded-xl bg-zinc-900 p-4">
        <p className="text-sm text-zinc-400">{room.name ?? "Sala aberta"}</p>
        <p className="text-3xl font-bold tracking-widest">{room.code}</p>
        <p className="text-sm text-zinc-400">
          Os convidados entram pelo QR da TV ou em <span className="text-zinc-200">{room.join_path}</span>
          {!live.connected && " · reconectando…"}
        </p>
      </section>

      <section className="flex flex-col gap-3 rounded-xl bg-zinc-900 p-4">
        <p className="text-sm text-zinc-400">Tocando agora</p>
        <p className="text-lg font-semibold">
          {playing ? `${songTitle(playing.song)} · ${playing.singer_name ?? playing.added_by}` : "Nada"}
          {live.playerState?.entry_id ? (
            <span className="ml-2 text-sm text-zinc-400">
              {formatTime(live.playerState.position)}
              {live.playerState.paused ? " · pausada" : ""}
            </span>
          ) : null}
        </p>
        <div className="flex flex-wrap gap-2">
          <button className={button} onClick={() => control("play")}>
            Tocar
          </button>
          <button className={button} onClick={() => control("pause")}>
            Pausar
          </button>
          <button className={button} onClick={() => control("skip")}>
            Pular
          </button>
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Fila</h2>
        {live.entries ? (
          <QueueList code={room.code} entries={live.entries} progress={live.progress} isHost />
        ) : (
          <p className="text-zinc-400">Carregando a fila…</p>
        )}
      </section>
    </>
  );
}
