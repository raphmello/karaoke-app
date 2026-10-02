// The TV on a phone: a narrow screen, or a phone on its side (wide but short). Larger screens keep the TV layout.
import { useEffect, useState } from "react";

const QUERY = "(max-width: 767px), (max-height: 500px)";

export function useCompact(): boolean {
  const [compact, setCompact] = useState(() => window.matchMedia(QUERY).matches);
  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const update = () => setCompact(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return compact;
}
