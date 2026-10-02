// /m/<code>: the guest's phone. Search YouTube or the library, add songs (with the key they start in), follow the queue, change the
// key of one's own entries, remove them and answer the transcription question.
import { useEffect, useState } from "react";
import { Library, Search } from "../room/AddSongs";
import { QueueList } from "../room/QueueList";
import { useRoom } from "../room/useRoom";
import { loadNickname } from "./identity";

type Tab = "queue" | "search" | "library";
const TAB_NAMES: Record<Tab, string> = { search: "Buscar", library: "Acervo", queue: "Fila" };

export function PhonePage({ code }: { code: string }) {
  const room = useRoom(code);
  const [tab, setTab] = useState<Tab>("search");
  const [notice, setNotice] = useState<string | null>(null);

  // Without a cookie of this room, the phone joins first.
  useEffect(() => {
    if (room.closedWith === 4401 || room.closedWith === 4403) location.replace(`/j/${code}`);
  }, [room.closedWith, code]);

  const added = (title: string) => {
    setNotice(`"${title}" entrou na fila.`);
    setTab("queue");
    window.setTimeout(() => setNotice(null), 4000);
  };
  const waiting = room.entries?.filter((e) => e.mine && e.status === "awaiting_decision").length ?? 0;

  if (room.closedWith === 4404) {
    return <p className="px-4 py-12 text-center text-zinc-400">Esta sala foi encerrada. Leia o QR Code da TV de novo.</p>;
  }
  return (
    <div className="mx-auto flex min-h-full max-w-xl flex-col">
      <header className="sticky top-0 z-10 bg-[#0b0b12]/95 px-4 pt-4 backdrop-blur">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-bold">Karaokê</h1>
          <span className="text-sm text-zinc-400">
            {loadNickname() || "Convidado"} · sala {code.toUpperCase()}
            {!room.connected && " · reconectando…"}
          </span>
        </div>
        <nav className="mt-3 grid grid-cols-3 gap-2 pb-3">
          {(["search", "library", "queue"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-lg py-2 font-semibold ${tab === t ? "bg-amber-400 text-zinc-950" : "bg-zinc-900 text-zinc-300"}`}
            >
              {TAB_NAMES[t]}
              {t === "queue" && room.entries ? ` (${room.entries.length})` : ""}
            </button>
          ))}
        </nav>
        {waiting > 0 && tab !== "queue" && (
          <button className="mb-3 w-full rounded-lg bg-amber-950 px-3 py-2 text-left text-sm text-amber-200" onClick={() => setTab("queue")}>
            Uma música sua precisa de resposta sobre a letra. Toque para ver.
          </button>
        )}
        {notice && <p className="mb-3 rounded-lg bg-emerald-950 px-3 py-2 text-sm text-emerald-200">{notice}</p>}
      </header>
      <main className="flex-1 px-4 pb-8">
        {tab === "search" ? (
          <Search code={code} onAdded={added} />
        ) : tab === "library" ? (
          <Library code={code} onAdded={added} />
        ) : room.entries ? (
          <QueueList code={code} entries={room.entries} progress={room.progress} isHost={false} />
        ) : (
          <p className="py-8 text-center text-zinc-400">Carregando a fila…</p>
        )}
      </main>
    </div>
  );
}
