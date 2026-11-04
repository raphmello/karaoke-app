import { expect, test } from "@playwright/test";
import { deservesScore, needle, phrase, pickScore } from "../src/lib/score";

test("the score is a whole number from 70 to 100, each one possible", () => {
  expect(pickScore(() => 0)).toBe(70);
  expect(pickScore(() => 0.999999)).toBe(100);
  const seen = new Set(Array.from({ length: 31 }, (_, i) => pickScore(() => i / 31)));
  expect(seen.size).toBe(31);
});

test("a song skipped before half of it gets no score", () => {
  expect(deservesScore(59, 120)).toBe(false);
  expect(deservesScore(60, 120)).toBe(true);
  expect(deservesScore(10, 0)).toBe(false); // the length is not known
});

test("each range has its phrases", () => {
  expect(phrase(97, () => 0)).toBe("Lenda! Pode lançar disco.");
  expect(phrase(90, () => 0)).toBe("Arrasou!");
  expect(phrase(85, () => 0)).toBe("Mandou bem!");
  expect(phrase(70, () => 0)).toBe("Valeu a coragem!");
});

test("the needle climbs past the score, slips back and locks on it", () => {
  expect(needle(0, 84, 90)).toBe(0);
  expect(needle(0.7, 84, 90)).toBeCloseTo(90);
  expect(needle(0.8, 84, 90)).toBeLessThan(90);
  expect(needle(0.8, 84, 90)).toBeGreaterThan(84);
  expect(needle(1, 84, 90)).toBe(84);
});
