import { expect, test } from "@playwright/test";
import type { QueueEntry, Song } from "../src/api";
import { nextEntry, statusText } from "../src/lib/queue";

let id = 0;
const entry = (status: string, songStatus: string, extra: Partial<Song> = {}): QueueEntry => ({
  id: ++id,
  video_id: `video${id}`.padEnd(11, "x"),
  position: id,
  status,
  singer_name: "Ana",
  semitones: 0,
  added_by: "Ana",
  mine: false,
  song: {
    video_id: `video${id}`, title: "T", artist: null, track: null, channel: null, duration_s: 100,
    thumbnail_url: null, status: songStatus, stage: null, original_key: null, language: null, lyrics_source: null,
    alignment_confidence: null, error: null, media: null, ...extra,
  },
});

test("the first ready entry plays", () => {
  const ready = entry("queued", "ready");
  expect(nextEntry([ready, entry("queued", "ready")])).toEqual({ kind: "play", entry: ready });
});

test("an entry waiting for the transcription answer, or whose song failed, is skipped", () => {
  const ready = entry("queued", "ready");
  expect(nextEntry([entry("awaiting_decision", "awaiting_decision"), entry("queued", "failed"), ready])).toEqual({
    kind: "play",
    entry: ready,
  });
});

test("a song still processing makes the TV wait instead of jumping ahead", () => {
  const processing = entry("queued", "processing");
  expect(nextEntry([processing, entry("queued", "ready")])).toEqual({ kind: "wait", entry: processing });
});

test("an entry already playing (the TV reloaded) comes first", () => {
  const playing = entry("playing", "ready");
  expect(nextEntry([entry("queued", "ready"), playing])).toEqual({ kind: "play", entry: playing });
});

test("an empty queue, or one with only skipped entries, is empty", () => {
  expect(nextEntry([])).toEqual({ kind: "empty" });
  expect(nextEntry([entry("awaiting_decision", "awaiting_decision")])).toEqual({ kind: "empty" });
});

test("the status line says what is happening", () => {
  expect(statusText(entry("queued", "processing", { stage: "separation" }), {})).toBe("Separando a voz");
  const live = entry("queued", "processing");
  expect(statusText(live, { [live.video_id]: { stage: "alignment", progress: 62 } })).toBe("Sincronizando a letra · 62%");
  expect(statusText(entry("awaiting_decision", "awaiting_decision"), {})).toBe("Letra não encontrada: aguardando resposta");
  expect(statusText(entry("queued", "failed", { error: "boom" }), {})).toBe("Erro no processamento: boom");
});
