// The lyrics on the TV, as a teleprompter: every line the same size, the one being sung at a fixed spot and lit
// word by word, the one just sung above it and the next two below, dimmed. When the line changes, the whole list
// rolls up smoothly instead of jumping.
import { Fragment, memo, useLayoutEffect, useRef, useState } from "react";
import { focusIndex, type Line, lyricsAt, wordFill } from "../lib/lyrics";

const SUNG = "#facc15";
const UNSUNG = "rgba(244, 244, 245, 0.95)";
const BEFORE = 1; // lines shown above the focus
const AFTER = 2; // and below it
const FOCUS_AT = 0.38; // where the focus line sits, as a share of the height
const ROLL_MS = 450;

/** The line being sung: each word fills left to right as it is sung. */
function SungLine({ line, t }: { line: Line; t: number }) {
  return (
    <>
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
    </>
  );
}

const PlainLine = memo(function PlainLine({ line }: { line: Line }) {
  return <>{line.words.map((w) => w.w).join(" ")}</>;
});

export function Lyrics({ lines, t, title }: { lines: Line[] | null; t: number; title: string }) {
  if (!lines || lines.length === 0) {
    return (
      <div className="text-center">
        <p className="text-5xl font-bold md:text-6xl">{title}</p>
        <p className="mt-6 text-3xl text-zinc-400">Instrumental</p>
      </div>
    );
  }
  return <Teleprompter lines={lines} t={t} />;
}

function Teleprompter({ lines, t }: { lines: Line[]; t: number }) {
  const view = lyricsAt(lines, t);
  const focus = focusIndex(lines, view);
  const box = useRef<HTMLDivElement>(null);
  const rows = useRef<(HTMLParagraphElement | null)[]>([]);
  const [shift, setShift] = useState(0);

  // Roll the list so the focus line sits at FOCUS_AT of the height; lines wrap, so measure instead of assuming.
  useLayoutEffect(() => {
    const place = () => {
      const row = rows.current[focus];
      if (row && box.current) setShift(box.current.clientHeight * FOCUS_AT - row.offsetTop);
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [focus, lines]);

  return (
    <div ref={box} className="relative h-full w-full overflow-hidden">
      <p
        className="absolute inset-x-0 text-center text-4xl tracking-[0.5em] text-amber-300"
        style={{ top: `calc(${FOCUS_AT * 100}% - 4rem)` }}
        aria-label="contagem regressiva"
      >
        {view.countdown ? "●".repeat(view.countdown) : ""}
      </p>
      <div
        className="absolute inset-x-0 top-0 flex flex-col items-center gap-6 px-6"
        style={{ transform: `translateY(${shift}px)`, transition: `transform ${ROLL_MS}ms ease-out` }}
      >
        {lines.map((line, i) => {
          const sung = i === view.index && view.current !== null;
          const visible = i >= focus - BEFORE && i <= focus + AFTER;
          return (
            <p
              key={i}
              ref={(el) => {
                rows.current[i] = el;
              }}
              className="max-w-6xl text-center text-5xl leading-tight font-bold md:text-6xl"
              style={{
                opacity: !visible ? 0 : sung ? 1 : i < focus ? 0.3 : 0.55,
                transition: `opacity ${ROLL_MS}ms ease-out`,
              }}
              aria-hidden={!visible}
            >
              {sung ? <SungLine line={line} t={t} /> : <PlainLine line={line} />}
            </p>
          );
        })}
      </div>
    </div>
  );
}
