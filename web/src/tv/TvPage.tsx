// /tv: logs in with the host's PIN (the TV is on the host's PC), finds the open room and plays its queue in order.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type ActiveRoom, api, type QueueEntry } from "../api";
import { nextEntry, songTitle, statusText } from "../lib/queue";
import { AudioEngine } from "../player/engine";
import { HostLogin } from "../room/HostLogin";
import { type Command, useRoom } from "../room/useRoom";
import { JoinQr } from "./JoinQr";
import { type PlayerReport, PlayerScreen } from "./PlayerScreen";

export function TvPage() {
  const queryClient = useQueryClient();
  const active = useQuery({
    queryKey: ["active-room"],
    queryFn: api.activeRoom,
    refetchInterval: (query) => (query.state.data ? false : 5000), // waits for the host to open a room
  });
  const status = active.error instanceof ApiError ? active.error.status : null;

  if (status === 401) {
    return <HostLogin title="Karaokê na TV" onDone={() => void queryClient.invalidateQueries({ queryKey: ["active-room"] })} />;
  }
  if (active.data) return <TvRoom key={active.data.code} room={active.data} />;
  return (
    <Centered>
      <p className="text-3xl font-bold">Nenhuma sala aberta</p>
      <p className="text-xl text-zinc-400">Abra a sala da noite na tela do host (/host). A TV entra nela sozinha.</p>
    </Centered>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="flex h-full flex-col items-center justify-center gap-6 px-6 text-center">{children}</main>;
}

function TvRoom({ room }: { room: ActiveRoom }) {
  const [engine, setEngine] = useState<AudioEngine | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The audio starts from this click, once per session: browsers allow sound only after an interaction.
  const start = async () => {
    try {
      setEngine(await AudioEngine.create());
    } catch (e) {
      setError(`O áudio não pôde ser iniciado: ${(e as Error).message}`);
    }
  };

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
  return <TvQueue room={room} engine={engine} />;
}

function TvQueue({ room, engine }: { room: ActiveRoom; engine: AudioEngine }) {
  const commands = useRef<((command: Command) => void) | null>(null);
  const [current, setCurrent] = useState<QueueEntry | null>(null);
  const [semitones, setSemitones] = useState(0);
  const finished = useRef(new Set<number>()); // until the next snapshot says so, never replay what just ended
  const send = useRef<(message: object) => void>(() => undefined);

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
      else commands.current?.(command);
    },
  });
  send.current = live.send;

  const entries = live.entries?.filter((entry) => !finished.current.has(entry.id)) ?? null;
  const next = entries ? nextEntry(entries) : null;

  // Nothing playing: the next ready entry starts on its own.
  useEffect(() => {
    if (!current && next?.kind === "play") {
      setCurrent(next.entry);
      setSemitones(next.entry.semitones);
    }
  }, [current, next]);

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
        corner={<JoinQr room={room} size={96} />}
      />
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
