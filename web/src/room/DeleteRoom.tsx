// "Excluir sala": the host deletes any room, a guest the one they created (docs/ARCHITECTURE.md, "Salas"). Shown only
// where the API says the caller manages the room. A second tap confirms; the room then leaves the list, its QR stops
// working and its screens are told.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { ConfirmButton } from "./ConfirmButton";

export function DeleteRoomButton({ code, onDeleted }: { code: string; onDeleted?: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const remove = async () => {
    setError(null);
    try {
      await api.removeRoom(code);
      await queryClient.invalidateQueries({ queryKey: ["rooms"] });
      onDeleted?.();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <span className="inline-flex flex-col gap-1">
      <ConfirmButton
        label="Excluir sala"
        confirmLabel="Excluir mesmo"
        onConfirm={() => void remove()}
        className="rounded-lg px-3 py-2 text-sm font-semibold text-red-300 ring-1 ring-red-800 hover:bg-red-950"
      />
      {error && <span className="text-sm text-red-400">{error}</span>}
    </span>
  );
}
