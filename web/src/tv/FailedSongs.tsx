// A song that could not be prepared, after the worker tried it again by itself (docs/ARCHITECTURE.md, "Novas
// tentativas e aviso da música que falhou"): a notice at the top of the TV, never over the lyrics, gone in 20 s or by
// its ✕. On a TV with the host's cookie it has "Tentar de novo" (the same as the queue's "Tentar processar de novo");
// elsewhere it says where the admin tries again, and that adding the song again tries it again too.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";

export type Failure = { key: number; videoId: string; title: string | null };

const NOTICE_MS = 20_000;

export function FailedSongs({ failures, onDismiss }: { failures: Failure[]; onDismiss: (key: number) => void }) {
  const host = useQuery({ queryKey: ["tv-is-host"], queryFn: api.isHost, retry: false });
  if (failures.length === 0) return null;
  return (
    <div className="pointer-events-none fixed top-4 left-1/2 z-40 flex w-[min(34rem,90vw)] -translate-x-1/2 flex-col gap-2">
      {failures.map((failure) => (
        <FailedSong
          key={failure.key}
          failure={failure}
          host={host.data === true}
          onDismiss={() => onDismiss(failure.key)}
        />
      ))}
    </div>
  );
}

function FailedSong({ failure, host, onDismiss }: { failure: Failure; host: boolean; onDismiss: () => void }) {
  const [title, setTitle] = useState(failure.title);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const dismiss = useRef(onDismiss);
  dismiss.current = onDismiss;
  useEffect(() => {
    const timer = window.setTimeout(() => dismiss.current(), NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, []);

  // The host's TV: the job says the song's name when it is in no queue of this room
  useEffect(() => {
    if (!host || failure.title) return;
    let gone = false;
    api.jobs().then(
      (jobs) => !gone && setTitle(jobs.find((j) => j.video_id === failure.videoId)?.title ?? null),
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [host, failure.videoId, failure.title]);

  const what = title ? `"${title}"` : "uma música";
  const retry = async () => {
    setBusy(true);
    try {
      await api.reprocess(failure.videoId, []);
      onDismiss();
    } catch (e) {
      setProblem((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div
      role="status"
      className="pointer-events-auto flex items-center gap-3 rounded-xl bg-zinc-900/95 px-4 py-3 text-left text-sm shadow-xl ring-1 ring-red-400/50"
    >
      <span className="flex-1 text-zinc-100">
        Não deu para preparar {what}.
        {!host && " O admin pode tentar de novo no Painel, ou adicione a música de novo."}
        {problem && <span className="block text-red-300">{problem}</span>}
      </span>
      {host && (
        <button
          className="shrink-0 rounded-lg bg-amber-400 px-3 py-1.5 font-bold text-zinc-950 disabled:opacity-50"
          disabled={busy}
          onClick={() => void retry()}
        >
          Tentar de novo
        </button>
      )}
      <button aria-label="Dispensar" className="shrink-0 text-zinc-400 hover:text-zinc-100" onClick={onDismiss}>
        ✕
      </button>
    </div>
  );
}
