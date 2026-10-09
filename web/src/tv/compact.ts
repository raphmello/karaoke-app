// The TV on a phone: a narrow screen, or a phone on its side (wide but short). Larger screens keep the TV layout.
// With the menu open beside it, the TV is narrower than the window: the layout around it then says, through
// CompactContext, whether the TV's own box is narrow.
import { createContext, useContext, useEffect, useState } from "react";

const QUERY = "(max-width: 767px), (max-height: 500px)";
export const NARROW_PX = 768;
export const SHORT_PX = 500;

/** null: no box to measure, follow the window. */
export const CompactContext = createContext<boolean | null>(null);

export function useCompact(): boolean {
  const boxed = useContext(CompactContext);
  const [compact, setCompact] = useState(() => window.matchMedia(QUERY).matches);
  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const update = () => setCompact(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return boxed ?? compact;
}
