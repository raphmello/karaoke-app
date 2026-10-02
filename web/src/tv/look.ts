// How the TV looks during a song: the video's thumbnail behind the lyrics, and an outline around the lyrics so they
// read over any image. Both are on when a new room opens; changes are kept per room, in the TV's browser.
import { useState } from "react";

export type Look = { background: boolean; outline: boolean };

const DEFAULT: Look = { background: true, outline: true };
const key = (roomCode: string) => `karaoke.tv.look.${roomCode}`;

function load(roomCode: string): Look {
  try {
    return { ...DEFAULT, ...JSON.parse(localStorage.getItem(key(roomCode)) ?? "{}") };
  } catch {
    return DEFAULT;
  }
}

export function useLook(roomCode: string): [Look, (change: Partial<Look>) => void] {
  const [look, setLook] = useState(() => load(roomCode));
  const change = (patch: Partial<Look>) =>
    setLook((current) => {
      const next = { ...current, ...patch };
      try {
        localStorage.setItem(key(roomCode), JSON.stringify(next));
      } catch {
        // a private window: the choice lasts until the page closes
      }
      return next;
    });
  return [look, change];
}
