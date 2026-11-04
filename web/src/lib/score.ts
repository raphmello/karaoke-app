// The score at the end of a song: a random
// number from 70 to 100, only for fun. The app does not judge the singing and never says it does.

export const MIN_SCORE = 70;
export const MAX_SCORE = 100;
export const SUSPENSE_MS = 4200; // the needle climbs while the drums roll
export const HOLD_MS = 5200; // the score stays this long once it locks

export function pickScore(random = Math.random): number {
  return MIN_SCORE + Math.floor(random() * (MAX_SCORE - MIN_SCORE + 1));
}

/** A song skipped before half of it was sung gets no score. */
export function deservesScore(position: number, duration: number): boolean {
  return duration > 0 && position >= duration / 2;
}

const PHRASES: [number, string[]][] = [
  [95, ["Lenda! Pode lançar disco.", "O palco é seu.", "Nota de show de estádio!"]],
  [90, ["Arrasou!", "Que voz!", "A sala inteira cantou junto."]],
  [80, ["Mandou bem!", "Bonito de ver.", "Tá pronto pro bis."]],
  [70, ["Valeu a coragem!", "Ninguém esquece essa.", "No próximo vem o 100."]],
];

export function phrase(score: number, random = Math.random): string {
  const list = (PHRASES.find(([min]) => score >= min) ?? PHRASES[PHRASES.length - 1])[1];
  return list[Math.floor(random() * list.length)];
}

const easeOut = (t: number) => 1 - (1 - t) ** 3;

/** Where the needle stands at a moment t (0 to 1) of the suspense: it climbs past the score to `peak`, hesitates,
 *  slips back and locks on the score at t = 1 (trembling aside, added by the screen). */
export function needle(t: number, score: number, peak: number): number {
  if (t >= 1) return score;
  if (t < 0.7) return peak * easeOut(t / 0.7);
  if (t < 0.85) return peak - (peak - score) * 0.3 * ((t - 0.7) / 0.15);
  return peak - (peak - score) * (0.3 + 0.7 * easeOut((t - 0.85) / 0.15));
}
