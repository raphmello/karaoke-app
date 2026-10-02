// The nickname is remembered in the browser only to prefill forms; who the guest is comes from the cookie.
const KEY = "karaoke.nickname";

export function loadNickname(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveNickname(nickname: string): void {
  try {
    localStorage.setItem(KEY, nickname);
  } catch {
    // private window: nothing to prefill next time
  }
}
