// /m/<code>: the guest's phone. Its one tab, "Sala", has the same two sub-tabs as the TV's menu and the host's
// screen: "Adicionar Música" (search YouTube or the library and add songs, with the key they start in) and "Fila"
// (follow the queue, change the key of one's own entries, remove them and answer the transcription question).
// The room's owner also runs its queue and, above it, the player, may delete the room and opens it as the TV ("Abrir
// como TV"); "Ver salas" goes back to the list.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, onSessionLost } from "../api";
import { AddSong } from "../room/AddSongs";
import { DeleteRoomButton } from "../room/DeleteRoom";
import { ExpiresIn } from "../room/Expiry";
import { OpenTvButton } from "../tv/OpenTv";
import { PlayerControls } from "../room/PlayerControls";
import { QueueList } from "../room/QueueList";
import { type RoomTab, RoomTabsNav } from "../room/RoomTabs";
import { useRoom } from "../room/useRoom";
import { loadNickname } from "./identity";

export function PhonePage({ code }: { code: string }) {
  const room = useRoom(code);
  const info = useQuery({ queryKey: ["room", code], queryFn: () => api.room(code) });
  const [tab, setTab] = useState<RoomTab>("add"); // a guest comes to add a song
  const [notice, setNotice] = useState<string | null>(null);

  // Without a cookie of this room, the phone joins first: on a closed socket or any request the API refuses.
  useEffect(() => {
    if (room.closedWith === 4401 || room.closedWith === 4403) location.replace(`/j/${code}`);
  }, [room.closedWith, code]);
  useEffect(() => onSessionLost(() => location.replace(`/j/${code}`)), [code]);

  const added = (title: string) => {
    setNotice(`"${title}" entrou na fila.`); // the phone stays where it is: only the notice
    window.setTimeout(() => setNotice(null), 4000);
  };
  const waiting = room.entries?.filter((e) => e.mine && e.status === "awaiting_decision").length ?? 0;

  if (room.closedWith === 4404) {
    return (
      <div className="flex flex-col items-center gap-4 px-4 py-12 text-center">
        <p className="text-zinc-400">Esta sala foi encerrada.</p>
        <a className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950" href="/">
          Ver salas
        </a>
      </div>
    );
  }
  return (
    <div className="mx-auto flex min-h-full max-w-xl flex-col">
      {/* Solid, so the list never shows through it while scrolling */}
      <header className="sticky top-0 z-10 border-b border-zinc-800 bg-[#0b0b12] px-4 pt-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-bold">{info.data?.name ?? "Karaokê"}</h1>
            <p className="text-sm text-zinc-400">
              {loadNickname() || "Convidado"}
              {info.data?.mine ? " · dono da sala" : ""} · sala {code.toUpperCase()}
              {info.data && (
                <>
                  {" · "}
                  <ExpiresIn when={info.data.expires_at} />
                </>
              )}
              {!room.connected && " · reconectando…"}
            </p>
          </div>
          <a className="shrink-0 rounded-lg px-2 py-1 text-sm text-zinc-400 underline hover:text-zinc-200" href="/">
            Ver salas
          </a>
        </div>
        {info.data?.manage && (
          <div className="mt-3 flex flex-wrap items-start gap-2">
            <span className="flex-1 [&>span]:w-full">
              <OpenTvButton
                code={code}
                className="w-full rounded-lg bg-zinc-800 px-3 py-2 text-center text-sm font-semibold hover:bg-zinc-700"
              />
            </span>
            <DeleteRoomButton code={code} onDeleted={() => location.assign("/")} />
          </div>
        )}
        <div className="mt-3 pb-3">
          <p className="mb-2 text-sm font-semibold tracking-widest text-amber-300 uppercase">Sala</p>
          <RoomTabsNav value={tab} onChange={setTab} count={room.entries?.length} />
        </div>
        {waiting > 0 && tab !== "queue" && (
          <button className="mb-3 w-full rounded-lg bg-amber-950 px-3 py-2 text-left text-sm text-amber-200" onClick={() => setTab("queue")}>
            Uma música sua precisa de resposta sobre a letra. Toque para ver.
          </button>
        )}
        {notice && <p className="mb-3 rounded-lg bg-emerald-950 px-3 py-2 text-sm text-emerald-200">{notice}</p>}
      </header>
      <main className="flex-1 px-4 pt-4 pb-8">
        {tab === "add" ? (
          <AddSong code={code} onAdded={added} />
        ) : room.entries ? (
          <div className="flex flex-col gap-4">
            {info.data?.manage && <PlayerControls code={code} entries={room.entries} playerState={room.playerState} />}
            <QueueList code={code} entries={room.entries} progress={room.progress} isHost={info.data?.manage ?? false} />
          </div>
        ) : (
          <p className="py-8 text-center text-zinc-400">Carregando a fila…</p>
        )}
      </main>
    </div>
  );
}
