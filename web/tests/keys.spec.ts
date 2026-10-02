import { expect, test } from "@playwright/test";
import { clampSemitones, keyLabel, keyName, parseKey } from "../src/lib/keys";

test("essentia's keys become Portuguese names", () => {
  expect(keyName(parseKey("A minor")!)).toBe("Lá menor");
  expect(keyName(parseKey("Bb major")!)).toBe("Si♭ maior");
  expect(keyName(parseKey("C# minor")!)).toBe("Dó♯ menor");
  expect(parseKey("H major")).toBeNull();
  expect(parseKey(null)).toBeNull();
});

test("half tones move the key around the circle", () => {
  expect(keyName(parseKey("A minor")!, -2)).toBe("Sol menor");
  expect(keyName(parseKey("C major")!, -1)).toBe("Si maior");
  expect(keyName(parseKey("B major")!, 1)).toBe("Dó maior");
});

test("the label shows the current key in name and semitones, and the original", () => {
  expect(keyLabel("A minor", -2)).toEqual({ current: "Tom: Sol menor (−2)", original: "original: Lá menor" });
  expect(keyLabel("A minor", 0)).toEqual({ current: "Tom: Lá menor (original)", original: null });
  expect(keyLabel(null, 3)).toEqual({ current: "Tom: +3", original: null });
});

test("the key stays within −6 and +6", () => {
  expect(clampSemitones(7)).toBe(6);
  expect(clampSemitones(-9)).toBe(-6);
});
