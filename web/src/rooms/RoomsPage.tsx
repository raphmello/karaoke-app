// /: the open rooms (docs/ARCHITECTURE.md, "Salas"; the look, "Telas do celular"). Anyone sees the list; from it one
// enters a room (its password, when it has one, is asked on the way in), opens its TV, makes a new room or deletes
// one's own (the host: any).
import { useQuery } from "@tanstack/react-query";
import { api, type RoomInfo } from "../api";
import { smallAction } from "../phone/MobileShell";
import { CreateRoomButton } from "../room/CreateRoom";
import { DeleteRoomButton } from "../room/DeleteRoom";
import { ExpiresIn } from "../room/Expiry";
import { primary } from "../tv/menu/ui";
import { OpenTvButton } from "../tv/OpenTv";

export function RoomsPage() {
  const rooms = useQuery({ queryKey: ["rooms"], queryFn: api.rooms, refetchInterval: 15000 });
  const host = useQuery({ queryKey: ["tv-is-host"], queryFn: api.isHost, retry: false });
  const isHost = host.data === true;

  return (
    <div className="min-h-dvh bg-(--menu-panel) text-[13px] leading-[1.4] text-(--menu-text)">
      <main className="mx-auto flex min-h-dvh max-w-2xl flex-col gap-4 px-4 py-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-medium">Salas de karaokê</h1>
            <p className="text-(--menu-text-3)">
              No celular, use <span className="font-medium text-(--menu-text)">Entrar na sala</span>. No aparelho
              ligado à TV, use <span className="font-medium text-(--menu-text)">Abrir como TV</span>.
            </p>
          </div>
          {/* Anyone makes a room and becomes its owner (the admin makes it as no one's); its TV opens right away */}
          <CreateRoomButton asHost={isHost} opensTv />
        </header>

        {rooms.isPending ? (
          <p className="text-(--menu-text-3)">Carregando as salas…</p>
        ) : rooms.isError ? (
          <p className="text-(--menu-err)">Não foi possível carregar as salas. Tentando de novo…</p>
        ) : rooms.data.length === 0 ? (
          <p className="rounded-xl bg-(--menu-field) p-6 text-center text-(--menu-text-3)">Nenhuma sala aberta agora.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {rooms.data.map((room) => (
              <RoomCard key={room.code} room={room} isHost={isHost} />
            ))}
          </ul>
        )}

        <footer className="mt-auto flex flex-col items-center gap-2 text-center">
          <a className="text-(--menu-text-3) underline hover:text-(--menu-text)" href="/host">
            Acessar como admin
          </a>
        </footer>
      </main>
    </div>
  );
}

function RoomCard({ room, isHost }: { room: RoomInfo; isHost: boolean }) {
  const enter = room.joined && !isHost ? `/m/${room.code}` : isHost ? `/host?sala=${room.code}` : `/j/${room.code}`;
  return (
    <li className="flex flex-col gap-2.5 rounded-xl bg-(--menu-field) px-[14px] py-3">
      <div className="min-w-0">
        <p className="truncate text-[15px] font-medium">
          {room.protected && <span aria-label="Com senha">🔒 </span>}
          {room.name ?? room.code}
        </p>
        <p className="text-[12px] text-(--menu-text-3)">
          {room.mine ? "Sua sala" : room.owner === "Host" ? "Do host" : `De ${room.owner}`} · sala {room.code} ·{" "}
          <ExpiresIn when={room.expires_at} />
        </p>
        {room.joined && !isHost && !room.mine && <p className="text-[11px] text-(--menu-ok)">Você está nesta sala</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <a className={primary} href={enter}>
          {isHost ? "Gerenciar" : "Entrar na sala"}
        </a>
        {/* The TV: for everyone; in a room with a password, whoever is not its owner nor the admin types it */}
        <OpenTvButton room={room} className={smallAction} />
        {room.manage && (
          <span className="ml-auto">
            <DeleteRoomButton code={room.code} />
          </span>
        )}
      </div>
    </li>
  );
}
