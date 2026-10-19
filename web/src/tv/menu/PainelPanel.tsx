// Painel (docs/ARCHITECTURE.md, "Menu lateral"), the host's: Disco (how full the disk is, and the purge of the songs
// removed the old way), Jobs (in progress, waiting and the history, with "Tentar de novo" for a failure) and Acervo
// (the old Gerenciar Acervo: Trocar letra, Reprocessar, Histórico and Remover).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Job, type Song } from "../../api";
import { History, LyricsForm, megabytes, ReprocessForm } from "../../host/LibraryAdmin";
import { PurgeRemoved } from "../../host/Panel";
import { STAGE_NAMES, songTitle } from "../../lib/queue";
import { formatTime } from "../time";
import { Icon } from "./icons";
import { Body, button, Card, gb, Label, PanelHeader, RoundButton, Tabs, Thumb, useToast } from "./ui";

export type PainelTab = "disco" | "jobs" | "acervo";

export function PainelPanel({ tab, onTab, onClose }: { tab: PainelTab; onTab: (tab: PainelTab) => void; onClose?: () => void }) {
  return (
    <>
      <PanelHeader title="Painel" onClose={onClose} />
      <Tabs<PainelTab>
        tabs={[
          ["disco", "Disco"],
          ["jobs", "Jobs"],
          ["acervo", "Acervo"],
        ]}
        current={tab}
        onChange={onTab}
      />
      {tab === "disco" && <Disco />}
      {tab === "jobs" && <Jobs />}
      {tab === "acervo" && <Acervo />}
    </>
  );
}

// --- Disco ----------------------------------------------------------------------------------------------------------

function Disco() {
  const disk = useQuery({ queryKey: ["disk"], queryFn: api.disk, refetchInterval: 60_000 });
  const d = disk.data;
  const used = d ? d.total_bytes - d.free_bytes : 0;
  return (
    <Body>
      {!d ? (
        <p className="text-[12px] text-(--menu-text-3)">{disk.isError ? disk.error.message : "Carregando…"}</p>
      ) : (
        <Card className={d.low ? "ring-1 ring-(--menu-err)" : ""}>
          <span className="text-[14px] font-medium">Uso de disco</span>
          <span className="text-[12px] text-(--menu-text-3)">
            {gb(used)} de {gb(d.total_bytes)} · {gb(d.free_bytes)} livres
          </span>
          <div className="h-[5px] rounded-[3px] bg-(--menu-thumb)">
            <div
              className="h-[5px] rounded-[3px] bg-(--menu-accent)"
              style={{ width: `${Math.min(100, (100 * used) / (d.total_bytes || 1))}%` }}
            />
          </div>
          <span className="text-[12px] text-(--menu-text-3)">
            Músicas: {d.songs} · {gb(d.media_bytes)}
          </span>
          {d.low && (
            <p className="text-[12px] text-(--menu-err)">
              O espaço está acabando. Cada música ocupa cerca de 65 MB; remover uma música do acervo libera o espaço dela.
            </p>
          )}
          {d.removed_songs > 0 && (
            <>
              <span className="text-[12px] text-(--menu-text-3)">
                Removidas: {d.removed_songs} · {gb(d.removed_bytes)}
              </span>
              <PurgeRemoved bytes={d.removed_bytes} />
            </>
          )}
        </Card>
      )}
    </Body>
  );
}

// --- Jobs -----------------------------------------------------------------------------------------------------------

const HISTORY_SHOWN = 3;

/** "há 12 min", "ontem", "há 3 dias": when a job finished, said for people. */
function ago(iso: string | null): string {
  if (!iso) return "";
  const seconds = (Date.now() - new Date(`${iso}Z`).getTime()) / 1000;
  if (seconds < 60) return "agora";
  if (seconds < 3600) return `há ${Math.floor(seconds / 60)} min`;
  if (seconds < 86_400) return `há ${Math.floor(seconds / 3600)} h`;
  const days = Math.floor(seconds / 86_400);
  return days === 1 ? "ontem" : `há ${days} dias`;
}

const stageName = (job: Job) => (job.stage ? (STAGE_NAMES[job.stage] ?? job.stage) : "Preparando");

function Jobs() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 2_000 });
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!jobs.data) {
    return (
      <Body>
        <p className="text-[12px] text-(--menu-text-3)">{jobs.isError ? jobs.error.message : "Carregando…"}</p>
      </Body>
    );
  }
  // A song's newest job only: an older failure that was tried again leaves the history
  const newest = new Map<string, number>();
  for (const job of jobs.data) if (!newest.has(job.video_id)) newest.set(job.video_id, job.id);
  const running = jobs.data.filter((job) => job.status === "running");
  const waiting = jobs.data.filter((job) => job.status === "pending").reverse(); // the oldest goes first
  const history = jobs.data
    .filter((job) => (job.status === "done" || job.status === "failed") && newest.get(job.video_id) === job.id)
    .sort((a, b) => (b.finished_at ?? "").localeCompare(a.finished_at ?? ""));
  const retry = async (job: Job) => {
    setError(null);
    try {
      await api.reprocess(job.video_id, []);
      toast(`“${job.title ?? job.video_id}” voltou para a fila de preparo`);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <Body>
      <Label first>Em andamento · {running.length}</Label>
      {running.length === 0 && <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">Nada sendo preparado agora.</p>}
      {running.map((job) => (
        <Card key={job.id} className="gap-[5px] px-3 py-[9px]">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">{stageName(job)}</span>
            <span className="text-[12px] text-(--menu-text-3)">{Math.round(job.progress * 100)}%</span>
          </div>
          <span className="truncate text-[12px] text-(--menu-text-3)">{job.title ?? job.video_id}</span>
          <div className="h-[5px] rounded-[3px] bg-(--menu-thumb)">
            <div className="h-[5px] rounded-[3px] bg-(--menu-accent) transition-[width] duration-700" style={{ width: `${Math.round(job.progress * 100)}%` }} />
          </div>
        </Card>
      ))}

      <Label>Na espera · {waiting.length}</Label>
      {waiting.length === 0 && <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">Nenhum na espera.</p>}
      {waiting.map((job) => (
        <div key={job.id} className="flex items-center gap-2.5 border-b border-(--menu-line) py-1.5 last:border-b-0">
          <Icon name="clock" className="h-[17px] w-[17px] text-(--menu-text-3)" />
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">{job.title ?? job.video_id}</div>
            <div className="text-[11px] text-(--menu-text-3)">
              {job.options.transcribe ? "Transcrever a letra" : job.options.redo?.length ? "Reprocessar" : "Preparar"}
            </div>
          </div>
        </div>
      ))}

      <Label>Histórico</Label>
      {error && <p className="text-[12px] text-(--menu-err)">{error}</p>}
      {history.length === 0 && <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">Sem histórico por enquanto.</p>}
      {(all ? history : history.slice(0, HISTORY_SHOWN)).map((job) => {
        const failed = job.status === "failed";
        return (
          <div key={job.id} className="flex items-center gap-2.5 border-b border-(--menu-line) py-1.5 last:border-b-0">
            <span className={failed ? "text-(--menu-err)" : "text-(--menu-ok)"}>
              <Icon name={failed ? "alert" : "ok"} className="h-[17px] w-[17px]" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{job.title ?? job.video_id}</div>
              <div className={`truncate text-[11px] ${failed ? "text-(--menu-err)" : "text-(--menu-text-3)"}`} title={job.error ?? undefined}>
                {failed ? `Falhou${job.stage ? ` em ${stageName(job).toLowerCase()}` : ""}` : "Pronta"} · {ago(job.finished_at)}
              </div>
            </div>
            {failed && (
              <button className={`${button} px-3 py-1.5 text-[12px]`} onClick={() => void retry(job)}>
                Tentar de novo
              </button>
            )}
          </div>
        );
      })}
      {history.length > HISTORY_SHOWN && (
        <button className="py-1.5 text-center text-[12px] text-(--menu-accent)" onClick={() => setAll(!all)}>
          {all ? "Mostrar menos" : "Ver histórico completo"}
        </button>
      )}
    </Body>
  );
}

// --- Acervo ---------------------------------------------------------------------------------------------------------

function Acervo() {
  const [q, setQ] = useState("");
  const songs = useQuery({ queryKey: ["library", q], queryFn: () => api.library(q), placeholderData: (previous) => previous });
  const count = songs.data?.length ?? 0;
  return (
    <Body>
      <label className="flex items-center gap-2 rounded-[10px] border border-transparent bg-(--menu-field) px-3 py-2 focus-within:border-(--menu-accent)">
        <Icon name="search" className="h-[17px] w-[17px] text-(--menu-text-3)" />
        <input
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-(--menu-text-off)"
          placeholder="Filtrar o acervo"
          aria-label="Filtrar o acervo"
          autoComplete="off"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
      </label>
      <Label>
        {count} música{count === 1 ? "" : "s"}
      </Label>
      {songs.isError && <p className="text-[12px] text-(--menu-err)">{songs.error.message}</p>}
      {songs.data?.map((song) => <AcervoRow key={song.video_id} song={song} />)}
    </Body>
  );
}

type Open = "lyrics" | "reprocess" | "history" | "remove" | null;

function AcervoRow({ song }: { song: Song }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<Open>(null);
  const [error, setError] = useState<string | null>(null);
  const toggle = (next: Open) => setOpen((current) => (current === next ? null : next));
  const run = async (action: () => Promise<unknown>, done: string) => {
    setError(null);
    try {
      await action();
      setOpen(null);
      toast(done);
      void queryClient.invalidateQueries({ queryKey: ["library"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["disk"] });
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const title = songTitle(song);

  return (
    <div className="border-b border-(--menu-line) py-1.5 last:border-b-0">
      <div className="flex items-center gap-2.5">
        <Thumb src={song.thumbnail_url} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{title}</div>
          <div className="truncate text-[11px] text-(--menu-text-3)">
            {[song.artist ?? song.channel, song.duration_s ? formatTime(song.duration_s) : null, "pronta"].filter(Boolean).join(" · ")}
          </div>
        </div>
        <RoundButton icon="lyrics" label="Trocar letra" active={open === "lyrics"} onClick={() => toggle("lyrics")} />
        <RoundButton icon="refresh" label="Reprocessar" active={open === "reprocess"} onClick={() => toggle("reprocess")} />
        <RoundButton icon="clock" label="Histórico" active={open === "history"} onClick={() => toggle("history")} />
        <RoundButton icon="trash" label="Remover" danger onClick={() => toggle("remove")} />
      </div>
      {open === "remove" && (
        <div className="mt-1.5 flex items-center gap-2 rounded-[10px] bg-(--menu-input) px-2.5 py-2 text-[12px]">
          <span className="min-w-0 flex-1">
            Remover “{title}” e liberar {megabytes(song.disk_bytes)}? Não dá para desfazer.
          </span>
          <button className={`${button} px-3 py-1.5 text-[12px]`} onClick={() => setOpen(null)}>
            Cancelar
          </button>
          <button
            className="rounded-[9px] bg-(--menu-err) px-3 py-1.5 text-[12px] font-medium text-(--menu-on-accent)"
            onClick={() => void run(() => api.removeSong(song.video_id), `“${title}” saiu do acervo`)}
          >
            Remover
          </button>
        </div>
      )}
      {open === "lyrics" && (
        <LyricsForm onSubmit={(text) => void run(() => api.replaceLyrics(song.video_id, text), "Letra trocada; o alinhamento roda de novo")} />
      )}
      {open === "reprocess" && (
        <ReprocessForm
          onSubmit={(stages) =>
            void run(async () => {
              const result = await api.reprocess(song.video_id, stages);
              return result;
            }, `Vai refazer: ${stages.map((s) => STAGE_NAMES[s] ?? s).join(", ")}`)
          }
        />
      )}
      {open === "history" && <History videoId={song.video_id} />}
      {error && <p className="mt-1.5 text-[12px] text-(--menu-err)">{error}</p>}
    </div>
  );
}
