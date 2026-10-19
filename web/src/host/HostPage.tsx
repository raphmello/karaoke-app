// /host: the host runs every open room (docs/ARCHITECTURE.md, "Salas" and "Telas do celular"), with the TV menu's
// look and a bar of icons at the bottom. Salas: the open rooms and "Criar sala"; in the one picked, its details
// ("Abrir como TV", "Excluir sala"), the Fila and Adicionar as on the TV's menu, and the player in "Cantando agora".
// Painel: Disco, Jobs and Acervo. /host?sala=<code> opens with that room picked (the list's "Gerenciar").
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, onSessionLost, retryWhileRestarting, type RoomInfo } from "../api";
import { MobileFrame, BottomNav, NavItem, smallAction } from "../phone/MobileShell";
import { CreateRoomButton } from "../room/CreateRoom";
import { HostLogin } from "../room/HostLogin";
import { useRoom } from "../room/useRoom";
import { PainelPanel, type PainelTab } from "../tv/menu/PainelPanel";
import { SalaPanel, type SalaTab } from "../tv/menu/SalaPanel";
import { PanelHeader } from "../tv/menu/ui";
import { OpenTvButton } from "../tv/OpenTv";

export function HostPage() {
  const queryClient = useQueryClient();
  // Only the host's cookie opens this screen: a room's TV reads the rooms too, so that is not the check
  const host = useQuery({ queryKey: ["host-check"], queryFn: api.hostCheck, ...retryWhileRestarting });
  const hostStatus = host.error instanceof ApiError ? host.error.status : null;
  const [lost, setLost] = useState(false);
  useEffect(() => onSessionLost(() => setLost(true)), []);

  if (hostStatus === 401 || lost) {
    return (
      <HostLogin
        title="Host do karaokê"
        onDone={() => {
          setLost(false);
          void queryClient.invalidateQueries();
        }}
      />
    );
  }
  if (host.isPending) {
    return (
      <MobileFrame>
        <p className="p-8 text-(--menu-text-3)">Carregando…</p>
      </MobileFrame>
    );
  }
  return <HostScreens />;
}

type View = "salas" | "painel";

function HostScreens() {
  const [view, setView] = useState<View>("salas");
  const [painel, setPainel] = useState<PainelTab>("disco");
  const rooms = useQuery({ queryKey: ["rooms"], queryFn: api.rooms, ...retryWhileRestarting, refetchInterval: 15000 });
  const [picked, setPicked] = useState<string | null>(
    () => new URLSearchParams(location.search).get("sala")?.toUpperCase() ?? null,
  );
  const pick = useCallback((code: string | null) => {
    setPicked(code);
    history.replaceState(null, "", code ? `/host?sala=${code}` : "/host");
  }, []);
  const list = rooms.data ?? [];
  // A room that is gone (removed or expired) is no longer picked; with one room only, it is
  const room = list.find((r) => r.code === picked) ?? (list.length === 1 ? list[0] : null);

  return (
    <MobileFrame
      nav={
        <BottomNav>
          <NavItem icon="mic" label="Salas" active={view === "salas"} onClick={() => setView("salas")} />
          <NavItem icon="dashboard" label="Painel" active={view === "painel"} onClick={() => setView("painel")} />
        </BottomNav>
      }
    >
      {view === "painel" ? (
        <PainelPanel tab={painel} onTab={setPainel} />
      ) : room ? (
        <Room key={room.code} room={room} rooms={list} onPick={pick} />
      ) : (
        <>
          <PanelHeader title="Salas" actions={<CreateRoomButton asHost onCreated={(created) => pick(created.code)} />} />
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-[14px] pt-3 pb-4">
            <p className="text-[12px] text-(--menu-text-3)">
              {rooms.isPending
                ? "Carregando as salas…"
                : rooms.isError
                  ? "Não foi possível carregar as salas. Tentando de novo…"
                  : list.length === 0
                    ? "Nenhuma sala aberta."
                    : "Escolha uma sala para gerenciar."}
            </p>
            <RoomChips rooms={list} picked={null} onPick={pick} />
          </div>
        </>
      )}
    </MobileFrame>
  );
}

/** Every open room as a chip: the one picked in yellow. */
function RoomChips({ rooms, picked, onPick }: { rooms: RoomInfo[]; picked: string | null; onPick: (code: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {rooms.map((r) => (
        <button
          key={r.code}
          onClick={() => onPick(r.code)}
          className={`rounded-[9px] px-3 py-1.5 text-left text-[12px] font-medium ${
            r.code === picked ? "bg-(--menu-accent) text-(--menu-on-accent)" : "bg-(--menu-btn) text-(--menu-text) hover:bg-(--menu-btn-hover)"
          }`}
        >
          {r.protected && "🔒 "}
          {r.name ?? r.code}
        </button>
      ))}
    </div>
  );
}

function Room({ room, rooms, onPick }: { room: RoomInfo; rooms: RoomInfo[]; onPick: (code: string | null) => void }) {
  const live = useRoom(room.code);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<SalaTab>("fila");
  // The socket closed because the room is gone (4404) or the session is (a 401 brings back the PIN): check again
  useEffect(() => {
    if (!live.closedWith) return;
    if (live.closedWith === 4404) onPick(null);
    void queryClient.invalidateQueries({ queryKey: ["rooms"] });
    // onPick is left out: once per close, not once per render of the parent
  }, [live.closedWith, queryClient]);

  return (
    <>
      {rooms.length > 1 && (
        <div className="px-[14px] pt-3">
          <RoomChips rooms={rooms} picked={room.code} onPick={onPick} />
        </div>
      )}
      <SalaPanel
        room={room}
        live={live}
        tab={tab}
        onTab={setTab}
        manage
        controls
        aside={<CreateRoomButton asHost className={smallAction} onCreated={(created) => onPick(created.code)} />}
        actions={<OpenTvButton room={room} className={smallAction} />}
        onDeleted={() => onPick(null)}
      />
    </>
  );
}
