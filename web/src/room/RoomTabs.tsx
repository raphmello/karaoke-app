// The "Sala" tab's two sub-tabs, the same on the TV's menu, the host's screen and the guest's phone: "Fila" and
// "Adicionar Música". Each screen brings its own queue and its own way to add.
import type { ReactNode } from "react";

export type RoomTab = "queue" | "add";

/** The two buttons alone, for a screen that keeps them apart from what they show (the phone's sticky header). */
export function RoomTabsNav({
  value,
  onChange,
  count,
}: {
  value: RoomTab;
  onChange: (tab: RoomTab) => void;
  count?: number; // songs in the queue, beside "Fila"
}) {
  return (
    <nav className="grid grid-cols-2 gap-2" aria-label="Sala">
      {(
        [
          ["queue", count === undefined ? "Fila" : `Fila (${count})`],
          ["add", "Adicionar Música"],
        ] as const
      ).map(([id, label]) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          aria-pressed={value === id}
          className={`rounded-lg py-2 text-sm font-semibold ${
            value === id ? "bg-zinc-100 text-zinc-950" : "bg-zinc-900 text-zinc-300 ring-1 ring-zinc-800 hover:bg-zinc-800"
          }`}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}

export function RoomTabs({
  value,
  onChange,
  count,
  queue,
  add,
}: {
  value: RoomTab;
  onChange: (tab: RoomTab) => void;
  count?: number;
  queue: ReactNode;
  add: ReactNode;
}) {
  return (
    <>
      <RoomTabsNav value={value} onChange={onChange} count={count} />
      {value === "queue" ? queue : add}
    </>
  );
}
