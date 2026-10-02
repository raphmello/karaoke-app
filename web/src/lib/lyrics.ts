// What the TV shows at time t, from lyrics/aligned.json (docs/ARCHITECTURE.md, "Letra").

export type Word = { w: string; s: number; e: number; c: number | null };
export type Line = { start: number; end: number; low_confidence: boolean; words: Word[] };
export type Aligned = { version: number; language: string | null; source: string; lines: Line[] };

export const LEAD_S = 1; // a line shows up to 1 s before it is sung, once the previous one has ended
export const BREAK_S = 3; // a pause at least this long gets a countdown (● ● ●)
export const CLEAR_S = 1; // a finished line stays this long before a break clears it
export const LOW_CONFIDENCE = 0.4; // below this mean word confidence a line lights up whole

export type LyricsView = {
  index: number; // the line that has appeared most recently, -1 before the first
  current: Line | null; // big, in the middle
  next: Line | null; // smaller, below
  countdown: number | null; // seconds left before a line that follows a break: 3, 2, 1
};

const gapBefore = (lines: Line[], i: number) => lines[i].start - (i > 0 ? lines[i - 1].end : 0);
const appearsAt = (lines: Line[], i: number) =>
  Math.max(i > 0 ? lines[i - 1].end : -Infinity, lines[i].start - LEAD_S);

export function lyricsAt(lines: Line[], t: number): LyricsView {
  let index = -1;
  while (index + 1 < lines.length && appearsAt(lines, index + 1) <= t) index++;
  const next = lines[index + 1] ?? null;
  let current: Line | null = index >= 0 ? lines[index] : null;
  // In a long break, or after the last line, the finished line clears away.
  if (current && t > current.end + CLEAR_S && (!next || gapBefore(lines, index + 1) >= BREAK_S)) current = null;

  // The countdown runs toward the next line to be sung, when a break comes before it.
  const upcoming = index >= 0 && t < lines[index].start ? index : index + 1;
  let countdown: number | null = null;
  if (upcoming < lines.length && gapBefore(lines, upcoming) >= BREAK_S) {
    const left = lines[upcoming].start - t;
    if (left > 0 && left <= BREAK_S) countdown = Math.ceil(left);
  }
  return { index, current, next, countdown };
}

/** True when the words' own timing can't be trusted: the line lights up whole as it starts. */
export function lightsWhole(line: Line): boolean {
  if (line.low_confidence) return true;
  const scores = line.words.map((word) => word.c).filter((c): c is number => c !== null);
  return scores.length > 0 && scores.reduce((a, b) => a + b, 0) / scores.length < LOW_CONFIDENCE;
}

/** How much of a word is sung at t, 0 to 1: the classic karaoke fill, left to right. */
export function wordFill(line: Line, word: Word, t: number): number {
  if (lightsWhole(line)) return t >= line.start ? 1 : 0;
  if (t <= word.s) return 0;
  if (t >= word.e) return 1;
  return (t - word.s) / (word.e - word.s);
}

/** The line at the focus spot of the scrolling lyrics: the one being sung (or about to be, up to 1 s early); in a
 *  long break, or before the first line, the next one to be sung, so the list has already rolled up to it. */
export function focusIndex(lines: Line[], view: LyricsView): number {
  if (view.current) return view.index;
  return Math.min(view.index + 1, lines.length - 1);
}
