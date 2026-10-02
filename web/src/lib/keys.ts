// Musical keys as the TV shows them: "Tom: Sol menor (−2) · original: Lá menor".

export const MIN_SEMITONES = -6;
export const MAX_SEMITONES = 6;

const NOTES = ["Dó", "Dó♯", "Ré", "Mi♭", "Mi", "Fá", "Fá♯", "Sol", "Lá♭", "Lá", "Si♭", "Si"];
const PITCH_CLASS: Record<string, number> = {
  C: 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6,
  G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11,
};

export type Key = { pitch: number; minor: boolean };

/** songs.original_key, as essentia writes it: "A minor", "Bb major". */
export function parseKey(value: string | null | undefined): Key | null {
  const [note, scale] = (value ?? "").split(" ");
  if (!(note in PITCH_CLASS) || (scale !== "major" && scale !== "minor")) return null;
  return { pitch: PITCH_CLASS[note], minor: scale === "minor" };
}

export function keyName(key: Key, semitones = 0): string {
  return `${NOTES[(key.pitch + semitones + 120) % 12]} ${key.minor ? "menor" : "maior"}`;
}

export function signed(n: number): string {
  return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0";
}

export function clampSemitones(n: number): number {
  return Math.max(MIN_SEMITONES, Math.min(MAX_SEMITONES, n));
}

/** The current key, always visible, in name and semitones; and the original, when they differ. */
export function keyLabel(originalKey: string | null | undefined, semitones: number) {
  const key = parseKey(originalKey);
  if (!key) {
    return { current: semitones === 0 ? "Tom: original" : `Tom: ${signed(semitones)}`, original: null };
  }
  if (semitones === 0) return { current: `Tom: ${keyName(key)} (original)`, original: null };
  return { current: `Tom: ${keyName(key, semitones)} (${signed(semitones)})`, original: `original: ${keyName(key)}` };
}
