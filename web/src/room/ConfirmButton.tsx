// A button that asks for a second tap before acting. window.confirm() is not used: embedded browsers (the ones
// apps open for a scanned QR code, the desktop app's pane) answer "cancel" without ever showing the dialog.
import { useEffect, useState } from "react";

export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  className,
}: {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  className: string;
}) {
  const [asking, setAsking] = useState(false);
  useEffect(() => {
    if (!asking) return;
    const timer = window.setTimeout(() => setAsking(false), 6000); // an untouched question goes away
    return () => window.clearTimeout(timer);
  }, [asking]);

  if (!asking) {
    return (
      <button type="button" className={className} onClick={() => setAsking(true)}>
        {label}
      </button>
    );
  }
  return (
    <span className="inline-flex flex-wrap gap-2">
      <button
        type="button"
        className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-500"
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        {confirmLabel}
      </button>
      <button
        type="button"
        className="rounded-lg bg-zinc-800 px-3 py-1.5 text-sm font-semibold hover:bg-zinc-700"
        onClick={() => setAsking(false)}
      >
        Cancelar
      </button>
    </span>
  );
}
