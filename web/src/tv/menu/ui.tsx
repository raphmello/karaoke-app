// The side menu's shared pieces (docs/ARCHITECTURE.md, "Menu lateral"): the panel's header with its X,
// the segmented tabs, round action buttons, cards, group labels and the short notice at the bottom of the video.
import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Icon, type IconName } from "./icons";

// Buttons and fields, in the menu's tokens (index.css)
export const button =
  "inline-flex items-center justify-center gap-[7px] rounded-[9px] bg-(--menu-btn) px-[14px] py-2 text-[13px] font-medium text-(--menu-text) hover:bg-(--menu-btn-hover) disabled:cursor-default disabled:bg-(--menu-btn) disabled:text-(--menu-text-off)";
export const primary =
  "inline-flex items-center justify-center gap-[7px] rounded-[10px] bg-(--menu-accent) px-[14px] py-[9px] text-[13px] font-medium text-(--menu-on-accent) hover:brightness-105 disabled:opacity-60";
export const input =
  "w-full min-w-0 rounded-[9px] border border-(--menu-input-line) bg-(--menu-input) px-3 py-2 text-[13px] text-(--menu-text) outline-none placeholder:text-(--menu-text-off) focus:border-(--menu-accent)";
export const select = `${input} cursor-pointer truncate`;
export const mono = "font-mono text-[12px] break-all text-[#d8d8de]";
export const sub = "text-[12px] text-(--menu-text-3)";

/** "279,8 GB": disk sizes, said in Portuguese. */
export const gb = (bytes: number) =>
  `${(bytes / 1024 ** 3).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`;

/** The panel's title (with what goes beside it), its own actions on the right and the X that closes the menu (on the
 * phone, with no menu to close, there is no X). */
export function PanelHeader({
  title,
  onClose,
  children,
  actions,
}: {
  title: string;
  onClose?: () => void;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 px-[14px] pt-[14px] text-[15px] font-medium">
      <h2 className="truncate">{title}</h2>
      {children}
      <span className="flex-1" />
      {actions}
      {onClose && <IconButton icon="x" label="Fechar o menu" onClick={onClose} />}
    </div>
  );
}

/** A square icon button of the header (28 px). */
export function IconButton({
  icon,
  label,
  onClick,
  className = "",
  pressed,
}: {
  icon: IconName;
  label: string;
  onClick: () => void;
  className?: string;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-(--menu-text-2) hover:bg-(--menu-btn) ${
        pressed ? "bg-(--menu-btn)" : ""
      } ${className}`}
    >
      <Icon name={icon} className="h-[18px] w-[18px]" />
    </button>
  );
}

/** A round action button (30 px, inside a bigger tap area): grey, or yellow for the main action. */
export function RoundButton({
  icon,
  label,
  onClick,
  accent,
  active,
  danger,
}: {
  icon: IconName;
  label: string;
  onClick: () => void;
  accent?: boolean;
  active?: boolean;
  danger?: boolean;
}) {
  const look = accent
    ? "bg-(--menu-accent) text-(--menu-on-accent) hover:brightness-110"
    : active
      ? "bg-(--menu-accent-soft) text-(--menu-accent)"
      : danger
        ? "bg-(--menu-btn) text-(--menu-err) hover:bg-(--menu-btn-hover)"
        : "bg-(--menu-btn) text-[#e4e4e8] hover:bg-(--menu-btn-hover)";
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={`flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full ${look}`}
    >
      <Icon name={icon} className="h-4 w-4" />
    </button>
  );
}

/** The segmented tabs under a panel's header. */
export function Tabs<T extends string>({
  tabs,
  current,
  onChange,
}: {
  tabs: [T, ReactNode][];
  current: T;
  onChange: (tab: T) => void;
}) {
  return (
    <div role="tablist" className="mx-[14px] mt-[10px] flex rounded-[10px] bg-(--menu-field) p-[3px]">
      {tabs.map(([id, label]) => (
        <button
          key={id}
          role="tab"
          aria-selected={current === id}
          onClick={() => onChange(id)}
          className={`group flex-1 rounded-lg py-[7px] text-center text-[13px] ${
            current === id ? "is-on bg-(--menu-accent) font-medium text-(--menu-on-accent)" : "text-(--menu-text-2)"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** A panel's scrolling body. */
export function Body({ children }: { children: ReactNode }) {
  return <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto px-[14px] pt-3 pb-4">{children}</div>;
}

/** A small label over a list ("Próximas · 3"), with an optional action on the right. */
export function Label({ children, action, first }: { children: ReactNode; action?: ReactNode; first?: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 text-[11px] text-(--menu-text-3) ${first ? "" : "mt-2"}`}>
      {children}
      {action && <span className="ml-auto">{action}</span>}
    </div>
  );
}

/** A group's label in Ajustes ("CONEXÃO"). */
export function GroupLabel({ children }: { children: ReactNode }) {
  return <div className="mt-2.5 text-[11px] tracking-[0.3px] text-(--menu-text-3) uppercase">{children}</div>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`flex flex-col gap-2 rounded-xl bg-(--menu-field) px-[14px] py-3 ${className}`}>{children}</div>;
}

/** A song's picture, or a plain square without one. */
export function Thumb({ src }: { src: string | null | undefined }) {
  return src ? (
    <img src={src} alt="" className="h-[38px] w-[38px] shrink-0 rounded-md object-cover" />
  ) : (
    <div className="h-[38px] w-[38px] shrink-0 rounded-md bg-(--menu-thumb)" />
  );
}

// --- the short notice ("“Evidências” entrou na fila"), at the bottom of the video, for ~2.4 s -----------------------

const ToastContext = createContext<(message: string) => void>(() => undefined);
export const useToast = () => useContext(ToastContext);
const TOAST_MS = 2400;

export function WithToast({ children }: { children: (toast: ReactNode) => ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const [shown, setShown] = useState(false);
  const timer = useRef(0);
  const show = useCallback((text: string) => {
    setMessage(text);
    setShown(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setShown(false), TOAST_MS);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const toast = (
    <div
      role="status"
      className={`pointer-events-none absolute bottom-[18px] left-1/2 z-50 -translate-x-1/2 rounded-[10px] bg-[#2f2f37] px-4 py-[9px] text-[13px] text-(--menu-text) shadow-[0_6px_24px_rgba(0,0,0,.5)] transition-all duration-250 ${
        shown ? "opacity-100" : "translate-y-2 opacity-0"
      }`}
    >
      {message}
    </div>
  );
  return <ToastContext.Provider value={show}>{children(toast)}</ToastContext.Provider>;
}
