// The host's library: change the lyrics, reprocess stages, remove and restore songs, and see their history.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Song } from "../api";
import { keyName, parseKey } from "../lib/keys";
import { songTitle, STAGE_NAMES } from "../lib/queue";
import { ConfirmButton } from "../room/ConfirmButton";
import { formatTime } from "../tv/time";

const small = "rounded-lg bg-zinc-800 px-3 py-1.5 text-sm font-semibold hover:bg-zinc-700 disabled:opacity-40";
type Panel = "lyrics" | "reprocess" | "history" | null;

export function LibraryAdmin() {
  const [q, setQ] = useState("");
  const [removed, setRemoved] = useState(false);
  const songs = useQuery({ queryKey: ["library", q, removed], queryFn: () => api.library(q, removed) });

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <input
          className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 outline-none focus:border-amber-400"
          placeholder="Buscar no acervo"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input type="checkbox" checked={removed} onChange={(event) => setRemoved(event.target.checked)} />
          Mostrar removidas
        </label>
      </div>
      {songs.isError && <p className="text-red-400">{songs.error.message}</p>}
      {songs.data?.length === 0 && <p className="text-zinc-400">Nenhuma música {removed ? "removida" : "no acervo"}.</p>}
      <ul className="flex flex-col gap-3">
        {songs.data?.map((song) => <SongRow key={song.video_id} song={song} />)}
      </ul>
    </section>
  );
}

function SongRow({ song }: { song: Song }) {
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<Panel>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const key = parseKey(song.original_key);
  const removed = song.status === "removed";

  const run = async (action: () => Promise<unknown>, done: string) => {
    setMessage(null);
    try {
      await action();
      if (done) setMessage({ ok: true, text: done });
      setPanel(null);
      void queryClient.invalidateQueries({ queryKey: ["library"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message });
    }
  };
  const toggle = (next: Panel) => setPanel((current) => (current === next ? null : next));

  return (
    <li className="rounded-xl bg-zinc-900 p-3">
      <div className="flex gap-3">
        <img src={song.thumbnail_url ?? undefined} alt="" className="h-14 w-24 shrink-0 rounded-lg object-cover" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{songTitle(song)}</p>
          <p className="truncate text-sm text-zinc-400">{song.artist ?? song.channel}</p>
          <p className="text-xs text-zinc-500">
            {song.duration_s ? formatTime(song.duration_s) : ""}
            {key ? ` · ${keyName(key)}` : ""}
            {song.lyrics_source ? ` · letra: ${song.lyrics_source}` : ""}
            {song.alignment_confidence !== null ? ` · confiança ${Math.round(song.alignment_confidence * 100)}%` : ""}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {removed ? (
          <button className={small} onClick={() => run(() => api.restoreSong(song.video_id), "Remoção desfeita.")}>
            Desfazer remoção
          </button>
        ) : (
          <>
            <button className={small} onClick={() => toggle("lyrics")}>
              Trocar letra
            </button>
            <button className={small} onClick={() => toggle("reprocess")}>
              Reprocessar
            </button>
            <ConfirmButton
              className={`${small} text-red-300`}
              label="Remover"
              confirmLabel="Remover do acervo (arquivos e histórico ficam)"
              onConfirm={() => void run(() => api.removeSong(song.video_id), "Música removida do acervo.")}
            />
          </>
        )}
        <button className={small} onClick={() => toggle("history")}>
          Histórico
        </button>
      </div>
      {message && <p className={`mt-2 text-sm ${message.ok ? "text-emerald-300" : "text-red-400"}`}>{message.text}</p>}
      {panel === "lyrics" && <LyricsForm onSubmit={(text) => run(() => api.replaceLyrics(song.video_id, text), "Letra trocada; o alinhamento roda de novo.")} />}
      {panel === "reprocess" && (
        <ReprocessForm
          onSubmit={(stages) =>
            run(async () => {
              const result = await api.reprocess(song.video_id, stages);
              setMessage({ ok: true, text: `Vai refazer: ${result.stages.map((s) => STAGE_NAMES[s] ?? s).join(", ") || "tudo o que faltava"}.` });
            }, "")
          }
        />
      )}
      {panel === "history" && <History videoId={song.video_id} />}
    </li>
  );
}

function LyricsForm({ onSubmit }: { onSubmit: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <div className="mt-3 flex flex-col gap-2">
      <p className="text-sm text-zinc-400">
        Cole a letra. Com tempos no formato LRC ([01:23.45] linha), as linhas seguem esses tempos; sem eles, a letra é
        alinhada inteira.
      </p>
      <textarea
        rows={8}
        className="rounded-lg border border-zinc-700 bg-zinc-950 p-3 font-mono text-sm outline-none focus:border-amber-400"
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <button className="self-start rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950 disabled:opacity-50" disabled={!text.trim()} onClick={() => onSubmit(text)}>
        Trocar e realinhar
      </button>
    </div>
  );
}

function ReprocessForm({ onSubmit }: { onSubmit: (stages: string[]) => void }) {
  const [stages, setStages] = useState<string[]>([]);
  return (
    <div className="mt-3 flex flex-col gap-2">
      <p className="text-sm text-zinc-400">Escolha as etapas. As que dependem delas também rodam de novo.</p>
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {Object.entries(STAGE_NAMES).map(([stage, name]) => (
          <label key={stage} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={stages.includes(stage)}
              onChange={(event) => setStages((s) => (event.target.checked ? [...s, stage] : s.filter((x) => x !== stage)))}
            />
            {name}
          </label>
        ))}
      </div>
      <button className="self-start rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950 disabled:opacity-50" disabled={stages.length === 0} onClick={() => onSubmit(stages)}>
        Reprocessar
      </button>
    </div>
  );
}

const EVENTS: Record<string, string> = {
  created: "Adicionada",
  lyrics_missing: "Letra não encontrada",
  transcription_accepted: "Transcrição aceita",
  transcription_declined: "Transcrição recusada",
  ready: "Pronta",
  removed: "Removida",
  reactivated: "Reativada",
};

function History({ videoId }: { videoId: string }) {
  const events = useQuery({ queryKey: ["history", videoId], queryFn: () => api.history(videoId) });
  if (events.isPending) return <p className="mt-3 text-sm text-zinc-400">Carregando…</p>;
  if (events.isError) return <p className="mt-3 text-sm text-red-400">{events.error.message}</p>;
  return (
    <ol className="mt-3 flex flex-col gap-1 text-sm">
      {events.data.map((event, i) => (
        <li key={i} className="text-zinc-300">
          <span className="text-zinc-500">{new Date(event.created_at + "Z").toLocaleString("pt-BR")}</span> ·{" "}
          {EVENTS[event.kind] ?? event.kind} · {event.by}
        </li>
      ))}
    </ol>
  );
}
