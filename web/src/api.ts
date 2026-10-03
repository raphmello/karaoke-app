// The REST API (docs/ARCHITECTURE.md, "API REST"). Cookies ride along: the host's or the guest's.
import type { Aligned } from "./lib/lyrics";

export type Song = {
  video_id: string;
  title: string | null;
  artist: string | null;
  track: string | null;
  channel: string | null;
  duration_s: number | null;
  thumbnail_url: string | null;
  status: string; // pending, awaiting_decision, processing, ready, failed, removed
  stage: string | null;
  original_key: string | null;
  language: string | null;
  lyrics_source: string | null;
  alignment_confidence: number | null;
  error: string | null;
  media: { instrumental: string; vocals: string; lyrics: string; thumb: string; original: string | null } | null;
};

export type QueueEntry = {
  id: number;
  video_id: string;
  position: number;
  status: string; // queued, awaiting_decision, playing
  singer_name: string | null;
  semitones: number;
  added_by: string;
  mine: boolean;
  song: Song;
};

export type SearchResult = {
  video_id: string;
  title: string | null;
  channel: string | null;
  duration_s: number | null;
  thumbnail_url: string;
  in_library: boolean;
};

export type SongEvent = { kind: string; by: string; details: Record<string, unknown> | null; created_at: string };
export type Job = {
  id: number;
  video_id: string;
  title: string | null;
  status: string; // pending, running, done, failed
  stage: string | null;
  progress: number;
  attempts: number;
  options: { transcribe?: boolean; redo?: string[] };
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};
export type Disk = {
  total_bytes: number;
  free_bytes: number;
  media_bytes: number;
  songs: number;
  removed_songs: number;
  removed_bytes: number;
  low: boolean;
};

export type Room = { code: string; name: string | null; join_path: string };
export type ActiveRoom = Room & { public_base_url: string };
export type Guest = { id: string; nickname: string; room_code: string };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

// The screens listen for a lost session (the host's cookie expired, the API restarted, the guest's room closed):
// the TV and /host go back to the PIN, the phone to joining the room.
const sessionLost = new Set<() => void>();

/** For queries the screens can't do without: retry while the server restarts (502, 503, no network), never when
 *  it refused (4xx, such as a lost session). */
export const retryWhileRestarting = {
  retry: (failures: number, error: Error) => failures < 30 && !(error instanceof ApiError && error.status < 500),
  retryDelay: 2000,
};

export function onSessionLost(listener: () => void): () => void {
  sessionLost.add(listener);
  return () => void sessionLost.delete(listener);
}

async function request<T>(path: string, init?: RequestInit, login = false): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (response.status === 401 && !login) sessionLost.forEach((listener) => listener());
  if (!response.ok) {
    let message = `Erro ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // not JSON
    }
    throw new ApiError(response.status, message);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});
const room = (code: string) => `/api/rooms/${encodeURIComponent(code)}`;
const song = (videoId: string) => `/api/songs/${encodeURIComponent(videoId)}`;

export const api = {
  search: (q: string) => request<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`),
  song: (videoId: string) => request<Song>(song(videoId)),
  hostLogin: (pin: string) => request<void>("/api/host/login", send("POST", { pin }), true), // a wrong PIN is not a lost session
  tvLogin: (pin: string) => request<void>("/api/tv/login", send("POST", { pin }), true), // TV_PIN, or the host's

  activeRoom: () => request<ActiveRoom>("/api/rooms/active"),
  openRoom: (name: string, moveQueue = false) =>
    request<Room>("/api/rooms", send("POST", { name: name || null, move_queue: moveQueue })),
  join: (code: string, nickname: string) => request<Guest>(`${room(code)}/join`, send("POST", { nickname })),
  queue: (code: string) => request<QueueEntry[]>(`${room(code)}/queue`),
  add: (code: string, body: { video_id: string; singer_name?: string; semitones: number }) =>
    request<QueueEntry>(`${room(code)}/queue`, send("POST", body)),
  change: (code: string, id: number, body: { semitones?: number; position?: number }) =>
    request<QueueEntry>(`${room(code)}/queue/${id}`, send("PATCH", body)),
  remove: (code: string, id: number) => request<void>(`${room(code)}/queue/${id}`, send("DELETE")),
  answer: (code: string, id: number, accept: boolean) =>
    request<void>(`${room(code)}/queue/${id}/transcription`, send("POST", { accept })),
  player: (code: string, action: "play" | "pause" | "skip") =>
    request<void>(`${room(code)}/player/${action}`, send("POST")),
  playerValue: (code: string, action: "guide" | "delay", value: number) =>
    request<void>(`${room(code)}/player/${action}`, send("POST", { value })),
  library: (q: string, removed = false) =>
    request<Song[]>(`/api/library?q=${encodeURIComponent(q)}${removed ? "&removed=true" : ""}`),
  replaceLyrics: (videoId: string, text: string) => request<void>(`${song(videoId)}/lyrics`, send("PUT", { text })),
  reprocess: (videoId: string, stages: string[]) =>
    request<{ stages: string[] }>(`${song(videoId)}/reprocess`, send("POST", { stages })),
  removeSong: (videoId: string) => request<void>(song(videoId), send("DELETE")),
  restoreSong: (videoId: string) => request<void>(`${song(videoId)}/restore`, send("POST")),
  history: (videoId: string) => request<SongEvent[]>(`${song(videoId)}/history`),
  jobs: () => request<Job[]>("/api/jobs"),
  // Whether this browser is the host's: the jobs panel answers the host alone (the active room answers the TV too)
  hostCheck: () => request<Job[]>("/api/jobs?limit=1").then(() => true),
  disk: () => request<Disk>("/api/disk"),
};

/** The aligned lyrics, served from the volume; null when the song has none. */
export async function fetchLyrics(url: string): Promise<Aligned | null> {
  const response = await fetch(url);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`letra: ${response.status}`);
  return response.json();
}
