// The library's pieces for Painel → Acervo (tv/menu/PainelPanel.tsx): change the lyrics, reprocess stages and see a
// song's history.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { STAGE_NAMES } from "../lib/queue";

/** "55 MB": what a song's files take, said for people. */
export function megabytes(bytes: number | null | undefined): string {
  return `${Math.max(1, Math.round((bytes ?? 0) / 1_000_000))} MB`;
}

export function LyricsForm({ onSubmit }: { onSubmit: (text: string) => void }) {
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

export function ReprocessForm({ onSubmit }: { onSubmit: (stages: string[]) => void }) {
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
  retried: "Tentada de novo",
  purged: "Apagada de vez",
};

export function History({ videoId }: { videoId: string }) {
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
