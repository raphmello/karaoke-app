// Opens the side menu at a song (docs/ARCHITECTURE.md, "Pronúncia", the notices): in Sala → Fila, scrolled to it and
// marked; when it is in no queue, in Painel → Jobs (a failure) or Painel → Acervo (a question).
import { createContext } from "react";

export type SongPlace = "fila" | "jobs" | "acervo";

/** null where the screen has no host's menu. */
export const ShowSong = createContext<((videoId: string, where: SongPlace) => void) | null>(null);
