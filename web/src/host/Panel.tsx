// Painel → Disco's purge of the songs removed the old way (tv/menu/PainelPanel.tsx).
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { ConfirmButton } from "../room/ConfirmButton";
import { gb } from "../tv/menu/ui";

/** The songs removed before removing deleted for good (docs/ARCHITECTURE.md, "Remover do acervo apaga de vez"):
 *  their files stayed, and nothing else shows them any more. One button deletes them all. */
export function PurgeRemoved({ bytes }: { bytes: number }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const purge = async () => {
    setMessage(null);
    try {
      const done = await api.purgeRemoved();
      setMessage({ ok: true, text: `${done.songs} música(s) apagada(s); ${gb(done.freed_bytes)} liberados.` });
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message });
    }
    void queryClient.invalidateQueries({ queryKey: ["disk"] });
  };
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <p className="text-sm text-zinc-400">Músicas removidas antes da versão 2026.1.10 ainda ocupam o disco.</p>
      <ConfirmButton
        className="rounded-lg bg-zinc-800 px-3 py-1.5 text-sm font-semibold text-red-300 hover:bg-zinc-700"
        label="Apagar de vez"
        confirmLabel={`Apagar de vez e liberar ${gb(bytes)} (não dá para desfazer)`}
        onConfirm={() => void purge()}
      />
      {message && <p className={`text-sm ${message.ok ? "text-emerald-300" : "text-red-400"}`}>{message.text}</p>}
    </div>
  );
}
