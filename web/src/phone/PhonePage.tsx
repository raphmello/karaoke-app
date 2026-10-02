// /m/<code>: the guest's phone. Search YouTube or the library, add songs (with the key they start in), follow the queue, change the
// key of one's own entries, remove them and answer the transcription question.
import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { api, type SearchResult } from "../api";
import { clampSemitones, MAX_SEMITONES, MIN_SEMITONES, signed } from "../lib/keys";
import { songTitle } from "../lib/queue";
import { QueueList } from "../room/QueueList";
import { useRoom } from "../room/useRoom";
import { formatTime } from "../tv/time";
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

function Search({ code, onAdded }: { code: string; onAdded: (title: string) => void }) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<SearchResult | null>(null);
  const results = useQuery({ queryKey: ["search", q], queryFn: () => api.search(q), enabled: q.length > 0 });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setPicked(null);
    setQ(text.trim());
  };

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={submit} className="flex gap-2">
        <input
          className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 outline-none focus:border-amber-400"
          placeholder="Música ou artista"
          value={text}
          onChange={(event) => setText(event.target.value)}
          enterKeyHint="search"
          aria-label="Buscar no YouTube"
        />
        <button className="rounded-lg bg-zinc-800 px-4 font-semibold" disabled={!text.trim()}>
          Buscar
        </button>
      </form>
      {results.isFetching && <p className="text-zinc-400">Buscando…</p>}
      {results.isError && <p className="text-red-400">{results.error.message}</p>}
      <ul className="flex flex-col gap-2">
        {results.data?.map((result) => (
          <li key={result.video_id} className="rounded-xl bg-zinc-900 p-3">
            <button className="flex w-full gap-3 text-left" onClick={() => setPicked(picked?.video_id === result.video_id ? null : result)}>
              <img src={result.thumbnail_url} alt="" className="h-14 w-24 shrink-0 rounded-lg object-cover" />
              <span className="min-w-0">
                <span className="line-clamp-2 font-semibold">{result.title}</span>
                <span className="block truncate text-sm text-zinc-400">
                  {result.channel}
                  {result.duration_s ? ` · ${formatTime(result.duration_s)}` : ""}
                </span>
                {result.in_library && <span className="text-xs text-emerald-400">Toca na hora</span>}
              </span>
            </button>
            {picked?.video_id === result.video_id && <AddForm code={code} result={result} onAdded={onAdded} />}
          </li>
        ))}
      </ul>
      {results.data?.length === 0 && <p className="text-zinc-400">Nada encontrado.</p>}
    </div>
  );
}

/** The songs that play right away, already processed. */
function Library({ code, onAdded }: { code: string; onAdded: (title: string) => void }) {
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const songs = useQuery({ queryKey: ["library", q], queryFn: () => api.library(q) });
  return (
    <div className="flex flex-col gap-4">
      <input
        className="rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 outline-none focus:border-amber-400"
        placeholder="Filtrar por música ou artista"
        value={q}
        onChange={(event) => setQ(event.target.value)}
        aria-label="Filtrar o acervo"
      />
      {songs.isError && <p className="text-red-400">{songs.error.message}</p>}
      {songs.data?.length === 0 && <p className="text-zinc-400">Nenhuma música pronta{q ? " com esse nome" : ""}.</p>}
      <ul className="flex flex-col gap-2">
        {songs.data?.map((song) => (
          <li key={song.video_id} className="rounded-xl bg-zinc-900 p-3">
            <button className="flex w-full gap-3 text-left" onClick={() => setPicked(picked === song.video_id ? null : song.video_id)}>
              <img src={song.thumbnail_url ?? undefined} alt="" className="h-14 w-24 shrink-0 rounded-lg object-cover" />
              <span className="min-w-0">
                <span className="block truncate font-semibold">{songTitle(song)}</span>
                <span className="block truncate text-sm text-zinc-400">
                  {song.artist ?? song.channel}
                  {song.duration_s ? ` · ${formatTime(song.duration_s)}` : ""}
                </span>
              </span>
            </button>
            {picked === song.video_id && (
              <AddForm code={code} result={{ video_id: song.video_id, title: songTitle(song) }} onAdded={onAdded} />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AddForm({
  code,
  result,
  onAdded,
}: {
  code: string;
  result: Pick<SearchResult, "video_id" | "title">;
  onAdded: (title: string) => void;
}) {
  const [singer, setSinger] = useState(loadNickname);
  const [semitones, setSemitones] = useState(0);
  const add = useMutation({
    mutationFn: () => api.add(code, { video_id: result.video_id, singer_name: singer.trim() || undefined, semitones }),
    onSuccess: () => onAdded(result.title ?? result.video_id),
  });

  return (
    <div className="mt-3 flex flex-col gap-3 border-t border-zinc-800 pt-3">
      <label className="flex flex-col gap-1 text-sm text-zinc-400">
        Quem canta
        <input
          maxLength={40}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-base text-zinc-100 outline-none focus:border-amber-400"
          value={singer}
          onChange={(event) => setSinger(event.target.value)}
        />
      </label>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-zinc-400">Começar no tom</span>
        <button className="rounded-lg bg-zinc-800 px-3 py-1.5" disabled={semitones <= MIN_SEMITONES} onClick={() => setSemitones((s) => clampSemitones(s - 1))}>
          −½
        </button>
        <span className="w-16 text-center text-amber-300">{semitones === 0 ? "original" : signed(semitones)}</span>
        <button className="rounded-lg bg-zinc-800 px-3 py-1.5" disabled={semitones >= MAX_SEMITONES} onClick={() => setSemitones((s) => clampSemitones(s + 1))}>
          +½
        </button>
      </div>
      {add.isError && <p className="text-sm text-red-400">{add.error.message}</p>}
      <button className="rounded-lg bg-amber-400 py-2.5 font-bold text-zinc-950 disabled:opacity-50" disabled={add.isPending} onClick={() => add.mutate()}>
        Adicionar à fila
      </button>
    </div>
  );
}
