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
  status: string;
  stage: string | null;
  original_key: string | null;
  language: string | null;
  lyrics_source: string | null;
  alignment_confidence: number | null;
  error: string | null;
  media: { instrumental: string; vocals: string; lyrics: string; thumb: string } | null;
};

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

export const api = {
  library: (q: string) => request<Song[]>(`/api/library${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  song: (videoId: string) => request<Song>(`/api/songs/${encodeURIComponent(videoId)}`),
  hostLogin: (pin: string) => request<void>("/api/host/login", { method: "POST", body: JSON.stringify({ pin }) }),
};

/** The aligned lyrics, served from the volume; null when the song has none. */
export async function fetchLyrics(url: string): Promise<Aligned | null> {
  const response = await fetch(url);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`letra: ${response.status}`);
  return response.json();
}
