import { expect, test } from "@playwright/test";
import type { Song } from "../src/api";
import { artistKey, byArtist, landing, letterOf } from "../src/lib/library";

const song = (artist: string | null, title: string, channel: string | null = null) =>
  ({ song_id: `${artist}|${title}`, artist, title, track: null, channel }) as unknown as Song;

test("artists sort without accents and leading articles; digits and symbols go to # at the end", () => {
  expect(artistKey("The Beatles")).toBe("beatles");
  expect(artistKey("Os Paralamas do Sucesso")).toBe("paralamas do sucesso");
  expect(artistKey("Ávila")).toBe("avila");
  expect(artistKey("Theatre of Tragedy")).toBe("theatre of tragedy"); // only a whole word is an article
  expect(letterOf("The Beatles")).toBe("B");
  expect(letterOf("Legião Urbana")).toBe("L");
  expect(letterOf("4 Non Blondes")).toBe("#");
  expect(letterOf("Élis Regina")).toBe("E");

  const groups = byArtist([
    song("4 Non Blondes", "What's Up"),
    song("Legião Urbana", "Tempo Perdido"),
    song("The Beatles", "Yesterday"),
    song("legiao urbana", "Índios"),
    song("Os Paralamas do Sucesso", "Lanterna dos Afogados"),
    song("The Beatles", "Blackbird"),
    song(null, "Um vídeo", "Canal"),
  ]);
  expect(groups.map((g) => [g.letter, g.name, g.songs.map((s) => s.title)])).toEqual([
    ["B", "The Beatles", ["Blackbird", "Yesterday"]],
    ["C", "Canal", ["Um vídeo"]],
    ["L", "Legião Urbana", ["Índios", "Tempo Perdido"]], // one artist for both spellings, the first one shown
    ["P", "Os Paralamas do Sucesso", ["Lanterna dos Afogados"]],
    ["#", "4 Non Blondes", ["What's Up"]],
  ]);
});

test("a letter with no artist jumps to the next one there is, or to the last", () => {
  const present = ["B", "L", "P", "#"];
  expect(landing("B", present)).toBe("B");
  expect(landing("C", present)).toBe("L");
  expect(landing("Z", present)).toBe("#");
  expect(landing("A", ["B"])).toBe("B");
  expect(landing("Z", ["B"])).toBe("B");
  expect(landing("A", [])).toBeNull();
});
