// /host: the host opens tonight's room and runs the queue and the player; manages the library; and watches the jobs
// and the disk.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { ApiError, type ActiveRoom, api, onSessionLost, retryWhileRestarting } from "../api";
import { songTitle } from "../lib/queue";
import { AddSong } from "../room/AddSongs";
import { HostLogin } from "../room/HostLogin";
import { LibraryAdmin } from "./LibraryAdmin";
import { Panel } from "./Panel";
import { QueueList } from "../room/QueueList";
import { useRoom } from "../room/useRoom";
import { formatTime } from "../tv/time";

const button = "rounded-lg bg-zinc-800 px-4 py-2 font-semibold hover:bg-zinc-700 disabled:opacity-40";

export function HostPage() {
  const queryClient = useQueryClient();
  // Only the host's cookie opens this screen: the TV's (TV_PIN) also reads the active room, so that is not the check
  const host = useQuery({ queryKey: ["host-check"], queryFn: api.hostCheck, ...retryWhileRestarting });
  const active = useQuery({
    queryKey: ["active-room"],
    queryFn: api.activeRoom,
    ...retryWhileRestarting,
    enabled: host.isSuccess,
  });
  const status = active.error instanceof ApiError ? active.error.status : null;
  const hostStatus = host.error instanceof ApiError ? host.error.status : null;
  const [lost, setLost] = useState(false);
  useEffect(() => onSessionLost(() => setLost(true)), []);

  if (hostStatus === 401 || status === 401 || lost) {
    return (
      <HostLogin
        title="Host do karaokê"
        onDone={() => {
          setLost(false);
          void queryClient.invalidateQueries();
        }}
      />
    );
  }
  if (host.isPending || active.isPending) return <p className="p-8 text-zinc-400">Carregando…</p>;
  return <HostTabs active={active.data ?? null} missing={status === 404} error={active.error?.message ?? null} />;
}

type Tab = "room" | "library" | "panel";
const TABS: [Tab, string][] = [["room", "Sala"], ["library", "Acervo"], ["panel", "Painel"]];

function HostTabs({ active, missing, error }: { active: ActiveRoom | null; missing: boolean; error: string | null }) {
  const [tab, setTab] = useState<Tab>("room");
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Host do karaokê</h1>
        <nav className="flex gap-2">
          {TABS.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`rounded-lg px-4 py-2 font-semibold ${tab === id ? "bg-amber-400 text-zinc-950" : "bg-zinc-900 text-zinc-300"}`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      {tab === "library" && <LibraryAdmin />}
      {tab === "panel" && <Panel />}
      {tab === "room" &&
        (active ? (
          <Room key={active.code} room={active} />
        ) : missing ? (
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-zinc-900 p-4">
            <p className="text-zinc-400">Nenhuma sala aberta.</p>
            <OpenRoomButton replacing={false} />
          </section>
        ) : (
          <p className="text-red-400">{error}</p>
        ))}
    </main>
  );
}

/** "Abrir sala" opens a dialog for the night's name (optional). With a room open, it warns that the current one
 *  closes and its QR stops working. */
function OpenRoomButton({ replacing }: { replacing: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950" onClick={() => setOpen(true)}>
        {replacing ? "Abrir sala nova" : "Abrir sala"}
      </button>
      {open && <OpenRoomDialog replacing={replacing} onClose={() => setOpen(false)} />}
    </>
  );
}

function OpenRoomDialog({ replacing, onClose }: { replacing: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [moveQueue, setMoveQueue] = useState(false);
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
      await api.openRoom(name.trim(), replacing && moveQueue);
      await queryClient.invalidateQueries({ queryKey: ["active-room"] });
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <form
        onSubmit={submit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="open-room-title"
        className="flex w-full max-w-md flex-col gap-4 rounded-2xl bg-zinc-900 p-6 ring-1 ring-zinc-700"
      >
        <h2 id="open-room-title" className="text-xl font-bold">
          {replacing ? "Abrir sala nova" : "Abrir sala"}
        </h2>
        <label className="flex flex-col gap-1 text-sm text-zinc-400">
          Nome da sala (opcional)
          <input
            autoFocus
            maxLength={80}
            className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-base text-zinc-100 outline-none focus:border-amber-400"
            placeholder="Ex.: Sexta com os amigos"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        {replacing && (
          <>
            <fieldset className="flex flex-col gap-2 text-sm">
              <legend className="mb-1 text-zinc-400">E a fila da sala atual?</legend>
              <label className="flex items-start gap-2">
                <input type="radio" name="queue" className="mt-1" checked={!moveQueue} onChange={() => setMoveQueue(false)} />
                <span>Começar a sala nova com a fila vazia</span>
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="queue" className="mt-1" checked={moveQueue} onChange={() => setMoveQueue(true)} />
                <span>
                  Levar as músicas que esperam para a sala nova
                  <span className="block text-zinc-500">Nela, só o host poderá remover essas músicas.</span>
                </span>
              </label>
            </fieldset>
            <p className="rounded-lg bg-amber-950 px-3 py-2 text-sm text-amber-200">
              A sala atual será encerrada e o QR Code antigo para de funcionar. Os convidados entram de novo pelo QR
              novo. Se uma música estiver tocando, ela vai até o fim.
            </p>
          </>
        )}
        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className={button} onClick={onClose}>
            Cancelar
          </button>
          <button className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950 disabled:opacity-50" disabled={busy}>
            {replacing ? "Encerrar a atual e abrir" : "Abrir sala"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Room({ room }: { room: ActiveRoom }) {
  const live = useRoom(room.code);
  const queryClient = useQueryClient();
  // The socket closed because the session or the room is gone: check again (a 401 brings back the PIN).
  useEffect(() => {
    if (live.closedWith) void queryClient.invalidateQueries({ queryKey: ["active-room"] });
  }, [live.closedWith, queryClient]);
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
      <section className="flex flex-wrap items-start justify-between gap-4 rounded-xl bg-zinc-900 p-4">
        <div>
          <p className="text-sm text-zinc-400">{room.name ?? "Sala aberta"}</p>
          <p className="text-3xl font-bold tracking-widest">{room.code}</p>
          <p className="text-sm text-zinc-400">
            Os convidados entram pelo QR da TV ou em <span className="text-zinc-200">{room.join_path}</span>
            {!live.connected && " · reconectando…"}
          </p>
        </div>
        <OpenRoomButton replacing />
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
        <TvSettings code={room.code} onError={setError} />
        {error && <p className="text-sm text-red-400">{error}</p>}
      </section>

      <AddSong code={room.code} />

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

/** Guide voice and the TV's delay, sent to the TV as player.command. */
function TvSettings({ code, onError }: { code: string; onError: (message: string | null) => void }) {
  const [guide, setGuide] = useState(0);
  const [delay, setDelay] = useState(0);
  const send = async (action: "guide" | "delay", value: number) => {
    onError(null);
    try {
      await api.playerValue(code, action, value);
    } catch (e) {
      onError((e as Error).message);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-6 text-sm text-zinc-300">
      <label className="flex items-center gap-3">
        Voz guia
        <input
          type="range"
          className="w-32 accent-amber-400"
          min={0}
          max={100}
          step={5}
          value={guide}
          onChange={(event) => setGuide(Number(event.target.value))}
          onPointerUp={() => send("guide", guide)}
          onKeyUp={() => send("guide", guide)}
        />
        <span className="w-10 tabular-nums">{guide}%</span>
      </label>
      <div className="flex items-center gap-2">
        Atraso da letra na TV
        {[-50, 50].map((step) => (
          <button
            key={step}
            className={button}
            onClick={() => {
              const value = delay + step;
              setDelay(value);
              void send("delay", value);
            }}
          >
            {step < 0 ? "−" : "+"}
          </button>
        ))}
        <span className="w-16 tabular-nums">
          {delay > 0 ? "+" : ""}
          {delay} ms
        </span>
      </div>
    </div>
  );
}
