// Moving to another screen without reloading the page: what was started in this page (the TV's audio, unlocked by a
// tap) keeps working. main.tsx listens and renders the screen for the new address.
import { useSyncExternalStore } from "react";

const EVENT = "karaoke:navigate";

export function navigate(path: string): void {
  history.pushState(null, "", path);
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("popstate", onChange);
  };
}

/** The current path, kept current through navigate() and the browser's back and forward. */
export function usePath(): string {
  return useSyncExternalStore(subscribe, () => location.pathname);
}
