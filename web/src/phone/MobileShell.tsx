// The phone's screens with the TV menu's look (docs/ARCHITECTURE.md, "Telas do celular"): the same panels as the
// TV's side menu (tv/menu/), full screen, with the short notice over their bottom; and, for the host, a bar of icons
// at the bottom.
import type { ReactNode } from "react";
import { Icon, type IconName } from "../tv/menu/icons";
import { WithToast } from "../tv/menu/ui";

/** The whole screen: the panel, the short notice over its bottom, and the bar of icons, if any. */
export function MobileFrame({ children, nav }: { children: ReactNode; nav?: ReactNode }) {
  return (
    <div className="flex h-dvh justify-center bg-(--menu-panel) text-[13px] leading-[1.4] text-(--menu-text)">
      <WithToast>
        {(toast) => (
          <div className="flex h-full w-full max-w-xl flex-col">
            <div className="relative flex min-h-0 flex-1 flex-col">
              {children}
              {toast}
            </div>
            {nav}
          </div>
        )}
      </WithToast>
    </div>
  );
}

/** The bar of icons at the bottom. */
export function BottomNav({ children }: { children: ReactNode }) {
  return (
    <nav
      aria-label="Menu"
      className="flex shrink-0 gap-1 border-t border-(--menu-line) bg-(--menu-rail) px-2 pt-1.5 pb-[max(6px,env(safe-area-inset-bottom))]"
    >
      {children}
    </nav>
  );
}

export function NavItem({
  icon,
  label,
  badge,
  active,
  onClick,
}: {
  icon: IconName;
  label: string;
  badge?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`relative flex flex-1 flex-col items-center gap-0.5 rounded-[10px] py-1.5 text-[11px] ${
        active ? "bg-(--menu-accent) text-(--menu-on-accent)" : "text-(--menu-text-2)"
      }`}
    >
      <Icon name={icon} />
      <span>{label}</span>
      {!!badge && (
        <span
          aria-label={`${badge} na fila`}
          className={`absolute top-0.5 left-[calc(50%+6px)] min-w-4 rounded-[9px] px-1 text-center text-[11px] font-medium ${
            active ? "bg-(--menu-on-accent) text-(--menu-accent)" : "bg-(--menu-accent) text-(--menu-on-accent)"
          }`}
        >
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </button>
  );
}

/** A small action under the room's details ("Abrir como TV", "Ver salas"). */
export const smallAction =
  "rounded-[9px] bg-(--menu-btn) px-3 py-1.5 text-[12px] font-medium text-(--menu-text) hover:bg-(--menu-btn-hover) disabled:opacity-40";
