// How long a room has left (docs/ARCHITECTURE.md, "Salas": it expires 24 h after it was made). The screens show it,
// and in the last half hour it turns amber; at the end the server closes the room and the screens lead to the list.
import { useEffect, useState } from "react";

const SOON_MIN = 30;

/** "expira em 5 h", "expira em 20 min" */
export function expiresIn(when: string, now = Date.now()): string {
  const minutes = minutesLeft(when, now);
  return minutes >= 60 ? `expira em ${Math.floor(minutes / 60)} h` : `expira em ${minutes} min`;
}

function minutesLeft(when: string, now: number): number {
  return Math.max(0, Math.round((Date.parse(when) - now) / 60000));
}

/** The time left, kept current while the screen stays open. */
export function ExpiresIn({ when }: { when: string }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, []);
  const soon = minutesLeft(when, now) < SOON_MIN;
  return <span className={soon ? "font-semibold text-amber-300" : undefined}>{expiresIn(when, now)}</span>;
}
