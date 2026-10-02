import { expect, test } from "@playwright/test";
import { type Line, lightsWhole, lyricsAt, wordFill } from "../src/lib/lyrics";

const line = (start: number, end: number, words = 2, c: number | null = 0.9, low_confidence = false): Line => ({
  start,
  end,
  low_confidence,
  words: Array.from({ length: words }, (_, i) => ({
    w: `w${i}`,
    s: start + ((end - start) * i) / words,
    e: start + ((end - start) * (i + 1)) / words,
    c,
  })),
});

// 10–14 s, 14.5–18 s, then a break of 7 s, 25–28 s
const LINES = [line(10, 14), line(14.5, 18), line(25, 28)];

test("before the first line: the next line and, after a long intro, a countdown", () => {
  expect(lyricsAt(LINES, 0)).toEqual({ index: -1, current: null, next: LINES[0], countdown: null });
  expect(lyricsAt(LINES, 7.5).countdown).toBe(3);
  expect(lyricsAt(LINES, 8.5).countdown).toBe(2);
});

test("a line shows up 1 s before it is sung, with the countdown down to the last dot", () => {
  const view = lyricsAt(LINES, 9.2);
  expect(view.current).toBe(LINES[0]);
  expect(view.next).toBe(LINES[1]);
  expect(view.countdown).toBe(1);
  expect(lyricsAt(LINES, 10).countdown).toBeNull();
});

test("the next line takes over as soon as the previous ends, never more than 1 s early", () => {
  expect(lyricsAt(LINES, 13.9).current).toBe(LINES[0]);
  expect(lyricsAt(LINES, 14).current).toBe(LINES[1]); // ended at 14, sung at 14.5
});

test("a long break clears the finished line and counts down to the next", () => {
  expect(lyricsAt(LINES, 18.5).current).toBe(LINES[1]);
  const view = lyricsAt(LINES, 20);
  expect(view.current).toBeNull();
  expect(view.next).toBe(LINES[2]);
  expect(lyricsAt(LINES, 22.1).countdown).toBe(3);
  expect(lyricsAt(LINES, 24.5)).toMatchObject({ current: LINES[2], countdown: 1 });
});

test("after the last line, the screen clears", () => {
  expect(lyricsAt(LINES, 28.5).current).toBe(LINES[2]);
  expect(lyricsAt(LINES, 30)).toMatchObject({ current: null, next: null, countdown: null });
});

test("words fill left to right as they are sung", () => {
  const [first, second] = LINES[0].words; // 10–12 and 12–14
  expect(wordFill(LINES[0], first, 9)).toBe(0);
  expect(wordFill(LINES[0], first, 11)).toBe(0.5);
  expect(wordFill(LINES[0], first, 12.5)).toBe(1);
  expect(wordFill(LINES[0], second, 12.5)).toBe(0.25);
});

test("a line with untrustworthy word times lights up whole as it starts", () => {
  for (const shaky of [line(10, 14, 2, 0.9, true), line(10, 14, 2, 0.1)]) {
    expect(lightsWhole(shaky)).toBe(true);
    expect(wordFill(shaky, shaky.words[1], 9.9)).toBe(0);
    expect(wordFill(shaky, shaky.words[1], 10)).toBe(1);
  }
  expect(lightsWhole(line(10, 14, 2, null))).toBe(false);
});
