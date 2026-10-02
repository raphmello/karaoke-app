// The room's WebSocket (docs/ARCHITECTURE.md, "WebSocket"): the queue, progress, questions and the player's state.
// On a dropped connection it reconnects with growing waits and gets a fresh queue.snapshot.
import { useCallback, useEffect, useRef, useState } from "react";
import type { QueueEntry } from "../api";
import type { Progress } from "../lib/queue";

export type PlayerState = { entry_id: number | null; position: number; paused: boolean; semitones: number };
export type Command = { action: "play" | "pause" | "skip" | "key" | "guide" | "delay"; semitones?: number; value?: number };

const GONE = new Set([4401, 4403, 4404]); // no cookie, another room, room closed: reconnecting won't help

export function useRoom(code: string | null, options: { tv?: boolean; onCommand?: (command: Command) => void } = {}) {
  const [entries, setEntries] = useState<QueueEntry[] | null>(null);
  const [playerState, setPlayerState] = useState<PlayerState | null>(null);
  const [progress, setProgress] = useState<Progress>({});
  const [question, setQuestion] = useState<{ video_id: string; entries: number[] } | null>(null);
  const [connected, setConnected] = useState(false);
  const [closedWith, setClosedWith] = useState<number | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const onCommand = useRef(options.onCommand);
  onCommand.current = options.onCommand;

  useEffect(() => {
    if (!code) return;
    let stopped = false;
    let wait = 1000;
    let timer = 0;

    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${location.host}/ws/rooms/${code}${options.tv ? "?role=tv" : ""}`);
      socket.current = ws;
      ws.onopen = () => {
        setConnected(true);
        wait = 1000;
      };
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        switch (message.type) {
          case "queue.snapshot":
            setEntries(message.entries);
            break;
          case "player.state":
            setPlayerState(message);
            break;
          case "player.command":
            onCommand.current?.(message);
            break;
          case "song.progress":
            setProgress((p) => ({ ...p, [message.video_id]: { stage: message.stage, progress: message.progress } }));
            break;
          case "song.ready":
          case "song.failed":
            setProgress(({ [message.video_id]: _, ...rest }) => rest);
            break;
          case "song.lyrics_missing":
            setQuestion({ video_id: message.video_id, entries: message.entries });
            break;
        }
      };
      ws.onclose = (event) => {
        setConnected(false);
        socket.current = null;
        if (stopped) return;
        if (GONE.has(event.code)) {
          setClosedWith(event.code);
          return;
        }
        timer = window.setTimeout(connect, wait);
        wait = Math.min(wait * 2, 15000);
      };
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket.current?.close();
    };
  }, [code, options.tv]);

  const send = useCallback((message: object) => {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(message));
  }, []);

  return { entries, playerState, progress, question, connected, closedWith, send, dismissQuestion: () => setQuestion(null) };
}
