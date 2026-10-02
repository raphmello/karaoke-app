// What the TV plays next, and how a queue entry describes itself (docs/ARCHITECTURE.md, "Entre músicas").
import type { QueueEntry } from "../api";

export type Next =
  | { kind: "play"; entry: QueueEntry }
  | { kind: "wait"; entry: QueueEntry } // the next one is still processing: the TV waits for it
  | { kind: "empty" };

/** In queue order: an entry already playing (the TV reloaded) comes first; entries waiting for the transcription
 *  answer, and songs that failed, are skipped; a song still processing makes the TV wait. */
export function nextEntry(entries: QueueEntry[]): Next {
  const playing = entries.find((entry) => entry.status === "playing" && entry.song.status === "ready");
  if (playing) return { kind: "play", entry: playing };
  for (const entry of entries) {
    if (entry.status !== "queued") continue;
    if (entry.song.status === "ready") return { kind: "play", entry };
    if (entry.song.status === "pending" || entry.song.status === "processing") return { kind: "wait", entry };
  }
  return { kind: "empty" };
}

const STAGES: Record<string, string> = {
  metadata: "Buscando os dados",
  lyrics: "Buscando a letra",
  download: "Baixando o áudio",
  separation: "Separando a voz",
  language: "Detectando o idioma",
  alignment: "Sincronizando a letra",
  key: "Detectando o tom",
  encode: "Finalizando",
};

export type Progress = Record<string, { stage: string; progress: number }>;

export function statusText(entry: QueueEntry, progress: Progress): string {
  if (entry.status === "playing") return "Tocando agora";
  if (entry.status === "awaiting_decision") return "Letra não encontrada: aguardando resposta";
  const song = entry.song;
  if (song.status === "ready") return "Pronta";
  if (song.status === "failed") return `Erro no processamento${song.error ? `: ${song.error}` : ""}`;
  const live = progress[entry.video_id];
  const stage = live?.stage ?? song.stage;
  if (stage) return `${STAGES[stage] ?? stage}${live ? ` · ${live.progress}%` : ""}`;
  return "Na fila para processar";
}

export function songTitle(song: { track: string | null; title: string | null; video_id: string }): string {
  return song.track ?? song.title ?? song.video_id;
}
