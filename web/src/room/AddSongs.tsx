// Adding a song to the queue, once found (tv/menu/SalaPanel.tsx's Adicionar, on the TV and on the phones): who sings
// and the key it starts in. The API decides who the entry belongs to from the cookie.
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { clampSemitones, MAX_SEMITONES, MIN_SEMITONES, signed } from "../lib/keys";
import { loadNickname } from "../phone/identity";
import { input, primary } from "../tv/menu/ui";

export function AddForm({
  code,
  result,
  onAdded,
}: {
  code: string;
  result: { video_id: string; title: string | null };
  onAdded: (title: string) => void;
}) {
  const [singer, setSinger] = useState(loadNickname);
  const [semitones, setSemitones] = useState(0);
  const add = useMutation({
    mutationFn: () => api.add(code, { video_id: result.video_id, singer_name: singer.trim() || undefined, semitones }),
    onSuccess: () => onAdded(result.title ?? result.video_id),
  });
  const step =
    "flex h-7 w-[34px] items-center justify-center rounded-[14px] text-[13px] text-[#e4e4e8] hover:bg-(--menu-btn-hover) disabled:opacity-40";

  return (
    <div className="mt-2.5 flex flex-col gap-2.5 border-t border-(--menu-line) pt-2.5">
      <label className="flex flex-col gap-1 text-[12px] text-(--menu-text-2)">
        Quem canta
        <input maxLength={40} className={input} value={singer} onChange={(event) => setSinger(event.target.value)} />
      </label>
      <div className="flex items-center gap-2.5 text-[12px]">
        <span className="text-(--menu-text-2)">Começar no tom</span>
        <span className="inline-flex items-center rounded-[17px] bg-(--menu-btn) p-0.5">
          <button
            className={step}
            aria-label="Meio tom abaixo"
            disabled={semitones <= MIN_SEMITONES}
            onClick={() => setSemitones((s) => clampSemitones(s - 1))}
          >
            −½
          </button>
          <span className={`min-w-16 px-1.5 text-center text-[13px] font-medium ${semitones ? "text-(--menu-accent)" : ""}`}>
            {semitones === 0 ? "original" : signed(semitones)}
          </span>
          <button
            className={step}
            aria-label="Meio tom acima"
            disabled={semitones >= MAX_SEMITONES}
            onClick={() => setSemitones((s) => clampSemitones(s + 1))}
          >
            +½
          </button>
        </span>
      </div>
      {add.isError && <p className="text-[12px] text-(--menu-err)">{add.error.message}</p>}
      <button className={primary} disabled={add.isPending} onClick={() => add.mutate()}>
        Adicionar à fila
      </button>
    </div>
  );
}
