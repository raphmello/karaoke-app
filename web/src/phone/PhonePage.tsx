// /m/<code>: the guest's phone (docs/ARCHITECTURE.md, "Telas do celular"): only the Sala, with the same Fila and
// Adicionar as the TV's menu. In Adicionar, one search for the library and YouTube, and the song goes in with the
// key it starts in; in the Fila, the guest changes the key of their own songs, removes them and answers the questions
// about the lyrics (the transcription and the automatic pronunciation). A song of theirs that could not be prepared,
// or that waits for an answer, has a notice that opens the queue at it. The room's owner also runs its whole queue
// and, in "Cantando agora", the player, and may delete the room. "Abrir como TV" makes this phone the room's TV;
// "Ver salas" goes back to the list.
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, onSessionLost, type QueueEntry } from "../api";
import { songTitle } from "../lib/queue";
import { useRoom } from "../room/useRoom";
import { AnswerNotices } from "../tv/AnswerNotices";
import { type Failure, FailedSongs } from "../tv/FailedSongs";
import { SalaPanel, type SalaTab } from "../tv/menu/SalaPanel";
import { OpenTvButton } from "../tv/OpenTv";
import { loadNickname } from "./identity";
import { MobileFrame, smallAction } from "./MobileShell";

export function PhonePage({ code }: { code: string }) {
  const [failures, setFailures] = useState<Failure[]>([]);
  const queued = useRef<QueueEntry[] | null>(null);
  const dismissFailure = useCallback((key: number) => setFailures((all) => all.filter((f) => f.key !== key)), []);
  const room = useRoom(code, {
    onSongFailed: (videoId) => {
      const entry = queued.current?.find((e) => e.video_id === videoId && e.mine);
      if (!entry) return; // someone else's song
      const failure = { key: Date.now(), videoId, title: songTitle(entry.song), inQueue: true };
      setFailures((all) => [...all.filter((f) => f.videoId !== videoId), failure]);
    },
  });
  queued.current = room.entries;
  const info = useQuery({ queryKey: ["room", code], queryFn: () => api.room(code) });
  const [tab, setTabNow] = useState<SalaTab>("adicionar"); // a guest comes to add a song
  const [focus, setFocus] = useState<string | null>(null);
  const setTab = (next: SalaTab) => {
    setTabNow(next);
    setFocus(null);
  };
  const show = (videoId: string) => {
    setTabNow("fila");
    setFocus(videoId);
  };

  // Without a cookie of this room, the phone joins first: on a closed socket or any request the API refuses.
  useEffect(() => {
    if (room.closedWith === 4401 || room.closedWith === 4403) location.replace(`/j/${code}`);
  }, [room.closedWith, code]);
  useEffect(() => onSessionLost(() => location.replace(`/j/${code}`)), [code]);

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
        focus={focus}
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
      <FailedSongs
        failures={failures}
        onDismiss={dismissFailure}
        onShow={(failure) => show(failure.videoId)}
        admin={false}
        hint="Adicione a música de novo para tentar outra vez."
      >
        <AnswerNotices entries={room.entries} admin={manage} onShow={show} />
      </FailedSongs>
    </MobileFrame>
  );
}
