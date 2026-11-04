// The phonetic lyrics on the TV (docs/ARCHITECTURE.md, "Pronúncia"): a song in a script outside the
// Latin alphabet may come with a second version, the fans' romanization (or, in Korean, Chinese, Russian and Greek,
// the app's own reading; or the host's), written for a Portuguese reader and timed word by word with the original. The phonetic one shows by default; the floating bar's tray (or
// the phone layout's settings) switches to the original, and each window remembers the choice. When such a song
// starts, a notice says so for a few seconds, or says the phonetic lyrics were not found (or that the automatic one
// waits for an answer in the queue).
import { useEffect, useState } from "react";
import type { Song } from "../api";

export type LyricsChoice = "phonetic" | "original";
const KEY = "karaoke.tv.lyrics"; // which version this window shows

function load(): LyricsChoice {
  try {
    return localStorage.getItem(KEY) === "original" ? "original" : "phonetic";
  } catch {
    return "phonetic";
  }
}

export function useLyricsChoice(): [LyricsChoice, (choice: LyricsChoice) => void] {
  const [choice, setChoice] = useState(load);
  const change = (next: LyricsChoice) => {
    setChoice(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // a private window: it lasts until the page closes
    }
  };
  return [choice, change];
}

const LANGUAGES: Record<string, string> = {
  ja: "japonês", zh: "chinês", ko: "coreano", ru: "russo", uk: "ucraniano", bg: "búlgaro", sr: "sérvio",
  mk: "macedônio", be: "bielorrusso", kk: "cazaque", el: "grego", hi: "hindi", mr: "marati", ne: "nepalês",
  th: "tailandês", ka: "georgiano", hy: "armênio", mn: "mongol",
};

/** Where the phonetic version came from, for people. */
export function phoneticOrigin(source: Song["phonetic_source"]): string {
  if (source === "host") return "Pronúncia corrigida pelo admin";
  return source === "auto" ? "Pronúncia automática (pode ter erros)" : "Pronúncia da comunidade";
}

/** The song has phonetic lyrics to show (not only "needed, not found"). */
export const hasPhonetic = (song: Pick<Song, "phonetic_source">) =>
  song.phonetic_source === "lrclib" || song.phonetic_source === "auto" || song.phonetic_source === "host";

export const NOTICE_MS = 6000;

/** "Letra em japonês: …", or that the phonetic lyrics were not found, for a few seconds when the song starts. */
export function PhoneticNotice({ song, compact }: { song: Song; compact?: boolean }) {
  const [shown, setShown] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(() => setShown(false), NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, []);
  if (!song.phonetic_source) return null;
  const language = (song.language && LANGUAGES[song.language]) || "outra escrita";
  const where = compact ? "toque em Ajustes" : "abra os ajustes da barra (⌃)";
  return (
    <div
      role="status"
      className={`pointer-events-none absolute top-3 left-1/2 z-20 -translate-x-1/2 ${compact ? "w-[calc(100%-32px)]" : "w-[min(560px,calc(100%-720px))]"} rounded-xl bg-black/75 px-4 py-3 text-center backdrop-blur-sm transition-opacity duration-500 ${
        shown ? "opacity-100" : "opacity-0"
      }`}
    >
      {hasPhonetic(song) ? (
        <>
          <p className={compact ? "text-sm" : "text-lg"}>
            Letra em {language}: mostrando a pronúncia em português, sincronizada com a original. Para ver a original,{" "}
            {where}.
          </p>
          <p className={`mt-1 text-amber-300 ${compact ? "text-xs" : "text-sm"}`}>{phoneticOrigin(song.phonetic_source)}</p>
        </>
      ) : (
        <p className={compact ? "text-sm" : "text-lg"}>
          {song.phonetic_source === "pendente"
            ? "A pronúncia dos fãs não foi encontrada, e a automática espera uma resposta na fila. Mostrando a letra original."
            : "Pronúncia não encontrada no LRCLIB para esta música. Mostrando a letra original."}
        </p>
      )}
    </div>
  );
}

/** "Letra: Pronúncia | Original", two buttons side by side. */
export function LyricsSwitch({
  choice,
  onChange,
  className = "",
}: {
  choice: LyricsChoice;
  onChange: (choice: LyricsChoice) => void;
  className?: string;
}) {
  const option = (value: LyricsChoice, label: string) => (
    <button
      type="button"
      aria-pressed={choice === value}
      onClick={() => onChange(value)}
      className={`rounded-lg px-2.5 py-1 text-[12px] ${
        choice === value ? "bg-(--menu-accent) font-medium text-(--menu-on-accent)" : "text-(--menu-text-2) hover:bg-(--menu-btn-hover)"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div className={`flex items-center gap-2.5 ${className}`} role="group" aria-label="Letra">
      <span className="text-[12px] text-(--menu-text-2)">Letra</span>
      <span className="inline-flex rounded-[10px] bg-(--menu-btn) p-0.5">
        {option("phonetic", "Pronúncia")}
        {option("original", "Original")}
      </span>
    </div>
  );
}
