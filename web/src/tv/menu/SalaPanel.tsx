// Sala (docs/ARCHITECTURE.md, "Menu lateral" and "Telas do celular"): the room's code and name, how long it has left
// and, for whoever manages it, "Excluir sala"; then two tabs. Fila: who sings now and the songs coming. Adicionar: one
// search for the library (every key typed) and for YouTube (after a pause), with the same "quem canta" and starting
// key as always (room/AddSongs.tsx's AddForm). What each screen may do follows the permission matrix: the host and
// the room's owner (manage) reorder by dragging, remove, try again and answer for any song; the TV and a guest change
// the key of, remove and answer for their own songs. On a phone that manages the room, the player's controls go in
// the "Cantando agora" card (the TV has its floating bar).
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { api, type QueueEntry, type RoomInfo } from "../../api";
import { clampSemitones, keyLabel, keyName, MAX_SEMITONES, MIN_SEMITONES, parseKey, signed } from "../../lib/keys";
import { liveProgress, MAX_SONG_S, songTitle, statusText, tooLong } from "../../lib/queue";
import { AddForm } from "../../room/AddSongs";
import { DeleteRoomButton } from "../../room/DeleteRoom";
import { ExpiresIn } from "../../room/Expiry";
import { PreviewBar, previewSources, usePreview } from "../../room/Preview";
import { ProgressBar } from "../../room/ProgressBar";
import type { PlayerState, useRoom } from "../../room/useRoom";
import { DELAY_LIMIT_MS, DELAY_STEP_MS, seconds } from "../controls/FloatingBar";
import { formatTime } from "../time";
import { Icon } from "./icons";
import { Body, button, IconButton, Label, PanelHeader, primary, RoundButton, Tabs, Thumb, useToast } from "./ui";

export type SalaTab = "fila" | "adicionar";
type Live = ReturnType<typeof useRoom>;
export function SalaPanel({
  room,
  live,
  tab,
  onTab,
  onClose,
  manage,
  controls = false,
  aside,
  actions,
  onDeleted,
  closed,
}: {
  room: RoomInfo | null;
  live: Live;
  tab: SalaTab;
  onTab: (tab: SalaTab) => void;
  onClose?: () => void;
  manage: boolean; // the host or the room's owner: the whole queue
  controls?: boolean; // the player's controls in "Cantando agora" (a phone; the TV has its floating bar)
  aside?: ReactNode; // beside the title, on the right (the guest's nickname)
  actions?: ReactNode; // under the room's details ("Abrir como TV", "Ver salas")
  onDeleted?: () => void; // the room was deleted from here
  closed?: boolean; // the room was deleted or expired: only a notice
}) {
  const code = room?.code ?? null;
  const waiting = live.entries?.filter((entry) => entry.status !== "playing").length ?? 0;

  return (
    <>
      <PanelHeader title={room?.name ?? "Sala"} onClose={onClose} actions={aside}>
        {code && (
          <span className="shrink-0 rounded-md bg-(--menu-btn) px-2 py-0.5 text-[12px] font-normal tracking-wider text-(--menu-accent)">
            {room?.protected && "🔒 "}
            {code.toUpperCase()}
          </span>
        )}
      </PanelHeader>
      {room && !closed && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-[14px] pt-1.5 text-[12px] text-(--menu-text-3)">
          <span>
            {room.owner === "Host" ? "Do host" : `De ${room.owner}`} · <ExpiresIn when={room.expires_at} />
            {!live.connected && " · reconectando…"}
          </span>
          {actions}
          {manage && <DeleteRoomButton code={room.code} onDeleted={onDeleted} />}
        </div>
      )}
      {!room || closed ? (
        <Body>
          <p className="py-2 text-[12px] text-(--menu-text-3)">
            {closed ? "Esta sala foi encerrada. Escolha outra em Ver salas." : "Nenhuma sala escolhida."}
          </p>
        </Body>
      ) : (
        <>
          <Tabs<SalaTab>
            tabs={[
              [
                "fila",
                <>
                  Fila <span className="text-(--menu-accent) group-[.is-on]:text-(--menu-on-accent)">{waiting}</span>
                </>,
              ],
              ["adicionar", "Adicionar"],
            ]}
            current={tab}
            onChange={onTab}
          />
          {tab === "fila" ? (
            <Fila code={room.code} live={live} manage={manage} controls={controls} onAdd={() => onTab("adicionar")} />
          ) : (
            <Adicionar code={room.code} />
          )}
        </>
      )}
    </>
  );
}

// --- Fila ---------------------------------------------------------------------------------------------------------

function Fila({
  code,
  live,
  manage: host,
  controls,
  onAdd,
}: {
  code: string;
  live: Live;
  manage: boolean;
  controls: boolean;
  onAdd: () => void;
}) {
  const toast = useToast();
  const entries = live.entries;
  const [errors, setErrors] = useState<Record<number, string>>({});
  // Keys asked for but not yet confirmed by a snapshot, so quick taps add up
  const [pending, setPending] = useState<Record<number, number>>({});
  // Dragging a song by its handle: which one, and the one it is over (pointer events, not the browser's drag and
  // drop, which phones and some embedded browsers do not deliver)
  const [drag, setDrag] = useState<{ id: number; over: number } | null>(null);
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    if (!entries) return;
    setPending((current) => {
      const left = Object.entries(current).filter(([id, value]) => entries.find((e) => e.id === Number(id))?.semitones !== value);
      return left.length === Object.keys(current).length ? current : Object.fromEntries(left);
    });
  }, [entries]);

  if (!entries) return <Body><p className="py-2 text-[12px] text-(--menu-text-3)">Carregando a fila…</p></Body>;

  const run = async (entryId: number, action: () => Promise<unknown>, done?: string) => {
    setErrors(({ [entryId]: _, ...rest }) => rest);
    try {
      await action();
      if (done) toast(done);
    } catch (e) {
      setErrors((current) => ({ ...current, [entryId]: (e as Error).message }));
      window.setTimeout(() => setErrors(({ [entryId]: _, ...rest }) => rest), 6000);
    }
  };
  const playing = entries.find((entry) => entry.status === "playing");
  const coming = entries.filter((entry) => entry.status !== "playing");
  // The row under the pointer while dragging
  const rowAt = (y: number): number | null => {
    const rows = [...(list.current?.querySelectorAll<HTMLElement>("[data-entry]") ?? [])];
    if (rows.length === 0) return null;
    const found = rows.find((row) => y < row.getBoundingClientRect().bottom) ?? rows[rows.length - 1];
    return Number(found.dataset.entry);
  };
  // Dropped on another song: it takes that one's place in the whole queue (the playing one stays first)
  const drop = () => {
    if (!drag) return;
    setDrag(null);
    if (drag.over === drag.id) return;
    const position = entries.findIndex((entry) => entry.id === drag.over);
    void run(drag.id, () => api.change(code, drag.id, { position }));
  };
  const indexOf = (id: number) => entries.findIndex((entry) => entry.id === id);
  const mayEdit = (entry: QueueEntry) => host || entry.mine;
  const keyOf = (entry: QueueEntry) => pending[entry.id] ?? entry.semitones;
  const setKeyOf = (entry: QueueEntry) => (n: number) => {
    const value = clampSemitones(n);
    setPending((current) => ({ ...current, [entry.id]: value }));
    void run(entry.id, () => api.change(code, entry.id, { semitones: value }));
  };
  const who = (entry: QueueEntry) => `${entry.singer_name ?? entry.added_by}${!host && entry.mine ? " (você)" : ""}`;
  // Without the handle, the lines under a song start under its title
  const indent = host ? "pl-[62px]" : "pl-[48px]";

  return (
    <Body>
      <Label first>Cantando agora</Label>
      {playing ? (
        <div className="rounded-xl bg-(--menu-field) px-[14px] py-3">
          <div className="flex items-center gap-2.5">
            <Thumb src={playing.song.thumbnail_url} />
            <SongText
              title={songTitle(playing.song)}
              sub={[playing.song.artist, who(playing), keyLabel(playing.song.original_key, keyOf(playing)).current]}
            />
            {!controls && (
              <span className="flex text-(--menu-accent)">
                <Icon name="play" className="h-[18px] w-[18px]" />
              </span>
            )}
          </div>
          {controls ? (
            <PlayerControls
              code={code}
              entry={playing}
              state={live.playerState}
              semitones={keyOf(playing)}
              onKey={setKeyOf(playing)}
              onError={(message) => setErrors((current) => ({ ...current, [playing.id]: message }))}
            />
          ) : (
            !host &&
            playing.mine && (
              <div className="mt-2 pl-[48px]">
                <KeyStepper semitones={keyOf(playing)} onChange={setKeyOf(playing)} />
              </div>
            )
          )}
          {errors[playing.id] && (
            <p role="alert" className="mt-1.5 text-[12px] text-(--menu-err)">
              {errors[playing.id]}
            </p>
          )}
        </div>
      ) : (
        <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">Nada tocando agora.</p>
      )}

      <Label>Próximas · {coming.length}</Label>
      {coming.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl bg-(--menu-field) px-[14px] py-5 text-center">
          <div className="font-medium">Nenhuma música na fila</div>
          <div className="text-[12px] text-(--menu-text-3)">Adicione a primeira música para começar.</div>
          <button className={primary} onClick={onAdd}>
            Adicionar música
          </button>
        </div>
      ) : (
        <ol ref={list} className="flex flex-col">
          {coming.map((entry) => {
            const semitones = keyOf(entry);
            const setKey = setKeyOf(entry);
            const prep = liveProgress(entry, live.progress);
            return (
              <li
                key={entry.id}
                data-entry={entry.id}
                className={`border-b border-(--menu-line) py-1.5 last:border-b-0 ${drag?.id === entry.id ? "opacity-40" : ""} ${
                  drag && drag.over === entry.id && drag.over !== drag.id
                    ? indexOf(drag.id) > indexOf(entry.id)
                      ? "shadow-[inset_0_2px_0_var(--menu-accent)]"
                      : "shadow-[inset_0_-2px_0_var(--menu-accent)]"
                    : ""
                }`}
              >
                <div className="flex items-center gap-2.5">
                  {host && (
                  <span
                    role="button"
                    aria-label={`Arrastar ${songTitle(entry.song)} para mudar a ordem`}
                    title="Arraste para mudar a ordem"
                    className={`-m-1.5 touch-none p-1.5 text-(--menu-text-off) hover:text-(--menu-text-2) ${drag ? "cursor-grabbing" : "cursor-grab"}`}
                    onPointerDown={(event) => {
                      event.preventDefault();
                      event.currentTarget.setPointerCapture(event.pointerId);
                      setDrag({ id: entry.id, over: entry.id });
                    }}
                    onPointerMove={(event) => {
                      if (drag?.id !== entry.id) return;
                      const over = rowAt(event.clientY);
                      if (over !== null && over !== drag.over) setDrag({ ...drag, over });
                    }}
                    onPointerUp={drop}
                    onPointerCancel={() => setDrag(null)}
                  >
                    <Icon name="grip" className="h-4 w-4" />
                  </span>
                  )}
                  <Thumb src={entry.song.thumbnail_url} />
                  <SongText
                    title={songTitle(entry.song)}
                    sub={[entry.song.artist, who(entry), keyLabel(entry.song.original_key, semitones).current]}
                  />
                  {mayEdit(entry) && (
                    <IconButton
                      icon="x"
                      label={`Remover ${songTitle(entry.song)}`}
                      onClick={() => void run(entry.id, () => api.remove(code, entry.id), `“${songTitle(entry.song)}” saiu da fila`)}
                    />
                  )}
                </div>
                {entry.song.status !== "ready" && entry.status !== "awaiting_decision" && (
                  <p className={`mt-1 ${indent} text-[11px] ${entry.song.status === "failed" ? "text-(--menu-err)" : "text-(--menu-text-3)"}`}>
                    {statusText(entry, live.progress)}
                    {!host && entry.song.status === "failed" && " Adicione de novo para tentar outra vez."}
                  </p>
                )}
                {prep && <ProgressBar percent={prep.progress} className={`mt-1 ${host ? "ml-[62px]" : "ml-[48px]"}`} />}
                {mayEdit(entry) && (
                <div className={`mt-1.5 flex flex-wrap items-center gap-2 ${indent}`}>
                  {entry.status === "awaiting_decision" ? (
                    <>
                      <p className="w-full text-[12px] text-(--menu-text-2)">
                        Não encontramos a letra desta música. Quer que ela seja transcrita automaticamente? A
                        transcrição pode ter erros.
                      </p>
                      <button className={primary} onClick={() => void run(entry.id, () => api.answer(code, entry.id, true))}>
                        Sim, transcrever
                      </button>
                      <button className={button} onClick={() => void run(entry.id, () => api.answer(code, entry.id, false))}>
                        Não, remover
                      </button>
                    </>
                  ) : (
                    <KeyStepper semitones={semitones} onChange={setKey} />
                  )}
                  {host && entry.song.status === "failed" && (
                    <button
                      className={button}
                      onClick={() => void run(entry.id, () => api.reprocess(entry.video_id, []), "Vai tentar de novo")}
                    >
                      Tentar de novo
                    </button>
                  )}
                </div>
                )}
                {errors[entry.id] && (
                  <p role="alert" className={`mt-1.5 ${indent} text-[12px] text-(--menu-err)`}>
                    {errors[entry.id]}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </Body>
  );

}

/** −½ · the key · +½, small, for an entry in the queue. */
function KeyStepper({ semitones, onChange }: { semitones: number; onChange: (n: number) => void }) {
  const step = "flex h-7 w-[34px] items-center justify-center rounded-[14px] text-[13px] text-[#e4e4e8] hover:bg-(--menu-btn-hover) disabled:opacity-40";
  return (
    <span className="inline-flex items-center rounded-[17px] bg-(--menu-btn) p-0.5">
      <button className={step} aria-label="Meio tom abaixo" disabled={semitones <= MIN_SEMITONES} onClick={() => onChange(semitones - 1)}>
        −½
      </button>
      <button
        className={`min-w-16 px-1.5 text-center font-medium ${semitones ? "text-(--menu-accent)" : ""}`}
        aria-label="Voltar ao tom original"
        title="Voltar ao tom original"
        disabled={semitones === 0}
        onClick={() => onChange(0)}
      >
        {semitones === 0 ? "original" : signed(semitones)}
      </button>
      <button className={step} aria-label="Meio tom acima" disabled={semitones >= MAX_SEMITONES} onClick={() => onChange(semitones + 1)}>
        +½
      </button>
    </span>
  );
}

/** The player, in "Cantando agora" on a phone that manages the room (the host's, the owner's): pause or resume, skip, and, behind the arrow, the guide voice,
 * the TV's lyrics delay and the key (as the floating bar's tray on the TV). The TV does what is asked
 * (player.command); its state comes back every second (player.state). */
function PlayerControls({
  code,
  entry,
  state,
  semitones,
  onKey,
  onError,
}: {
  code: string;
  entry: QueueEntry;
  state: PlayerState | null;
  semitones: number;
  onKey: (n: number) => void;
  onError: (message: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [guide, setGuide] = useState(0);
  const [delayMs, setDelayMs] = useState(0);
  const mine = state?.entry_id === entry.id;
  const paused = mine ? state.paused : false;
  const position = mine ? state.position : 0;
  const duration = entry.song.duration_s ?? 0;
  const ask = async (action: () => Promise<unknown>) => {
    try {
      await action();
    } catch (e) {
      onError((e as Error).message);
    }
  };
  const delay = (ms: number) => {
    const value = Math.max(-DELAY_LIMIT_MS, Math.min(DELAY_LIMIT_MS, ms));
    setDelayMs(value);
    void ask(() => api.playerValue(code, "delay", value));
  };
  const key = parseKey(entry.song.original_key);
  // "Sib menor · +1", or only the shift when the key is unknown
  const name = key
    ? `${keyName(key, semitones)}${semitones ? ` · ${signed(semitones)}` : ""}`
    : semitones
      ? signed(semitones)
      : "original";
  return (
    <div className="mt-3 flex flex-col gap-2.5">
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-(--menu-accent) text-(--menu-on-accent)"
          aria-label={paused ? "Retomar" : "Pausar"}
          title={paused ? "Retomar" : "Pausar"}
          onClick={() => void ask(() => api.player(code, paused ? "play" : "pause"))}
        >
          <Icon name={paused ? "play" : "pause"} className="h-[18px] w-[18px]" />
        </button>
        <RoundButton icon="skip" label="Pular" onClick={() => void ask(() => api.player(code, "skip"))} />
        <span className="shrink-0 text-[12px] text-(--menu-text-3) tabular-nums">
          {formatTime(position)} / {formatTime(duration)}
        </span>
        <div className="h-1 min-w-0 flex-1 rounded-full bg-(--menu-thumb)">
          <div
            className="h-full rounded-full bg-(--menu-accent)"
            style={{ width: `${duration ? Math.min(100, (100 * position) / duration) : 0}%` }}
          />
        </div>
        <RoundButton
          icon={open ? "down" : "up"}
          label={open ? "Recolher os ajustes" : "Mostrar os ajustes"}
          active={open}
          onClick={() => setOpen(!open)}
        />
      </div>
      {open && (
        <div className="flex flex-col gap-2 rounded-xl bg-(--menu-panel) p-2.5">
          <div className="flex items-center gap-2.5">
            <span className="shrink-0 text-[12px] whitespace-nowrap text-(--menu-text-2)">Voz guia</span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={guide}
              onChange={(event) => setGuide(Number(event.target.value))}
              onPointerUp={() => void ask(() => api.playerValue(code, "guide", guide))}
              onKeyUp={() => void ask(() => api.playerValue(code, "guide", guide))}
              aria-label="Voz guia"
              className="menu-range min-w-12 flex-1"
              style={{ ["--v" as string]: `${guide}%` }}
            />
            <span className="min-w-[34px] text-right text-[12px] tabular-nums">{guide}%</span>
          </div>
          <div className="flex items-center gap-2.5">
            <span className="shrink-0 text-[12px] whitespace-nowrap text-(--menu-text-2)">Atraso da letra na TV</span>
            <span className="ml-auto inline-flex items-center rounded-[17px] bg-(--menu-field) p-0.5">
              <button className={step} aria-label="Diminuir atraso" onClick={() => delay(delayMs - DELAY_STEP_MS)}>
                −
              </button>
              <span className="min-w-16 text-center text-[13px] tabular-nums">{seconds(delayMs)} s</span>
              <button className={step} aria-label="Aumentar atraso" onClick={() => delay(delayMs + DELAY_STEP_MS)}>
                +
              </button>
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <span className="shrink-0 text-[12px] whitespace-nowrap text-(--menu-text-2)">Tom</span>
            <span className="ml-auto inline-flex items-center rounded-[17px] bg-(--menu-field) p-0.5">
              <button className={step} aria-label="Meio tom abaixo" disabled={semitones <= MIN_SEMITONES} onClick={() => onKey(semitones - 1)}>
                −½
              </button>
              <span className={`min-w-24 px-1.5 text-center font-medium ${semitones ? "text-(--menu-accent)" : ""}`} aria-live="polite">
                {name}
              </span>
              <button className={step} aria-label="Meio tom acima" disabled={semitones >= MAX_SEMITONES} onClick={() => onKey(semitones + 1)}>
                +½
              </button>
            </span>
            <RoundButton
              icon="reset"
              label={key ? `Voltar ao original: ${keyName(key)}` : "Voltar ao tom original"}
              onClick={() => onKey(0)}
            />
          </div>
        </div>
      )}
    </div>
  );
}

const step =
  "flex h-7 w-[34px] items-center justify-center rounded-[14px] text-[13px] text-[#e4e4e8] hover:bg-(--menu-btn-hover) disabled:opacity-40";

function SongText({ title, sub }: { title: string; sub: (string | null | undefined)[] }) {
  return (
    <div className="min-w-0 flex-1">
      <div className="truncate font-medium">{title}</div>
      <div className="truncate text-[11px] text-(--menu-text-3)">{sub.filter(Boolean).join(" · ")}</div>
    </div>
  );
}

// --- Adicionar ------------------------------------------------------------------------------------------------------

const YOUTUBE_SHOWN = 3;
const DEBOUNCE_MS = 400;

function Adicionar({ code }: { code: string }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [remote, setRemote] = useState(""); // the text YouTube searches, after a pause
  const [more, setMore] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const q = text.trim();
  useEffect(() => {
    setMore(false);
    const timer = window.setTimeout(() => setRemote(q.length >= 2 ? q : ""), DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [q]);
  const library = useQuery({ queryKey: ["library", q], queryFn: () => api.library(q), placeholderData: (previous) => previous });
  // A new text is a new query: an older answer never shows for it
  const youtube = useQuery({ queryKey: ["search", remote], queryFn: () => api.search(remote), enabled: !!remote });
  const fromYoutube = (youtube.data ?? []).filter((result) => !result.in_library); // in the library: shown there only
  const waitingForYoutube = q.length >= 2 && (remote !== q || youtube.isFetching);
  const added = (title: string) => {
    setPicked(null);
    toast(`“${title}” entrou na fila`);
  };

  return (
    <Body>
      <label className="flex items-center gap-2 rounded-[10px] border border-transparent bg-(--menu-field) px-3 py-2 focus-within:border-(--menu-accent)">
        <Icon name="search" className="h-[17px] w-[17px] text-(--menu-text-3)" />
        <input
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-(--menu-text-off)"
          placeholder="Buscar música ou artista"
          aria-label="Buscar música ou artista"
          autoComplete="off"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        {text && (
          <button type="button" className="flex text-(--menu-text-3)" aria-label="Limpar busca" onClick={() => setText("")}>
            <Icon name="x" className="h-4 w-4" />
          </button>
        )}
      </label>

      <Label>
        <Icon name="books" className="h-3.5 w-3.5" />
        {q ? `No acervo · ${library.data?.length ?? 0} resultado${library.data?.length === 1 ? "" : "s"}` : `No acervo · ${library.data?.length ?? 0}`}
      </Label>
      {library.isError && <p className="text-[12px] text-(--menu-err)">{library.error.message}</p>}
      {library.data?.length === 0 && (
        <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">
          {q ? "Nada no acervo com esse nome." : "O acervo ainda está vazio."}
        </p>
      )}
      {library.data?.map((song) => (
        <ResultRow
          key={song.video_id}
          sources={previewSources(song.video_id, song.media?.original)}
          thumbnail={song.thumbnail_url}
          title={songTitle(song)}
          sub={[song.artist ?? song.channel, song.duration_s ? formatTime(song.duration_s) : null]}
          picked={picked === song.video_id}
          onPick={() => setPicked(picked === song.video_id ? null : song.video_id)}
        >
          <AddForm code={code} result={{ video_id: song.video_id, title: songTitle(song) }} onAdded={added} />
        </ResultRow>
      ))}

      <Label>
        <Icon name="youtube" className="h-3.5 w-3.5" />
        No YouTube · 10 mais relevantes
      </Label>
      {q.length < 2 ? (
        <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">Digite ao menos 2 letras para buscar no YouTube.</p>
      ) : waitingForYoutube ? (
        Array.from({ length: YOUTUBE_SHOWN }, (_, i) => <SkeletonRow key={i} />)
      ) : youtube.isError ? (
        <p className="px-0.5 py-1 text-[12px] text-(--menu-err)">
          A busca no YouTube falhou agora. O acervo continua funcionando; tente de novo em instantes.
        </p>
      ) : fromYoutube.length === 0 ? (
        <p className="px-0.5 py-1 text-[12px] text-(--menu-text-3)">Nada novo no YouTube com esse nome.</p>
      ) : (
        <>
          {(more ? fromYoutube : fromYoutube.slice(0, YOUTUBE_SHOWN)).map((result) => {
            const id = `youtube:${result.video_id}`;
            return (
              <ResultRow
                key={id}
                sources={previewSources(result.video_id)}
                thumbnail={result.thumbnail_url}
                title={result.title ?? result.video_id}
                sub={[result.channel, result.duration_s ? formatTime(result.duration_s) : null]}
                warning={tooLong(result) ? `Longo demais para o karaokê (mais de ${MAX_SONG_S / 60} min)` : undefined}
                picked={picked === id}
                onPick={() => setPicked(picked === id ? null : id)}
              >
                <AddForm code={code} result={{ video_id: result.video_id, title: result.title }} onAdded={added} />
              </ResultRow>
            );
          })}
          {fromYoutube.length > YOUTUBE_SHOWN && (
            <button className="py-1.5 text-center text-[12px] text-(--menu-accent)" onClick={() => setMore(!more)}>
              {more ? "Mostrar menos" : `Mostrar mais ${fromYoutube.length - YOUTUBE_SHOWN}`}
            </button>
          )}
        </>
      )}
    </Body>
  );
}

/** A result: picture, title, who and how long, "Ouvir" and "Adicionar"; picked, it opens the add form below. */
function ResultRow({
  sources,
  thumbnail,
  title,
  sub,
  warning,
  picked,
  onPick,
  children,
}: {
  sources: string[];
  thumbnail: string | null;
  title: string;
  sub: (string | null | undefined)[];
  warning?: string;
  picked: boolean;
  onPick: () => void;
  children: ReactNode;
}) {
  const preview = usePreview(sources);
  const playing = preview.state === "playing";
  return (
    <div className={`rounded-xl px-2 py-1 ${picked ? "border border-(--menu-accent) bg-(--menu-field) py-2" : "border border-transparent"}`}>
      <div className="flex items-center gap-2.5">
        <Thumb src={thumbnail} />
        <button className="min-w-0 flex-1 text-left" onClick={onPick}>
          <div className="truncate font-medium">{title}</div>
          <div className="truncate text-[11px] text-(--menu-text-3)">{sub.filter(Boolean).join(" · ")}</div>
          {warning && <div className="text-[11px] text-(--menu-err)">{warning}</div>}
        </button>
        <RoundButton
          icon={playing ? "stop" : "headphones"}
          label={playing ? "Parar a prévia" : "Ouvir a prévia"}
          active={playing}
          onClick={preview.toggle}
        />
        <RoundButton icon={picked ? "x" : "plus"} label={picked ? "Fechar sem adicionar" : "Adicionar à fila"} accent={!picked} onClick={onPick} />
      </div>
      <PreviewBar preview={preview} />
      {picked && children}
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="flex items-center gap-2.5 px-2 py-1" aria-hidden="true">
      <div className="menu-skeleton h-[38px] w-[38px] shrink-0 rounded-md" />
      <div className="flex-1">
        <div className="menu-skeleton my-1 h-2.5 w-3/4 rounded-[5px]" />
        <div className="menu-skeleton my-1 h-2.5 w-1/2 rounded-[5px]" />
      </div>
    </div>
  );
}
