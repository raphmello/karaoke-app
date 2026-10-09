// The TV's menu (docs/ARCHITECTURE.md, "Menu lateral"): collapsed behind a "☰ Menu" button on the right edge; open,
// a column beside the TV, never over it, so the lyrics, the QR and the controls stay in view during a song. The TV
// shrinks to the space left and picks its layout by its own width (CompactContext). On a phone the column does not
// fit, so the menu covers the screen and the TV comes back when it closes.
//
// Sala (with Fila and Adicionar Música) is the TV's; Gerenciar Acervo and Painel are the host's and ask for the
// host's PIN right there. "Sair do admin" drops the host's cookie and locks them again.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { type ActiveRoom, api } from "../api";
import { OpenRoomButton } from "../host/HostPage";
import { LibraryAdmin } from "../host/LibraryAdmin";
import { Panel } from "../host/Panel";
import { AddSong } from "../room/AddSongs";
import { QueueList } from "../room/QueueList";
import { type RoomTab, RoomTabs } from "../room/RoomTabs";
import { useRoom } from "../room/useRoom";
import { CompactContext, NARROW_PX, SHORT_PX, useCompact } from "./compact";

type Section = "room" | "library" | "panel";
const SECTIONS: [Section, string, boolean][] = [
  // id, label, host only
  ["room", "Sala", false],
  ["library", "Gerenciar Acervo", true],
  ["panel", "Painel", true],
];

/** The TV (`children`) and, beside it, its menu. */
export function TvMenuLayout({ room, children }: { room: ActiveRoom | null; children: ReactNode }) {
  const phone = useCompact(); // the window's size: outside the TV's box
  const [open, setOpen] = useState(false);
  const [section, setSection] = useState<Section>("room");
  const queryClient = useQueryClient();
  const host = useQuery({ queryKey: ["tv-is-host"], queryFn: api.isHost, retry: false });
  const isHost = host.data === true;

  // The TV's box: narrow or short, the TV takes its phone layout even in a wide window
  const box = useRef<HTMLDivElement>(null);
  const [boxCompact, setBoxCompact] = useState<boolean | null>(null);
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setBoxCompact(width < NARROW_PX || height < SHORT_PX);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const leaveAdmin = async () => {
    setSection("room"); // Gerenciar Acervo and Painel go before the cookie does, so nothing of theirs asks again
    await api.hostLogout().catch(() => undefined);
    // The TV opened with the host's PIN has no TV cookie: the active room then asks for the PIN again
    await queryClient.invalidateQueries({ queryKey: ["tv-is-host"] });
    await queryClient.invalidateQueries({ queryKey: ["active-room"] });
  };

  const tvHidden = open && phone;
  return (
    <div className="flex h-full">
      <div ref={box} className={`relative h-full min-w-0 flex-1 ${tvHidden ? "hidden" : ""}`}>
        <CompactContext.Provider value={boxCompact}>{children}</CompactContext.Provider>
        {!open && (
          <button
            onClick={() => setOpen(true)}
            aria-label="Abrir o menu"
            // On a phone the middle of the edge is where the lyrics run: the button goes up, under the header
            className={`absolute right-0 z-40 flex flex-col items-center gap-1 rounded-l-xl border border-r-0 border-amber-400/70 bg-zinc-900/90 font-semibold text-amber-300 shadow-lg hover:bg-zinc-800 ${
              phone ? "top-28 px-2 py-2" : "top-1/2 -translate-y-1/2 px-3 py-4"
            }`}
          >
            <span className={`${phone ? "text-xl" : "text-2xl"} leading-none`}>☰</span>
            <span className={phone ? "text-xs" : "text-sm"}>Menu</span>
          </button>
        )}
      </div>
      {open && (
        <aside
          aria-label="Menu"
          className={`flex h-full bg-zinc-950 text-left ${
            phone ? "w-full flex-col" : "w-[min(560px,45vw)] min-w-[360px] shrink-0 border-l border-zinc-800"
          }`}
          // Typing in the menu must not reach the TV's keys (space pauses, arrows change the key)
          onKeyDown={(event) => event.key !== "Escape" && event.stopPropagation()}
        >
          <nav
            className={
              phone
                ? "flex shrink-0 gap-2 overflow-x-auto border-b border-zinc-800 p-3"
                : "flex w-40 shrink-0 flex-col gap-2 border-r border-zinc-800 p-3"
            }
          >
            <button
              onClick={() => setOpen(false)}
              aria-label="Fechar o menu"
              className={`shrink-0 rounded-lg px-3 py-2 text-left font-semibold text-zinc-300 hover:bg-zinc-800 ${phone ? "" : "mb-2"}`}
            >
              ✕ Fechar
            </button>
            {SECTIONS.map(([id, label, hostOnly]) => (
              <button
                key={id}
                onClick={() => setSection(id)}
                className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm font-semibold ${
                  section === id ? "bg-amber-400 text-zinc-950" : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
                }`}
              >
                {label}
                {hostOnly && !isHost ? " 🔒" : ""}
              </button>
            ))}
            {isHost && (
              <button
                onClick={() => void leaveAdmin()}
                className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm font-semibold text-zinc-400 ring-1 ring-zinc-700 hover:bg-zinc-800 ${
                  phone ? "" : "mt-auto"
                }`}
              >
                Sair do admin
              </button>
            )}
          </nav>
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
            {section === "room" &&
              (room ? (
                // The room's socket says who it is when it opens: entering or leaving the admin opens a new one, or
                // the queue would keep marking "mine" for whoever this was before
                <RoomSection key={`${room.code}-${isHost}`} room={room} isHost={isHost} />
              ) : (
                <NoRoom isHost={isHost} />
              ))}
            {section === "library" && (isHost ? <LibraryAdmin /> : <AdminUnlock what="o acervo" />)}
            {section === "panel" && (isHost ? <Panel /> : <AdminUnlock what="o painel" />)}
          </div>
        </aside>
      )}
    </div>
  );
}

/** The host's PIN, asked inside the menu: it unlocks Acervo and Painel (and the queue's host tools). */
function AdminUnlock({ what }: { what: string }) {
  const queryClient = useQueryClient();
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.hostLogin(pin);
      await queryClient.invalidateQueries({ queryKey: ["tv-is-host"] });
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-xl bg-zinc-900 p-4">
      <p className="font-semibold">Só o admin abre {what}.</p>
      <p className="text-sm text-zinc-400">Digite o PIN de administrador.</p>
      <input
        type="password"
        inputMode="numeric"
        autoFocus
        className="rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-lg outline-none focus:border-amber-400"
        value={pin}
        onChange={(event) => setPin(event.target.value)}
        aria-label="PIN de administrador"
      />
      {error && <p className="text-sm text-red-400">{error}</p>}
      <button
        className="rounded-lg bg-amber-400 px-4 py-2 font-bold text-zinc-950 disabled:opacity-50"
        disabled={busy || !pin}
      >
        Entrar como admin
      </button>
    </form>
  );
}

function NoRoom({ isHost }: { isHost: boolean }) {
  if (!isHost) {
    return (
      <>
        <p className="rounded-xl bg-zinc-900 p-4 text-zinc-400">Nenhuma sala aberta. Só o admin abre a sala.</p>
        <AdminUnlock what="a sala" />
      </>
    );
  }
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-zinc-900 p-4">
      <p className="text-zinc-400">Nenhuma sala aberta.</p>
      <OpenRoomButton replacing={false} />
    </section>
  );
}

/** The room, then Fila and Adicionar Música. The TV sees the queue and adds songs; the host also reorders, removes,
 *  tries again and opens a new room. */
function RoomSection({ room, isHost }: { room: ActiveRoom; isHost: boolean }) {
  const live = useRoom(room.code);
  const [tab, setTab] = useState<RoomTab>("queue");
  return (
    <>
      <section className="flex flex-wrap items-start justify-between gap-3 rounded-xl bg-zinc-900 p-4">
        <div>
          <p className="text-sm text-zinc-400">{room.name ?? "Sala aberta"}</p>
          <p className="text-2xl font-bold tracking-widest">{room.code}</p>
          <p className="text-sm text-zinc-400">
            Os convidados entram pelo QR da TV
            {!live.connected && " · reconectando…"}
          </p>
        </div>
        {isHost && <OpenRoomButton replacing />}
      </section>
      <RoomTabs
        value={tab}
        onChange={setTab}
        count={live.entries?.length}
        queue={
          live.entries ? (
            <QueueList code={room.code} entries={live.entries} progress={live.progress} isHost={isHost} />
          ) : (
            <p className="text-zinc-400">Carregando a fila…</p>
          )
        }
        add={<AddSong code={room.code} />}
      />
    </>
  );
}
