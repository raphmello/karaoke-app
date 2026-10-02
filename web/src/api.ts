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
  media: { instrumental: string; vocals: string; lyrics: string; thumb: string } | null;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
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

export const api = {
  search: (q: string) => request<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`),
  song: (videoId: string) => request<Song>(`/api/songs/${encodeURIComponent(videoId)}`),
  hostLogin: (pin: string) => request<void>("/api/host/login", send("POST", { pin })),
  activeRoom: () => request<ActiveRoom>("/api/rooms/active"),
  openRoom: (name: string) => request<Room>("/api/rooms", send("POST", { name: name || null })),
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
};

/** The aligned lyrics, served from the volume; null when the song has none. */
export async function fetchLyrics(url: string): Promise<Aligned | null> {
  const response = await fetch(url);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`letra: ${response.status}`);
  return response.json();
}
