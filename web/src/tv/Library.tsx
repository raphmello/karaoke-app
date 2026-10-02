import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, api, type Song } from "../api";
import { keyName, parseKey } from "../lib/keys";
import { formatTime } from "./time";

/** Phase 3: the TV picks a ready song from the library. The queue takes over in phase 4. */
export function Library({ onPick, onUnauthorized }: { onPick: (song: Song) => void; onUnauthorized: () => void }) {
  const [q, setQ] = useState("");
  const songs = useQuery({ queryKey: ["library", q], queryFn: () => api.library(q) });
  const unauthorized = songs.error instanceof ApiError && songs.error.status === 401;
  useEffect(() => {
    if (unauthorized) onUnauthorized();
  }, [unauthorized, onUnauthorized]);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 md:px-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Acervo</h1>
        <input
          className="w-full max-w-md rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-lg outline-none focus:border-amber-400"
          placeholder="Buscar por música ou artista"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
      </header>
      {songs.isPending && <p className="text-zinc-400">Carregando…</p>}
      {songs.isError && <p className="text-red-400">{songs.error.message}</p>}
      {songs.data?.length === 0 && <p className="text-zinc-400">Nenhuma música pronta{q ? " com esse nome" : ""}.</p>}
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {songs.data?.map((song) => {
          const key = parseKey(song.original_key);
          return (
            <li key={song.video_id}>
              <button
                className="flex w-full items-center gap-4 rounded-xl bg-zinc-900 p-3 text-left hover:bg-zinc-800 focus:outline-2 focus:outline-amber-400"
                onClick={() => onPick(song)}
              >
                <img src={song.media?.thumb} alt="" className="h-16 w-28 shrink-0 rounded-lg object-cover" />
                <span className="min-w-0">
                  <span className="block truncate font-semibold">{song.track ?? song.title}</span>
                  <span className="block truncate text-sm text-zinc-400">{song.artist ?? song.channel}</span>
                  <span className="block text-xs text-zinc-500">
                    {song.duration_s ? formatTime(song.duration_s) : ""}
                    {key ? ` · ${keyName(key)}` : ""}
                    {song.lyrics_source === "transcrita" ? " · letra transcrita" : ""}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
