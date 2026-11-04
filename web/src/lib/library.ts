// The library as a list by artist (docs/specs/02-scrollbar-lista-musicas, section 3): artists in alphabetical order,
// without accents and leading articles ("The Beatles" under B), those starting with a digit or a symbol in "#" at the
// end, and each artist's songs by title. The name shown never changes.
import type { Song } from "../api";
import { songTitle } from "./queue";

/** Leading words the order skips ("Os Paralamas do Sucesso" under P); easy to change. */
export const ARTICLES = ["the", "os", "as", "a", "o"];
export const LETTERS = [..."ABCDEFGHIJKLMNOPQRSTUVWXYZ", "#"];
export const OTHER = "#";

/** Lower case, no accents: what the order and the grouping compare. */
export function plain(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
}

/** The artist's sort key: plain, without a leading article. */
export function artistKey(name: string): string {
  const text = plain(name);
  for (const article of ARTICLES) {
    if (text.startsWith(`${article} `) && text.length > article.length + 1) return text.slice(article.length + 1).trim();
  }
  return text;
}

/** The group's letter: A to Z, or "#" for a digit or a symbol. */
export function letterOf(name: string): string {
  const first = artistKey(name).charAt(0).toUpperCase();
  return first >= "A" && first <= "Z" ? first : OTHER;
}

export function artistOf(song: Song): string {
  return song.artist ?? song.channel ?? "Sem artista";
}

export type ArtistGroup = { key: string; name: string; letter: string; songs: Song[] };

// "Música 9" before "Música 10"
const compare = (a: string, b: string) => a.localeCompare(b, "pt-BR", { numeric: true });

/** The library by artist: "#" last, artists by their key, songs by title. Names that differ only in case or
 *  accents are one artist, shown as first found. */
export function byArtist(songs: Song[]): ArtistGroup[] {
  const groups = new Map<string, ArtistGroup>();
  for (const song of songs) {
    const name = artistOf(song);
    const id = plain(name);
    const group = groups.get(id) ?? { key: artistKey(name), name, letter: letterOf(name), songs: [] };
    group.songs.push(song);
    groups.set(id, group);
  }
  const ordered = [...groups.values()].sort(
    (a, b) => Number(a.letter === OTHER) - Number(b.letter === OTHER) || compare(a.key, b.key),
  );
  for (const group of ordered) group.songs.sort((a, b) => compare(plain(songTitle(a)), plain(songTitle(b))));
  return ordered;
}

/** The songs in the library's order, for the flat list of a search. */
export function inOrder(songs: Song[]): Song[] {
  return byArtist(songs).flatMap((group) => group.songs);
}

/** Where a letter pressed on the index goes: itself, else the next letter there is, else the last one. */
export function landing(letter: string, present: string[]): string | null {
  if (!present.length) return null;
  const at = LETTERS.indexOf(letter);
  return present.find((l) => LETTERS.indexOf(l) >= at) ?? present[present.length - 1];
}
