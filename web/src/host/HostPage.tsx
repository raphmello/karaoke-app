// /host: the host runs every open room (docs/ARCHITECTURE.md, "Salas"): creates and deletes rooms and, in the one
// picked, the queue and the player; manages the library; and watches the jobs and the disk. /host?sala=<code> opens
// with that room picked (the list's "Gerenciar").
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, onSessionLost, retryWhileRestarting, type RoomInfo } from "../api";
import { AddSong } from "../room/AddSongs";
import { CreateRoomButton } from "../room/CreateRoom";
import { DeleteRoomButton } from "../room/DeleteRoom";
import { ExpiresIn } from "../room/Expiry";
import { HostLogin } from "../room/HostLogin";
import { PlayerControls } from "../room/PlayerControls";
import { QueueList } from "../room/QueueList";
import { type RoomTab, RoomTabs } from "../room/RoomTabs";
import { useRoom } from "../room/useRoom";
import { LibraryAdmin } from "./LibraryAdmin";
import { Panel } from "./Panel";

export function HostPage() {
  const queryClient = useQueryClient();
  // Only the host's cookie opens this screen: the TV's (TV_PIN) reads the rooms too, so that is not the check
  const host = useQuery({ queryKey: ["host-check"], queryFn: api.hostCheck, ...retryWhileRestarting });
  const hostStatus = host.error instanceof ApiError ? host.error.status : null;
  const [lost, setLost] = useState(false);
  useEffect(() => onSessionLost(() => setLost(true)), []);

  if (hostStatus === 401 || lost) {
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
  if (host.isPending) return <p className="p-8 text-zinc-400">Carregando…</p>;
  return <HostTabs />;
}

type Tab = "room" | "library" | "panel";
const TABS: [Tab, string][] = [["room", "Salas"], ["library", "Gerenciar Acervo"], ["panel", "Painel"]];

function HostTabs() {
  const [tab, setTab] = useState<Tab>("room");
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-bold">Host do karaokê</h1>
          <a className="text-sm text-zinc-400 underline hover:text-zinc-200" href="/">
            Ver salas
          </a>
        </div>
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
      {tab === "room" && <Rooms />}
    </main>
  );
}

/** Every open room as a chip, and the one picked below them. The pick lives in the address, so a reload keeps it. */
function Rooms() {
  const rooms = useQuery({ queryKey: ["rooms"], queryFn: api.rooms, ...retryWhileRestarting, refetchInterval: 15000 });
  const [picked, setPicked] = useState<string | null>(
    () => new URLSearchParams(location.search).get("sala")?.toUpperCase() ?? null,
  );
  const pick = useCallback((code: string | null) => {
    setPicked(code);
    history.replaceState(null, "", code ? `/host?sala=${code}` : "/host");
  }, []);
  const list = rooms.data ?? [];
  // A room that is gone (removed or expired) is no longer picked; with one room only, it is
  const room = list.find((r) => r.code === picked) ?? (list.length === 1 ? list[0] : null);

  return (
    <>
      <section className="flex flex-col gap-3 rounded-xl bg-zinc-900 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-zinc-400">
            {rooms.isPending
              ? "Carregando as salas…"
              : rooms.isError
                ? "Não foi possível carregar as salas. Tentando de novo…"
                : list.length === 0
                  ? "Nenhuma sala aberta."
                  : `${list.length} ${list.length === 1 ? "sala aberta" : "salas abertas"}`}
          </p>
          <CreateRoomButton asHost onCreated={(created) => pick(created.code)} />
        </div>
        {list.length > 1 && (
          <div className="flex flex-wrap gap-2">
            {list.map((r) => (
              <button
                key={r.code}
                onClick={() => pick(r.code)}
                className={`rounded-lg px-3 py-2 text-left text-sm font-semibold ${
                  r.code === room?.code ? "bg-amber-400 text-zinc-950" : "bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
                }`}
              >
                {r.protected && "🔒 "}
                {r.name ?? r.code}
              </button>
            ))}
          </div>
        )}
        {list.length > 1 && !room && <p className="text-sm text-zinc-500">Escolha uma sala para gerenciar.</p>}
      </section>
      {room && <Room key={room.code} room={room} onGone={() => pick(null)} />}
    </>
  );
}

function Room({ room, onGone }: { room: RoomInfo; onGone: () => void }) {
  const live = useRoom(room.code);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<RoomTab>("queue");
  // The socket closed because the room is gone (4404) or the session is (a 401 brings back the PIN): check again
  useEffect(() => {
    if (!live.closedWith) return;
    if (live.closedWith === 4404) onGone();
    void queryClient.invalidateQueries({ queryKey: ["rooms"] });
    // onGone is left out: once per close, not once per render of the parent
  }, [live.closedWith, queryClient]);

  return (
    <>
      <section className="flex flex-col gap-3 rounded-xl bg-zinc-900 p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm text-zinc-400">
              {room.protected && "🔒 "}
              {room.name ?? "Sala aberta"} · {room.owner === "Host" ? "do host" : `de ${room.owner}`} ·{" "}
              <ExpiresIn when={room.expires_at} />
            </p>
            <p className="text-3xl font-bold tracking-widest">{room.code}</p>
            <p className="text-sm text-zinc-400">
              Os convidados entram pelo QR da TV ou em <span className="text-zinc-200">{room.join_path}</span>
              {!live.connected && " · reconectando…"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <a className="rounded-lg bg-zinc-800 px-4 py-2 font-semibold hover:bg-zinc-700" href={`/tv/${room.code}`}>
              Abrir como TV
            </a>
            <DeleteRoomButton code={room.code} onDeleted={onGone} />
          </div>
        </div>
      </section>

      <PlayerControls code={room.code} entries={live.entries} playerState={live.playerState} />

      <RoomTabs
        value={tab}
        onChange={setTab}
        count={live.entries?.length}
        queue={
          live.entries ? (
            <QueueList code={room.code} entries={live.entries} progress={live.progress} isHost />
          ) : (
            <p className="text-zinc-400">Carregando a fila…</p>
          )
        }
        add={<AddSong code={room.code} />}
      />
    </>
  );
}
