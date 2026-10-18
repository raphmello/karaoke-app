// /tv/<code>: one room's TV (docs/ARCHITECTURE.md, "Salas"). Its password, its owner or the admin opens it (anyone,
// in a room without a password). From "Abrir como TV" it opens ready, with the audio that tap started; opened by its
// address or reloaded, it asks for one tap first, since the browser plays no sound before one. Then it plays the
// room's queue in order.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, onSessionLost, retryWhileRestarting, type QueueEntry, type RoomInfo } from "../api";
import { keyLabel } from "../lib/keys";
import { liveProgress, type Next, nextEntry, songTitle, statusText } from "../lib/queue";
import { AudioEngine } from "../player/engine";
import { ProgressBar } from "../room/ProgressBar";
import { type Command, useRoom } from "../room/useRoom";
import { type Failure, FailedSongs } from "./FailedSongs";
import { useCompact } from "./compact";
import { JoinQr } from "./JoinQr";
import { useLook } from "./look";
import { engineTaken, handedEngine } from "./OpenTv";
import { type PlayerReport, PlayerScreen } from "./PlayerScreen";
import { TvMenuLayout } from "./TvMenu";

const COUNTDOWN_S = 5; // between songs (docs/ARCHITECTURE.md, "Entre músicas")

export function TvPage({ code }: { code: string }) {
  const queryClient = useQueryClient();
  const [closed, setClosed] = useState(false); // the room was removed or expired: the song playing finishes
  const [engine, setEngine] = useState<AudioEngine | null>(null);
  // The tap on "Abrir como TV" already started the audio: the TV opens without asking for another
  const handed = handedEngine(code);
  useEffect(() => {
    if (!handed) return;
    handed.then(
      (ready) => {
        engineTaken(handed);
        setEngine(ready);
      },
      () => engineTaken(handed),
    );
  }, [handed]);
  const info = useQuery({
    queryKey: ["room", code],
    queryFn: () => api.room(code),
    ...retryWhileRestarting,
    enabled: !closed,
  });
  const last = useRef<RoomInfo | null>(null); // what the screen keeps showing once the room is gone
  if (info.data) last.current = info.data;
  const room = info.data ?? last.current;
  const [lost, setLost] = useState(false);
  useEffect(() => onSessionLost(() => setLost(true)), []);

  if (!room) {
    if (info.error instanceof ApiError && info.error.status === 404) {
      return (
        <Centered>
          <p className="text-3xl font-bold">Sala não encontrada</p>
          <p className="text-xl text-zinc-400">A sala {code} foi encerrada ou expirou.</p>
          <RoomsLink big />
        </Centered>
      );
    }
    return (
      <Centered>
        <p className="text-xl text-zinc-400">{info.isError ? "Sem conexão com o servidor. Tentando de novo…" : "Carregando…"}</p>
      </Centered>
    );
  }
  if (!closed && (lost || !room.tv)) {
    return (
      <TvAccess
        room={room}
        engine={engine}
        onEngine={setEngine}
        onDone={() => {
          setLost(false);
          void queryClient.invalidateQueries({ queryKey: ["room", code] });
          void queryClient.invalidateQueries({ queryKey: ["tv-is-host"] });
        }}
      />
    );
  }
  // From here on, the TV has its menu on the right (docs/ARCHITECTURE.md, "Menu lateral")
  return (
    <TvMenuLayout room={room} closed={closed}>
      <TvRoom
        key={room.code}
        room={room}
        engine={engine}
        starting={handed !== null}
        onEngine={setEngine}
        closed={closed}
        onClosed={() => setClosed(true)}
      />
    </TvMenuLayout>
  );
}

/** Back to the list of rooms, to open another one. */
function RoomsLink({ big = false }: { big?: boolean }) {
  return big ? (
    <a className="rounded-2xl bg-amber-400 px-10 py-5 text-3xl font-bold text-zinc-950" href="/">
      Ver salas
    </a>
  ) : (
    <a className="text-center text-sm text-zinc-400 underline hover:text-zinc-200" href="/">
      Ver salas
    </a>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="flex h-full flex-col items-center justify-center gap-6 px-6 text-center">{children}</main>;
}

/** This browser is not the room's TV yet. Its owner, or anyone in a room without a password, opens it with one tap;
 *  otherwise it takes the room's password, or the admin's PIN. The tap that sends it also starts the audio: the
 *  context is made before the first await, while it still counts as the tap; a refusal throws it away. */
function TvAccess({
  room,
  engine,
  onEngine,
  onDone,
}: {
  room: RoomInfo;
  engine: AudioEngine | null;
  onEngine: (engine: AudioEngine) => void;
  onDone: () => void;
}) {
  const free = room.mine || !room.protected; // nothing to type
  const [way, setWay] = useState<"password" | "pin">("password");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const ctx = AudioEngine.context();
    try {
      if (free) await api.roomTv(room.code);
      else if (way === "password") await api.roomTv(room.code, secret);
      else await api.hostLogin(secret);
    } catch (e) {
      void ctx.close().catch(() => undefined);
      setError((e as Error).message);
      setBusy(false);
      return;
    }
    if (!engine) await AudioEngine.create(ctx).then(onEngine, () => void ctx.close().catch(() => undefined));
    else void ctx.close().catch(() => undefined);
    onDone();
  };

  return (
    <main className="flex h-full items-center justify-center px-4">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-zinc-900 p-8">
        <h1 className="text-2xl font-bold">{room.name ?? `Sala ${room.code}`}</h1>
        {free ? (
          room.mine && <p className="text-zinc-400">Esta sala é sua.</p>
        ) : (
          <>
            <p className="text-zinc-400">{way === "password" ? "Digite a senha da sala." : "Digite o PIN do admin."}</p>
            <input
              type="password"
              inputMode={way === "pin" ? "numeric" : undefined}
              autoFocus
              maxLength={64}
              className="rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-xl outline-none focus:border-amber-400"
              value={secret}
              onChange={(event) => setSecret(event.target.value)}
              aria-label={way === "password" ? "Senha da sala" : "PIN do admin"}
            />
          </>
        )}
        {error && <p className="text-red-400">{error}</p>}
        <button
          className="rounded-lg bg-amber-400 px-4 py-3 text-lg font-bold text-zinc-950 disabled:opacity-50"
          disabled={busy || (!free && !secret)}
          autoFocus={free}
        >
          {free ? "Toque para começar" : "Abrir"}
        </button>
        {!free && (
          <button
            type="button"
            className="text-sm text-zinc-400 underline hover:text-zinc-200"
            onClick={() => {
              setWay(way === "password" ? "pin" : "password");
              setSecret("");
              setError(null);
            }}
          >
            {way === "password" ? "Usar o PIN do admin" : "Usar a senha da sala"}
          </button>
        )}
        <RoomsLink />
      </form>
    </main>
  );
}

function TvRoom({
  room,
  engine,
  starting,
  onEngine,
  closed,
  onClosed,
}: {
  room: RoomInfo;
  engine: AudioEngine | null;
  starting: boolean; // the tap on "Abrir como TV" started the audio, which is getting ready
  onEngine: (engine: AudioEngine) => void;
  closed: boolean;
  onClosed: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  // Opened by its address or reloaded: the browser plays no sound before a tap on this page
  const start = async () => {
    try {
      onEngine(await AudioEngine.create());
    } catch (e) {
      setError(`O áudio não pôde ser iniciado: ${(e as Error).message}`);
    }
  };

  // Before the audio starts nothing plays: the notice can take the whole screen.
  if (closed && !engine) return <ClosedNotice room={room} />;
  if (!engine && starting) {
    return (
      <Centered>
        <p className="text-xl text-zinc-400">Abrindo a TV…</p>
      </Centered>
    );
  }
  if (!engine) {
    return (
      <Centered>
        <p className="text-3xl font-bold">{room.name ?? `Sala ${room.code}`}</p>
        <button className="rounded-2xl bg-amber-400 px-10 py-5 text-3xl font-bold text-zinc-950" onClick={start} autoFocus>
          Toque para começar
        </button>
        {error && <p className="text-red-400">{error}</p>}
      </Centered>
    );
  }
  return <TvQueue room={room} engine={engine} closed={closed} onClosed={onClosed} />;
}

/** The room was removed or expired: its QR no longer works. */
function ClosedNotice({ room }: { room: RoomInfo }) {
  return (
    <Centered>
      <p className="text-4xl font-bold">A sala {room.name ?? room.code} foi encerrada</p>
      <p className="text-xl text-zinc-400">Escolha outra sala para continuar.</p>
      <RoomsLink big />
    </Centered>
  );
}

/** Over the song still playing in a closed room: it finishes, and the TV can move on at any time. */
function ClosedBanner({ room }: { room: RoomInfo }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 bg-amber-950 px-6 py-3 text-amber-100">
      <p>
        <span className="font-bold">A sala {room.name ?? room.code} foi encerrada.</span> Esta música vai até o fim.
      </p>
      <a className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950" href="/">
        Ver salas
      </a>
    </div>
  );
}

function TvQueue({
  room,
  engine,
  closed,
  onClosed,
}: {
  room: RoomInfo;
  engine: AudioEngine;
  closed: boolean;
  onClosed: () => void;
}) {
  const commands = useRef<((command: Command) => void) | null>(null);
  const [current, setCurrent] = useState<QueueEntry | null>(null);
  const [look, changeLook] = useLook(room.code);
  const [semitones, setSemitones] = useState(0);
  const finished = useRef(new Set<number>()); // until the next snapshot says so, never replay what just ended
  const send = useRef<(message: object) => void>(() => undefined);
  const [left, setLeft] = useState(COUNTDOWN_S);
  const [held, setHeld] = useState(false); // the host paused between songs
  const compact = useCompact();

  const end = useCallback(() => {
    setCurrent((entry) => {
      if (entry) finished.current.add(entry.id);
      return null;
    });
    // Nothing plays now: the server marks the entry that was playing as done.
    send.current({ type: "player.state", entry_id: null, position: 0, paused: true, semitones: 0 });
  }, []);

  // Songs that could not be prepared: a notice each, named from the queue while it has them
  const [failures, setFailures] = useState<Failure[]>([]);
  const queued = useRef<QueueEntry[] | null>(null);
  const dismissFailure = useCallback((key: number) => setFailures((all) => all.filter((f) => f.key !== key)), []);

  const live = useRoom(room.code, {
    tv: true,
    onSongFailed: (videoId) => {
      const entry = queued.current?.find((e) => e.video_id === videoId);
      const failure = { key: Date.now(), videoId, title: entry ? songTitle(entry.song) : null };
      setFailures((all) => [...all.filter((f) => f.videoId !== videoId), failure]);
    },
    onCommand: (command) => {
      if (command.action === "skip") end();
      else if (command.action === "key" && command.semitones !== undefined) setSemitones(command.semitones);
      else if (!current && (command.action === "pause" || command.action === "play")) setHeld(command.action === "pause");
      else commands.current?.(command);
    },
  });
  send.current = live.send;
  queued.current = live.entries;
  const notices = <FailedSongs failures={failures} onDismiss={dismissFailure} />;

  // The socket closed because the session or the room is gone: check again (a 401 brings back the PIN).
  const queryClient = useQueryClient();
  useEffect(() => {
    if (live.closedWith === 4404) onClosed();
    else if (live.closedWith) void queryClient.invalidateQueries({ queryKey: ["room", room.code] });
  }, [live.closedWith, queryClient, room.code]);

  const entries = live.entries?.filter((entry) => !finished.current.has(entry.id)) ?? null;
  const next = entries ? nextEntry(entries) : null;

  // Between songs: the next ready entry starts on its own after the countdown, unless the host paused it. A skip
  // (the server skips the entry about to start) or a new first entry starts the countdown over.
  const upcoming = !current && !closed && next?.kind === "play" ? next.entry : null;
  const upcomingRef = useRef(upcoming);
  upcomingRef.current = upcoming;
  useEffect(() => setLeft(COUNTDOWN_S), [upcoming?.id]);
  useEffect(() => {
    if (!upcoming || held) return;
    if (left <= 0) {
      const entry = upcomingRef.current!;
      setCurrent(entry);
      setSemitones(entry.semitones);
      return;
    }
    const timer = window.setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [upcoming?.id, held, left]);

  // The entry as the server sees it now: its key may have changed on the owner's phone or the host's screen,
  // and if it left the queue, the TV moves on.
  const latest = current ? live.entries?.find((entry) => entry.id === current.id) : undefined;
  useEffect(() => {
    if (latest) setSemitones(latest.semitones);
  }, [latest?.semitones]);
  useEffect(() => {
    if (current && live.entries && !latest) end();
  }, [current, live.entries, latest, end]);

  const report = useCallback(
    ({ position, paused }: PlayerReport) => {
      if (current) live.send({ type: "player.state", entry_id: current.id, position, paused, semitones });
    },
    [current, semitones, live.send],
  );

  if (current) {
    return (
      <>
        <PlayerScreen
          key={current.id}
          song={current.song}
          singer={current.singer_name ?? current.added_by}
          engine={engine}
          semitones={semitones}
          onSemitones={(value) => {
            setSemitones(value);
            void api.change(room.code, current.id, { semitones: value }).catch(() => undefined);
          }}
          onSkip={() => void api.player(room.code, "skip").catch(end)}
          onEnded={end}
          onReport={report}
          commands={commands}
          corner={
            closed ? undefined : compact ? (
              <JoinQr room={room} size={72} />
            ) : (
              <JoinQr room={room} size={150} caption="Leia para entrar e escolher músicas" />
            )
          }
          look={look}
          onLook={changeLook}
          upNext={
            closed ? undefined : (
              <UpNext next={nextEntry(entries?.filter((e) => e.id !== current.id) ?? [])} compact={compact} />
            )
          }
          banner={closed ? <ClosedBanner room={room} /> : undefined}
        />
        {notices}
      </>
    );
  }
  if (closed) return <ClosedNotice room={room} />;
  if (upcoming) {
    return (
      <>
        <BetweenSongs room={room} entry={upcoming} left={left} held={held} connected={live.connected} compact={compact} />
        {notices}
      </>
    );
  }
  return (
    <Centered>
      {next?.kind === "wait" ? (
        <>
          <p className="text-3xl font-bold">Preparando a próxima: {songTitle(next.entry.song)}</p>
          <p className="text-xl text-zinc-400">
            {next.entry.singer_name ?? next.entry.added_by} · {statusText(next.entry, live.progress)}
          </p>
          {liveProgress(next.entry, live.progress) && (
            <ProgressBar percent={liveProgress(next.entry, live.progress)!.progress} className="h-3 w-full max-w-xl" />
          )}
        </>
      ) : (
        <>
          <p className="text-3xl font-bold">Leia o QR Code e escolha uma música</p>
          <p className="text-xl text-zinc-400">A fila está vazia. A primeira música começa assim que ficar pronta.</p>
        </>
      )}
      <JoinQr room={room} size={260} />
      {!live.connected && <p className="text-amber-300">Reconectando ao servidor…</p>}
      {notices}
    </Centered>
  );
}

/** Between songs: the next singer, the song, its key and the QR, then a short countdown. */
function BetweenSongs({
  room,
  entry,
  left,
  held,
  connected,
  compact,
}: {
  room: RoomInfo;
  entry: QueueEntry;
  left: number;
  held: boolean;
  connected: boolean;
  compact: boolean;
}) {
  const key = keyLabel(entry.song.original_key, entry.semitones);
  if (compact) {
    return (
      <main className="flex h-full flex-col items-center justify-center gap-6 overflow-y-auto px-4 py-6 text-center short:flex-row short:gap-10">
        <div className="flex min-w-0 flex-col items-center gap-2">
          <p className="text-sm tracking-widest text-zinc-400 uppercase">Próxima</p>
          <p className="max-w-full truncate text-4xl font-bold text-amber-300">{entry.singer_name ?? entry.added_by}</p>
          <p className="text-xl font-semibold">{songTitle(entry.song)}</p>
          <p className="text-zinc-400">
            {entry.song.artist ?? entry.song.channel} · {key.current}
          </p>
          <p className="mt-3 text-3xl font-bold tabular-nums" aria-live="polite">
            {held ? <span className="text-xl text-zinc-400">Pausado pelo host</span> : `Começa em ${Math.max(left, 0)}`}
          </p>
          {!connected && <p className="text-amber-300">Reconectando ao servidor…</p>}
        </div>
        <JoinQr room={room} size={160} />
      </main>
    );
  }
  return (
    <main className="flex h-full flex-col items-center justify-center gap-12 px-8 lg:flex-row lg:gap-24">
      <div className="flex max-w-3xl flex-col items-center gap-4 text-center lg:items-start lg:text-left">
        <p className="text-2xl tracking-widest text-zinc-400 uppercase">Próxima</p>
        <p className="text-6xl font-bold text-amber-300 md:text-7xl">{entry.singer_name ?? entry.added_by}</p>
        <p className="text-3xl font-semibold md:text-4xl">{songTitle(entry.song)}</p>
        <p className="text-xl text-zinc-400">
          {entry.song.artist ?? entry.song.channel} · {key.current}
        </p>
        <p className="mt-6 text-5xl font-bold tabular-nums" aria-live="polite">
          {held ? <span className="text-3xl text-zinc-400">Pausado pelo host</span> : `Começa em ${Math.max(left, 0)}`}
        </p>
        {!connected && <p className="text-amber-300">Reconectando ao servidor…</p>}
      </div>
      <JoinQr room={room} size={220} />
    </main>
  );
}

/** In a corner while a song plays: who sings next, and what. Nothing when the queue has nothing to play. */
function UpNext({ next, compact }: { next: Next; compact: boolean }) {
  if (next.kind === "empty") return null;
  const { entry } = next;
  if (compact) {
    // one line, between the lyrics and the controls
    return (
      <p className="truncate rounded-lg bg-black/60 px-3 py-1.5 text-sm backdrop-blur-sm">
        <span className="font-semibold tracking-widest text-amber-300 uppercase">A seguir</span>{" "}
        <span className="font-bold">{entry.singer_name ?? entry.added_by}</span>
        <span className="text-zinc-300"> · {songTitle(entry.song)}</span>
      </p>
    );
  }
  return (
    <div className="max-w-sm rounded-xl bg-black/60 px-4 py-3 backdrop-blur-sm">
      <p className="text-xs font-semibold tracking-widest text-amber-300 uppercase">
        A seguir{next.kind === "wait" ? " · preparando" : ""}
      </p>
      <p className="truncate text-2xl font-bold">{entry.singer_name ?? entry.added_by}</p>
      <p className="truncate text-zinc-300">
        {songTitle(entry.song)}
        {entry.song.artist ? ` · ${entry.song.artist}` : ""}
      </p>
    </div>
  );
}
