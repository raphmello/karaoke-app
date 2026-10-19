// The TV's menu (docs/ARCHITECTURE.md, "Menu lateral"): collapsed behind a "☰ Menu" button on the right edge; open,
// a bar of icons (68 px) and, beside it, the chosen item's panel, never over the TV, so the lyrics, the QR and the
// controls stay in view during a song. The TV shrinks to the space left and picks its layout by its own width
// (CompactContext). On a phone the column does not fit, so the menu covers the screen and the TV comes back when it
// closes.
//
// Sala (Fila and Adicionar) is the TV's; Painel (Disco, Jobs and Acervo) is the host's and asks for the host's PIN
// right there. "Sair do admin" drops the host's cookie and locks it again. "Ver salas" leaves this room's TV for the
// list of rooms.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { api, type RoomInfo } from "../api";
import { useRoom } from "../room/useRoom";
import { CompactContext, NARROW_PX, SHORT_PX, useCompact } from "./compact";
import { Icon, type IconName } from "./menu/icons";
import { PainelPanel, type PainelTab } from "./menu/PainelPanel";
import { SalaPanel, type SalaTab } from "./menu/SalaPanel";
import { Body, Card, input, PanelHeader, primary, WithToast } from "./menu/ui";

type View = "sala" | "painel";
/** Where the menu was, so it opens again there: the item, and the tab of Sala and of Painel. */
type MenuState = { view: View; sala: SalaTab; painel: PainelTab };

/** The TV (`children`) and, beside it, its menu. */
export function TvMenuLayout({ room, closed, children }: { room: RoomInfo; closed: boolean; children: ReactNode }) {
  const phone = useCompact(); // the window's size: outside the TV's box
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState<MenuState>({ view: "sala", sala: "fila", painel: "disco" });
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
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !event.defaultPrevented && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const leaveAdmin = async () => {
    setMenu((current) => ({ ...current, view: "sala" })); // Painel goes before the cookie does, so it asks nothing
    await api.hostLogout().catch(() => undefined);
    // A TV opened by the admin has no TV cookie: the room then asks for the admin's PIN again (or its owner's tap)
    await queryClient.invalidateQueries({ queryKey: ["tv-is-host"] });
    await queryClient.invalidateQueries({ queryKey: ["room", room.code] });
  };

  const tvHidden = open && phone;
  return (
    <WithToast>
      {(toast) => (
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
            {toast}
          </div>
          {open && (
            // The room's socket says who it is when it opens: entering or leaving the admin opens a new one, or the
            // queue would keep marking "mine" for whoever this was before
            <SideMenu
              key={`${room.code}-${isHost}`}
              room={room}
              closed={closed}
              isHost={isHost}
              phone={phone}
              state={menu}
              onState={setMenu}
              onLeaveAdmin={() => void leaveAdmin()}
              onClose={() => setOpen(false)}
            />
          )}
        </div>
      )}
    </WithToast>
  );
}

function SideMenu({
  room,
  closed,
  isHost,
  phone,
  state,
  onState,
  onLeaveAdmin,
  onClose,
}: {
  room: RoomInfo;
  closed: boolean;
  isHost: boolean;
  phone: boolean;
  state: MenuState;
  onState: (state: MenuState) => void;
  onLeaveAdmin: () => void;
  onClose: () => void;
}) {
  const live = useRoom(closed ? null : room.code);
  const waiting = live.entries?.filter((entry) => entry.status !== "playing").length ?? 0;
  const go = (view: View) => onState({ ...state, view });

  return (
    <div
      className={`flex h-full shrink-0 text-left text-[13px] leading-[1.4] text-(--menu-text) ${phone ? "w-full" : ""}`}
      // Typing in the menu must not reach the TV's keys (space pauses, arrows change the key)
      onKeyDown={(event) => event.key !== "Escape" && event.stopPropagation()}
    >
      <nav aria-label="Menu lateral" className="flex h-full w-[68px] shrink-0 flex-col items-center gap-1 bg-(--menu-rail) py-2.5">
        <RailItem icon="mic" label="Sala" badge={waiting} active={state.view === "sala"} onClick={() => go("sala")} />
        <RailItem icon="dashboard" label="Painel" active={state.view === "painel"} onClick={() => go("painel")} />
        <div className="mt-auto" />
        <RailItem icon="external" label="Ver salas" href="/" />
        {isHost && <RailItem icon="x" label="Sair do admin" onClick={onLeaveAdmin} />}
      </nav>
      <aside
        aria-label="Painel do menu"
        className={`relative flex h-full min-h-0 flex-col bg-(--menu-panel) ${phone ? "min-w-0 flex-1" : "w-[clamp(340px,30vw,400px)] shrink-0"}`}
      >
        {state.view === "sala" ? (
          <SalaPanel
            room={room}
            live={live}
            tab={state.sala}
            onTab={(sala) => onState({ ...state, sala })}
            onClose={onClose}
            manage={isHost || room.manage}
            closed={closed}
          />
        ) : isHost ? (
          <PainelPanel tab={state.painel} onTab={(painel) => onState({ ...state, painel })} onClose={onClose} />
        ) : (
          <AdminUnlock onClose={onClose} />
        )}
      </aside>
    </div>
  );
}

/** The host's PIN, asked inside the menu: it unlocks the Painel (and the queue's host tools). */
function AdminUnlock({ onClose }: { onClose: () => void }) {
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
    <>
      <PanelHeader title="Painel" onClose={onClose} />
      <Body>
        <Card>
          <form onSubmit={submit} className="flex flex-col gap-2.5">
            <div className="font-medium">Só o admin abre o painel.</div>
            <p className="text-[12px] text-(--menu-text-3)">Digite o PIN de administrador.</p>
            <input
              type="password"
              inputMode="numeric"
              autoFocus
              className={input}
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              aria-label="PIN de administrador"
            />
            {error && <p className="text-[12px] text-(--menu-err)">{error}</p>}
            <button className={primary} disabled={busy || !pin}>
              Entrar como admin
            </button>
          </form>
        </Card>
      </Body>
    </>
  );
}

function RailItem({
  icon,
  label,
  badge,
  active = false,
  onClick,
  href,
}: {
  icon: IconName;
  label: string;
  badge?: number;
  active?: boolean;
  onClick?: () => void;
  href?: string;
}) {
  const className = `relative flex w-14 flex-col items-center gap-0.5 rounded-[10px] py-2 text-center text-[11px] leading-tight ${
    active ? "bg-(--menu-accent) text-(--menu-on-accent)" : "text-(--menu-text-2) hover:bg-(--menu-btn)"
  } focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--menu-accent)`;
  const body = (
    <>
      <Icon name={icon} />
      <span>{label}</span>
      {!!badge && (
        <span
          aria-label={`${badge} na fila`}
          className={`absolute top-0.5 right-0.5 min-w-4 rounded-[9px] px-1 text-center text-[11px] font-medium ${
            active ? "bg-(--menu-on-accent) text-(--menu-accent)" : "bg-(--menu-accent) text-(--menu-on-accent)"
          }`}
        >
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </>
  );
  return href ? (
    <a href={href} title={label} className={className}>
      {body}
    </a>
  ) : (
    <button type="button" onClick={onClick} title={label} aria-current={active ? "page" : undefined} className={className}>
      {body}
    </button>
  );
}
