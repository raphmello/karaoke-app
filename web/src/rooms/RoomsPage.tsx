// /: the open rooms (docs/ARCHITECTURE.md, "Salas"). Anyone sees the list; from it one enters a room (its password,
// when it has one, is asked on the way in), opens its TV, makes a new room or deletes one's own (the host: any).
import { useQuery } from "@tanstack/react-query";
import { api, type RoomInfo } from "../api";
import { CreateRoomButton } from "../room/CreateRoom";
import { DeleteRoomButton } from "../room/DeleteRoom";
import { ExpiresIn } from "../room/Expiry";
import { OpenTvButton } from "../tv/OpenTv";

export function RoomsPage() {
  const rooms = useQuery({ queryKey: ["rooms"], queryFn: api.rooms, refetchInterval: 15000 });
  const host = useQuery({ queryKey: ["tv-is-host"], queryFn: api.isHost, retry: false });
  const isHost = host.data === true;

  return (
    <main className="mx-auto flex min-h-full max-w-2xl flex-col gap-6 px-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Salas de karaokê</h1>
          <p className="text-sm text-zinc-400">
            No celular, use <span className="font-semibold text-zinc-200">Entrar na sala</span>. No aparelho ligado à
            TV, use <span className="font-semibold text-zinc-200">Abrir como TV</span>.
          </p>
        </div>
        {/* Anyone makes a room and becomes its owner; the admin makes it as no one's */}
        <CreateRoomButton asHost={isHost} onCreated={(room) => location.assign(isHost ? `/host?sala=${room.code}` : `/m/${room.code}`)} />
      </header>

      {rooms.isPending ? (
        <p className="text-zinc-400">Carregando as salas…</p>
      ) : rooms.isError ? (
        <p className="text-red-400">Não foi possível carregar as salas. Tentando de novo…</p>
      ) : rooms.data.length === 0 ? (
        <p className="rounded-xl bg-zinc-900 p-6 text-center text-zinc-400">Nenhuma sala aberta agora.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {rooms.data.map((room) => (
            <RoomCard key={room.code} room={room} isHost={isHost} />
          ))}
        </ul>
      )}

      <footer className="mt-auto flex flex-col items-center gap-2 text-center text-sm text-zinc-500">
        <a className="text-zinc-400 underline hover:text-zinc-200" href="/host">
          Acessar como admin
        </a>
      </footer>
    </main>
  );
}

function RoomCard({ room, isHost }: { room: RoomInfo; isHost: boolean }) {
  const enter = room.joined && !isHost ? `/m/${room.code}` : isHost ? `/host?sala=${room.code}` : `/j/${room.code}`;
  return (
    <li className="flex flex-col gap-3 rounded-xl bg-zinc-900 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold">
            {room.protected && <span aria-label="Com senha">🔒 </span>}
            {room.name ?? room.code}
          </p>
          <p className="text-sm text-zinc-400">
            {room.mine ? "Sua sala" : room.owner === "Host" ? "Do host" : `De ${room.owner}`} · sala {room.code} ·{" "}
            <ExpiresIn when={room.expires_at} />
          </p>
          {room.joined && !isHost && !room.mine && <p className="text-xs text-emerald-400">Você está nesta sala</p>}
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <a className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950" href={enter}>
          {isHost ? "Gerenciar" : "Entrar na sala"}
        </a>
        {/* The TV: for everyone; in a room with a password, whoever is not its owner nor the admin types it */}
        <OpenTvButton room={room} className="rounded-lg bg-zinc-800 px-4 py-2 font-semibold hover:bg-zinc-700" />
        {room.manage && (
          <span className="ml-auto">
            <DeleteRoomButton code={room.code} />
          </span>
        )}
      </div>
    </li>
  );
}
