// The card in the TV's top left corner, over the video (docs/ARCHITECTURE.md, "Barra de controles"): "Tocando agora" and, when
// someone is next, "A seguir", taking turns. Each stays 3 s, then fades out in 0,5 s and the other fades in, in 0,5 s.
// In the corner, the card never covers the lyrics. The TV on a phone keeps its own layout.
import { type ReactNode, useEffect, useState } from "react";

export const CARD_SHOWN_MS = 3000;
export const CARD_FADE_MS = 500;

/** "A SEGUIR" over who sings, and the song: the same look for the song playing and the next one. */
export function CornerCard({ label, name, detail }: { label: string; name: string; detail: ReactNode }) {
  return (
    <div className="max-w-sm rounded-xl bg-black/60 px-4 py-3 backdrop-blur-sm">
      <p className="text-xs font-semibold tracking-widest text-amber-300 uppercase">{label}</p>
      <p className="truncate text-2xl font-bold">{name}</p>
      <p className="truncate text-zinc-300">{detail}</p>
    </div>
  );
}

/** The cards taking turns, with a fade between them; a single card just stays. */
export function Alternating({ cards }: { cards: ReactNode[] }) {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);
  const count = cards.length;
  useEffect(() => {
    if (count < 2) return;
    const timer = window.setTimeout(
      () => {
        if (visible) setVisible(false);
        else {
          setIndex((index + 1) % count);
          setVisible(true);
        }
      },
      visible ? CARD_SHOWN_MS + CARD_FADE_MS : CARD_FADE_MS, // the fade in counts in the time shown
    );
    return () => window.clearTimeout(timer);
  }, [visible, index, count]);
  const shown = count < 2 ? 0 : index % count;
  return (
    <div
      className="transition-opacity ease-in-out"
      style={{ opacity: count < 2 || visible ? 1 : 0, transitionDuration: `${CARD_FADE_MS}ms` }}
    >
      {cards[shown]}
    </div>
  );
}
