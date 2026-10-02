import { Fragment } from "react";
import { type Line, lyricsAt, wordFill } from "../lib/lyrics";

const SUNG = "#facc15";
const UNSUNG = "rgba(244, 244, 245, 0.92)";

/** The line being sung: each word fills left to right as it is sung. */
function CurrentLine({ line, t }: { line: Line; t: number }) {
  return (
    <p className="text-5xl leading-tight font-bold md:text-7xl">
      {line.words.map((word, i) => {
        const fill = wordFill(line, word, t) * 100;
        return (
          <Fragment key={i}>
            {i > 0 ? " " : null}
            <span
              style={{
                backgroundImage: `linear-gradient(to right, ${SUNG} ${fill}%, ${UNSUNG} ${fill}%)`,
                backgroundClip: "text",
                WebkitBackgroundClip: "text",
                color: "transparent",
              }}
            >
              {word.w}
            </span>
          </Fragment>
        );
      })}
    </p>
  );
}

export function Lyrics({ lines, t, title }: { lines: Line[] | null; t: number; title: string }) {
  if (!lines || lines.length === 0) {
    return (
      <div className="text-center">
        <p className="text-5xl font-bold md:text-6xl">{title}</p>
        <p className="mt-6 text-3xl text-zinc-400">Instrumental</p>
      </div>
    );
  }
  const view = lyricsAt(lines, t);
  return (
    <div className="flex w-full flex-col items-center gap-8 text-center">
      <p className="h-12 text-4xl tracking-[0.5em] text-amber-300" aria-label="contagem regressiva">
        {view.countdown ? "●".repeat(view.countdown) : ""}
      </p>
      <div className="min-h-[2.5em] text-5xl md:text-7xl">{view.current && <CurrentLine line={view.current} t={t} />}</div>
      <p className="min-h-[2em] text-2xl text-zinc-400 md:text-4xl">{view.next?.words.map((w) => w.w).join(" ")}</p>
    </div>
  );
}
