import { expect, test } from "@playwright/test";
import { stagesOf } from "../src/tv/menu/Reprocess";

test("Tudo sends every stage; a choice sends its own, and the API adds what depends on it", () => {
  expect(stagesOf(true, new Set())).toEqual([
    "metadata", "lyrics", "download", "separation", "language", "alignment", "phonetic", "key", "encode",
  ]);
  expect(stagesOf(false, new Set(["letra", "fonetica"]))).toEqual(["lyrics", "phonetic"]);
  expect(stagesOf(false, new Set(["audio"]))).toEqual(["download"]);
  expect(stagesOf(false, new Set())).toEqual([]);
});
