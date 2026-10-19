// The entry screens (the QR's choice, the guest's nickname and the PIN) with the desktop menu's look (docs/
// ARCHITECTURE.md, "Telas do celular"): a card in the middle of the screen, in the menu's tokens.
import type { FormEvent, ReactNode } from "react";

export const entryInput =
  "w-full min-w-0 rounded-[10px] border border-(--menu-input-line) bg-(--menu-input) px-3.5 py-3 text-[16px] text-(--menu-text) outline-none placeholder:text-(--menu-text-off) focus:border-(--menu-accent)";
export const entryPrimary =
  "rounded-[10px] bg-(--menu-accent) px-4 py-3 text-[15px] font-medium text-(--menu-on-accent) hover:brightness-105 disabled:opacity-60";
export const entryLink = "self-center text-[13px] text-(--menu-text-3) underline";

export function EntryCard({
  title,
  prompt,
  onSubmit,
  children,
}: {
  title: string;
  prompt: ReactNode;
  onSubmit?: (event: FormEvent) => void;
  children: ReactNode;
}) {
  const body = (
    <>
      <h1 className="text-[20px] font-medium">{title}</h1>
      <p className="-mt-1.5 text-[13px] text-(--menu-text-3)">{prompt}</p>
      {children}
    </>
  );
  const card = "flex w-full max-w-sm flex-col gap-3.5 rounded-2xl bg-(--menu-field) p-6";
  return (
    <main className="flex min-h-dvh items-center justify-center bg-(--menu-panel) px-4 py-8 text-(--menu-text)">
      {onSubmit ? (
        <form onSubmit={onSubmit} className={card}>
          {body}
        </form>
      ) : (
        <div className={card}>{body}</div>
      )}
    </main>
  );
}
