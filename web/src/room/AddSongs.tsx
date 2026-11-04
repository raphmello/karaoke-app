// Adding a song to the queue, once found (tv/menu/SalaPanel.tsx's Adicionar, on the TV and on the phones): who sings
// and the key it starts in. The API decides who the entry belongs to from the cookie.
import { useMutation } from "@tanstack/react-query";
import { useContext, useState } from "react";
import { api } from "../api";
import { clampSemitones, keyName, MAX_SEMITONES, MIN_SEMITONES, parseKey, signed } from "../lib/keys";
import { loadNickname } from "../phone/identity";
import { Touch } from "../tv/menu/SongList";
import { input, primary } from "../tv/menu/ui";

export function AddForm({
  code,
  result,
  onAdded,
}: {
  code: string;
  result: { video_id: string; title: string | null; original_key?: string | null };
  onAdded: (title: string) => void;
}) {
  const touch = useContext(Touch);
  const [singer, setSinger] = useState(loadNickname);
  const [semitones, setSemitones] = useState(0);
  const add = useMutation({
    mutationFn: () => api.add(code, { video_id: result.video_id, singer_name: singer.trim() || undefined, semitones }),
    onSuccess: () => onAdded(result.title ?? result.video_id),
  });

  return (
    <div className={`flex flex-col gap-2.5 ${touch ? "" : "mt-2.5 border-t border-(--menu-line) pt-2.5"}`}>
      <label className="flex flex-col gap-1 text-[12px] text-(--menu-text-2)">
        Quem canta
        <input
          maxLength={40}
          className={`${input} ${touch ? "py-2.5 text-[16px]" : ""}`}
          value={singer}
          onChange={(event) => setSinger(event.target.value)}
        />
      </label>
      <div className="flex items-center gap-2.5 text-[12px]">
        <span className="text-(--menu-text-2)">Começar no tom</span>
        <KeyPicker originalKey={result.original_key} semitones={semitones} onChange={(n) => setSemitones(clampSemitones(n))} />
      </div>
      {add.isError && <p className="text-[12px] text-(--menu-err)">{add.error.message}</p>}
      <button className={`${primary} ${touch ? "min-h-[49px] w-full text-[15px]" : ""}`} disabled={add.isPending} onClick={() => add.mutate()}>
        Adicionar à fila
      </button>
    </div>
  );
}

/** −½ · the key by name · +½, as the floating bar's key control and with its names (lib/keys' keyName): "Dó♯ menor",
 *  yellow when it differs from the original. A song not prepared yet has no key known: "tom a detectar", then the
 *  shift ("+1"). */
export function KeyPicker({
  originalKey,
  semitones,
  onChange,
}: {
  originalKey: string | null | undefined;
  semitones: number;
  onChange: (n: number) => void;
}) {
  const touch = useContext(Touch);
  const key = parseKey(originalKey);
  const name = key ? keyName(key, semitones) : semitones ? signed(semitones) : "tom a detectar";
  const original = key ? `Original: ${keyName(key)}` : "O tom aparece quando a música estiver preparada";
  const step = `flex items-center justify-center text-[13px] text-[#e4e4e8] hover:bg-(--menu-btn-hover) disabled:opacity-40 ${
    touch ? "h-11 w-[52px] rounded-[20px]" : "h-7 w-[34px] rounded-[14px]"
  }`;
  return (
    <span className="inline-flex items-center rounded-[17px] bg-(--menu-btn) p-0.5">
      <button type="button" className={step} aria-label="Meio tom abaixo" disabled={semitones <= MIN_SEMITONES} onClick={() => onChange(semitones - 1)}>
        −½
      </button>
      <span
        className={`min-w-[92px] px-1.5 text-center text-[13px] font-medium whitespace-nowrap ${semitones ? "text-(--menu-accent)" : ""}`}
        title={original}
        aria-label={`Tom: ${name}. ${original}`}
        aria-live="polite"
      >
        {name}
      </span>
      <button type="button" className={step} aria-label="Meio tom acima" disabled={semitones >= MAX_SEMITONES} onClick={() => onChange(semitones + 1)}>
        +½
      </button>
    </span>
  );
}
