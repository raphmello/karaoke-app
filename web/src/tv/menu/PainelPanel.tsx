// Painel (docs/ARCHITECTURE.md, "Menu lateral"), the host's: Disco (how full the disk is, and the purge of the songs
// removed the old way), Jobs (in progress, waiting and the history, with "Tentar de novo" for a failure) and Acervo
// (the old Gerenciar Acervo: Trocar letra, Reprocessar, Histórico and Remover).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useContext, useEffect, useRef, useState } from "react";
import { api, fetchLyrics, type Job, type Song } from "../../api";
import { History, LyricsForm, megabytes } from "../../host/LibraryAdmin";
import { PurgeRemoved } from "../../host/Panel";
import { artistOf, byArtist, inOrder } from "../../lib/library";
import { STAGE_NAMES, songTitle } from "../../lib/queue";
import { joined } from "../Lyrics";
import { formatTime } from "../time";
import { Icon } from "./icons";
import { ReprocessForm } from "./Reprocess";
import { ShowSong } from "./showSong";
import { ArtistGroups, LibraryScroll, Touch } from "./SongList";
import { Body, button, Card, gb, input, Label, PanelHeader, primary, RoundButton, Tabs, Thumb, useToast } from "./ui";

export type PainelTab = "disco" | "jobs" | "acervo";

export function PainelPanel({
  tab,
  onTab,
  onClose,
  focus = null,
}: {
  tab: PainelTab;
  onTab: (tab: PainelTab) => void;
  onClose?: () => void;
  focus?: string | null; // a song a notice pointed at, marked in Jobs
}) {
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
      {tab === "jobs" && <Jobs focus={focus} />}
      {tab === "acervo" && <Acervo focus={focus} />}
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

function Jobs({ focus }: { focus: string | null }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 2_000 });
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The song a failure's notice pointed at, in view
  const rows = useRef<HTMLDivElement>(null);
  const loaded = !!jobs.data;
  useEffect(() => {
    if (!focus || !loaded) return;
    rows.current?.querySelector(`[data-song="${CSS.escape(focus)}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focus, loaded]);
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

  const pointed = focus ? history.findIndex((job) => job.video_id === focus) : -1;
  const shown = all || pointed >= HISTORY_SHOWN ? history : history.slice(0, HISTORY_SHOWN);

  return (
    <Body>
      <div ref={rows} className="contents">
      <Label first>Em andamento · {running.length}</Label>
      {running.length === 0 && <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">Nada sendo preparado agora.</p>}
      {running.map((job) => (
        <Card
          key={job.id}
          data-song={job.video_id}
          className={`gap-[5px] px-3 py-[9px] ${focus === job.video_id ? "ring-1 ring-(--menu-accent)" : ""}`}
        >
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
        <div
          key={job.id}
          data-song={job.video_id}
          className={`flex items-center gap-2.5 border-b border-(--menu-line) py-1.5 last:border-b-0 ${focus === job.video_id ? "-mx-1.5 rounded-[10px] bg-(--menu-accent-soft) px-1.5 ring-1 ring-(--menu-accent)" : ""}`}
        >
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
      {shown.map((job) => {
        const failed = job.status === "failed";
        return (
          <div
            key={job.id}
            data-song={job.video_id}
            className={`flex items-center gap-2.5 border-b border-(--menu-line) py-1.5 last:border-b-0 ${focus === job.video_id ? "-mx-1.5 rounded-[10px] bg-(--menu-accent-soft) px-1.5 ring-1 ring-(--menu-accent)" : ""}`}
          >
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
      </div>
    </Body>
  );
}

// --- Acervo ---------------------------------------------------------------------------------------------------------

function Acervo({ focus }: { focus: string | null }) {
  const [q, setQ] = useState("");
  const songs = useQuery({ queryKey: ["library", q], queryFn: () => api.library(q), placeholderData: (previous) => previous });
  const touch = useContext(Touch);
  const list = songs.data ?? [];
  const count = list.length;
  const filtering = !!q.trim();
  // From the library by artist (docs/specs/02-scrollbar-lista-musicas): by artist with the A–Z index; filtered, a flat list
  const groups = filtering ? null : byArtist(list);
  const row = (song: Song) => (
    <AcervoRow key={song.video_id} song={song} marked={focus === song.video_id} withArtist={filtering} />
  );
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* opaque and above the list (LibraryScroll), with the space under the field: on an iPhone, rows showed
          through between the field and the artist's sticky header */}
      <div className="relative z-20 bg-(--menu-panel) px-[14px] pt-3 pb-2">
        <label
          className={`flex items-center gap-2 rounded-[10px] border border-transparent bg-(--menu-field) focus-within:border-(--menu-accent) ${
            touch ? "px-3.5 py-2.5" : "px-3 py-2"
          }`}
        >
          <Icon name="search" className="h-[17px] w-[17px] text-(--menu-text-3)" />
          <input
            className={`min-w-0 flex-1 bg-transparent outline-none placeholder:text-(--menu-text-off) ${touch ? "text-[16px]" : ""}`}
            placeholder="Filtrar o acervo"
            aria-label="Filtrar o acervo"
            autoComplete="off"
            value={q}
            onChange={(event) => setQ(event.target.value)}
          />
        </label>
      </div>
      <LibraryScroll groups={groups && groups.length ? groups : null}>
        <Label first>
          <Icon name="books" className="h-3.5 w-3.5" />
          {filtering ? `${count} resultado${count === 1 ? "" : "s"}` : `${count} música${count === 1 ? "" : "s"}`}
        </Label>
        {songs.isError && <p className="text-[12px] text-(--menu-err)">{songs.error.message}</p>}
        {songs.data?.length === 0 && (
          <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">
            {filtering ? "Nenhuma música encontrada." : "O acervo ainda está vazio."}
          </p>
        )}
        {groups ? <ArtistGroups groups={groups} row={row} /> : inOrder(list).map(row)}
      </LibraryScroll>
    </div>
  );
}

type Open = "lyrics" | "reprocess" | "history" | "remove" | null;

/** "pronta", or what a song being prepared again is doing: it stays in the library, and can go in the queue. */
function libraryStatus(song: Song): { text: string; tone: string } {
  if (song.status === "ready") return { text: "pronta", tone: "" };
  if (song.status === "failed") return { text: "falhou ao reprocessar", tone: "text-(--menu-err)" };
  return { text: "em processamento", tone: "text-(--menu-accent)" };
}

function AcervoRow({ song, marked, withArtist }: { song: Song; marked: boolean; withArtist: boolean }) {
  const touch = useContext(Touch);
  const showSong = useContext(ShowSong); // where the menu (or the host's phone) can open Jobs at the song
  // The song a notice pointed at, in view once
  const row = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (marked) row.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [marked]);
  const toast = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<Open>(null);
  const [error, setError] = useState<string | null>(null);
  const toggle = (next: Open) => setOpen((current) => (current === next ? null : next));
  const run = async (action: () => Promise<unknown>, done: string): Promise<boolean> => {
    setError(null);
    try {
      await action();
      setOpen(null);
      toast(done);
      void queryClient.invalidateQueries({ queryKey: ["library"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["disk"] });
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };
  const title = songTitle(song);
  const actions = (
    <>
      <RoundButton icon="lyrics" label={`Trocar letra de “${title}”`} active={open === "lyrics"} big={touch} onClick={() => toggle("lyrics")} />
      <RoundButton icon="refresh" label={`Reprocessar “${title}”`} active={open === "reprocess"} big={touch} onClick={() => toggle("reprocess")} />
      <RoundButton icon="clock" label={`Histórico de “${title}”`} active={open === "history"} big={touch} onClick={() => toggle("history")} />
      <RoundButton icon="trash" label={`Remover “${title}”`} danger big={touch} onClick={() => toggle("remove")} />
    </>
  );

  return (
    <div
      ref={row}
      className={`py-1.5 ${
        marked ? "-mx-1.5 rounded-[10px] bg-(--menu-accent-soft) px-1.5 ring-1 ring-(--menu-accent)" : ""
      }`}
    >
      <div className={`flex items-center ${touch ? "gap-2" : "gap-2.5"}`}>
        <Thumb src={song.thumbnail_url} big={touch} />
        <div className="min-w-0 flex-1">
          <div className={`truncate font-medium ${touch ? "text-[15px]" : ""}`}>{title}</div>
          <div className={`truncate text-(--menu-text-3) ${touch ? "text-[12px]" : "text-[11px]"}`}>
            {/* being prepared again: the status first, so it is never cut off */}
            {song.status !== "ready" && <span className={libraryStatus(song).tone}>{libraryStatus(song).text} · </span>}
            {[withArtist ? artistOf(song) : null, song.duration_s ? formatTime(song.duration_s) : null].filter(Boolean).join(" · ")}
            {song.status === "ready" && " · pronta"}
          </div>
        </div>
        {!touch && actions}
      </div>
      {/* on a phone, four 44 px buttons leave the title no room: they go on a line of their own */}
      {touch && <div className="mt-1 flex justify-end gap-2">{actions}</div>}
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
      {song.phonetic_source === "pendente" && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2 rounded-[10px] bg-(--menu-accent-soft) px-2.5 py-2 text-[12px]">
          <span className="w-full text-(--menu-text)">
            Não encontramos a pronúncia dos fãs. Usar a pronúncia automática? Ela pode ter erros. A música só toca depois
            da resposta.
          </span>
          <button
            className={`${primary} px-3 py-1.5 text-[12px]`}
            onClick={() => void run(() => api.answerPhoneticSong(song.video_id, true), "Pronúncia automática ligada")}
          >
            Usar automática
          </button>
          <button
            className={`${button} px-3 py-1.5 text-[12px]`}
            onClick={() => void run(() => api.answerPhoneticSong(song.video_id, false), "Fica só a letra original")}
          >
            Não, só a original
          </button>
        </div>
      )}
      {open === "lyrics" && <ChangeLyrics song={song} run={run} />}
      {open === "reprocess" && (
        <ReprocessForm
          onSubmit={(stages) =>
            void run(() => api.reprocess(song.video_id, stages), `“${title}” vai ser reprocessada`).then(
              (sent) => sent && showSong?.(song.video_id, "jobs"),
            )
          }
          onCancel={() => setOpen(null)}
        />
      )}
      {open === "history" && <History videoId={song.video_id} />}
      {error && <p className="mt-1.5 text-[12px] text-(--menu-err)">{error}</p>}
    </div>
  );
}

/** "Trocar letra": the original (the song is aligned again) or, when the lyrics need one, the phonetic version, one
 *  line for each line of the lyrics: the fans' corrected, or one written where none was found (docs/ARCHITECTURE.md,
 *  "Pronúncia"). */
function ChangeLyrics({ song, run }: { song: Song; run: (action: () => Promise<unknown>, done: string) => Promise<unknown> }) {
  const [tab, setTab] = useState<"original" | "phonetic">("original");
  return (
    <div className="mt-2 flex flex-col gap-2">
      {song.phonetic_source && song.media && (
        <Tabs<"original" | "phonetic">
          tabs={[
            ["original", "Original"],
            ["phonetic", "Pronúncia"],
          ]}
          current={tab}
          onChange={setTab}
        />
      )}
      {tab === "original" ? (
        <LyricsForm
          onSubmit={(text) => void run(() => api.replaceLyrics(song.video_id, text), "Letra trocada; o alinhamento roda de novo")}
        />
      ) : (
        <PhoneticForm song={song} run={run} />
      )}
    </div>
  );
}

function PhoneticForm({ song, run }: { song: Song; run: (action: () => Promise<unknown>, done: string) => Promise<unknown> }) {
  // The phonetic version to correct; the automatic one waiting for an answer (beside the lyrics, not given to the
  // TVs until accepted); without either, the original's lines, for the host to swap each one for its romanization
  const pending = song.phonetic_source === "pendente";
  const url = song.media!.phonetic ?? (pending ? song.media!.lyrics.replace("/aligned.json", "/phonetic.json") : song.media!.lyrics);
  const writing = !song.media!.phonetic && !pending;
  const current = useQuery({ queryKey: ["lyrics", url], queryFn: () => fetchLyrics(url) });
  const [text, setText] = useState<string | null>(null);
  const lines = current.data?.lines ?? [];
  const value = text ?? lines.map((line) => joined(line.words)).join("\n");
  const typed = value.split("\n");
  const fits = typed.length === lines.length;
  if (current.isPending) return <p className="text-[12px] text-(--menu-text-3)">Carregando a pronúncia…</p>;
  if (current.isError) return <p className="text-[12px] text-(--menu-err)">{current.error.message}</p>;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] text-(--menu-text-3)">
        {writing
          ? "Não há pronúncia da comunidade para esta música. Troque cada linha da letra original por ela escrita como se fala, em letras do nosso alfabeto, na mesma ordem; cada palavra fica no tempo da parte da original que ela lê."
          : pending
            ? "A pronúncia automática, para corrigir: uma linha para cada linha da letra, na mesma ordem. Salvar também responde à pergunta, com a sua versão."
            : "Uma linha para cada linha da letra, na mesma ordem. As palavras corrigidas ficam no tempo das que estavam ali."}{" "}
        Nada é processado de novo.
      </p>
      <textarea
        rows={10}
        className={`${input} font-mono`}
        value={value}
        onChange={(event) => setText(event.target.value)}
        aria-label="Pronúncia"
      />
      {!fits && (
        <p className="text-[12px] text-(--menu-err)">
          A letra tem {lines.length} linhas; aqui há {typed.length}.
        </p>
      )}
      <button
        className={`${primary} self-start`}
        disabled={!fits || text === null}
        onClick={() => void run(() => api.replacePhonetic(song.video_id, typed), "Pronúncia corrigida")}
      >
        Salvar a pronúncia
      </button>
    </div>
  );
}
