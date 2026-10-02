// Finding a song and adding it to the queue: a YouTube search or the library, then who sings and the key it starts in.
// Used by the guest's phone and by the host's screen; the API decides who the entry belongs to from the cookie.
import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";
import { api, type SearchResult } from "../api";
import { clampSemitones, MAX_SEMITONES, MIN_SEMITONES, signed } from "../lib/keys";
import { MAX_SONG_S, songTitle, tooLong } from "../lib/queue";
import { loadNickname } from "../phone/identity";
import { formatTime } from "../tv/time";
import { PreviewBar, PreviewButton, previewSources, usePreview } from "./Preview";

/** A song in the results or the library, with its two actions on the right: hear a preview, and add it to the
 *  queue (which opens who sings and the starting key). Tapping the card also opens the add form. */
function SongRow({
  sources,
  thumbnail,
  details,
  picked,
  onPick,
  children,
}: {
  sources: string[];
  thumbnail: string | null;
  details: ReactNode;
  picked: boolean;
  onPick: () => void;
  children: ReactNode;
}) {
  const preview = usePreview(sources);
  return (
    <li className={`rounded-xl bg-zinc-900 p-3 ${picked ? "ring-1 ring-amber-400" : ""}`}>
      <div className="flex items-center gap-2 sm:gap-3">
        <button className="flex min-w-0 flex-1 gap-3 text-left" onClick={onPick}>
          <img src={thumbnail ?? undefined} alt="" className="h-12 w-16 shrink-0 rounded-lg object-cover sm:h-14 sm:w-24" />
          <span className="min-w-0">{details}</span>
        </button>
        <Labeled label={preview.state === "playing" ? "Pausar" : "Ouvir"}>
          <PreviewButton preview={preview} />
        </Labeled>
        <Labeled label={picked ? "Fechar" : "Adicionar"}>
          <button
            type="button"
            onClick={onPick}
            aria-label={picked ? "Fechar sem adicionar" : "Adicionar à fila"}
            aria-expanded={picked}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${
              picked ? "bg-zinc-700 text-zinc-100" : "bg-amber-400 text-zinc-950 hover:bg-amber-300"
            }`}
          >
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
              {picked ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M12 5v14M5 12h14" />}
            </svg>
          </button>
        </Labeled>
      </div>
      <PreviewBar preview={preview} />
      {children}
    </li>
  );
}

/** A round button with its name under it, so the icon doesn't have to explain itself. */
function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex w-12 shrink-0 flex-col items-center gap-1 sm:w-14">
      {children}
      <span className="text-[11px] leading-none text-zinc-400" aria-hidden="true">
        {label}
      </span>
    </div>
  );
}

export function Search({ code, onAdded }: { code: string; onAdded: (title: string) => void }) {
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
          <SongRow
            key={result.video_id}
            sources={previewSources(result.video_id)}
            thumbnail={result.thumbnail_url}
            picked={picked?.video_id === result.video_id}
            onPick={() => setPicked(picked?.video_id === result.video_id ? null : result)}
            details={
              <>
                <span className="line-clamp-2 font-semibold">{result.title}</span>
                <span className="block truncate text-sm text-zinc-400">
                  {result.channel}
                  {result.duration_s ? ` · ${formatTime(result.duration_s)}` : ""}
                </span>
                {tooLong(result) ? (
                  <span className="text-xs text-red-400">Longo demais para o karaokê (mais de {MAX_SONG_S / 60} min)</span>
                ) : (
                  result.in_library && <span className="text-xs text-emerald-400">Toca na hora</span>
                )}
              </>
            }
          >
            {picked?.video_id === result.video_id && <AddForm code={code} result={result} onAdded={onAdded} />}
          </SongRow>
        ))}
      </ul>
      {results.data?.length === 0 && <p className="text-zinc-400">Nada encontrado.</p>}
    </div>
  );
}

/** The songs that play right away, already processed. */
export function Library({ code, onAdded }: { code: string; onAdded: (title: string) => void }) {
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
          <SongRow
            key={song.video_id}
            sources={previewSources(song.video_id, song.media?.original)}
            thumbnail={song.thumbnail_url}
            picked={picked === song.video_id}
            onPick={() => setPicked(picked === song.video_id ? null : song.video_id)}
            details={
              <>
                <span className="line-clamp-2 leading-snug font-semibold">{songTitle(song)}</span>
                <span className="block truncate text-sm text-zinc-400">
                  {song.artist ?? song.channel}
                  {song.duration_s ? ` · ${formatTime(song.duration_s)}` : ""}
                </span>
              </>
            }
          >
            {picked === song.video_id && (
              <AddForm code={code} result={{ video_id: song.video_id, title: songTitle(song) }} onAdded={onAdded} />
            )}
          </SongRow>
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

/** Adding a song, for the guest's Room tab and the host's: from a YouTube search or from the library. */
export function AddSong({ code, onAdded }: { code: string; onAdded?: (title: string) => void }) {
  const [source, setSource] = useState<"search" | "library">("search");
  const [notice, setNotice] = useState<string | null>(null);
  const added = (title: string) => {
    setNotice(`"${title}" entrou na fila.`);
    window.setTimeout(() => setNotice(null), 4000);
    onAdded?.(title);
  };
  return (
    <section className="flex flex-col gap-3 rounded-xl bg-zinc-900 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Adicionar música</h2>
        <div className="flex gap-2">
          {([["search", "Buscar no YouTube"], ["library", "Acervo"]] as const).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setSource(id)}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${source === id ? "bg-amber-400 text-zinc-950" : "bg-zinc-800 text-zinc-300"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {notice && <p className="rounded-lg bg-emerald-950 px-3 py-2 text-sm text-emerald-200">{notice}</p>}
      {source === "search" ? <Search code={code} onAdded={added} /> : <Library code={code} onAdded={added} />}
    </section>
  );
}
