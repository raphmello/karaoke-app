// What waits for someone's answer (docs/ARCHITECTURE.md, "Pronúncia"): a song whose lyrics were not found
// ("transcrever?") or whose automatic pronunciation waits ("usar a pronúncia automática?"). Such a song does not play
// until someone answers, so whoever can answer (the entry's owner, the room's owner, the host) gets a notice at the
// top with "Ver na fila", which opens the queue at the song, where the question is; for the host, a song in no
// queue (reprocessed in the library) has "Ver no Acervo". It stays until answered or dismissed by its ✕.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type QueueEntry } from "../api";
import { songTitle } from "../lib/queue";

export type Question = { key: string; videoId: string; title: string; about: "letra" | "fonetica"; inQueue: boolean };

/** The questions this person can answer, one per song: their own entries', or every entry's for who manages the room. */
export function questions(entries: QueueEntry[] | null, admin: boolean): Question[] {
  const found = new Map<string, Question>();
  for (const entry of entries ?? []) {
    if (!admin && !entry.mine) continue;
    const about =
      entry.status === "awaiting_decision"
        ? "letra"
        : entry.status === "queued" && entry.song.status === "ready" && entry.song.phonetic_source === "pendente"
          ? "fonetica"
          : null;
    if (about && !found.has(entry.video_id)) {
      found.set(entry.video_id, {
        key: `${about}:${entry.video_id}`,
        videoId: entry.video_id,
        title: songTitle(entry.song),
        about,
        inQueue: true,
      });
    }
  }
  return [...found.values()];
}

/** The notices, for the stack at the top of the screen (FailedSongs' container). */
export function AnswerNotices({
  entries,
  admin,
  host = false,
  onShow,
}: {
  entries: QueueEntry[] | null;
  admin: boolean; // answers for any entry of the room (the host, the room's owner)
  host?: boolean; // the host: also the songs in no queue
  onShow: (videoId: string, inQueue: boolean) => void;
}) {
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  // The host's library: a song in no queue whose automatic pronunciation waits (reprocessed there)
  const library = useQuery({ queryKey: ["library", ""], queryFn: () => api.library(""), enabled: host, refetchInterval: 15_000 });
  const inQueue = questions(entries, admin);
  const elsewhere: Question[] = (host ? (library.data ?? []) : [])
    .filter((song) => song.phonetic_source === "pendente" && !inQueue.some((q) => q.videoId === song.video_id))
    .map((song) => ({ key: `fonetica:${song.video_id}`, videoId: song.video_id, title: songTitle(song), about: "fonetica", inQueue: false }));
  const shown = [...inQueue, ...elsewhere].filter((question) => !dismissed.has(question.key));
  const dismiss = (key: string) => setDismissed((current) => new Set([...current, key]));
  return (
    <>
      {shown.map((question) => (
        <div
          key={question.key}
          role="status"
          className="pointer-events-auto flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-zinc-900/95 px-4 py-3 text-left text-sm shadow-xl ring-1 ring-amber-400/60"
        >
          <span className="min-w-[12rem] flex-1 text-zinc-100">
            “{question.title}” espera uma resposta:{" "}
            {question.about === "letra"
              ? "a letra não foi encontrada. Transcrever?"
              : "a pronúncia dos fãs não foi encontrada. Usar a automática?"}{" "}
            {question.inQueue && "Ela só toca depois da resposta."}
          </span>
          <button
            className="shrink-0 rounded-lg bg-amber-400 px-3 py-1.5 font-bold text-zinc-950"
            onClick={() => {
              onShow(question.videoId, question.inQueue);
              dismiss(question.key);
            }}
          >
            {question.inQueue ? "Ver na fila" : "Ver no Acervo"}
          </button>
          <button aria-label="Dispensar" className="shrink-0 text-zinc-400 hover:text-zinc-100" onClick={() => dismiss(question.key)}>
            ✕
          </button>
        </div>
      ))}
    </>
  );
}
