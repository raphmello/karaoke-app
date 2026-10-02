// The host's panel: the disk (with a warning when it runs low) and the jobs, with a retry for the failed ones.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { STAGE_NAMES } from "../lib/queue";

const GB = 1024 ** 3;
const gb = (bytes: number) => `${(bytes / GB).toFixed(1)} GB`;
const STATUS: Record<string, string> = { pending: "Na fila", running: "Rodando", done: "Concluído", failed: "Falhou" };

export function Panel() {
  const queryClient = useQueryClient();
  const disk = useQuery({ queryKey: ["disk"], queryFn: api.disk, refetchInterval: 60_000 });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 5_000 });
  const [error, setError] = useState<string | null>(null);

  // Only a song's newest job offers a retry: an older failure may already have been tried again.
  const latest = new Map<string, number>();
  for (const job of jobs.data ?? []) if (!latest.has(job.video_id)) latest.set(job.video_id, job.id);

  const retry = async (videoId: string) => {
    setError(null);
    try {
      await api.reprocess(videoId, []);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <section className={`rounded-xl p-4 ${disk.data?.low ? "bg-red-950 ring-1 ring-red-500" : "bg-zinc-900"}`}>
        <h2 className="mb-2 text-lg font-semibold">Disco</h2>
        {disk.data ? (
          <>
            {disk.data.low && (
              <p className="mb-2 font-semibold text-red-200">
                O espaço está acabando. Cada música ocupa cerca de 65 MB; músicas removidas continuam ocupando espaço.
              </p>
            )}
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
              <dt className="text-zinc-400">Livre</dt>
              <dd>
                {gb(disk.data.free_bytes)} de {gb(disk.data.total_bytes)}
              </dd>
              <dt className="text-zinc-400">Músicas</dt>
              <dd>
                {disk.data.songs} · {gb(disk.data.media_bytes)}
              </dd>
              <dt className="text-zinc-400">Removidas</dt>
              <dd>
                {disk.data.removed_songs} · {gb(disk.data.removed_bytes)}
              </dd>
            </dl>
          </>
        ) : (
          <p className="text-zinc-400">{disk.isError ? disk.error.message : "Carregando…"}</p>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Jobs</h2>
        {error && <p className="mb-2 text-sm text-red-400">{error}</p>}
        {jobs.data?.length === 0 && <p className="text-zinc-400">Nenhum job ainda.</p>}
        <ul className="flex flex-col gap-2">
          {jobs.data?.map((job) => (
            <li key={job.id} className="rounded-xl bg-zinc-900 p-3 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-semibold">{job.title ?? job.video_id}</span>
                <span className={job.status === "failed" ? "text-red-400" : job.status === "running" ? "text-amber-300" : "text-zinc-400"}>
                  {STATUS[job.status] ?? job.status}
                  {job.status === "running" && job.stage ? ` · ${STAGE_NAMES[job.stage] ?? job.stage} · ${Math.round(job.progress * 100)}%` : ""}
                </span>
              </div>
              <p className="text-xs text-zinc-500">
                {job.options.transcribe ? "transcrição · " : ""}
                {job.options.redo?.length ? `refazer: ${job.options.redo.map((s) => STAGE_NAMES[s] ?? s).join(", ")} · ` : ""}
                {job.attempts} tentativa{job.attempts === 1 ? "" : "s"}
              </p>
              {job.error && <p className="mt-1 break-words text-xs text-red-300">{job.error}</p>}
              {job.status === "failed" && latest.get(job.video_id) === job.id && (
                <button className="mt-2 rounded-lg bg-zinc-800 px-3 py-1.5 font-semibold hover:bg-zinc-700" onClick={() => retry(job.video_id)}>
                  Tentar de novo
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
