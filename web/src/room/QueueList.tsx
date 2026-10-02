// The queue as the phone and the host see it. What each one may do follows the permission matrix: the owner (and
// the host) change the key, remove and answer the transcription question; only the host reorders.
import { useEffect, useState } from "react";
import { api, type QueueEntry } from "../api";
import { clampSemitones, keyLabel, MAX_SEMITONES, MIN_SEMITONES } from "../lib/keys";
import { type Progress, songTitle, statusText } from "../lib/queue";
import { ConfirmButton } from "./ConfirmButton";

const small = "rounded-lg bg-zinc-800 px-3 py-1.5 text-sm font-semibold hover:bg-zinc-700 disabled:opacity-40";

export function QueueList({
  code,
  entries,
  progress,
  isHost,
}: {
  code: string;
  entries: QueueEntry[];
  progress: Progress;
  isHost: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  // Keys asked for but not yet confirmed by a snapshot, so quick taps add up instead of all starting from the old value.
  const [pending, setPending] = useState<Record<number, number>>({});
  useEffect(() => {
    setPending((current) => {
      const left = Object.entries(current).filter(([id, value]) => entries.find((e) => e.id === Number(id))?.semitones !== value);
      return left.length === Object.keys(current).length ? current : Object.fromEntries(left);
    });
  }, [entries]);
  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (entries.length === 0) return <p className="py-8 text-center text-zinc-400">A fila está vazia.</p>;
  return (
    <div className="flex flex-col gap-3">
      {error && <p className="rounded-lg bg-red-950 px-3 py-2 text-sm text-red-200">{error}</p>}
      <ol className="flex flex-col gap-3">
        {entries.map((entry, index) => {
          const mayEdit = isHost || entry.mine;
          const semitones = pending[entry.id] ?? entry.semitones;
          const key = keyLabel(entry.song.original_key, semitones);
          const setKey = (n: number) => {
            const value = clampSemitones(n);
            setPending((current) => ({ ...current, [entry.id]: value }));
            void run(() => api.change(code, entry.id, { semitones: value }));
          };
          return (
            <li
              key={entry.id}
              className={`rounded-xl p-3 ${entry.status === "playing" ? "bg-amber-950/60 ring-1 ring-amber-500" : "bg-zinc-900"}`}
            >
              <div className="flex gap-3">
                <img src={entry.song.thumbnail_url ?? undefined} alt="" className="h-14 w-24 shrink-0 rounded-lg object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {songTitle(entry.song)}
                    {entry.song.artist && <span className="font-normal text-zinc-400"> · {entry.song.artist}</span>}
                  </p>
                  <p className="truncate text-sm text-zinc-400">
                    {entry.singer_name ?? entry.added_by}
                    {entry.mine ? " · sua" : ""}
                  </p>
                  <p className={`text-xs ${entry.song.status === "failed" ? "text-red-400" : "text-zinc-500"}`}>
                    {statusText(entry, progress)}
                  </p>
                </div>
                {isHost && (
                  <div className="flex flex-col gap-1">
                    <button className={small} disabled={index === 0} onClick={() => run(() => api.change(code, entry.id, { position: index - 1 }))} aria-label="Subir na fila">
                      ↑
                    </button>
                    <button className={small} disabled={index === entries.length - 1} onClick={() => run(() => api.change(code, entry.id, { position: index + 1 }))} aria-label="Descer na fila">
                      ↓
                    </button>
                  </div>
                )}
              </div>

              {entry.status === "awaiting_decision" && mayEdit && (
                <div className="mt-3 rounded-lg bg-zinc-800 p-3 text-sm">
                  <p>
                    Não encontramos a letra desta música. Quer que ela seja transcrita automaticamente? A transcrição pode
                    ter erros.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="rounded-lg bg-amber-400 px-3 py-1.5 font-semibold text-zinc-950" onClick={() => run(() => api.answer(code, entry.id, true))}>
                      Sim, transcrever
                    </button>
                    <button className={small} onClick={() => run(() => api.answer(code, entry.id, false))}>
                      Não, remover
                    </button>
                  </div>
                </div>
              )}

              {mayEdit && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {entry.status !== "awaiting_decision" && (
                    <>
                  <button className={small} disabled={semitones <= MIN_SEMITONES} onClick={() => setKey(semitones - 1)}>
                    −½ tom
                  </button>
                  <span className="min-w-28 text-center text-sm text-amber-300" title={key.original ?? undefined}>
                    {key.current}
                  </span>
                  <button className={small} disabled={semitones >= MAX_SEMITONES} onClick={() => setKey(semitones + 1)}>
                    +½ tom
                  </button>
                  <button className={small} disabled={semitones === 0} onClick={() => setKey(0)}>
                    Tom original
                  </button>
                    </>
                  )}
                  <span className="ml-auto">
                    <ConfirmButton
                      className={`${small} text-red-300`}
                      label="Remover"
                      confirmLabel={entry.status === "playing" ? "Remover e pular" : "Confirmar remoção"}
                      onConfirm={() => void run(() => api.remove(code, entry.id))}
                    />
                  </span>
                </div>
              )}
              {isHost && entry.song.status === "failed" && (
                <button className={`${small} mt-2`} onClick={() => run(() => api.reprocess(entry.video_id, []))}>
                  Tentar processar de novo
                </button>
              )}
              {!mayEdit && <p className="mt-2 text-xs text-zinc-500">{key.current}</p>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
