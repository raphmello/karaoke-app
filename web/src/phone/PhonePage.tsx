// /m/<code>: the guest's phone (docs/ARCHITECTURE.md, "Telas do celular"): only the Sala, with the same Fila and
// Adicionar as the TV's menu. In Adicionar, one search for the library and YouTube, and the song goes in with the
// key it starts in; in the Fila, the guest changes the key of their own songs, removes them and answers the
// transcription question. The room's owner also runs its whole queue and, in "Cantando agora", the player, and may
// delete the room. "Abrir como TV" makes this phone the room's TV; "Ver salas" goes back to the list.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, onSessionLost } from "../api";
import { useRoom } from "../room/useRoom";
import { SalaPanel, type SalaTab } from "../tv/menu/SalaPanel";
import { OpenTvButton } from "../tv/OpenTv";
import { loadNickname } from "./identity";
import { MobileFrame, smallAction } from "./MobileShell";

export function PhonePage({ code }: { code: string }) {
  const room = useRoom(code);
  const info = useQuery({ queryKey: ["room", code], queryFn: () => api.room(code) });
  const [tab, setTab] = useState<SalaTab>("adicionar"); // a guest comes to add a song

  // Without a cookie of this room, the phone joins first: on a closed socket or any request the API refuses.
  useEffect(() => {
    if (room.closedWith === 4401 || room.closedWith === 4403) location.replace(`/j/${code}`);
  }, [room.closedWith, code]);
  useEffect(() => onSessionLost(() => location.replace(`/j/${code}`)), [code]);

  const waiting = room.entries?.filter((e) => e.mine && e.status === "awaiting_decision").length ?? 0;
  const manage = info.data?.manage ?? false;

  if (room.closedWith === 4404) {
    return (
      <MobileFrame>
        <div className="flex flex-col items-center gap-4 px-4 py-12 text-center">
          <p className="text-(--menu-text-3)">Esta sala foi encerrada.</p>
          <a className={smallAction} href="/">
            Ver salas
          </a>
        </div>
      </MobileFrame>
    );
  }
  return (
    <MobileFrame>
      <SalaPanel
        room={info.data ?? null}
        live={room}
        tab={tab}
        onTab={setTab}
        manage={manage}
        controls={manage}
        aside={
          <span className="truncate text-[12px] font-normal text-(--menu-text-3)">
            {loadNickname() || "Convidado"}
            {info.data?.mine ? " · dono" : ""}
          </span>
        }
        actions={
          info.data && (
            <>
              <OpenTvButton room={info.data} className={smallAction} />
              <a className={smallAction} href="/">
                Ver salas
              </a>
            </>
          )
        }
        onDeleted={() => location.assign("/")}
      />
      {waiting > 0 && tab !== "fila" && (
        <button
          className="mx-[14px] mb-3 rounded-[10px] bg-(--menu-accent-soft) px-3 py-2 text-left text-[12px] text-(--menu-accent)"
          onClick={() => setTab("fila")}
        >
          Uma música sua precisa de resposta sobre a letra. Toque para ver.
        </button>
      )}
    </MobileFrame>
  );
}
