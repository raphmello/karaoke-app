// A PIN screen: the admin's (host's) for /host and the QR's "Admin" choice; the TV's for /tv, which takes the
// admin's too. The screen says nothing about where the PIN is kept: whoever reaches it from the internet learns
// nothing from it.
import { type FormEvent, type ReactNode, useState } from "react";
import { api } from "../api";
import { EntryCard, entryInput, entryLink, entryPrimary } from "../phone/EntryCard";

export function HostLogin({
  title,
  onDone,
  onBack,
  footer,
  login = api.hostLogin,
  prompt = "Digite o PIN de administrador.",
  submit: submitLabel = "Entrar",
}: {
  title: string;
  onDone: () => void;
  onBack?: () => void;
  footer?: ReactNode; // under the form (the TV links to /host there)
  login?: (pin: string) => Promise<void>;
  prompt?: string;
  submit?: string; // the button's label
}) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(pin);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <EntryCard title={title} prompt={prompt} onSubmit={submit}>
      <input
        type="password"
        inputMode="numeric"
        autoFocus
        className={`${entryInput} tracking-[0.3em]`}
        value={pin}
        onChange={(event) => setPin(event.target.value)}
        aria-label={prompt}
      />
      {error && <p className="text-[13px] text-(--menu-err)">{error}</p>}
      <button className={entryPrimary} disabled={busy || !pin}>
        {submitLabel}
      </button>
      {onBack && (
        <button type="button" className={entryLink} onClick={onBack}>
          Voltar
        </button>
      )}
      {footer}
    </EntryCard>
  );
}
