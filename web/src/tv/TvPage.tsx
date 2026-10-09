// /tv: logs in with the TV's PIN (or the host's), finds the open room and plays its queue in order.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type ActiveRoom, api, onSessionLost, retryWhileRestarting, type QueueEntry } from "../api";
import { keyLabel } from "../lib/keys";
import { type Next, nextEntry, songTitle, statusText } from "../lib/queue";
import { AudioEngine } from "../player/engine";
import { HostLogin } from "../room/HostLogin";
import { type Command, useRoom } from "../room/useRoom";
import { useCompact } from "./compact";
import { JoinQr } from "./JoinQr";
import { useLook } from "./look";
import { type PlayerReport, PlayerScreen } from "./PlayerScreen";
import { TvMenuLayout } from "./TvMenu";

const COUNTDOWN_S = 5; // between songs (docs/ARCHITECTURE.md, "Entre músicas")

export function TvPage() {
  const queryClient = useQueryClient();
  const [room, setRoom] = useState<ActiveRoom | null>(null); // the room the TV is in
  const [closed, setClosed] = useState(false); // the host closed it: the TV offers the new one
  const [engine, setEngine] = useState<AudioEngine | null>(null); // kept across rooms: no second "Iniciar"
  const active = useQuery({
    queryKey: ["active-room"],
    queryFn: api.activeRoom,
    ...retryWhileRestarting,
    // waits for the host to open a room, or the next one after this one closed
    refetchInterval: (query) => (!query.state.data || closed ? 3000 : false),
  });
  const status = active.error instanceof ApiError ? active.error.status : null;
  const [lost, setLost] = useState(false);
  useEffect(() => onSessionLost(() => setLost(true)), []);
  useEffect(() => {
    if (!room && active.data) setRoom(active.data);
  }, [room, active.data]);
  const next = closed && active.data && active.data.code !== room?.code ? active.data : null;

  if (status === 401 || lost) {
    return (
      <HostLogin
        title="Open Karaoke"
        submit="Iniciar"
        onDone={() => {
          setLost(false);
          void queryClient.invalidateQueries();
        }}
        footer={<AdminLink />}
        login={async (pin) => {
          // The tap that sends the PIN also starts the audio: the context is made before the first await, while it
          // still counts as the tap. A wrong PIN throws it away; a failure past the login leaves the "Iniciar" screen.
          const ctx = AudioEngine.context();
          try {
            await api.tvLogin(pin);
          } catch (error) {
            void ctx.close().catch(() => undefined);
            throw error;
          }
          if (!engine) {
            await AudioEngine.create(ctx).then(setEngine, () => void ctx.close().catch(() => undefined));
          } else {
            void ctx.close().catch(() => undefined);
          }
        }}
        prompt="Digite o PIN para Iniciar."
      />
    );
  }
  // From here on, the TV has its menu on the right (docs/ARCHITECTURE.md, "Menu lateral")
  if (room) {
    return (
      <TvMenuLayout room={closed ? null : room}>
        <TvRoom
          key={room.code}
          room={room}
          engine={engine}
          onEngine={setEngine}
          closed={closed ? { next, go: () => next && (setRoom(next), setClosed(false)) } : null}
          onClosed={() => {
            setClosed(true);
            void queryClient.invalidateQueries({ queryKey: ["active-room"] });
          }}
        />
      </TvMenuLayout>
    );
  }
  return (
    <TvMenuLayout room={null}>
      <Centered>
        <p className="text-3xl font-bold">Nenhuma sala aberta</p>
        <p className="text-xl text-zinc-400">
          Abra a sala da noite no menu ☰, à direita, ou na tela do host (/host). A TV entra nela sozinha.
        </p>
      </Centered>
    </TvMenuLayout>
  );
}

/** The way from the TV's PIN screen to the host's screen; past the PIN, the TV's menu is the way to the host. */
function AdminLink() {
  return (
    <a className="text-center text-sm text-zinc-400 underline hover:text-zinc-200" href="/host">
      Acessar como admin
    </a>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="flex h-full flex-col items-center justify-center gap-6 px-6 text-center">{children}</main>;
}

type Closed = { next: ActiveRoom | null; go: () => void } | null;

function TvRoom({
  room,
  engine,
  onEngine,
  closed,
  onClosed,
}: {
  room: ActiveRoom;
  engine: AudioEngine | null;
  onEngine: (engine: AudioEngine) => void;
  closed: Closed;
  onClosed: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  // The audio starts from this click, once per session: browsers allow sound only after an interaction.
  const start = async () => {
    try {
      onEngine(await AudioEngine.create());
    } catch (e) {
      setError(`O áudio não pôde ser iniciado: ${(e as Error).message}`);
    }
  };

  if (closed) {
    // Before "Iniciar" nothing plays: the notice can take the whole screen.
    if (!engine) return <ClosedNotice room={room} closed={closed} />;
  }
  if (!engine) {
    return (
      <Centered>
        <JoinQr room={room} size={220} />
        <button className="rounded-2xl bg-amber-400 px-10 py-5 text-3xl font-bold text-zinc-950" onClick={start} autoFocus>
          Iniciar
        </button>
        {error && <p className="text-red-400">{error}</p>}
      </Centered>
    );
  }
  return <TvQueue room={room} engine={engine} closed={closed} onClosed={onClosed} />;
}

/** The host opened another room: this one's QR no longer works. */
function ClosedNotice({ room, closed }: { room: ActiveRoom; closed: NonNullable<Closed> }) {
  return (
    <Centered>
      <p className="text-4xl font-bold">A sala {room.code} foi encerrada</p>
      {closed.next ? (
        <>
          <p className="text-xl text-zinc-400">
            O host abriu a sala {closed.next.code}
            {closed.next.name ? ` (${closed.next.name})` : ""}.
          </p>
          <button className="rounded-2xl bg-amber-400 px-10 py-5 text-3xl font-bold text-zinc-950" onClick={closed.go} autoFocus>
            Ir para a nova sala
          </button>
        </>
      ) : (
        <p className="text-xl text-zinc-400">Aguardando o host abrir a nova sala…</p>
      )}
    </Centered>
  );
}

/** Over the song still playing in a closed room: it finishes, and the TV can move on at any time. */
function ClosedBanner({ room, closed }: { room: ActiveRoom; closed: NonNullable<Closed> }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 bg-amber-950 px-6 py-3 text-amber-100">
      <p>
        <span className="font-bold">A sala {room.code} foi encerrada.</span>{" "}
        {closed.next ? `A nova sala é ${closed.next.code}. Esta música vai até o fim.` : "Aguardando o host abrir a nova sala…"}
      </p>
      {closed.next && (
        <button className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950" onClick={closed.go}>
          Ir para a nova sala
        </button>
      )}
    </div>
  );
}

function TvQueue({
  room,
  engine,
  closed,
  onClosed,
}: {
  room: ActiveRoom;
  engine: AudioEngine;
  closed: Closed;
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

  const live = useRoom(room.code, {
    tv: true,
    onCommand: (command) => {
      if (command.action === "skip") end();
      else if (command.action === "key" && command.semitones !== undefined) setSemitones(command.semitones);
      else if (!current && (command.action === "pause" || command.action === "play")) setHeld(command.action === "pause");
      else commands.current?.(command);
    },
  });
  send.current = live.send;

  // The socket closed because the session or the room is gone: check again (a 401 brings back the PIN).
  const queryClient = useQueryClient();
  useEffect(() => {
    if (live.closedWith === 4404) onClosed();
    else if (live.closedWith) void queryClient.invalidateQueries({ queryKey: ["active-room"] });
  }, [live.closedWith, queryClient]);

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
        banner={closed ? <ClosedBanner room={room} closed={closed} /> : undefined}
      />
    );
  }
  if (closed) return <ClosedNotice room={room} closed={closed} />;
  if (upcoming) {
    return (
      <BetweenSongs room={room} entry={upcoming} left={left} held={held} connected={live.connected} compact={compact} />
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
        </>
      ) : (
        <>
          <p className="text-3xl font-bold">Leia o QR Code e escolha uma música</p>
          <p className="text-xl text-zinc-400">A fila está vazia. A primeira música começa assim que ficar pronta.</p>
        </>
      )}
      <JoinQr room={room} size={260} />
      {!live.connected && <p className="text-amber-300">Reconectando ao servidor…</p>}
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
  room: ActiveRoom;
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
